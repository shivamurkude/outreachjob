"""Recipient lists: upload, parse, and query."""

import csv
import io
import re
from datetime import datetime
from typing import Any

import openpyxl
from beanie import PydanticObjectId

from app.core.logging import get_logger
from app.models.recipient_item import RecipientItem
from app.models.recipient_list import RecipientList
from app.models.user import User
from app.storage.base import get_storage

log = get_logger(__name__)
EMAIL_RE = re.compile(r"^[^@]+@[^@]+\.[^@]+$")


def normalize_email(s: str) -> str:
    return s.strip().lower() if s else ""


def extract_domain(email: str) -> str:
    if "@" in email:
        return email.split("@", 1)[1].lower()
    return ""


async def upload_list(user: User, name: str, file_content: bytes, filename: str) -> RecipientList:
    """Save file to storage and create RecipientList with status=processing."""
    log.info("upload_list", user_id=str(user.id), name=name, filename=filename, size=len(file_content))
    storage = get_storage()
    key = f"lists/{user.id}/{name or filename}"
    await storage.put(key, file_content)
    rlist = RecipientList(
        user=user,
        name=name or filename,
        storage_path=key,
        status="processing",
    )
    await rlist.insert()
    log.info("upload_list_ok", user_id=str(user.id), list_id=str(rlist.id))
    return rlist


def parse_csv(content: bytes) -> list[dict[str, Any]]:
    log.debug("parse_csv", size=len(content))
    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    log.debug("parse_csv_ok", rows=len(rows))
    return rows


def parse_xlsx(content: bytes) -> list[dict[str, Any]]:
    log.debug("parse_xlsx", size=len(content))
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    if not ws:
        return []
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(h).strip() if h is not None else f"col{i}" for i, h in enumerate(rows[0])]
    out = [dict(zip(headers, row)) for row in rows[1:] if any(v is not None for v in row)]
    log.debug("parse_xlsx_ok", rows=len(out))
    return out


def find_email_column(row: dict) -> str | None:
    log.debug("find_email_column")
    for k, v in row.items():
        if v and isinstance(v, str) and "@" in v and EMAIL_RE.match(v.strip()):
            return v.strip().lower()
    for k in ("email", "Email", "EMAIL", "email_address"):
        if k in row and row[k]:
            return normalize_email(str(row[k]))
    for k, v in row.items():
        if v and isinstance(v, str) and "@" in v:
            return normalize_email(v)
    return None


async def process_recipient_list_upload(list_id: str) -> None:
    """
    ARQ job: load file from storage, parse CSV/XLSX, create RecipientItems, update list status.
    """
    log.info("process_recipient_list_upload", list_id=list_id)
    from app.db.init import init_db
    await init_db()

    rlist = await RecipientList.get(list_id)
    if not rlist or rlist.status != "processing":
        log.debug("process_recipient_list_upload_skip", list_id=list_id, status=getattr(rlist, "status", None))
        return
    storage = get_storage()
    try:
        content = await storage.get(rlist.storage_path)
    except FileNotFoundError:
        rlist.status = "failed"
        rlist.updated_at = datetime.utcnow()
        await rlist.save()
        return
    filename = rlist.storage_path.split("/")[-1]
    if filename.lower().endswith(".xlsx") or filename.lower().endswith(".xls"):
        rows = parse_xlsx(content)
    else:
        rows = parse_csv(content)
    valid = 0
    invalid = 0
    for row in rows:
        email = find_email_column(row)
        if not email or not EMAIL_RE.match(email):
            invalid += 1
            continue
        domain = extract_domain(email)
        name = None
        company = None
        for k, v in row.items():
            if v is None:
                continue
            v = str(v).strip()
            if not v:
                continue
            k_lower = k.lower()
            if k_lower in ("name", "full name", "contact name"):
                name = v
            elif k_lower in ("company", "organization", "org"):
                company = v
        item = RecipientItem(
            list=rlist,
            email=email,
            domain=domain,
            name=name,
            company=company,
            raw_row=dict(row),
        )
        await item.insert()
        valid += 1
    rlist.total_count = len(rows)
    rlist.valid_count = valid
    rlist.invalid_count = invalid
    rlist.status = "ready"
    rlist.updated_at = datetime.utcnow()
    await rlist.save()
    log.info("process_recipient_list_upload_ok", list_id=list_id, total=len(rows), valid=valid, invalid=invalid)


async def get_list(user_id: PydanticObjectId, list_id: PydanticObjectId) -> RecipientList | None:
    log.debug("get_list", user_id=str(user_id), list_id=str(list_id))
    rlist = await RecipientList.find_one(
        RecipientList.id == list_id,
        RecipientList.user.id == user_id,
    )
    log.debug("get_list_ok", list_id=str(list_id), found=rlist is not None)
    return rlist


async def get_list_items(
    list_id: PydanticObjectId,
    limit: int = 100,
    offset: int = 0,
) -> list[RecipientItem]:
    log.debug("get_list_items", list_id=str(list_id), limit=limit, offset=offset)
    items = await RecipientItem.find(RecipientItem.list.id == list_id).skip(offset).limit(limit).to_list()
    log.debug("get_list_items_ok", list_id=str(list_id), count=len(items))
    return items
