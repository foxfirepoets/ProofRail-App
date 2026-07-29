"""gmail_disposition.py — the DETERMINISTIC disposition engine for the Gmail state machine.

Split of responsibility (build-simplicity-auditor):
  * CLASSIFICATION (INVOICE / DRAW_SHEET / BANK_NOTICE / MARKETING / ...) is fuzzy → done by the
    cognition layer (Claude via the runner). It is an INPUT to this module.
  * DISPOSITION (which ProofRail label, remove INBOX?, move to Trash?) is pure rules → done here,
    deterministically, so it is testable offline and cannot "improvise" an unsafe action.

Enforces OWNER_OVERRIDE_2026-07-14.md §1 and directive §8. Fail-safe: when uncertain, ARCHIVE
(remove INBOX + label), never Trash. Permanent deletion is not representable in the output at all.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stv_label_map  # noqa: E402  -- STV_LABELS_V2 flag-gated ProofRail/* -> STV/* translation

# classification -> durable workflow label (the message's home after it leaves the Inbox)
# NOTE: DRAW_SHEET / VENDOR_INQUIRY / LENDER_CORRESPONDENCE are deliberately NOT here — they used to
# map unconditionally to "ProofRail/Action" (a blanket default hit on ~every message in those three
# classes; see migration_artifacts/13_Action_Selectivity_Change.md and
# migration_artifacts/08_ProofRail_Value_Review.md §2.2). They're now handled by the
# ACTION_ELIGIBLE_CLASSES gate in _target_label() below, so Action only fires when the classifier
# itself reports low confidence.
LABEL_FOR = {
    "INVOICE": "ProofRail/Approval",
    "APPROVAL": "ProofRail/Processed",
    "LENDER_DOC": "ProofRail/Processed",
    "LIEN_WAIVER": "ProofRail/Processed",
    "INSPECTION": "ProofRail/Processed",
    "BANK_NOTICE": "ProofRail/Risk-BankChange",
    "MARKETING": "ProofRail/Archive",
    "SPAM": "ProofRail/Archive",
    "OTHER": "ProofRail/Archive",
}
TRASHABLE_CLASSES = {"MARKETING", "SPAM", "NOISE", "PROMOTION"}
TRASH_CONFIDENCE = 0.90

# ProofRail/Action selectivity (LOCKED decision: migration_artifacts/09_ProofRail_Decisions_LOCKED.md
# item 2 -- "Fix code to be selective — do not keep a deliberate blanket"). These three classes are
# the only ones where the upstream classifier is plausibly UNSURE which bucket a message belongs in;
# Action means "a human needs to look at this," not "this happened to land in one of these classes."
# It is now gated on the confidence the classifier actually reports -- never a default. A confident
# call in one of these classes is routed and filed exactly like any other resolved class
# (ProofRail/Processed), same treatment as APPROVAL/LENDER_DOC/LIEN_WAIVER/INSPECTION above.
ACTION_ELIGIBLE_CLASSES = {"DRAW_SHEET", "VENDOR_INQUIRY", "LENDER_CORRESPONDENCE"}
ACTION_CONFIDENCE_THRESHOLD = 0.75  # below this, the classifier itself is unsure -> flag for a human


@dataclass
class Facts:
    classification: str
    confidence: float = 1.0
    has_attachment: bool = False
    attachment_filed: bool = False          # True if no attachment, or attachment saved+filed
    audit_logged: bool = False              # the required audit event was written
    exception_recorded: bool = False        # for BANK_NOTICE / FAIL invoice
    is_business_thread: bool = True
    has_pending_action: bool = False
    invoiceproof_verdict: str | None = None  # PASS | FLAG | FAIL | None


@dataclass
class Disposition:
    final_labels: list[str] = field(default_factory=list)
    remove_inbox: bool = False
    trash: bool = False
    stays_in_inbox_reason: str | None = None
    reason: str = ""
    # NOTE: there is deliberately no `permanent_delete` field. This system cannot express it.


def _target_label(f: Facts) -> str:
    if f.classification == "INVOICE" and f.invoiceproof_verdict == "FAIL":
        return "ProofRail/Quarantined"
    if f.classification in ACTION_ELIGIBLE_CLASSES:
        return ("ProofRail/Action" if f.confidence < ACTION_CONFIDENCE_THRESHOLD
                else "ProofRail/Processed")
    return LABEL_FOR.get(f.classification, "ProofRail/Archive")


def decide_disposition(f: Facts) -> Disposition:
    label = _target_label(f)
    # STV_LABELS_V2=1 -> emit STV/* labels via stv_label_map instead; unset/off = unchanged
    # legacy ProofRail/* behavior (identity passthrough). See scripts/stv_label_map.py.
    d = Disposition(final_labels=stv_label_map.maybe_translate([label]))

    # --- Trash path (marketing/spam only, all conditions must hold; else fail-safe to archive) ---
    if f.classification in TRASHABLE_CLASSES:
        safe_to_trash = (
            not f.has_attachment
            and not f.is_business_thread
            and not f.has_pending_action
            and f.confidence >= TRASH_CONFIDENCE
            and f.audit_logged
        )
        if safe_to_trash:
            d.trash = True
            d.remove_inbox = True  # trash implies leaving the inbox
            d.final_labels = []    # trashed messages carry no workflow label
            d.reason = "high-confidence no-value marketing/spam -> Gmail Trash (recoverable)"
            return d
        # any doubt -> archive, do NOT trash
        d.reason = "marketing/spam but trash conditions not fully met -> archive, not trash"
        # fall through to archive eligibility below

    # --- Archive (remove INBOX) eligibility ---
    if not f.audit_logged:
        d.remove_inbox = False
        d.stays_in_inbox_reason = "no audit event yet"
        d.reason = d.reason or "not logged -> stays in Inbox"
        return d

    if f.has_attachment and not f.attachment_filed:
        d.remove_inbox = False
        d.stays_in_inbox_reason = "attachment not saved+filed"
        d.reason = "attachment not filed -> stays in Inbox until filed"
        return d

    if f.classification == "BANK_NOTICE" and not f.exception_recorded:
        d.remove_inbox = False
        d.stays_in_inbox_reason = "bank-change exception not yet recorded"
        d.reason = "bank notice held in Inbox until risk exception is durable"
        return d

    if f.classification == "INVOICE" and f.invoiceproof_verdict == "FAIL" and not f.exception_recorded:
        d.remove_inbox = False
        d.stays_in_inbox_reason = "FAIL invoice exception not yet recorded"
        d.reason = "quarantine exception not durable -> stays in Inbox"
        return d

    # routed + logged + (filed or no attachment) + (exception where required) -> archive
    d.remove_inbox = True
    d.reason = d.reason or f"routed durably -> remove INBOX, home = {label}"
    return d


def enact(gc, msg_id: str, d: Disposition, *, live: bool = False, audit_fn=None) -> dict:
    """Apply the decision via the Gmail client. Default DRY-RUN (touches nothing)."""
    plan = {"msg_id": msg_id, "remove_inbox": d.remove_inbox, "trash": d.trash,
            "labels": d.final_labels, "reason": d.reason,
            "stays_in_inbox_reason": d.stays_in_inbox_reason}
    if not live:
        plan["mode"] = "DRY-RUN"
        return plan
    plan["mode"] = "LIVE"
    if d.trash:
        gc.trash(msg_id)
    elif d.remove_inbox:
        gc.remove_inbox(msg_id, add_labels=d.final_labels)
    elif d.final_labels:
        gc.modify(msg_id, add=d.final_labels)  # label only, stays in inbox
    if audit_fn:
        audit_fn(msg_id, d)
    return plan
