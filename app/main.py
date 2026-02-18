import time
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import (
    AppError,
    app_exception_handler,
    generic_exception_handler,
    validation_exception_handler,
)
from app.core.logging import bind_request_id, configure_logging, get_logger
from app.db.init import init_db
from app.routers import admin, auth, campaigns, credits, enrich, gmail, lists, onboarding, payments, referrals, resume, suppressions, templates, verify
from fastapi.exceptions import RequestValidationError

settings = get_settings()
configure_logging(debug=settings.debug)
log = get_logger(__name__)

app = FastAPI(
    title="FINDMYJOB v2 API",
    version="2.0.0",
    default_response_class=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    bind_request_id(request_id)
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    log.info(
        "request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round(duration_ms, 2),
    )
    response.headers["X-Request-ID"] = request_id
    return response


app.add_exception_handler(AppError, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Routers
app.include_router(auth.router, prefix="/v1/auth", tags=["auth"])
app.include_router(onboarding.router, prefix="/v1/onboarding", tags=["onboarding"])
app.include_router(resume.router, prefix="/v1/resume", tags=["resume"])
app.include_router(gmail.router, prefix="/v1/gmail", tags=["gmail"])
app.include_router(lists.router, prefix="/v1/recipients", tags=["recipients"])
app.include_router(templates.router, prefix="/v1/templates", tags=["templates"])
app.include_router(verify.router, prefix="/v1/verify", tags=["verify"])
app.include_router(suppressions.router, prefix="/v1/suppressions", tags=["suppressions"])
app.include_router(enrich.router, prefix="/v1/enrich", tags=["enrich"])
app.include_router(campaigns.router, prefix="/v1/campaigns", tags=["campaigns"])
app.include_router(credits.router, prefix="/v1/credits", tags=["credits"])
app.include_router(payments.router, prefix="/v1/payments", tags=["payments"])
app.include_router(referrals.router, prefix="/v1/referrals", tags=["referrals"])
app.include_router(admin.router, prefix="/v1/admin", tags=["admin"])


@app.on_event("startup")
async def startup():
    if settings.sentry_dsn:
        import sentry_sdk
        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.env, traces_sample_rate=0.1)
        log.info("startup", msg="Sentry enabled")
    await init_db()
    log.info("startup", msg="DB connected")


@app.get("/health")
async def health():
    """Health check for load balancers and monitoring."""
    return {"status": "ok"}
