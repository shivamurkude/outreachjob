import logging

import certifi
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)
# Reduce MongoDB driver log noise (heartbeat started/succeeded every ~10s)
logging.getLogger("pymongo").setLevel(logging.WARNING)
logging.getLogger("motor").setLevel(logging.WARNING)
from app.models.audit_log import AuditLog
from app.models.campaign import Campaign
from app.models.credit_balance import CreditBalance
from app.models.credit_ledger import CreditLedgerEntry
from app.models.email_verification_result import EmailVerificationResult
from app.models.enrichment_result import EnrichmentResult
from app.models.failed_job import FailedJob
from app.models.gmail_account import GmailAccount
from app.models.payment_order import PaymentOrder
from app.models.recipient_item import RecipientItem
from app.models.recipient_list import RecipientList
from app.models.resume_document import ResumeDocument
from app.models.scheduled_email import ScheduledEmail
from app.models.suppression_entry import SuppressionEntry
from app.models.system_recipient import SystemRecipient
from app.models.template import Template
from app.models.user import User

DOCUMENT_MODELS = [
    User,
    GmailAccount,
    CreditBalance,
    CreditLedgerEntry,
    PaymentOrder,
    ResumeDocument,
    RecipientList,
    RecipientItem,
    Template,
    Campaign,
    ScheduledEmail,
    EmailVerificationResult,
    EnrichmentResult,
    SuppressionEntry,
    SystemRecipient,
    AuditLog,
    FailedJob,
]


def _use_tls(uri: str) -> bool:
    """True if URI uses TLS (Atlas or explicit tls=true). Avoids TLS for plain mongodb:// in CI."""
    log.debug("_use_tls", uri_prefix=uri[:30] + "..." if len(uri) > 30 else uri)
    return "mongodb+srv://" in uri or "tls=true" in uri.lower()


async def init_db() -> None:
    log.info("init_db_start")
    settings = get_settings()
    kwargs = {}
    if _use_tls(settings.mongodb_uri):
        kwargs["tlsCAFile"] = certifi.where()
        kwargs["tlsDisableOCSPEndpointCheck"] = True
    client = AsyncIOMotorClient(settings.mongodb_uri, **kwargs)
    database = client[settings.mongodb_db_name]
    await init_beanie(database=database, document_models=DOCUMENT_MODELS)
    log.info("init_db_ok", db_name=settings.mongodb_db_name)
