"""Hermes Agent HTTP 客户端 — Chat Completions API"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import aiohttp
from backend.prompt_assembly import PromptAssembler, PromptBlueprint

from .config import HermesConfig


class RunStatus(Enum):
    """任务状态"""

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


@dataclass
class RunResult:
    """一次任务的结果"""

    run_id: str
    status: RunStatus
    output: Optional[str] = None
    error: Optional[str] = None


class HermesClient:
    """Hermes Agent Chat Completions 客户端

    使用 /v1/chat/completions 接口（OpenAI 兼容），
    一次请求等待 Hermes 执行完毕后返回结果，无需轮询。
    """

    def __init__(self, config: HermesConfig):
        self._config = config
        self._base_url = config.api_base.rstrip("/")
        self._prompt_assembler = PromptAssembler()

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

    async def execute_task(self, task: str, instructions: Optional[str] = None) -> RunResult:
        """执行一个任务并等待结果。

        使用 Chat Completions API，Hermes 会执行任务（调用工具等），
        完成后返回最终结果。

        Args:
            task: 任务描述
            instructions: 可选的 system instructions

        Returns:
            RunResult 包含状态和输出
        """
        blocks = []
        if instructions:
            blocks.append(
                self._prompt_assembler.make_identity_block(
                    block_id="delegate_role",
                    title="执行角色",
                    content=instructions,
                    stability="static",
                )
            )
        blocks.append(
            self._prompt_assembler.make_behavior_block(
                block_id="delegate_rules",
                title="执行原则",
                rules=[
                    "准确执行用户委派的任务。",
                    "优先给出清晰、完整、可直接使用的结果。",
                ],
                stability="static",
            )
        )
        blocks.append(
            self._prompt_assembler.make_input_block(
                block_id="delegate_input",
                title="任务描述",
                content=task,
                stability="turn",
            )
        )
        rendered = self._prompt_assembler.render_messages(
            PromptBlueprint(name="agent_delegate_v2"),
            blocks,
        )

        payload = {
            "model": "hermes-agent",
            "messages": rendered.messages,
            "stream": False,
        }

        try:
            # 使用配置的 timeout（默认 300 秒），Hermes 执行任务可能需要较长时间
            timeout = aiohttp.ClientTimeout(total=self._config.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                print(f"[HermesClient] 发送任务到 {self._base_url}/v1/chat/completions ...")
                async with session.post(
                    f"{self._base_url}/v1/chat/completions",
                    headers=self._headers(),
                    json=payload,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # 提取 assistant 回复内容
                        choices = data.get("choices", [])
                        if choices:
                            content = choices[0].get("message", {}).get("content", "")
                            return RunResult(
                                run_id=data.get("id", "unknown"),
                                status=RunStatus.COMPLETED,
                                output=content,
                            )
                        else:
                            return RunResult(
                                run_id=data.get("id", "unknown"),
                                status=RunStatus.FAILED,
                                error="Hermes 返回了空结果",
                            )
                    else:
                        error_text = await resp.text()
                        print(f"[HermesClient] 请求失败: {resp.status} - {error_text[:300]}")
                        return RunResult(
                            run_id="unknown",
                            status=RunStatus.FAILED,
                            error=f"请求失败 ({resp.status}): {error_text[:200]}",
                        )
        except aiohttp.ServerTimeoutError:
            return RunResult(
                run_id="unknown",
                status=RunStatus.FAILED,
                error=f"任务超时（{self._config.timeout}秒），Hermes 未在规定时间内完成",
            )
        except aiohttp.ClientError as e:
            return RunResult(
                run_id="unknown",
                status=RunStatus.FAILED,
                error=f"网络错误: {e}",
            )
        except Exception as e:
            print(f"[HermesClient] 执行任务异常: {e}")
            return RunResult(
                run_id="unknown",
                status=RunStatus.FAILED,
                error=f"执行异常: {e}",
            )
