"""管理员认证依赖

基于 JWT 登录令牌验证用户身份，并检查 is_admin 字段。
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from backend.user.auth import auth_manager
from backend.user import user_manager


async def require_admin(request: Request) -> None:
    """校验当前请求用户是否为管理员。

    从 Authorization: Bearer <token> 或 query ?token= 中提取 JWT，
    解码后验证用户存在且 is_admin == 1。
    """
    token = _extract_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌",
        )

    payload = auth_manager.decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌无效或已过期",
        )

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌格式错误",
        )

    user = await user_manager.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )

    if not getattr(user, "is_admin", 0):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )


def _extract_token(request: Request) -> str:
    """从请求中提取 token（Bearer header 或 query param）"""
    # 优先从 Authorization header
    auth_header = request.headers.get("authorization", "")
    if auth_header:
        parts = auth_header.strip().split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
            return parts[1].strip()

    # 其次从 query param
    token = request.query_params.get("token", "")
    if token:
        return token

    return ""
