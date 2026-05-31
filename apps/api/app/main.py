"""FiscAudit Pro — FastAPI entrypoint."""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import (
    acompte_is, amortissements, auth, audit_cases, brigades, cash_payments,
    charges_financieres, controls, datasets, dons_liberalites, invoices,
    monthly_returns, petit_materiel, primes_assurance, reconciliations,
    taxpayers, users,
)
from app.storage import ensure_bucket


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("fiscaudit")
settings = get_settings()


app = FastAPI(
    title="FiscAudit Pro API",
    description="Plateforme d'audit fiscal — DGI Cameroun (prototype)",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(brigades.router)
app.include_router(taxpayers.router)
app.include_router(audit_cases.router)
app.include_router(datasets.router)
app.include_router(controls.router)
app.include_router(monthly_returns.router)
app.include_router(reconciliations.router)
app.include_router(invoices.router)
app.include_router(amortissements.router)
app.include_router(cash_payments.router)
app.include_router(dons_liberalites.router)
app.include_router(acompte_is.router)
app.include_router(primes_assurance.router)
app.include_router(charges_financieres.router)
app.include_router(petit_materiel.router)
app.include_router(users.router)


@app.on_event("startup")
def on_startup() -> None:
    try:
        ensure_bucket()
        log.info("Local storage directory ready")
    except Exception as e:  # noqa: BLE001
        log.warning("Could not ensure storage directory at startup: %s", e)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "service": "fiscaudit-api", "version": "0.1.0"}
