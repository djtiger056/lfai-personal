from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, Tuple


_IM_ACTIONS_PATTERN = re.compile(r"\[IM_ACTIONS\](.+?)\[/IM_ACTIONS\]", re.DOTALL)


def extract_im_actions_block(text: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """提取最后一个合法 IM_ACTIONS 块，并从可见文本中移除。"""
    matches = list(_IM_ACTIONS_PATTERN.finditer(str(text or "")))
    if not matches:
        return text, None

    for match in reversed(matches):
        raw = (match.group(1) or "").strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        cleaned = (text[: match.start()] + text[match.end() :]).strip()
        return cleaned, payload

    return text, None
