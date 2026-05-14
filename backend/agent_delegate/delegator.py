"""Agent 委派调度器 — 管理任务的提交、轮询和结果推送"""

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

    run_id: str
    task_description: str
    user_id: str
    session_id: str
    channel: str
    submitted_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    result: Optional[RunResult] = None


# 推送回调类型：(target_dict, message_text) -> None
PushCallback = Callable[[Dict[str, Any], Union[str, Dict[str, Any]]], Awaitable[None]]


class AgentDelegator:
    """管理任务委派的生命周期。

    职责：
    1. 接收来自 Bot 的委派请求
    2. 提交到 Hermes Agent
    3. 后台轮询任务状态
    4. 完成后通过回调推送结果给用户
    """

    def __init__(self, config: AgentDelegateConfig):
        self._config = config
        self._client = HermesClient(config.hermes)
        self._active_tasks: Dict[str, TaskRecord] = {}  # run_id -> TaskRecord
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
        self._push_callback: Optional[PushCallback] = None
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def set_push_callback(self, callback: PushCallback) -> None:
        """设置结果推送回调。

        回调签名: async def callback(target: dict, payload: str) -> None
        target 包含 channel, user_id, session_id 等信息。
        """
        self._push_callback = callback

    async def start(self) -> None:
        """启动后台 worker"""
        if not self._config.enabled:
            print("[AgentDelegate] 未启用，跳过启动")
            return

        # 检查 Hermes 是否在线
        online = await self._client.health_check()
        if online:
            print("[AgentDelegate] Hermes Agent 连接正常")
        else:
            print("[AgentDelegate] 警告: Hermes Agent 不可达，任务提交可能失败")

        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        print("[AgentDelegate] 后台 worker 已启动")

    async def stop(self) -> None:
        """停止后台 worker"""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        print("[AgentDelegate] 已停止")

    async def submit(
        self,
        task_description: str,
        user_id: str,
        session_id: str,
        channel: str = "qq_private",
    ) -> bool:
        """提交一个委派任务。

        Args:
            task_description: 任务描述（从 [DELEGATE: ...] 标签中提取）
            user_id: 用户 ID
            session_id: 会话 ID
            channel: 推送通道

        Returns:
            是否成功提交
        """
        if not self._config.enabled:
            print("[AgentDelegate] 未启用，忽略提交")
            return False

        # 并发控制
        async with self._lock:
            if len(self._active_tasks) >= self._config.hermes.max_concurrent_tasks:
                print(f"[AgentDelegate] 达到并发上限 ({self._config.hermes.max_concurrent_tasks})，排队等待")
                # 简单策略：拒绝并通知用户
                if self._push_callback:
                    target = self._build_target(channel, user_id, session_id)
                    await self._push_callback(
                        target,
                        "抱歉，现在任务太多了，等前面的做完再帮你处理哦～"
                    )
                return False

        # 提交到 Hermes
        run_id = await self._client.submit_run(
            task=task_description,
            instructions=self._config.hermes.instructions,
        )

        if not run_id:
            # 提交失败，通知用户
            if self._push_callback:
                target = self._build_target(channel, user_id, session_id)
                await self._push_callback(
                    target,
                    "抱歉，助手暂时不在线，等会儿再试试吧～"
                )
            return False

        # 记录任务
        record = TaskRecord(
            run_id=run_id,
            task_description=task_description,
            user_id=user_id,
            session_id=session_id,
            channel=channel,
        )

        async with self._lock:
            self._active_tasks[run_id] = record

        print(f"[AgentDelegate] 任务已提交: run_id={run_id}, task={task_description[:50]}...")
        return True

    async def _worker(self) -> None:
        """后台 worker：定期轮询所有进行中的任务"""
        poll_interval = self._config.hermes.poll_interval

        while self._running:
            try:
                await self._tick()
            except Exception as e:
                print(f"[AgentDelegate] worker 异常: {e}")

            await asyncio.sleep(poll_interval)

    async def _tick(self) -> None:
        """一次轮询周期"""
        async with self._lock:
            if not self._active_tasks:
                return
            # 复制一份避免迭代时修改
            tasks_snapshot = dict(self._active_tasks)

        for run_id, record in tasks_snapshot.items():
            result = await self._client.poll_run(run_id)

            if result.status == RunStatus.COMPLETED:
                record.result = result
                record.completed_at = time.time()
                await self._on_complete(record)
                async with self._lock:
                    self._active_tasks.pop(run_id, None)

            elif result.status in (RunStatus.FAILED, RunStatus.CANCELLED):
                record.result = result
                record.completed_at = time.time()
                await self._on_failed(record)
                async with self._lock:
                    self._active_tasks.pop(run_id, None)

            # STARTED / RUNNING / UNKNOWN → 继续等待

    async def _on_complete(self, record: TaskRecord) -> None:
        """任务完成回调 — 推送结果给用户"""
        if not self._push_callback:
            print(f"[AgentDelegate] 任务完成但无推送回调: {record.run_id}")
            return

        output = record.result.output if record.result else "（无输出）"
        elapsed = (record.completed_at or time.time()) - record.submitted_at
        elapsed_str = f"{elapsed:.1f}秒"

        print(f"[AgentDelegate] 任务完成: run_id={record.run_id}, 耗时={elapsed_str}")

        target = self._build_target(record.channel, record.user_id, record.session_id)
        await self._push_callback(target, output)

    async def _on_failed(self, record: TaskRecord) -> None:
        """任务失败回调 — 推送错误信息给用户"""
        if not self._push_callback:
            print(f"[AgentDelegate] 任务失败但无推送回调: {record.run_id}")
            return

        error = "未知错误"
        if record.result:
            error = record.result.error or record.result.output or "未知错误"

        print(f"[AgentDelegate] 任务失败: run_id={record.run_id}, error={error[:100]}")

        target = self._build_target(record.channel, record.user_id, record.session_id)
        message = f"任务执行失败了：{error}"
        await self._push_callback(target, message)

    def _build_target(self, channel: str, user_id: str, session_id: str) -> Dict[str, Any]:
        """构建推送目标字典（兼容 ProactiveChatScheduler 的 sender 格式）"""
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
        for run_id, record in self._active_tasks.items():
            result.append({
                "run_id": run_id,
                "task": record.task_description,
                "user_id": record.user_id,
                "channel": record.channel,
                "submitted_at": record.submitted_at,
                "elapsed": time.time() - record.submitted_at,
            })
        return result
