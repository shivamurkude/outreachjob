from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse


class AppError(Exception):
    """Base application error with consistent schema."""

    def __init__(
        self,
        message: str,
        code: str = "ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: dict[str, Any] | None = None,
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message, code="UNAUTHORIZED", status_code=status.HTTP_401_UNAUTHORIZED)


class ForbiddenError(AppError):
    def __init__(self, message: str = "Forbidden"):
        super().__init__(message, code="FORBIDDEN", status_code=status.HTTP_403_FORBIDDEN)


class NotFoundError(AppError):
    def __init__(self, message: str = "Not found"):
        super().__init__(message, code="NOT_FOUND", status_code=status.HTTP_404_NOT_FOUND)


class ConflictError(AppError):
    def __init__(self, message: str = "Conflict", details: dict[str, Any] | None = None):
        super().__init__(message, code="CONFLICT", status_code=status.HTTP_409_CONFLICT, details=details)


class BadRequestError(AppError):
    def __init__(self, message: str = "Bad request", details: dict[str, Any] | None = None):
        super().__init__(message, code="BAD_REQUEST", status_code=status.HTTP_400_BAD_REQUEST, details=details)


def error_response(request: Request, exc: AppError) -> ORJSONResponse:
    body = {
        "error": {
            "message": exc.message,
            "code": exc.code,
            "details": exc.details,
        }
    }
    if hasattr(request.state, "request_id"):
        body["request_id"] = request.state.request_id
    return ORJSONResponse(status_code=exc.status_code, content=body)


async def app_exception_handler(request: Request, exc: AppError) -> ORJSONResponse:
    return error_response(request, exc)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> ORJSONResponse:
    body = {
        "error": {
            "message": "Validation error",
            "code": "VALIDATION_ERROR",
            "details": {"errors": exc.errors()},
        }
    }
    if hasattr(request.state, "request_id"):
        body["request_id"] = request.state.request_id
    return ORJSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=body,
    )


async def generic_exception_handler(request: Request, exc: Exception) -> ORJSONResponse:
    from app.core.logging import get_logger
    get_logger(__name__).exception("unhandled_exception", exc_info=exc)
    body = {
        "error": {
            "message": "Internal server error",
            "code": "INTERNAL_ERROR",
            "details": {},
        }
    }
    if hasattr(request.state, "request_id"):
        body["request_id"] = request.state.request_id
    return ORJSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=body,
    )
