"""Pagination helpers."""

from typing import TypeVar, Generic

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    limit: int
    offset: int
    total: int | None = None


def paginate(limit: int, offset: int, max_limit: int = 200) -> tuple[int, int]:
    """Clamp limit/offset; return (limit, offset)."""
    limit = max(1, min(limit, max_limit))
    offset = max(0, offset)
    return limit, offset
