"""Shared FastAPI dependencies."""

from fastapi import Request

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import load_session_cookie
from app.models.user import User

SESSION_COOKIE_NAME = "findmyjob_session"


async def get_current_user(request: Request) -> User:
    """Dependency: load session from cookie and return User."""
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie:
        raise UnauthorizedError("Not authenticated")
    payload = load_session_cookie(cookie)
    if not payload:
        raise UnauthorizedError("Invalid or expired session")
    user_id = payload.get("user_id")
    if not user_id:
        raise UnauthorizedError("Invalid session")
    user = await User.get(user_id)
    if not user:
        raise UnauthorizedError("User not found")
    if payload.get("session_version") != user.session_version:
        raise UnauthorizedError("Session invalidated")
    return user


async def require_admin(request: Request) -> User:
    """Dependency: require current user to have role admin."""
    user = await get_current_user(request)
    if getattr(user, "role", "user") != "admin":
        raise ForbiddenError("Admin only")
    return user
