"""banking_plaid.py — READ-ONLY Plaid banking connector for the Summa Terra pipeline.

Purpose (directive §20): give the autonomous accounting pipeline controlled, read-only access to
account metadata, balances, posted/pending transactions, and (where available) statements — for
reconciliation and "what is this transaction?" research. It CANNOT move money.

The safety is STRUCTURAL, not a prompt: this client only ever calls Plaid's read endpoints
(/accounts, /balance, /transactions, /item, /institutions, /statements). It defines NO method that
initiates a transfer/payment/payee/ACH/wire — Plaid's money-movement products (Transfer, Payment
Initiation) are simply never called and require separate product enablement Plaid gates anyway.

Env (from Ben Projects/.env): CLIENT_ID, SANDBOX_SECRET, PRODUCTION_SECRET.
Access tokens (one per linked bank login) are stored in .plaid_tokens.json (gitignored).

CLI:
    python scripts/banking_plaid.py --sandbox-selftest      # prove the read path end-to-end (no login)
    python scripts/banking_plaid.py --link                  # create a Link token for a real bank login
    python scripts/banking_plaid.py --accounts <item_name>  # list accounts for a linked bank
"""
from __future__ import annotations

import json
import os
import sys

import requests

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENV_CANDIDATES = [os.path.join(os.path.dirname(_REPO), ".env"),          # Ben Projects/.env (has Plaid)
                   os.path.join(_REPO, ".env")]
TOKENS_PATH = os.path.join(_REPO, ".plaid_tokens.json")
HOSTS = {"sandbox": "https://sandbox.plaid.com", "production": "https://production.plaid.com"}
# read-only product set — deliberately excludes transfer / payment_initiation
READ_PRODUCTS = ["transactions"]


def _parse_env(path):
    d = {}
    if os.path.exists(path):
        for ln in open(path, encoding="utf-8", errors="ignore"):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1); d[k.strip()] = v.strip().strip('"').strip("'")
    return d


def _load_creds():
    merged = {}
    for p in _ENV_CANDIDATES:
        for k, v in _parse_env(p).items():
            merged.setdefault(k, v)
    if not merged.get("CLIENT_ID"):
        raise RuntimeError("CLIENT_ID/SANDBOX_SECRET not found in Ben Projects/.env")
    return merged


def _mask(acct_num_or_mask: str | None) -> str | None:
    if not acct_num_or_mask:
        return acct_num_or_mask
    s = str(acct_num_or_mask)
    return "****" + s[-4:] if len(s) > 4 else s


class ReadOnlyPlaidClient:
    """Only read endpoints. No transfer/payment/payee/ACH/wire method exists on this class."""

    def __init__(self, environment: str = "sandbox"):
        creds = _load_creds()
        self.environment = environment
        self.host = HOSTS[environment]
        self.client_id = creds["CLIENT_ID"]
        self.secret = creds["SANDBOX_SECRET"] if environment == "sandbox" else creds["PRODUCTION_SECRET"]

    def _post(self, path: str, body: dict) -> dict:
        payload = {"client_id": self.client_id, "secret": self.secret, **body}
        r = requests.post(self.host + path, json=payload, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"Plaid {path} {r.status_code}: {r.text[:300]}")
        return r.json()

    # ---- Link (one-time bank login) ----
    def create_link_token(self, user_id: str = "stv-accounting") -> dict:
        return self._post("/link/token/create", {
            "user": {"client_user_id": user_id}, "client_name": "Summa Terra Accounting",
            "products": READ_PRODUCTS, "country_codes": ["US"], "language": "en"})

    def create_hosted_link_token(self, label: str) -> dict:
        """Hosted Link: Plaid hosts the login page + handles OAuth redirects (needed for UCCU).
        Transactions-only: UCCU does NOT support Plaid's Statements product (adding it makes Plaid
        report 'connectivity not supported' for UCCU), so statement PDFs come from HALO/manual, not
        Plaid. Returns {link_token, hosted_link_url}."""
        return self._post("/link/token/create", {
            "user": {"client_user_id": f"stv-{label}"}, "client_name": "Summa Terra Accounting",
            "products": ["transactions"], "country_codes": ["US"], "language": "en",
            "hosted_link": {}})

    def get_link_public_token(self, link_token: str) -> dict:
        """After the user finishes the hosted flow, retrieve the public_token + institution.
        Returns {public_token, institution_name} or {public_token: None} if not finished yet."""
        r = self._post("/link/token/get", {"link_token": link_token})
        for s in r.get("link_sessions", []):
            res = s.get("results", {}) or {}
            for it in res.get("item_add_results", []) or []:
                if it.get("public_token"):
                    inst = (it.get("institution") or {}).get("name")
                    return {"public_token": it["public_token"], "institution_name": inst}
        return {"public_token": None}

    def exchange_public_token(self, public_token: str) -> str:
        return self._post("/item/public_token/exchange", {"public_token": public_token})["access_token"]

    # ---- read-only data (the MCP tool contract) ----
    def get_connection_status(self, access_token: str) -> dict:
        item = self._post("/item/get", {"access_token": access_token})["item"]
        return {"item_id": item.get("item_id"), "institution_id": item.get("institution_id"),
                "products": item.get("products"), "error": item.get("error")}

    def list_accounts(self, access_token: str) -> list[dict]:
        accts = self._post("/accounts/get", {"access_token": access_token})["accounts"]
        return [{"account_id": a["account_id"], "name": a.get("name"),
                 "official_name": a.get("official_name"), "type": str(a.get("type")),
                 "subtype": str(a.get("subtype")), "last4": _mask(a.get("mask")),
                 "balances": a.get("balances")} for a in accts]

    def get_balances(self, access_token: str) -> list[dict]:
        accts = self._post("/accounts/balance/get", {"access_token": access_token})["accounts"]
        return [{"account_id": a["account_id"], "name": a.get("name"), "last4": _mask(a.get("mask")),
                 "current": a["balances"].get("current"), "available": a["balances"].get("available"),
                 "iso_currency": a["balances"].get("iso_currency_code")} for a in accts]

    def refresh_transactions(self, access_token: str) -> dict:
        """Ask Plaid to pull fresh transaction data from the institution now, instead of
        waiting for the next scheduled sync. Async: new transactions typically become
        available within a couple minutes, sometimes longer for slower institutions."""
        return self._post("/transactions/refresh", {"access_token": access_token})

    def search_transactions(self, access_token: str, start: str, end: str, count: int = 100) -> list[dict]:
        res = self._post("/transactions/get", {"access_token": access_token,
                        "start_date": start, "end_date": end, "options": {"count": count}})
        out = []
        for t in res.get("transactions", []):
            out.append({"transaction_id": t["transaction_id"], "date": t["date"],
                        "amount": t["amount"], "name": t.get("name"),
                        "merchant": t.get("merchant_name"), "pending": t.get("pending"),
                        "account_id": t.get("account_id"), "category": t.get("category")})
        return out

    def get_transaction(self, access_token: str, transaction_id: str, start: str, end: str) -> dict | None:
        for t in self.search_transactions(access_token, start, end, count=500):
            if t["transaction_id"] == transaction_id:
                return t
        return None

    def list_statements(self, access_token: str) -> dict:
        # Statements product has narrower coverage; fail soft rather than pretending.
        try:
            return self._post("/statements/list", {"access_token": access_token})
        except RuntimeError as e:
            return {"available": False, "reason": str(e)}


# ---- token store ----
def _load_tokens() -> dict:
    return json.load(open(TOKENS_PATH)) if os.path.exists(TOKENS_PATH) else {}


def _save_token(name: str, access_token: str, environment: str):
    toks = _load_tokens()
    toks[name] = {"access_token": access_token, "environment": environment}
    json.dump(toks, open(TOKENS_PATH, "w"), indent=2)


def sandbox_selftest():
    """Prove the full read path against Plaid sandbox — no human login required."""
    c = ReadOnlyPlaidClient("sandbox")
    # sandbox-only helper to mint a public_token for a test institution (First Platypus Bank)
    pub = c._post("/sandbox/public_token/create",
                  {"institution_id": "ins_109508", "initial_products": READ_PRODUCTS})["public_token"]
    access = c.exchange_public_token(pub)
    accounts = c.list_accounts(access)
    balances = c.get_balances(access)
    txns = c.search_transactions(access, "2024-01-01", "2026-12-31", count=5)
    status = c.get_connection_status(access)
    print(json.dumps({
        "environment": "sandbox", "connection": status,
        "accounts": [{"name": a["name"], "last4": a["last4"], "type": a["type"]} for a in accounts],
        "balances": [{"name": b["name"], "current": b["current"], "cur": b["iso_currency"]} for b in balances],
        "sample_transactions": [{"date": t["date"], "amount": t["amount"], "name": t["name"]} for t in txns[:5]],
        "write_methods_present": [m for m in dir(c) if any(w in m.lower()
                                   for w in ("transfer", "payment", "wire", "ach", "payee", "pay_"))],
    }, indent=2))


if __name__ == "__main__":
    if "--sandbox-selftest" in sys.argv:
        sandbox_selftest()
    elif "--link" in sys.argv:
        env = "production" if "--production" in sys.argv else "sandbox"
        print(json.dumps(ReadOnlyPlaidClient(env).create_link_token(), indent=2))
    elif "--accounts" in sys.argv:
        name = sys.argv[sys.argv.index("--accounts") + 1]
        tok = _load_tokens()[name]
        c = ReadOnlyPlaidClient(tok["environment"])
        print(json.dumps(c.list_accounts(tok["access_token"]), indent=2))
    else:
        print(__doc__)
