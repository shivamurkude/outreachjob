from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import get_settings
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


async def init_db() -> None:
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongodb_uri)
    database = client[settings.mongodb_db_name]
    await init_beanie(database=database, document_models=DOCUMENT_MODELS)
