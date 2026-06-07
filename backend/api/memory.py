"""
记忆系统API端点
"""

import json
import re
import sqlite3
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Query, Body, Depends
from pydantic import BaseModel

from ..config import config
from ..memory import MemoryManager, MemoryConfig, MemoryItem, MemorySummary
from .deps import get_access_token
from backend.accounts import account_registry
from backend.personal_storage import DATA_DIR
from backend.personal_auth import decode_personal_token, is_ui_auth_enabled
from backend.utils.companion_identity import (
    companion_memory_session_id,
    companion_session_id,
    companion_user_id,
    parse_companion_memory_session_id,
    parse_companion_session_id,
    parse_companion_user_id,
)

router = APIRouter(prefix="/api", tags=["memory"])

# 共享MemoryManager实例
_memory_manager = None
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)


def _get_project_username(user: Any, fallback: str = "当前用户") -> str:
    return str(getattr(user, "username", None) or getattr(user, "nickname", None) or fallback).strip()


def _sanitize_linyu_account(user: Any) -> str:
    account = str(getattr(user, "linyu_account", None) or "").strip()
    if account and account != "-" and not _UUID_RE.fullmatch(account) and not account.endswith("..."):
        return account
    return "已绑定账号"


def _build_memory_identity_display(user: Any, channel: str) -> str:
    username = _get_project_username(user)
    if channel == "qq":
        qq_id = str(getattr(user, "qq_user_id", None) or "").strip()
        return f"{username} | QQ:{qq_id}"
    if channel == "linyu":
        return f"{username} | Linyu:{_sanitize_linyu_account(user)}"
    raise ValueError(f"不支持的记忆渠道: {channel}")


async def _get_authenticated_user(token: str) -> Any:
    if not is_ui_auth_enabled():
        return {"personal": True}
    if not token:
        raise HTTPException(status_code=401, detail="缺少令牌")
    if not decode_personal_token(token):
        raise HTTPException(status_code=401, detail="无效的令牌")
    return {"personal": True}


def _get_accessible_memory_entries(user: Any) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = [
        {
            "user_id": "web_user",
            "display_name": "Web 控制台",
            "selector_key": "Web 控制台",
            "channel": "web",
            "default_session_id": "web_user",
            "memory_user_id": "web_user",
            "memory_session_id": "web_user",
            "remote_user_id": "",
            "project_user_id": "web_user",
        }
    ]

    linyu_display_by_remote_id: Dict[str, str] = {}
    for account in account_registry.list_accounts(enabled=True):
        platform = str(account.get("platform") or "")
        remote_user_id = str(account.get("remote_user_id") or "")
        display = _account_display_name(account)
        if not remote_user_id:
            continue
        if platform == "linyu":
            linyu_display_by_remote_id[remote_user_id] = display
            continue
        if platform != "qq":
            continue
        entries.append({
            "user_id": remote_user_id,
            "display_name": f"QQ:{display}",
            "selector_key": f"qq:{remote_user_id}",
            "channel": "qq",
            "default_session_id": remote_user_id,
            "memory_user_id": remote_user_id,
            "memory_session_id": remote_user_id,
            "remote_user_id": remote_user_id,
            "project_user_id": remote_user_id,
        })

    companion_display_by_id: Dict[str, Dict[str, str]] = {}
    for companion in account_registry.list_companions(enabled=True):
        companion_key = str(companion.get("id") or "").strip()
        if not companion_key:
            continue
        companion_id = str(companion.get("companion_id") or companion_user_id(companion_key))
        companion_name = str(companion.get("companion_name") or "").strip()
        platform_accounts = companion.get("platform_accounts") or []
        linyu_account_name = next((item.get("account_name") for item in platform_accounts if item.get("platform") == "linyu"), "") or ""
        qq_account_name = next((item.get("account_name") for item in platform_accounts if item.get("platform") == "qq"), "") or ""
        companion_display_by_id[companion_key] = {
            "companion_id": companion_id,
            "companion_name": companion_name or linyu_account_name or qq_account_name or f"伴侣{companion_key}",
            "ai_account_name": linyu_account_name,
            "qq_account_name": qq_account_name,
        }
        bound_accounts = companion.get("bound_accounts") or []
        user_labels: List[str] = []
        source_sessions: List[str] = []
        channel = "linyu" if linyu_account_name else "qq" if qq_account_name else "memory"
        for bound_account in bound_accounts:
            remote_user_id = str(bound_account.get("remote_user_id") or "").strip()
            if not remote_user_id:
                continue
            user_account_name = _account_display_name(bound_account)
            platform = str(bound_account.get("platform") or "").strip()
            if platform == "linyu":
                linyu_display_by_remote_id.setdefault(remote_user_id, user_account_name)
            if user_account_name and user_account_name not in user_labels:
                user_labels.append(user_account_name)
            source_sessions.append(companion_session_id(companion_key, platform, remote_user_id))

        if not source_sessions:
            continue

        platform_parts: List[str] = []
        if linyu_account_name:
            platform_parts.append(f"Linyu:{linyu_account_name}")
        if qq_account_name:
            platform_parts.append(f"QQ:{qq_account_name}")
        users_text = "、".join(user_labels[:3]) if user_labels else "未绑定用户"
        if len(user_labels) > 3:
            users_text += f" 等{len(user_labels)}人"
        label = f"{companion_display_by_id[companion_key]['companion_name']} | {' / '.join(platform_parts) or '无平台账号'} | 绑定:{users_text}"
        memory_session_id = companion_memory_session_id(companion_key)
        entries.append({
            "user_id": companion_id,
            "display_name": label,
            "selector_key": f"companion:{companion_key}",
            "channel": channel,
            "default_session_id": memory_session_id,
            "memory_user_id": companion_id,
            "memory_session_id": memory_session_id,
            "remote_user_id": "",
            "project_user_id": companion_id,
            "companion_id": companion_id,
            "companion_name": companion_display_by_id[companion_key]["companion_name"],
            "ai_account_id": companion_key,
            "ai_account_name": linyu_account_name,
            "user_account_name": users_text,
            "source_session_ids": source_sessions,
        })

    stored_entries = _get_stored_memory_entries(linyu_display_by_remote_id, companion_display_by_id)
    entries.extend(stored_entries)
    entries = _dedupe_memory_entries(entries)
    return entries


def _account_display_name(account: Dict[str, Any]) -> str:
    return str(
        account.get("display_name")
        or account.get("account_name")
        or account.get("remote_user_id")
        or ""
    ).strip()


def _get_stored_memory_entries(
    linyu_display_by_remote_id: Dict[str, str],
    companion_display_by_id: Dict[str, Dict[str, str]],
) -> List[Dict[str, str]]:
    """Expose existing memory DB identities after the personal-edition refactor.

    Historical Linyu memories may be stored in older shapes and the new
    companion-isolated shape:
    - user_id=<old web user numeric id>, session_id=linyu_private:<linyu uuid>
    - user_id=<linyu uuid>, session_id=<linyu uuid>
    - user_id=companion:linyu:<id>, session_id=linyu_private:<id>:<linyu uuid>

    The UI should display a friendly Linyu account when possible while querying
    the real persisted memory keys.
    """

    db_path = DATA_DIR / "lfbot.db"
    if not db_path.exists():
        return []

    rows: list[sqlite3.Row] = []
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT user_id, session_id, MAX(latest) AS latest, SUM(total) AS total
                FROM (
                    SELECT user_id, session_id, MAX(created_at) AS latest, COUNT(*) AS total
                    FROM memory_items
                    GROUP BY user_id, session_id
                    UNION ALL
                    SELECT user_id, session_id, MAX(created_at) AS latest, COUNT(*) AS total
                    FROM memory_summaries
                    GROUP BY user_id, session_id
                )
                GROUP BY user_id, session_id
                ORDER BY latest DESC
                """
            ).fetchall()
    except Exception:
        return []

    entries: List[Dict[str, str]] = []
    for row in rows:
        memory_user_id = str(row["user_id"] or "").strip()
        memory_session_id = str(row["session_id"] or "").strip()
        if not memory_user_id or not memory_session_id:
            continue
        if memory_user_id == "web_user" and memory_session_id == "web_user":
            continue

        channel = "web"
        remote_user_id = memory_session_id
        display_name = memory_user_id

        parsed_companion_session = parse_companion_session_id(memory_session_id)
        if parsed_companion_session:
            channel = "linyu" if parsed_companion_session["platform"] == "linyu" else parsed_companion_session["platform"]
            companion_key = parsed_companion_session["companion_id"]
            remote_user_id = parsed_companion_session["remote_user_id"]
            companion = companion_display_by_id.get(companion_key, {})
            if channel == "linyu":
                display = linyu_display_by_remote_id.get(remote_user_id)
                if not display and _UUID_RE.fullmatch(remote_user_id):
                    display = f"{remote_user_id[:8]}..."
                companion_name = companion.get("companion_name") or f"伴侣{companion_key}"
                ai_account_name = companion.get("ai_account_name") or "-"
                display_name = f"{companion_name} | Linyu:{ai_account_name} | 用户:{display or remote_user_id}（历史记忆）"
            else:
                display_name = f"{companion.get('companion_name') or memory_user_id} | {channel.upper()} 用户:{remote_user_id}（历史记忆）"
        elif _UUID_RE.fullmatch(memory_user_id):
            channel = "linyu"
            remote_user_id = memory_user_id
            display = linyu_display_by_remote_id.get(remote_user_id)
            display_name = f"Linyu:{display or remote_user_id[:8] + '...'}（历史记忆）"
        elif parse_companion_user_id(memory_user_id) is not None:
            channel = "linyu"
            companion_id = str(parse_companion_user_id(memory_user_id) or "")
            companion = companion_display_by_id.get(companion_id, {})
            display_name = f"{companion.get('companion_name') or memory_user_id}（历史记忆）"
        elif parse_companion_memory_session_id(memory_session_id) is not None:
            channel = "linyu"
            companion_id = str(parse_companion_memory_session_id(memory_session_id) or "")
            companion = companion_display_by_id.get(companion_id, {})
            display_name = f"{companion.get('companion_name') or memory_user_id}（统一记忆）"
        elif memory_user_id.startswith("linyu_ai_"):
            channel = "linyu"
            display_name = f"Linyu AI:{memory_user_id}（历史记忆）"
        elif memory_user_id.isdigit():
            display_name = f"历史身份:{memory_user_id}"

        selector_key = f"{channel}:{memory_user_id}:{memory_session_id}"
        entries.append({
            "user_id": memory_user_id,
            "display_name": display_name,
            "selector_key": selector_key,
            "channel": channel,
            "default_session_id": memory_session_id,
            "memory_user_id": memory_user_id,
            "memory_session_id": memory_session_id,
            "remote_user_id": remote_user_id,
            "project_user_id": memory_user_id,
        })
    return entries


def _dedupe_memory_entries(entries: List[Dict[str, str]]) -> List[Dict[str, str]]:
    deduped: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        memory_user_id = str(entry.get("memory_user_id") or entry.get("user_id") or "").strip()
        memory_session_id = str(entry.get("memory_session_id") or entry.get("default_session_id") or "").strip()
        key = (memory_user_id, memory_session_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def _get_accessible_memory_user_ids(user: Any) -> set[str]:
    allowed_ids: set[str] = set()
    for entry in _get_accessible_memory_entries(user):
        for key in ("user_id", "remote_user_id", "project_user_id", "memory_user_id"):
            value = str(entry.get(key) or "").strip()
            if value:
                allowed_ids.add(value)
    return allowed_ids


def _ensure_user_id_access(user: Any, user_id: str, field_name: str = "user_id") -> str:
    requested = str(user_id or "").strip()
    allowed_ids = _get_accessible_memory_user_ids(user)
    if not requested or requested not in allowed_ids:
        raise HTTPException(status_code=403, detail=f"无权访问该{field_name}对应的记忆")
    return requested


def _ensure_session_access(user: Any, session_id: Optional[str]) -> Optional[str]:
    if session_id is None:
        return None
    requested = str(session_id or "").strip()
    if not requested:
        return None

    allowed_session_ids = {value for value in _get_accessible_memory_user_ids(user) if value}
    for entry in _get_accessible_memory_entries(user):
        default_session_id = str(
            entry.get("memory_session_id") or entry.get("default_session_id") or ""
        ).strip()
        if default_session_id:
            allowed_session_ids.add(default_session_id)

    if requested not in allowed_session_ids:
        raise HTTPException(status_code=403, detail="无权访问该session_id对应的记忆")
    return requested


async def _ensure_memory_owner_access(manager: Any, user: Any, memory_id: str) -> None:
    vector_store = getattr(manager, "vector_store", None)
    collection = getattr(vector_store, "collection", None)
    if collection is None:
        return

    result = collection.get(ids=[memory_id], include=["metadatas"])
    ids = result.get("ids") or []
    if not ids:
        raise HTTPException(status_code=404, detail="记忆未找到")

    metadatas = result.get("metadatas") or []
    owner_user_id = str((metadatas[0] or {}).get("user_id") or "").strip() if metadatas else ""
    _ensure_user_id_access(user, owner_user_id)


def _split_roleplay_memory_user_id(user_id: str) -> tuple[str, bool]:
    suffix = "::roleplay"
    raw = str(user_id or "")
    if raw.endswith(suffix):
        return raw[:-len(suffix)], True
    return raw, False

def get_memory_manager():
    """获取共享记忆管理器实例"""
    global _memory_manager
    if _memory_manager is None:
        # 从配置创建MemoryConfig
        memory_config_dict = config.get('memory', {})
        memory_config = MemoryConfig(**memory_config_dict)
        
        _memory_manager = MemoryManager(memory_config)
        
        # 异步初始化（这里简化处理，实际应该在应用启动时初始化）
        # 注意：FastAPI不支持在同步函数中直接运行async函数
        # 我们将在第一次请求时初始化，或者更好的方式是在应用启动事件中初始化
    return _memory_manager


async def ensure_memory_manager_initialized():
    """确保记忆管理器已初始化"""
    manager = get_memory_manager()
    # 检查是否已初始化
    if hasattr(manager, 'engine') and manager.engine is None:
        try:
            await manager.initialize()
            print("记忆管理器已初始化")
        except Exception as e:
            print(f"记忆管理器初始化失败: {e}")
            raise HTTPException(status_code=500, detail=f"记忆系统初始化失败: {str(e)}")
    return manager


# 请求/响应模型
class UpdateMemoryConfigRequest(BaseModel):
    """更新记忆配置请求"""
    config: Dict[str, Any]

class AddLongTermMemoryRequest(BaseModel):
    """添加长期记忆请求"""
    user_id: str
    content: str
    importance: float = 0.5
    metadata: Dict[str, Any] = {}

class SearchMemoriesRequest(BaseModel):
    """搜索记忆请求"""
    user_id: str
    query: str
    top_k: int = 3
    score_threshold: float = 0.5

class ClearMemoriesRequest(BaseModel):
    """清除记忆请求"""
    user_id: str
    session_id: Optional[str] = None

class UpdateLongTermMemoryRequest(BaseModel):
    """更新长期记忆请求"""
    content: Optional[str] = None
    importance: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None

class BatchAddLongTermMemoriesRequest(BaseModel):
    """批量添加长期记忆请求"""
    user_id: str
    memories: List[Dict[str, Any]]  # 每个元素包含 content, importance, metadata

class BatchDeleteShortTermMemoriesRequest(BaseModel):
    """批量删除短期记忆请求"""
    user_id: str
    session_id: Optional[str] = None
    before_date: Optional[str] = None  # ISO格式日期字符串

class ExternalContextRequest(BaseModel):
    """外部记忆上下文请求"""
    user_id: str
    max_token_size: int = 500
    prefer_topics: Optional[List[str]] = None
    customize_context_prompt: Optional[str] = None


@router.get("/memory/config")
async def get_memory_config():
    """获取记忆系统配置"""
    try:
        memory_config_dict = config.get('memory', {})
        return {"config": memory_config_dict}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取配置失败: {str(e)}")


@router.post("/memory/config")
async def update_memory_config(request: UpdateMemoryConfigRequest):
    """更新记忆系统配置"""
    try:
        # 更新配置文件
        config.update_config('memory', request.config)
        
        # 重新初始化MemoryManager（下次请求时会使用新配置）
        global _memory_manager
        _memory_manager = None
        
        return {"message": "配置更新成功", "config": request.config}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")


@router.get("/memory/users")
async def get_memory_users(token: str = Depends(get_access_token)):
    """仅返回当前登录用户可访问的记忆身份。"""
    try:
        user = await _get_authenticated_user(token)
        user_info_list = _get_accessible_memory_entries(user)
        user_ids = list(dict.fromkeys(entry["user_id"] for entry in user_info_list))
        return {"user_ids": user_ids, "user_info": user_info_list}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取用户ID列表失败: {str(e)}")


@router.get("/memory/stats")
async def get_memory_stats():
    """获取记忆系统统计信息"""
    try:
        manager = await ensure_memory_manager_initialized()
        stats = await manager.get_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")


@router.get("/memory/short-term")
async def get_short_term_memories(
    user_id: str = Query(..., description="用户ID"),
    session_id: str = Query(..., description="会话ID"),
    limit: int = Query(50, description="最大返回数量"),
    token: str = Depends(get_access_token),
):
    """获取短期记忆（对话历史）"""
    try:
        user = await _get_authenticated_user(token)
        user_id = _ensure_user_id_access(user, user_id)
        session_id = _ensure_session_access(user, session_id) or user_id
        manager = await ensure_memory_manager_initialized()
        memories = await manager.get_short_term_memories(user_id, session_id, limit)
        return {"memories": memories}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取短期记忆失败: {str(e)}")


@router.get("/memory/pending")
async def get_pending_memories(
    user_id: str = Query(..., description="用户ID"),
    session_id: str = Query(..., description="会话ID"),
    limit: int = Query(100, description="最大返回数量"),
    token: str = Depends(get_access_token),
):
    """获取待处理区原文（超过短期窗口的对话原文）"""
    try:
        user = await _get_authenticated_user(token)
        user_id = _ensure_user_id_access(user, user_id)
        session_id = _ensure_session_access(user, session_id) or user_id
        manager = await ensure_memory_manager_initialized()
        if not hasattr(manager, "get_pending_memories"):
            raise HTTPException(status_code=500, detail="当前记忆管理器不支持待处理区")
        memories = await manager.get_pending_memories(user_id=user_id, session_id=session_id, limit=limit)
        return {"memories": memories}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取待处理区失败: {str(e)}")


@router.post("/memory/pending/summarize")
async def summarize_pending_memories(
    user_id: str = Query(..., description="用户ID"),
    session_id: str = Query(..., description="会话ID"),
    token: str = Depends(get_access_token),
):
    """手动触发：摘要待处理区（若不足一个chunk则无操作）"""
    try:
        user = await _get_authenticated_user(token)
        user_id = _ensure_user_id_access(user, user_id)
        session_id = _ensure_session_access(user, session_id) or user_id
        manager = await ensure_memory_manager_initialized()
        if not hasattr(manager, "summarize_pending_now"):
            raise HTTPException(status_code=500, detail="当前记忆管理器不支持待处理区摘要")
        result = await manager.summarize_pending_now(user_id=user_id, session_id=session_id, force=True)
        if isinstance(result, dict):
            return result
        return {"ok": bool(result), "processed": bool(result), "force": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"触发待处理区摘要失败: {str(e)}")


@router.get("/memory/mid-term")
async def get_mid_term_memories(
    user_id: str = Query(..., description="用户ID"),
    session_id: Optional[str] = Query(None, description="会话ID（可选）"),
    limit: int = Query(10, description="最大返回数量"),
    token: str = Depends(get_access_token),
):
    """获取中期记忆（对话摘要）"""
    try:
        user = await _get_authenticated_user(token)
        user_id = _ensure_user_id_access(user, user_id)
        session_id = _ensure_session_access(user, session_id)
        manager = await ensure_memory_manager_initialized()
        summaries = await manager.get_mid_term_summaries(user_id, session_id, limit)
        return {"summaries": summaries}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取中期记忆失败: {str(e)}")


@router.get("/memory/long-term")
async def get_long_term_memories(
    user_id: str = Query(..., description="用户ID"),
    limit: int = Query(100, description="最大返回数量"),
    token: str = Depends(get_access_token),
):
    """获取长期记忆"""
    try:
        user = await _get_authenticated_user(token)
        user_id = _ensure_user_id_access(user, user_id)
        manager = await ensure_memory_manager_initialized()
        memories = await manager.get_long_term_memories(user_id, limit)
        return {"memories": memories}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取长期记忆失败: {str(e)}")


@router.post("/memory/long-term/search")
async def search_long_term_memories(request: SearchMemoriesRequest, token: str = Depends(get_access_token)):
    """搜索长期记忆"""
    try:
        user = await _get_authenticated_user(token)
        request.user_id = _ensure_user_id_access(user, request.user_id)
        manager = await ensure_memory_manager_initialized()
        memories = await manager.search_long_term_memories(
            user_id=request.user_id,
            query=request.query,
            top_k=request.top_k,
            score_threshold=request.score_threshold
        )
        return {"memories": memories}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索长期记忆失败: {str(e)}")


@router.post("/memory/long-term")
async def add_long_term_memory(request: AddLongTermMemoryRequest, token: str = Depends(get_access_token)):
    """手动添加长期记忆"""
    try:
        user = await _get_authenticated_user(token)
        request.user_id = _ensure_user_id_access(user, request.user_id)
        manager = await ensure_memory_manager_initialized()
        success = await manager.add_long_term_memory(
            user_id=request.user_id,
            content=request.content,
            importance=request.importance,
            metadata=request.metadata
        )
        
        if success:
            return {"message": "长期记忆添加成功"}
        else:
            raise HTTPException(status_code=500, detail="长期记忆添加失败")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加长期记忆失败: {str(e)}")


@router.delete("/memory/long-term/{memory_id}")
async def delete_long_term_memory(memory_id: str, token: str = Depends(get_access_token)):
    """删除长期记忆（简化实现，实际需要用户验证）"""
    try:
        user = await _get_authenticated_user(token)
        manager = await ensure_memory_manager_initialized()
        if getattr(manager.config, "long_term_strategy", "local").lower() == "external":
            raise HTTPException(status_code=501, detail="外部记忆暂不支持删除操作")
        await _ensure_memory_owner_access(manager, user, memory_id)

        # 兼容不同类型的记忆管理器
        if hasattr(manager, 'vector_store') and manager.vector_store:
            # 原始MemoryManager使用vector_store
            success = await manager.vector_store.delete_memory(memory_id)
        elif hasattr(manager, '_delete_long_term_memory_by_id'):
            success = await manager._delete_long_term_memory_by_id(memory_id)
        else:
            raise HTTPException(status_code=500, detail="当前记忆管理器不支持删除操作")

        if success:
            return {"message": "记忆删除成功"}
        else:
            raise HTTPException(status_code=404, detail="记忆未找到")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除记忆失败: {str(e)}")


@router.put("/memory/long-term/{memory_id}")
async def update_long_term_memory(
    memory_id: str,
    request: UpdateLongTermMemoryRequest,
    token: str = Depends(get_access_token),
):
    """更新长期记忆（编辑内容和重要性）"""
    try:
        user = await _get_authenticated_user(token)
        manager = await ensure_memory_manager_initialized()
        if getattr(manager.config, "long_term_strategy", "local").lower() == "external":
            raise HTTPException(status_code=501, detail="外部记忆暂不支持更新操作")
        await _ensure_memory_owner_access(manager, user, memory_id)

        # 兼容不同类型的记忆管理器
        if hasattr(manager, 'vector_store') and manager.vector_store:
            update_metadata = dict(request.metadata or {})
            if request.importance is not None:
                update_metadata["importance"] = request.importance
            success = await manager.vector_store.update_memory(
                memory_id=memory_id,
                content=request.content,
                metadata=update_metadata or None,
            )
        elif hasattr(manager, '_update_long_term_memory_by_id'):
            success = await manager._update_long_term_memory_by_id(
                memory_id=memory_id,
                content=request.content,
                importance=request.importance,
                metadata=request.metadata
            )
        else:
            raise HTTPException(status_code=500, detail="当前记忆管理器不支持更新操作")

        if success:
            return {"message": "记忆更新成功"}
        else:
            raise HTTPException(status_code=404, detail="记忆未找到")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新记忆失败: {str(e)}")


@router.post("/memory/batch/add-short-term")
async def batch_add_short_term_memories(
    user_id: str = Query(..., description="用户ID"),
    session_id: str = Query(..., description="会话ID"),
    messages: List[Dict[str, Any]] = Body(..., description="消息列表"),
    token: str = Depends(get_access_token),
):
    """批量添加短期记忆"""
    try:
        from ..memory.models import ConversationMessage
        from datetime import datetime

        user = await _get_authenticated_user(token)
        user_id = _ensure_user_id_access(user, user_id)
        session_id = _ensure_session_access(user, session_id) or user_id
        manager = await ensure_memory_manager_initialized()

        # 转换消息格式
        conversation_messages = []
        for msg in messages:
            conversation_messages.append(ConversationMessage(
                role=msg.get("role", "user"),
                content=msg.get("content", ""),
                timestamp=datetime.fromisoformat(msg.get("timestamp", datetime.now().isoformat()))
            ))

        count = await manager.batch_add_short_term_memories(
            user_id=user_id,
            session_id=session_id,
            messages=conversation_messages
        )

        return {"message": f"已批量添加 {count} 条短期记忆", "count": count}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量添加短期记忆失败: {str(e)}")


@router.post("/memory/batch/add-long-term")
async def batch_add_long_term_memories(request: BatchAddLongTermMemoriesRequest, token: str = Depends(get_access_token)):
    """批量添加长期记忆"""
    try:
        user = await _get_authenticated_user(token)
        request.user_id = _ensure_user_id_access(user, request.user_id)
        manager = await ensure_memory_manager_initialized()

        # 兼容不同类型的记忆管理器
        if hasattr(manager, 'add_long_term_memories_batch'):
            count = await manager.add_long_term_memories_batch(
                user_id=request.user_id,
                memories=request.memories
            )
            return {"message": f"已批量添加 {count} 条长期记忆", "count": count}
        else:
            raise HTTPException(status_code=500, detail="当前记忆管理器不支持批量添加操作")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量添加长期记忆失败: {str(e)}")


@router.post("/memory/batch/delete-short-term")
async def batch_delete_short_term_memories(request: BatchDeleteShortTermMemoriesRequest, token: str = Depends(get_access_token)):
    """批量删除短期记忆"""
    try:
        user = await _get_authenticated_user(token)
        request.user_id = _ensure_user_id_access(user, request.user_id)
        request.session_id = _ensure_session_access(user, request.session_id)
        manager = await ensure_memory_manager_initialized()

        from datetime import datetime
        before_date = None
        if request.before_date:
            before_date = datetime.fromisoformat(request.before_date)

        count = await manager.delete_short_term_memories_batch(
            user_id=request.user_id,
            session_id=request.session_id,
            before_date=before_date
        )

        return {"message": f"已批量删除 {count} 条短期记忆", "count": count}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量删除短期记忆失败: {str(e)}")


@router.post("/memory/clear")
async def clear_memories(request: ClearMemoriesRequest, token: str = Depends(get_access_token)):
    """清除记忆"""
    try:
        user = await _get_authenticated_user(token)
        request.user_id = _ensure_user_id_access(user, request.user_id)
        request.session_id = _ensure_session_access(user, request.session_id)
        manager = await ensure_memory_manager_initialized()
        success = await manager.clear_all_memories(
            user_id=request.user_id,
            session_id=request.session_id
        )
        
        if success:
            try:
                from backend.api.bot_provider import get_bot

                bot = get_bot()
                memory_user_id, memory_session_id = bot._get_memory_scope(request.user_id, request.session_id)
                bot._history_manager.clear(memory_session_id, bot._get_user_system_prompt(memory_user_id))
                bot._history_manager._history_loaded_sessions.discard(memory_session_id)
            except Exception:
                pass
            return {"message": "记忆清除成功"}
        else:
            raise HTTPException(status_code=500, detail="记忆清除失败")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清除记忆失败: {str(e)}")


@router.get("/memory/test")
async def test_memory_system():
    """测试记忆系统连接"""
    try:
        manager = await ensure_memory_manager_initialized()
        stats = await manager.get_stats()
        return {
            "status": "正常",
            "stats": stats,
            "message": "记忆系统运行正常"
        }
    except Exception as e:
        return {
            "status": "异常",
            "error": str(e),
            "message": "记忆系统测试失败"
        }


@router.get("/memory/external/ping")
async def external_memory_ping():
    """测试外部记忆系统连接"""
    try:
        manager = await ensure_memory_manager_initialized()
        result = await manager.ping_external_memory()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"外部记忆连接失败: {str(e)}")


@router.get("/memory/external/profiles")
async def get_external_profiles(
    user_id: str = Query(..., description="用户ID"),
    token: str = Depends(get_access_token),
):
    """获取外部记忆画像"""
    try:
        user = await _get_authenticated_user(token)
        user_id = _ensure_user_id_access(user, user_id)
        manager = await ensure_memory_manager_initialized()
        profiles = await manager.get_external_profiles(user_id=user_id)
        return {"profiles": profiles}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取外部画像失败: {str(e)}")


@router.get("/memory/external/events")
async def get_external_events(
    user_id: str = Query(..., description="用户ID"),
    limit: int = Query(10, description="最大返回数量"),
    query: Optional[str] = Query(None, description="检索关键词（可选）"),
    token: str = Depends(get_access_token),
):
    """获取外部记忆事件"""
    try:
        user = await _get_authenticated_user(token)
        user_id = _ensure_user_id_access(user, user_id)
        manager = await ensure_memory_manager_initialized()
        events = await manager.get_external_events(user_id=user_id, limit=limit, query=query)
        return {"events": events}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取外部事件失败: {str(e)}")


@router.post("/memory/external/context")
async def get_external_context(request: ExternalContextRequest, token: str = Depends(get_access_token)):
    """获取外部记忆上下文"""
    try:
        user = await _get_authenticated_user(token)
        request.user_id = _ensure_user_id_access(user, request.user_id)
        manager = await ensure_memory_manager_initialized()
        prefer_topics = request.prefer_topics
        if prefer_topics is None:
            prefer_topics = getattr(manager.config, "external_memory_prefer_topics", None)
        context = await manager.get_external_context(
            user_id=request.user_id,
            max_token_size=request.max_token_size,
            prefer_topics=prefer_topics,
            customize_context_prompt=request.customize_context_prompt
        )
        return {"context": context}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取外部上下文失败: {str(e)}")
