"""FastAPI router for the atomic payments path (CHUNK_7_PAYMENTS).

Defines a module-level ``router``; per the isolation contract it must be registered
in app/main.py by the orchestrator (do NOT wire it here).

* ``POST /ap/intake``            -> OCR/JSON intake + InvoiceProof verdict (enveloped)
* ``GET  /bills/{bill_id}/proof``-> the stored InvoiceProof/VCAP bundle (enveloped)

Every response uses the ``{"data","error","meta"}`` envelope. The default service uses
DB-backed collaborators; tests swap ``router._service`` / ``router._fetch_proof`` with
in-memory fakes, so the router is import-safe with no DB running.
"""
from __future__ import annotations

import os
import tempfile
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.audit import append_audit_row
from app.db import get_session
from app.payments.invoiceproof import InvoiceProofError
from app.payments.ocr import OcrError, bill_draft_from_json, bill_draft_from_pdf
from app.payments.schemas import IntakeJsonIn
from app.payments.service import PaymentsService
from app.payments.vcap import VcapSecretMissing

router = APIRouter()

SessionDep = Depends(get_session)

# Process-wide default wiring (DB-backed). Audit + VCAP secret come from the app.audit
# service and the environment respectively.
_service = PaymentsService(append_audit=append_audit_row)


def _ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "error": None, "meta": meta or {}}


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"data": None, "error": {"code": code, "message": message}, "meta": {}},
    )


def _fetch_proof(session: Session, bill_id: str) -> dict[str, Any] | None:
    """Default proof lookup: bill -> invoiceproof_bundle_id -> proof_bundles row (real DB)."""
    from app.models import Bill, ProofBundle

    bill = session.get(Bill, bill_id)
    if bill is None or bill.invoiceproof_bundle_id is None:
        return None
    bundle = session.get(ProofBundle, bill.invoiceproof_bundle_id)
    if bundle is None:
        return None
    return {
        "bundle_id": str(bundle.id),
        "bill_id": bill_id,
        "kind": bundle.kind,
        "vcap_state": bundle.vcap_state,
        "proof_hash": bundle.proof_hash,
        "proof_signature": bundle.proof_signature,
        "passed": bundle.passed,
        "payload": bundle.payload,
    }


async def _draft_from_request(request: Request) -> dict[str, Any]:
    """Build a canonical bill draft from either a multipart PDF upload or a JSON body."""
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise OcrError("multipart intake requires a 'file' upload")
        data = await upload.read()  # type: ignore[union-attr]
        suffix = os.path.splitext(getattr(upload, "filename", "") or "")[1] or ".pdf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            return bill_draft_from_pdf(
                tmp_path,
                company_id=str(form.get("company_id")) if form.get("company_id") else None,
                vendor_id=str(form.get("vendor_id")) if form.get("vendor_id") else None,
            )
        finally:
            os.unlink(tmp_path)

    body = await request.json()
    parsed = IntakeJsonIn.model_validate(body)
    return bill_draft_from_json(parsed.model_dump())


@router.post("/ap/intake")
async def intake_endpoint(request: Request, session: Session = SessionDep) -> Any:
    """Submit an invoice (PDF upload or JSON) → OCR + InvoiceProof verdict (enveloped)."""
    try:
        draft = await _draft_from_request(request)
    except ValidationError as exc:
        return _error(400, "invalid_invoice", exc.errors()[0].get("msg", "invalid invoice"))
    except OcrError as exc:
        return _error(422, "ocr_failed", str(exc))
    except (ValueError, KeyError):
        return _error(400, "invalid_request", "request body could not be parsed")

    if not draft.get("company_id") or not draft.get("vendor_id"):
        return _error(400, "invalid_invoice", "company_id and vendor_id are required")

    try:
        decision = _service.process_intake(session, draft)
    except InvoiceProofError as exc:
        return _error(422, "invoiceproof_invalid", str(exc))
    except VcapSecretMissing as exc:
        return _error(503, "vcap_secret_missing", str(exc))

    status = 200 if decision["passed"] else 202
    return JSONResponse(status_code=status, content=_ok(decision, {"decision": decision["decision"]}))


@router.get("/bills/{bill_id}/proof")
def get_proof_endpoint(bill_id: str, session: Session = SessionDep) -> Any:
    """Fetch the InvoiceProof/VCAP proof bundle for a bill; enveloped 404 if absent."""
    proof = _fetch_proof(session, bill_id)
    if proof is None:
        return _error(404, "not_found", f"no proof bundle for bill '{bill_id}'")
    return _ok(proof)
