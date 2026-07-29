"""intake_preclassifier.py — ProofRail deterministic intake pre-classifier.

Folds the three keep-worthy pieces of the retired Gmail AccountingOS into ProofRail
(CONSOLIDATION_PROOFRAIL_ABSORBS_ACCOUNTINGOS.md):
  1. Prompt-injection scrub (before any LLM sees the body).
  2. BANK-CHANGE → P0 HARD STOP, checked BEFORE anything else — never reaches the LLM, fires a P0
     Spaces alert, requires out-of-band phone verification. Also BEC + legal-notice P0.
  3. Entity alias resolver (60+ aliases incl. the naming traps) → canonical entity + fee recipient.

This runs at the TOP of the inbox stage. It is deterministic and testable offline; the LLM only
handles what the rules can't resolve (requires_llm=True).
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stv_label_map  # noqa: E402  -- STV_LABELS_V2 flag-gated ProofRail/* -> STV/* translation

# ---------------- 1. injection guard ----------------
_INJECTION = [re.compile(p, re.IGNORECASE) for p in [
    r"ignore (previous|above|prior|all) instructions", r"you are (now|a|an)", r"act as (a|an|if)",
    r"system prompt", r"override (your|the) (instructions|rules|guidelines)",
    r"forget (everything|your|all)", r"new (role|instruction|task|objective)",
    r"<(system|assistant|human|user|prompt)>", r"\[INST\]", r"###\s*(instruction|system|prompt)",
    r"disregard (all|the|your)", r"instead (of|do|you should|respond)"]]


def strip_injection(text: str) -> tuple[str, bool]:
    detected = False
    for pat in _INJECTION:
        if pat.search(text or ""):
            detected = True
            text = pat.sub("[REDACTED]", text)
    return text, detected


# ---------------- 2. P0 pattern sets ----------------
BANK_CHANGE = ["routing number", "ach account", "new bank account", "new account number",
               "changed bank", "updated bank", "wire instructions have changed", "new wire instructions",
               "updated routing", "new ach", "bank account number", "new payment details", "email only"]
# Duplicate-payment risk — a "has this cleared / duplicate check" signal means a payment may be about
# to go out twice. Phrases trace to docs/MINED_VALUE_gmail_automation.md items 4 & 9 (Rock Creek water
# meter $8,428.34 two-check incident, "duplicate-payment guard" gap).
DUPLICATE_CHECK = ["check hasn't cleared", "check has not cleared", "not yet cleared",
                   "duplicate check", "duplicate payment", "two checks"]
BEC = ["urgent wire", "ceo fraud", "wire transfer urgently", "confidential wire", "keep this confidential"]
LEGAL = ["notice of default", "foreclosure", "lis pendens", "lawsuit", "demand letter", "default notice"]
NEWSLETTER = ["unsubscribe", "newsletter", "promotional", "email preferences", "no longer wish to receive"]
DRAW = ["draw package", "pay app", "g702", "g703", "aia application", "construction draw",
        "draw request", "draw #", "lien waivers", "cost certification", "arixa draw", "granite draw"]
UNUSUAL_DOMAINS = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "icloud.com"}

# ---------------- 3. entity alias map (naming traps preserved) ----------------
ENTITY_ALIASES = {
    "12sb": ("12SB, LLC", "UNCERTAIN"), "hunter's landing": ("12SB, LLC", "UNCERTAIN"),
    "hunters landing": ("12SB, LLC", "UNCERTAIN"), "407 12th st": ("12SB, LLC", "UNCERTAIN"),
    "hln": ("Hunter's Landing North LLC", "STV"), "hunter's landing north": ("Hunter's Landing North LLC", "STV"),
    "hle": ("Hunter's Landing East", "STV"),
    "ledges at moab": ("Ledges at Moab LLC", "Lykos Acquisitions, LLC"), "moab": ("Ledges at Moab LLC", "Lykos Acquisitions, LLC"),
    "madison park": ("Madison Park LLC", "Summa Terra Development Group, LLC"), "madison": ("Madison Park LLC", "Summa Terra Development Group, LLC"),
    "sunset village": ("Madison Park LLC", "Summa Terra Development Group, LLC"), "sunset rim": ("Madison Park LLC", "Summa Terra Development Group, LLC"),
    "union walk": ("Union Station LLC", "STV"), "union station": ("Union Station LLC", "STV"),
    "union": ("Union Station LLC", "STV"), "ln 86": ("Union Station LLC", "STV"), "granite ln 86": ("Union Station LLC", "STV"),
    "freeman ranch": ("Freeman Ranch LLC", "STV"), "vic partners": ("Vic Partners LLC", "STV"),
    "the vic": ("Vic Partners LLC", "STV"), "vic centre": ("Vic Partners LLC", "STV"),
    "ensign": ("Ensign Partners LLC", "STV"), "rm texas": ("RM Texas Partners LLC", "STV"),
    "rock creek": ("Rock Creek Acquisitions LLC", "UNCERTAIN"), "summa elite": ("Rock Creek Acquisitions LLC", "UNCERTAIN"),
    "quincy court": ("Quincy Court LLC", "STV"), "quincy partners": ("Quincy Court LLC", "STV"), "denton": ("Quincy Court LLC", "STV"),
    "elephant rock": ("Elephant Rock LLC", "STV"), "ventura landing": ("Ventura Landing LLC", "STV"), "ventura": ("Ventura Landing LLC", "STV"),
    "pecan crossing": ("Ventura Landing LLC", "STV"),  # confirmed alias (QB memo "EM wired to Capital Title for Pecan Crossing"), Ben 2026-07-16
    "carlo": ("Carlo @ Washington", "STV"), "hart city": ("Hart City", "STV"),
    "bcb townhomes": ("BCB Townhomes", "STV"), "bcb": ("BCB Townhomes", "STV"), "brigham city": ("BCB Townhomes", "STV"),
    "stve": ("STV Entitlement Services LLC", "N/A"), "stv": ("Summa Terra Ventures, LLC", "N/A"),
    "stdg": ("Summa Terra Development Group, LLC", "N/A"), "lykos": ("Lykos Acquisitions, LLC", "N/A"),
    "stv cm": ("STV CM, LLC", "N/A"),  # status UNCONFIRMED — never route a fee here
}
_STV_CM_BLOCKED = {"STV CM, LLC"}

# ---------------- 4. sender-based triage (ROUTING HINT ONLY — NOT a coding source) ----------------
# CRITICAL: SENDER_TO_ENTITY / SENDER_RULES are a CLASSIFICATION / ROUTING HINT only. They exist to
# break a tie on entity/workflow when the email CONTENT does not resolve one — nothing more.
#   * They MUST NOT override or short-circuit the bank-change P0 hard stop or the injection guard;
#     those still fire FIRST on content (they return before this map is ever consulted).
#   * They MUST NOT be used to CODE an invoice's QBO Location/Class. QBO coding follows
#     /proofrail-coding-rules (explicit project/address -> history -> vendor default -> flag), which
#     explicitly says "never infer entity from sender." That is why the sender map sets `entity`
#     (triage) but NEVER sets `fee_recipient` — a fee is never routed off the sender.
# Every binding below is traceable to docs/MINED_VALUE_gmail_automation.md (items 8, 10, 16, 18).
# Keys may be a full address or a bare domain; full-address match wins over domain.
SENDER_TO_ENTITY = {
    "granite.org": "Union Station LLC",              # item 10/16/18: BetzyT@granite.org -> Union Walk
    "betzyt@granite.org": "Union Station LLC",        # item 16: Betzy Taylor, Union Walk loan processor
    "eliteconstructionusa.com": "Rock Creek Acquisitions LLC",   # item 10: Elite Construction GC -> Rock Creek
    "lauren.w.farnsworth@gmail.com": "Madison Park LLC",         # item 10/16: Lauren Farnsworth (Phoenix Tide)
    "canyonviewcu.com": "12SB, LLC",                  # item 8/18: Canyon View CU = 12SB (NOT HLN) — confirmed
    # NOTE: arixacapital.com is intentionally OMITTED here — item 18 maps it to TWO entities
    # ([HLN, Madison Park]); ambiguous, so entity stays content-resolved. It gets a workflow-only
    # hint in SENDER_RULES below instead of an (unsafe, guessed) entity binding.
}

# sender -> (workflow, urgency) hint. Same triage-only rule: never a coding/fee source.
SENDER_RULES = {
    "rickscpas.com": ("Tax/Legal Review", "P2"),     # item 18: mricks@rickscpas.com -> TAX_WORKFLOW
    "arixacapital.com": ("Construction Draw", "P1"),  # item 18: draws@arixacapital.com lender draw
                                                      # (entity NOT set — ambiguous HLN/Madison, see note above)
}


def _sender_keys(sender: str) -> tuple[str, str]:
    """Return (full_address, domain) lowercased for lookups. Full-address match wins over domain."""
    s = (sender or "").strip().lower()
    domain = s.split("@")[-1] if "@" in s else s
    return s, domain


def resolve_sender_entity(sender: str) -> tuple[str | None, str]:
    """TRIAGE-ONLY sender->entity hint. Returns (canonical_entity, matched_key) or (None, "").
    Never a QBO coding/fee source (see /proofrail-coding-rules)."""
    if not sender:
        return None, ""
    full, domain = _sender_keys(sender)
    if full in SENDER_TO_ENTITY:
        return SENDER_TO_ENTITY[full], full
    if domain in SENDER_TO_ENTITY:
        return SENDER_TO_ENTITY[domain], domain
    return None, ""


def resolve_sender_workflow(sender: str) -> tuple[str | None, str | None]:
    """TRIAGE-ONLY sender->(workflow, urgency) hint. Returns (None, None) if unmapped."""
    if not sender:
        return None, None
    full, domain = _sender_keys(sender)
    if full in SENDER_RULES:
        return SENDER_RULES[full]
    if domain in SENDER_RULES:
        return SENDER_RULES[domain]
    return None, None


@dataclass
class Precheck:
    workflow: str = "Unknown"
    urgency: str = "P2"
    requires_p0: bool = False
    bank_change_risk: bool = False
    injection_detected: bool = False
    entity: str | None = None
    entity_source: str | None = None  # "content" | "sender:<key> (triage hint)" — provenance, not a coding source
    fee_recipient: str | None = None
    fee_blocked: bool = False
    requires_llm: bool = False
    labels: list = field(default_factory=list)
    notes: str = ""


def _has(text: str, pats) -> bool:
    t = text.lower()
    return any(p in t for p in pats)


def resolve_entity(text: str) -> tuple[str | None, str | None]:
    """Exact then fuzzy (rapidfuzz if available). Returns (canonical, fee_recipient) or (None,None)."""
    if not text:
        return None, None
    t = text.lower()
    # longest alias first so the most specific wins ("stv cm" beats "stv", "union walk" beats "union")
    for alias in sorted(ENTITY_ALIASES, key=len, reverse=True):
        if alias in t:
            return ENTITY_ALIASES[alias]
    try:
        from rapidfuzz import fuzz
        best, key = 0, None
        for alias in ENTITY_ALIASES:
            s = fuzz.partial_ratio(t, alias)
            if s > best:
                best, key = s, alias
        if best >= 90 and key:
            return ENTITY_ALIASES[key]
    except ImportError:
        pass
    return None, None


def preclassify(email: dict, notify: bool = False) -> Precheck:
    """email: {sender, subject, body}. notify=True fires a P0 Spaces alert on bank-change."""
    sender = (email.get("sender") or "").strip().lower()
    body, injected = strip_injection(email.get("body") or "")
    full = f"{email.get('subject','')} {body}".lower()
    domain = sender.split("@")[-1] if "@" in sender else ""
    r = Precheck(injection_detected=injected)

    # 2. BANK-CHANGE HARD STOP — before anything else, never to the LLM
    if _has(full, BANK_CHANGE):
        r.bank_change_risk = True
        r.requires_p0 = True
        r.urgency = "P0"
        r.workflow = "Bank Change Risk"
        r.labels = stv_label_map.maybe_translate(["ProofRail/Risk-BankChange"])
        r.notes = ("Bank-change request — P0. Verify by phone to the number on file; never update "
                   "from email." + (f" Unusual sender domain: {domain}." if domain in UNUSUAL_DOMAINS else ""))
        if notify:
            try:
                import sys, os as _os
                sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
                import notify_chat
                notify_chat.fire_p0(f"BANK-CHANGE RISK from {sender}: “{email.get('subject','')}”. "
                                    f"Do NOT update anything from email — verify by phone.")
            except Exception:
                pass
        return r

    # DUPLICATE-PAYMENT RISK — P0. Checked right after the bank-change hard stop and before any
    # routing: a "has this cleared / duplicate check" signal means a payment may go out twice.
    if _has(full, DUPLICATE_CHECK):
        r.requires_p0 = True
        r.urgency = "P0"
        r.workflow = "Duplicate Payment Risk"
        r.labels = stv_label_map.maybe_translate(["ProofRail/Risk-DuplicatePayment"])
        r.notes = ("Possible duplicate payment — P0. Confirm the original check/payment status "
                   "before issuing any new payment.")
        return r

    if _has(full, BEC) or _has(full, LEGAL):
        r.requires_p0 = True
        r.urgency = "P0"
        r.workflow = "BEC/Legal"
        r.requires_llm = True
        return r

    if _has(full, NEWSLETTER):
        r.workflow = "Newsletter/FYI"
        r.urgency = "P3"
        return r

    # entity resolution (used for coding + fee routing) — CONTENT first, per /proofrail-coding-rules
    r.entity, r.fee_recipient = resolve_entity(full)
    if r.entity:
        r.entity_source = "content"
    else:
        # TRIAGE FALLBACK ONLY: content named no entity — use the sender map as a routing hint.
        # This sets `entity` for triage/routing but deliberately leaves `fee_recipient` None: a fee
        # is NEVER routed off the sender, and QBO coding never infers entity from sender.
        se, key = resolve_sender_entity(sender)
        if se:
            r.entity = se
            r.entity_source = f"sender:{key} (triage hint — not a coding source)"
    if r.entity in _STV_CM_BLOCKED:
        r.fee_blocked = True  # STV CM LLC UNCONFIRMED — never route a fee here

    if _has(full, DRAW):
        r.workflow = "Construction Draw"
        r.urgency = "P1"
        # ProofRail/Action is a "needs human" signal, not a default for every keyword-matched draw
        # (LOCKED decision migration_artifacts/09_ProofRail_Decisions_LOCKED.md item 2; see
        # migration_artifacts/13_Action_Selectivity_Change.md). A draw whose entity resolved
        # confidently (content match above, or a sender-map triage hint) is already routed cleanly
        # and needs no flag. Only a draw with NO resolved entity is a real ambiguity -- a human has
        # to figure out which project/entity this draw belongs to before it can proceed.
        if not r.entity:
            r.labels = stv_label_map.maybe_translate(["ProofRail/Action"])
        return r

    # priority senders escalate
    if sender in {"mike@summaterraventures.com", "porter@summaterraventures.com"}:
        r.urgency = "P1"
        r.workflow = "Internal Payment Approval" if "approved" in full else "Payment Request"

    # sender WORKFLOW hint (triage only) — applied last. P0 stops already returned above, and this
    # only fills a still-"Unknown" workflow, so it can never override a content-derived classification.
    if r.workflow == "Unknown":
        sw, su = resolve_sender_workflow(sender)
        if sw:
            r.workflow, r.urgency = sw, su

    r.requires_llm = True  # anything unresolved goes to the cognition layer
    return r
