"""FastAPI router for the transport layer.

Exposes the QBWC SOAP endpoint and the /sync/health CRUX metric. This module only
*defines* ``router``; per the isolation contract it must be registered in
app/main.py by the orchestrator (do not wire it here).
"""
from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app.transport.metrics import PollMetrics
from app.transport.qbwc import QBWCSessionManager, dispatch_soap
from app.transport.qwc import WSDL

router = APIRouter()

# Process-wide singletons: the Web Connector polls one endpoint; the metric is global.
metrics = PollMetrics()
manager = QBWCSessionManager(metrics=metrics)


@router.api_route("/qbwc", methods=["GET", "POST"])
async def qbwc_endpoint(request: Request) -> Response:
    """QBWC SOAP endpoint. GET ?wsdl serves the contract; POST handles SOAP calls."""
    if request.method == "GET":
        return Response(content=WSDL, media_type="text/xml")
    body = await request.body()
    reply = dispatch_soap(body, manager)
    return Response(content=reply, media_type="text/xml")


@router.get("/sync/health")
def sync_health() -> dict:
    """The CRUX measurement: poll cadence + max queue depth + backoff state."""
    return {"data": metrics.snapshot(), "error": None, "meta": {"source": "qbwc"}}
