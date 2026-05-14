"""Hermes Agent HTTP 客户端 — 封装 Runs API"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import aiohttp

from .config import HermesConfig


class RunStatus(Enum):
    """Hermes Run 状态"""

    STARTED = "started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


@dataclass
class RunResult:
    """一次 Run 的结果"""

    run_id: str
    status: RunStatus
    output: Optional[str] = None
    error: Optional[str] = None


class HermesClient:
    """Hermes Agent Runs API 客户端"""

    def __init__(self, config: HermesConfig):
        self._config = config
        self._base_url = config.api_base.rstrip("/")

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        return headers

    async def health_check(self) -> bool:
        """检查 Hermes 是否在线"""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{self._base_url}/health",
                    headers=self._headers(),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("status") == "ok"
                    return False
        except Exception:
            return False

    async def submit_run(self, task: str, instructions: Optional[str] = None) -> Optional[str]:
        """提交一个任务到 Hermes，返回 run_id。

        Args:
            task: 任务描述
            instructions: 可选的 system instructions

        Returns:
            run_id 字符串，失败返回 None
        """
        payload = {
            "input": task,
        }
        if instructions:
            payload["instructions"] = instructions

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self._base_url}/v1/runs",
                    headers=self._headers(),
                    json=payload,
                ) as resp:
                    if resp.status in (200, 201):
                        data = await resp.json()
                        return data.get("run_id")
                    else:
                        error_text = await resp.text()
                        print(f"[AgentDelegate] 提交任务失败: {resp.status} - {error_text}")
                        return None
        except Exception as e:
            print(f"[AgentDelegate] 提交任务异常: {e}")
            return None

    async def poll_run(self, run_id: str) -> RunResult:
        """查询 run 的当前状态。

        Args:
            run_id: 任务 ID

        Returns:
            RunResult 包含状态和输出
        """
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{self._base_url}/v1/runs/{run_id}",
                    headers=self._headers(),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        status_str = data.get("status", "unknown")
                        try:
                            status = RunStatus(status_str)
                        except ValueError:
                            status = RunStatus.UNKNOWN

                        output = data.get("output")
                        error = data.get("error")

                        return RunResult(
                            run_id=run_id,
                            status=status,
                            output=output,
                            error=error,
                        )
                    else:
                        error_text = await resp.text()
                        return RunResult(
                            run_id=run_id,
                            status=RunStatus.UNKNOWN,
                            error=f"查询失败: {resp.status} - {error_text}",
                        )
        except Exception as e:
            return RunResult(
                run_id=run_id,
                status=RunStatus.UNKNOWN,
                error=f"查询异常: {e}",
            )

    async def stop_run(self, run_id: str) -> bool:
        """取消一个正在执行的任务。

        Args:
            run_id: 任务 ID

        Returns:
            是否成功发送停止请求
        """
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{self._base_url}/v1/runs/{run_id}/stop",
                    headers=self._headers(),
                ) as resp:
                    return resp.status in (200, 202)
        except Exception as e:
            print(f"[AgentDelegate] 停止任务异常: {e}")
            return False

    async def wait_for_completion(self, run_id: str) -> RunResult:
        """轮询等待任务完成。

        会按照配置的 poll_interval 间隔轮询，直到任务完成或超时。

        Args:
            run_id: 任务 ID

        Returns:
            最终的 RunResult
        """
        elapsed = 0.0
        poll_interval = self._config.poll_interval
        timeout = self._config.timeout

        while elapsed < timeout:
            result = await self.poll_run(run_id)

            if result.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED):
                return result

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        # 超时，尝试停止任务
        await self.stop_run(run_id)
        return RunResult(
            run_id=run_id,
            status=RunStatus.FAILED,
            error=f"任务超时（{timeout}秒），已自动取消",
        )
