from __future__ import annotations

from typing import Optional


COMPANION_PREFIX = "companion:"
LEGACY_LINYU_COMPANION_PREFIX = "companion:linyu:"
COMPANION_SESSION_PREFIX = "companion_session:"
COMPANION_MEMORY_SESSION_PREFIX = "companion_memory:"
LEGACY_LINYU_SESSION_PREFIX = "linyu_private:"


def companion_user_id(companion_id: int | str) -> str:
    return f"{COMPANION_PREFIX}{int(companion_id)}"


def parse_companion_user_id(user_id: str) -> Optional[int]:
    raw = str(user_id or "").strip()
    if raw.startswith(LEGACY_LINYU_COMPANION_PREFIX):
        value = raw[len(LEGACY_LINYU_COMPANION_PREFIX):]
    elif raw.startswith(COMPANION_PREFIX):
        value = raw[len(COMPANION_PREFIX):]
    else:
        return None
    try:
        return int(value)
    except Exception:
        return None


def is_companion_user_id(user_id: str) -> bool:
    return parse_companion_user_id(user_id) is not None


def companion_session_id(companion_id: int | str, platform: str, remote_user_id: str) -> str:
    return f"{COMPANION_SESSION_PREFIX}{int(companion_id)}:{str(platform or '').strip()}:{str(remote_user_id or '').strip()}"


def companion_memory_session_id(companion_id: int | str) -> str:
    return f"{COMPANION_MEMORY_SESSION_PREFIX}{int(companion_id)}"


def parse_companion_session_id(session_id: str) -> Optional[dict[str, str]]:
    raw = str(session_id or "").strip()
    if raw.startswith(COMPANION_SESSION_PREFIX):
        parts = raw.split(":", 3)
        if len(parts) != 4:
            return None
        _, companion_id, platform, remote_user_id = parts
        try:
            int(companion_id)
        except Exception:
            return None
        return {
            "companion_id": companion_id,
            "platform": platform,
            "remote_user_id": remote_user_id,
        }

    if raw.startswith(LEGACY_LINYU_SESSION_PREFIX):
        parts = raw.split(":")
        if len(parts) >= 3:
            return {
                "companion_id": parts[1],
                "platform": "linyu",
                "remote_user_id": ":".join(parts[2:]),
            }
    return None


def parse_companion_memory_session_id(session_id: str) -> Optional[int]:
    raw = str(session_id or "").strip()
    if not raw.startswith(COMPANION_MEMORY_SESSION_PREFIX):
        return None
    value = raw[len(COMPANION_MEMORY_SESSION_PREFIX):]
    try:
        return int(value)
    except Exception:
        return None


def is_companion_memory_session_id(session_id: str) -> bool:
    return parse_companion_memory_session_id(session_id) is not None


def normalize_companion_memory_scope(user_id: str, session_id: Optional[str] = None) -> tuple[str, str]:
    companion_id = parse_companion_user_id(user_id)
    if companion_id is None:
        parsed_session = parse_companion_memory_session_id(str(session_id or ""))
        if parsed_session is not None:
            return companion_user_id(parsed_session), companion_memory_session_id(parsed_session)
        return str(user_id or "").strip(), str(session_id or user_id or "").strip()

    return companion_user_id(companion_id), companion_memory_session_id(companion_id)
