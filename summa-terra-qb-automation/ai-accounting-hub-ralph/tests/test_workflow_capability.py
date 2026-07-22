"""Capability-token unit tests (ATXN allowed_actions, fail-closed)."""
from __future__ import annotations

import pytest

from app.workflow.capability import CapabilityError, mint_capability, verify_capability

SECRET = "cap-secret"


def test_round_trip_allows_scoped_action():
    token = mint_capability(agent_id="a", allowed_actions=["create_bill"], secret=SECRET)
    claims = verify_capability(token, "create_bill", secret=SECRET)
    assert claims["agent_id"] == "a"


def test_action_out_of_scope_denied():
    token = mint_capability(agent_id="a", allowed_actions=["read"], secret=SECRET)
    with pytest.raises(CapabilityError):
        verify_capability(token, "create_bill", secret=SECRET)


def test_tampered_signature_denied():
    token = mint_capability(agent_id="a", allowed_actions=["create_bill"], secret=SECRET)
    forged = token[:-1] + ("0" if token[-1] != "0" else "1")
    with pytest.raises(CapabilityError):
        verify_capability(forged, "create_bill", secret=SECRET)


def test_wrong_secret_denied():
    token = mint_capability(agent_id="a", allowed_actions=["create_bill"], secret=SECRET)
    with pytest.raises(CapabilityError):
        verify_capability(token, "create_bill", secret="other-secret")


def test_missing_secret_defaults_to_deny(monkeypatch):
    monkeypatch.delenv("AGENT_CAPABILITY_SIGNING_SECRET", raising=False)
    with pytest.raises(CapabilityError):
        verify_capability("anything", "create_bill")


def test_malformed_token_denied():
    with pytest.raises(CapabilityError):
        verify_capability("not-a-token", "create_bill", secret=SECRET)
