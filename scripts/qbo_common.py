"""qbo_common.py — shared QBO SANDBOX API layer for the Summa Terra test build.

SAFETY CONTRACT (non-negotiable, enforced in code):
  * SANDBOX ONLY. Hard-fails unless QB_ENV=sandbox and the base URL host is
    sandbox-quickbooks.api.intuit.com. There is no production mode.
  * DRY RUN by default. Writes happen only when --execute-sandbox is passed.
  * NO DELETES. This module exposes no delete/void operation.
  * NO SECRETS in output. Tokens/secrets are never printed or logged; every
    audit line passes through redact().
  * EVERY WRITE IS AUDIT-LOGGED to logs/qbo_seed_YYYYMMDD.jsonl before and
    after the API call, with the deterministic RequestId used.

Realm map (never mix):
  Realm A = partnership/projects  -> QB_PROJECT_REALM_ID ("Advanced Sandbox Company US 0e8d")
  Realm B = parent/corporate      -> QB_PARENT_REALM_ID  ("Advanced Sandbox Company US ee68")
"""

import base64
import csv
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT, ".env")
TOKEN_CACHE = os.path.join(ROOT, ".qbo_tokens.json")
LOG_DIR = os.path.join(ROOT, "logs")
SRC_DIR = os.path.join(ROOT, "qbo Source Files")

OAUTH_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
SANDBOX_HOST = "sandbox-quickbooks.api.intuit.com"
DEFAULT_MINORVERSION = "75"
WRITE_THROTTLE_SECONDS = 0.25  # ~240 writes/min, well under Intuit's per-realm limit

# ---------------------------------------------------------------- env / guards

def load_env(path=ENV_PATH):
    """Parse .env into a dict. Later duplicate keys win. Values never printed."""
    env = {}
    if not os.path.exists(path):
        sys.exit("FATAL: .env not found at project root. Copy .env.example and fill secrets.")
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def guard_sandbox(env):
    """Hard stop unless this is unambiguously the Intuit sandbox. No production mode exists."""
    base = env.get("QB_BASE_URL", "")
    host = urllib.parse.urlparse(base).netloc
    if env.get("QB_ENV") != "sandbox" or host != SANDBOX_HOST:
        sys.exit(
            "FATAL: sandbox guard failed. QB_ENV must be 'sandbox' and QB_BASE_URL host must be "
            f"'{SANDBOX_HOST}'. This tooling has no production mode and never will."
        )
    return base.rstrip("/")


def resolve_execute(argv=None):
    """Writes are enabled ONLY by the --execute-sandbox flag. Env DRY_RUN cannot enable writes."""
    argv = sys.argv if argv is None else argv
    return "--execute-sandbox" in argv


REALM_DEFS = {
    "A": {
        "label": "Realm A (partnership/projects)",
        "id_key": "QB_PROJECT_REALM_ID",
        "refresh_key": "QB_PROJECT_REFRESH_TOKEN",
        "expected_name_key": "QB_PROJECT_NAME",
        "expected_name_default": "Advanced Sandbox Company US 0e8d",
    },
    "B": {
        "label": "Realm B (parent/corporate)",
        "id_key": "QB_PARENT_REALM_ID",
        "refresh_key": "QB_PARENT_REFRESH_TOKEN",
        "expected_name_key": "QB_PARENT_NAME",
        "expected_name_default": "Advanced Sandbox Company US ee68",
    },
}

# ---------------------------------------------------------------- redaction / audit

_SECRET_VALUES = set()


def _register_secret(value):
    if value and len(value) >= 8:
        _SECRET_VALUES.add(value)


def redact(text):
    """Strip every known secret value and anything token-shaped from a string."""
    if not isinstance(text, str):
        text = json.dumps(text, default=str)
    for s in _SECRET_VALUES:
        text = text.replace(s, "[REDACTED]")
    text = re.sub(r"(Bearer\s+)[A-Za-z0-9._\-]+", r"\1[REDACTED]", text)
    text = re.sub(r"(refresh_token\"?\s*[:=]\s*\"?)[A-Za-z0-9._\-]+", r"\1[REDACTED]", text)
    text = re.sub(r"(access_token\"?\s*[:=]\s*\"?)[A-Za-z0-9._\-]+", r"\1[REDACTED]", text)
    text = re.sub(r"(client_secret\"?\s*[:=]\s*\"?)[A-Za-z0-9._\-]+", r"\1[REDACTED]", text)
    return text


def audit(event):
    """Append one redacted JSONL event to logs/qbo_seed_YYYYMMDD.jsonl. Append-only, never rewritten."""
    os.makedirs(LOG_DIR, exist_ok=True)
    event = dict(event)
    event.setdefault("ts", datetime.now(timezone.utc).isoformat())
    line = redact(json.dumps(event, ensure_ascii=False, default=str))
    path = os.path.join(LOG_DIR, f"qbo_seed_{datetime.now(timezone.utc):%Y%m%d}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------- OAuth token handling

def _load_token_cache():
    if os.path.exists(TOKEN_CACHE):
        try:
            with open(TOKEN_CACHE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_token_cache(cache):
    with open(TOKEN_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f)


def _persist_rotated_refresh_token(env_key, new_token):
    """Intuit rotates refresh tokens on every refresh; write the new one back to .env."""
    with open(ENV_PATH, encoding="utf-8-sig") as f:
        lines = f.readlines()
    out, replaced = [], False
    for line in lines:
        if line.strip().startswith(env_key + "="):
            out.append(f"{env_key}={new_token}\n")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{env_key}={new_token}\n")
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(out)


class QboError(Exception):
    def __init__(self, status, body):
        self.status = status
        self.body = body
        super().__init__(f"QBO HTTP {status}: {redact(body)[:800]}")


class Realm:
    """One sandbox realm connection with token refresh, throttled writes, and audit logging."""

    def __init__(self, key, env):
        if key not in REALM_DEFS:
            sys.exit(f"FATAL: unknown realm '{key}' (use A or B)")
        d = REALM_DEFS[key]
        self.key = key
        self.label = d["label"]
        self.base = guard_sandbox(env)
        self.realm_id = env.get(d["id_key"], "")
        self.refresh_env_key = d["refresh_key"]
        self.expected_name = env.get(d["expected_name_key"], d["expected_name_default"])
        self.client_id = env.get("QB_CLIENT_ID", "")
        self.client_secret = env.get("QB_CLIENT_SECRET", "")
        self.minorversion = env.get("QBO_MINORVERSION") or DEFAULT_MINORVERSION
        self._refresh_token = env.get(d["refresh_key"], "")
        self._access_token = None
        self._access_expires = 0
        for v in (self.client_secret, self._refresh_token):
            _register_secret(v)
        if not self.realm_id or not self.realm_id.isdigit():
            sys.exit(f"FATAL: {d['id_key']} missing/invalid in .env")
        if not (self.client_id and self.client_secret and self._refresh_token):
            sys.exit(f"FATAL: QB_CLIENT_ID / QB_CLIENT_SECRET / {d['refresh_key']} must be set in .env")

    # ---- tokens
    def _refresh_access_token(self):
        cache = _load_token_cache()
        entry = cache.get(self.realm_id, {})
        if entry.get("refresh_token"):
            self._refresh_token = entry["refresh_token"]
            _register_secret(self._refresh_token)
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        data = urllib.parse.urlencode(
            {"grant_type": "refresh_token", "refresh_token": self._refresh_token}
        ).encode()
        req = urllib.request.Request(
            OAUTH_TOKEN_URL,
            data=data,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                tok = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            audit({"event": "token_refresh_failed", "realm": self.key, "status": e.code})
            raise QboError(e.code, f"token refresh failed for {self.label}: {body}")
        self._access_token = tok["access_token"]
        self._access_expires = time.time() + int(tok.get("expires_in", 3600)) - 120
        _register_secret(self._access_token)
        new_refresh = tok.get("refresh_token")
        if new_refresh and new_refresh != self._refresh_token:
            _register_secret(new_refresh)
            self._refresh_token = new_refresh
            _persist_rotated_refresh_token(self.refresh_env_key, new_refresh)
        cache[self.realm_id] = {
            "access_token": self._access_token,
            "expires_at": self._access_expires,
            "refresh_token": self._refresh_token,
        }
        _save_token_cache(cache)
        audit({"event": "token_refreshed", "realm": self.key, "realm_id": self.realm_id})

    def _token(self):
        if self._access_token and time.time() < self._access_expires:
            return self._access_token
        cache = _load_token_cache()
        entry = cache.get(self.realm_id, {})
        if entry.get("access_token") and time.time() < entry.get("expires_at", 0):
            self._access_token = entry["access_token"]
            self._access_expires = entry["expires_at"]
            _register_secret(self._access_token)
            return self._access_token
        self._refresh_access_token()
        return self._access_token

    # ---- HTTP core
    def _request(self, method, path, params=None, body=None, _retry=0):
        params = dict(params or {})
        params.setdefault("minorversion", self.minorversion)
        url = f"{self.base}/company/{self.realm_id}/{path.lstrip('/')}?{urllib.parse.urlencode(params)}"
        headers = {
            "Authorization": f"Bearer {self._token()}",
            "Accept": "application/json",
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            if e.code == 401 and _retry < 1:
                self._refresh_access_token()
                return self._request(method, path, params, body, _retry + 1)
            if e.code in (429, 500, 502, 503) and _retry < 5:
                wait = int(e.headers.get("Retry-After", 0) or 0) or min(2 ** (_retry + 1), 30)
                time.sleep(wait)
                return self._request(method, path, params, body, _retry + 1)
            raise QboError(e.code, raw)

    def get(self, path, params=None):
        return self._request("GET", path, params)

    def query(self, q):
        return self._request("GET", "query", {"query": q})

    def query_all(self, entity, where=""):
        """Fetch every row of an entity (paginated). Read-only."""
        rows, start = [], 1
        while True:
            q = f"SELECT * FROM {entity} {where} STARTPOSITION {start} MAXRESULTS 1000"
            resp = self.query(q).get("QueryResponse", {})
            batch = resp.get(entity, [])
            rows.extend(batch)
            if len(batch) < 1000:
                return rows
            start += 1000

    def company_info(self):
        return self.get(f"companyinfo/{self.realm_id}")["CompanyInfo"]

    def assert_company(self):
        """Read-only sanity check before any write: confirm we're talking to the expected sandbox."""
        info = self.company_info()
        name = info.get("CompanyName", "")
        ok = name == self.expected_name
        audit({"event": "company_check", "realm": self.key, "company_name": name, "matches_expected": ok})
        if not ok:
            print(f"  WARN: {self.label} CompanyName is '{name}' (expected '{self.expected_name}'). "
                  "Halting writes for this realm.", flush=True)
        return ok, name

    def create(self, entity, payload, natural_key):
        """POST create with a deterministic RequestId so an identical retry cannot double-create."""
        rid = hashlib.sha1(f"{self.realm_id}|{entity}|{natural_key}".encode()).hexdigest()[:36]
        audit({"event": "create_attempt", "realm": self.key, "entity": entity,
               "name": natural_key, "request_id": rid})
        try:
            resp = self._request("POST", entity.lower(), {"requestid": rid}, payload)
            obj = resp.get(entity, resp)
            audit({"event": "create_ok", "realm": self.key, "entity": entity,
                   "name": natural_key, "qbo_id": obj.get("Id"), "request_id": rid})
            time.sleep(WRITE_THROTTLE_SECONDS)
            return obj
        except QboError as e:
            audit({"event": "create_error", "realm": self.key, "entity": entity,
                   "name": natural_key, "status": e.status, "detail": redact(e.body)[:500],
                   "request_id": rid})
            time.sleep(WRITE_THROTTLE_SECONDS)
            raise


# ---------------------------------------------------------------- CSV + seed runner

def read_csv(filename):
    path = os.path.join(SRC_DIR, filename)
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f)]


def read_single_column_csv(filename):
    path = os.path.join(SRC_DIR, filename)
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = [r[0].strip() for r in csv.reader(f) if r and r[0].strip()]
    return rows[1:]  # drop header


def run_seed(realm, entity, plan, execute):
    """Execute (or print) a seed plan: list of dicts {name, exists, payload, key}.

    Returns summary {created, skipped, errors: [(name, msg)]}. Never deletes, never updates.
    """
    summary = {"realm": realm.key, "entity": entity, "created": 0, "skipped": 0, "errors": []}
    mode = "EXECUTE-SANDBOX" if execute else "DRY RUN"
    print(f"\n[{mode}] {realm.label} :: {entity} — {len(plan)} rows "
          f"({sum(1 for p in plan if p['exists'])} already exist)")
    if execute:
        ok, name = realm.assert_company()
        if not ok:
            summary["errors"].append(("__realm__", f"company name mismatch: {name}"))
            return summary
    for p in plan:
        if p["exists"]:
            summary["skipped"] += 1
            audit({"event": "exists_skip", "realm": realm.key, "entity": entity, "name": p["key"]})
            continue
        if not execute:
            print(f"  would create {entity}: {p['key']}")
            summary["created"] += 1  # counted as planned-create in dry run
            continue
        try:
            creator = p.get("create") or (lambda pp=p: realm.create(entity, pp["payload"], pp["key"]))
            obj = creator()
            p["qbo_id"] = obj.get("Id")
            summary["created"] += 1
            print(f"  created {entity}: {p['key']} (Id {obj.get('Id')})")
        except QboError as e:
            summary["errors"].append((p["key"], redact(e.body)[:300]))
            print(f"  ERROR {entity}: {p['key']} -> HTTP {e.status}")
    audit({"event": "seed_summary", **{k: v for k, v in summary.items() if k != "errors"},
           "error_count": len(summary["errors"]), "mode": mode})
    return summary


def print_summary_table(summaries):
    print("\n================ SEED SUMMARY ================")
    print(f"{'Realm':<7}{'Entity':<12}{'Created':>9}{'Skipped':>9}{'Errors':>8}")
    for s in summaries:
        print(f"{s['realm']:<7}{s['entity']:<12}{s['created']:>9}{s['skipped']:>9}{len(s['errors']):>8}")
    errs = [(s["realm"], s["entity"], n, m) for s in summaries for (n, m) in s["errors"]]
    if errs:
        print("\nFAILED ROWS:")
        for r, e, n, m in errs:
            print(f"  [{r}/{e}] {n}: {m}")
    return errs


# ---------------------------------------------------------------- account type maps

ACCOUNT_TYPE_MAP = {
    "Bank": "Bank",
    "Credit Card": "Credit Card",
    "Equity": "Equity",
    "Income": "Income",
    "Expenses": "Expense",
    "Fixed Assets": "Fixed Asset",
    "Long Term Liabilities": "Long Term Liability",
    "Other Current Assets": "Other Current Asset",
    "Other Current Liabilities": "Other Current Liability",
    "Cost of Goods Sold": "Cost of Goods Sold",
    "Other Income": "Other Income",
    "Other Expense": "Other Expense",
}

ACCOUNT_SUBTYPE_MAP = {
    "Checking": "Checking",
    "Credit Card": "CreditCard",
    "Partner Distributions": "PartnerDistributions",
    "Partner's Equity": "PartnersEquity",
    "Other Miscellaneous Service Cost": "OtherMiscellaneousServiceCost",
    "Accumulated Depreciation": "AccumulatedDepreciation",
    "Other fixed assets": "OtherFixedAssets",
    "Service/Fee Income": "ServiceFeeIncome",
    "Notes Payable": "NotesPayable",
    "Other Current Assets": "OtherCurrentAssets",
    "Other Current Liabilities": "OtherCurrentLiabilities",
    "Other Miscellaneous Income": "OtherMiscellaneousIncome",
    "Other Costs of Services - COS": "OtherCostsOfServiceCos",
}


def bootstrap(realm_key):
    """Standard script entry: env + guards + realm handle + execute flag."""
    env = load_env()
    realm = Realm(realm_key, env)
    execute = resolve_execute()
    return realm, execute
