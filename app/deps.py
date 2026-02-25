"""Shared FastAPI dependencies."""

from fastapi import Request

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.logging import get_logger
from app.core.security import load_session_cookie
from app.models.user import User

SESSION_COOKIE_NAME = "findmyjob_session"
log = get_logger(__name__)


async def get_current_user(request: Request) -> User:
    """Dependency: load session from cookie and return User."""
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie:
        log.info("auth_failed", reason="no_cookie", path=request.url.path)
        raise UnauthorizedError("Not authenticated")
    payload = load_session_cookie(cookie)
    if not payload:
        log.info("auth_failed", reason="invalid_or_expired_session", path=request.url.path)
        raise UnauthorizedError("Invalid or expired session")
    user_id = payload.get("user_id")
    if not user_id:
        log.info("auth_failed", reason="invalid_session_no_user_id", path=request.url.path)
        raise UnauthorizedError("Invalid session")
    user = await User.get(user_id)
    if not user:
        log.info("auth_failed", reason="user_not_found", user_id=user_id, path=request.url.path)
        raise UnauthorizedError("User not found")
    if payload.get("session_version") != user.session_version:
        log.info("auth_failed", reason="session_invalidated", user_id=user_id, path=request.url.path)
        raise UnauthorizedError("Session invalidated")
    log.debug("auth_ok", user_id=user_id, path=request.url.path)
    return user


async def require_admin(request: Request) -> User:
    """Dependency: require current user to have role admin."""
    user = await get_current_user(request)
    if getattr(user, "role", "user") != "admin":
        log.info("admin_required_failed", user_id=str(user.id), path=request.url.path)
        raise ForbiddenError("Admin only")
    return user
