"""Agent 委派调度器 — 管理任务的提交和结果推送"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

from .client import HermesClient, RunResult, RunStatus
from .config import AgentDelegateConfig


@dataclass
class TaskRecord:
    """一个委派任务的记录"""

    task_id: str
    task_description: str
    user_id: str
    session_id: str
    channel: str
    submitted_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    result: Optional[RunResult] = None


# 推送回调类型：(target_dict, message_text) -> None
PushCallback = Callable[[Dict[str, Any], Union[str, Dict[str, Any]]], Awaitable[None]]

# 任务去重：相似度阈值（描述前N个字符相同视为重复）
_DEDUP_PREFIX_LEN = 60
# 去重时间窗口（秒）：同一用户在此时间内提交相似任务视为重复
_DEDUP_WINDOW_SECONDS = 300


class AgentDelegator:
    """管理任务委派的生命周期。

    职责：
    1. 接收来自 Bot 的委派请求
    2. 去重检测，避免重复提交
    3. 异步调用 Hermes Agent Chat Completions API
    4. 完成后通过回调推送结果给用户
    """

    def __init__(self, config: AgentDelegateConfig):
        self._config = config
        self._client = HermesClient(config.hermes)
        self._active_tasks: Dict[str, TaskRecord] = {}  # task_id -> TaskRecord
        self._push_callback: Optional[PushCallback] = None
        self._lock = asyncio.Lock()
        self._task_counter = 0

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def set_push_callback(self, callback: PushCallback) -> None:
        """设置结果推送回调。"""
        self._push_callback = callback

    async def start(self) -> None:
        """启动委派器（检查连接）"""
        if not self._config.enabled:
            print("[AgentDelegate] 未启用，跳过启动")
            return

        online = await self._client.health_check()
        if online:
            print("[AgentDelegate] Hermes Agent 连接正常")
        else:
            print("[AgentDelegate] 警告: Hermes Agent 不可达，任务提交可能失败")

    async def stop(self) -> None:
        """停止委派器"""
        print("[AgentDelegate] 已停止")

    def _generate_task_id(self) -> str:
        self._task_counter += 1
        return f"task_{int(time.time())}_{self._task_counter}"

    def _find_duplicate_task(self, task_description: str, user_id: str) -> Optional[TaskRecord]:
        """检查是否有相同用户的相似任务正在执行。"""
        now = time.time()
        task_prefix = task_description[:_DEDUP_PREFIX_LEN].strip().lower()

        for record in self._active_tasks.values():
            if record.user_id != user_id:
                continue
            if now - record.submitted_at > _DEDUP_WINDOW_SECONDS:
                continue
            existing_prefix = record.task_description[:_DEDUP_PREFIX_LEN].strip().lower()
            if task_prefix == existing_prefix:
                return record
        return None

    async def submit(
        self,
        task_description: str,
        user_id: str,
        session_id: str,
        channel: str = "qq_private",
    ) -> bool:
        """提交一个委派任务。

        任务会在后台异步执行，完成后通过 push_callback 推送结果。

        Returns:
            是否成功提交
        """
        if not self._config.enabled:
            print("[AgentDelegate] 未启用，忽略提交")
            return False

        async with self._lock:
            # 去重检测
            duplicate = self._find_duplicate_task(task_description, user_id)
            if duplicate:
                elapsed = time.time() - duplicate.submitted_at
                print(
                    f"[AgentDelegate] 去重拦截: 用户 {user_id} 的相似任务正在执行 "
                    f"(task_id={duplicate.task_id}, 已等待 {elapsed:.0f}s)"
                )
                if self._push_callback:
                    target = self._build_target(channel, user_id, session_id)
                    await self._push_callback(
                        target,
                        f"这个任务还在处理中哦，已经跑了 {elapsed:.0f} 秒，再等等～"
                    )
                return False

            # 并发控制
            if len(self._active_tasks) >= self._config.hermes.max_concurrent_tasks:
                print(f"[AgentDelegate] 达到并发上限 ({self._config.hermes.max_concurrent_tasks})")
                if self._push_callback:
                    target = self._build_target(channel, user_id, session_id)
                    await self._push_callback(
                        target,
                        "抱歉，现在任务太多了，等前面的做完再帮你处理哦～"
                    )
                return False

            # 创建任务记录
            task_id = self._generate_task_id()
            record = TaskRecord(
                task_id=task_id,
                task_description=task_description,
                user_id=user_id,
                session_id=session_id,
                channel=channel,
            )
            self._active_tasks[task_id] = record

        print(f"[AgentDelegate] 任务已提交: task_id={task_id}, task={task_description[:80]}...")

        # 在后台异步执行任务
        asyncio.create_task(self._execute_and_push(record))
        return True

    async def _execute_and_push(self, record: TaskRecord) -> None:
        """异步执行任务并推送结果。"""
        try:
            result = await self._client.execute_task(
                task=record.task_description,
                instructions=self._config.hermes.instructions,
            )
            record.result = result
            record.completed_at = time.time()

            if result.status == RunStatus.COMPLETED:
                await self._on_complete(record)
            else:
                await self._on_failed(record)

        except Exception as e:
            print(f"[AgentDelegate] 任务执行异常: task_id={record.task_id}, error={e}")
            record.completed_at = time.time()
            record.result = RunResult(
                run_id="unknown",
                status=RunStatus.FAILED,
                error=f"执行异常: {e}",
            )
            await self._on_failed(record)
        finally:
            # 从活跃任务中移除
            async with self._lock:
                self._active_tasks.pop(record.task_id, None)

    async def _on_complete(self, record: TaskRecord) -> None:
        """任务完成回调 — 推送结果给用户"""
        if not self._push_callback:
            print(f"[AgentDelegate] 任务完成但无推送回调: {record.task_id}")
            return

        output = record.result.output if record.result else "（无输出）"
        elapsed = (record.completed_at or time.time()) - record.submitted_at

        print(f"[AgentDelegate] ✅ 任务完成: task_id={record.task_id}, 耗时={elapsed:.0f}s")

        target = self._build_target(record.channel, record.user_id, record.session_id)
        await self._push_callback(target, output)

    async def _on_failed(self, record: TaskRecord) -> None:
        """任务失败回调 — 推送错误信息给用户"""
        if not self._push_callback:
            print(f"[AgentDelegate] 任务失败但无推送回调: {record.task_id}")
            return

        error = "未知错误"
        if record.result:
            error = record.result.error or record.result.output or "未知错误"

        elapsed = (record.completed_at or time.time()) - record.submitted_at
        print(f"[AgentDelegate] ❌ 任务失败: task_id={record.task_id}, 耗时={elapsed:.0f}s, error={error[:100]}")

        target = self._build_target(record.channel, record.user_id, record.session_id)
        message = f"任务没跑成功：{error}"
        await self._push_callback(target, message)

    def _build_target(self, channel: str, user_id: str, session_id: str) -> Dict[str, Any]:
        """构建推送目标字典"""
        return {
            "channel": channel,
            "user_id": user_id,
            "session_id": session_id,
        }

    def active_task_count(self) -> int:
        """当前活跃任务数"""
        return len(self._active_tasks)

    def active_tasks_snapshot(self) -> List[Dict[str, Any]]:
        """获取当前活跃任务的快照（用于 API 查询）"""
        result = []
        for task_id, record in self._active_tasks.items():
            result.append({
                "task_id": task_id,
                "task": record.task_description,
                "user_id": record.user_id,
                "channel": record.channel,
                "submitted_at": record.submitted_at,
                "elapsed": time.time() - record.submitted_at,
            })
        return result
