"""qbo_token_refresh.py — refresh QBO sandbox access tokens for Realm A and Realm B.

Usage:
    python scripts/qbo_token_refresh.py [--realm A|B]

Prints token STATUS only. Never prints token values (safety contract in qbo_common).
Persists Intuit's rotated refresh tokens back to .env automatically.
"""
import sys

from qbo_common import Realm, load_env


def main():
    env = load_env()
    keys = ["A", "B"]
    if "--realm" in sys.argv:
        keys = [sys.argv[sys.argv.index("--realm") + 1].upper()]
    for key in keys:
        realm = Realm(key, env)
        try:
            realm._refresh_access_token()
            ok, name = realm.assert_company()
            print(f"{realm.label}: token refreshed OK — company '{name}' "
                  f"({'matches expected' if ok else 'NAME MISMATCH'})")
        except Exception as e:  # noqa: BLE001 — report and continue to other realm
            print(f"{realm.label}: token refresh FAILED — {e}")
            continue


if __name__ == "__main__":
    main()
