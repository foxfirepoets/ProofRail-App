"""Tests for OPTIONAL Ed25519 signing of the chain head (default OFF)."""
from __future__ import annotations

import os
import stat

from app.audit import signing
from app.audit.signing import (
    load_or_create_key,
    maybe_sign_head,
    sign_head,
    signing_enabled,
    verify_head,
)

HEAD = "a" * 64


def test_signing_off_by_default(monkeypatch) -> None:
    monkeypatch.delenv("AIVS_SIGNING_ENABLED", raising=False)
    assert signing_enabled() is False
    assert maybe_sign_head(HEAD) is None


def test_signing_enabled_flag(monkeypatch) -> None:
    monkeypatch.setenv("AIVS_SIGNING_ENABLED", "true")
    assert signing_enabled() is True


def test_key_generated_and_signature_verifies(tmp_path) -> None:
    key_file = tmp_path / "keys" / "aivs.key"
    key = load_or_create_key(key_file)
    assert key_file.exists()
    sig = sign_head(HEAD, key_file)
    assert verify_head(HEAD, sig, key.public_key()) is True
    assert verify_head("b" * 64, sig, key.public_key()) is False


def test_key_written_with_0600(tmp_path) -> None:
    key_file = tmp_path / "k.key"
    load_or_create_key(key_file)
    mode = stat.S_IMODE(os.stat(key_file).st_mode)
    # On POSIX this is exactly 0600; on Windows perms are advisory, so only
    # assert the owner can read/write and (where enforced) others cannot.
    assert mode & stat.S_IRUSR
    if os.name == "posix":
        assert mode == 0o600


def test_maybe_sign_when_enabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AIVS_SIGNING_ENABLED", "true")
    monkeypatch.setenv("AIVS_SIGNING_KEY_PATH", str(tmp_path / "aivs.key"))
    sig = maybe_sign_head(HEAD)
    assert sig is not None
    key = load_or_create_key(signing.key_path())
    assert verify_head(HEAD, sig, key.public_key()) is True
