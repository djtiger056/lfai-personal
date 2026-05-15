"""TTS 标签解析器

解析 AI 回复中的 [TTS]...[/TTS] 标签，提取需要语音播报的文本。
当 AI 主动决定用语音表达时，会在回复中使用该标签。

模式参考：gen_img_parser.py 的 [GEN_IMG: ...] 标签解析。
"""

from __future__ import annotations

import re
from typing import Optional, Tuple


# 匹配 [TTS]...[/TTS] 标签（支持跨行）
_TTS_TAG_RE = re.compile(r"\[TTS\](.*?)\[/TTS\]", re.IGNORECASE | re.DOTALL)


def extract_tts_tag(text: str) -> Tuple[str, Optional[str]]:
    """从文本中提取 [TTS]...[/TTS] 语音标签。

    如果存在多个标签，合并所有标签内的文本作为 TTS 内容。

    Args:
        text: AI 的原始回复文本

    Returns:
        (cleaned_text, tts_text):
            - cleaned_text: 移除 TTS 标签后的展示文本
            - tts_text: 需要语音播报的文本，如果没有标签则为 None
    """
    if not text:
        return "", None

    matches = list(_TTS_TAG_RE.finditer(text))
    if not matches:
        return text, None

    # 提取所有标签内的文本，合并为 TTS 内容
    tts_parts = []
    for match in matches:
        content = (match.group(1) or "").strip()
        if content:
            tts_parts.append(content)

    if not tts_parts:
        return text, None

    tts_text = "".join(tts_parts)

    # 生成展示文本：移除标签但保留标签内的文字（用户仍能看到文字内容）
    cleaned = _TTS_TAG_RE.sub(lambda m: (m.group(1) or "").strip(), text)
    # 清理多余空白
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()

    return cleaned, tts_text
