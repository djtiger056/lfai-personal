"""[DELEGATE: ...] 标签解析器"""

from __future__ import annotations

import re
from typing import Optional, Tuple

# 匹配 [DELEGATE: 任务描述] 标签，支持多行内容
_DELEGATE_PATTERN = re.compile(
    r"\[DELEGATE:\s*(.+?)\]",
    re.DOTALL,
)


def extract_delegate_tag(text: str) -> Tuple[str, Optional[str]]:
    """从 LLM 回复中提取委派标签。

    Args:
        text: LLM 的原始回复文本

    Returns:
        (cleaned_text, task_description)
        - cleaned_text: 去掉标签后的文本（用于直接发送给用户）
        - task_description: 提取到的任务描述，如果没有标签则为 None
    """
    match = _DELEGATE_PATTERN.search(text)
    if not match:
        return text, None

    task_description = match.group(1).strip()
    if not task_description:
        return text, None

    # 去掉标签，清理多余空白
    cleaned = _DELEGATE_PATTERN.sub("", text).strip()

    return cleaned, task_description
