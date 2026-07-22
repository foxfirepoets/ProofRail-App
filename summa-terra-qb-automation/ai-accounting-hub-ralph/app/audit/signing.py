"""Optional Ed25519 signing of the AIVS chain head.

Signing is OFF by default (the SHA-256 hash chain is itself tamper-evident,
AIVS section 5). When enabled, the private key is generated locally and written
with ``0600`` permissions. Reads ``AIVS_SIGNING_ENABLED`` / ``AIVS_SIGNING_KEY_PATH``
straight from the environment (these live in .env.example) to avoid editing the
shared ``app.config`` module.
"""
from __future__ import annotations

import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

DEFAULT_KEY_PATH = "./keys/aivs_ed25519.key"


def signing_enabled() -> bool:
    return os.environ.get("AIVS_SIGNING_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def key_path() -> Path:
    return Path(os.environ.get("AIVS_SIGNING_KEY_PATH", DEFAULT_KEY_PATH))


def _write_private_key(path: Path, key: Ed25519PrivateKey) -> None:
    raw = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    # Create with 0600 from the start; chmod afterwards covers pre-existing files.
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, raw)
    finally:
        os.close(fd)
    try:
        os.chmod(str(path), 0o600)
    except OSError:
        # POSIX perms are advisory on some filesystems (e.g. Windows); best effort.
        pass


def load_or_create_key(path: Path | None = None) -> Ed25519PrivateKey:
    target = path or key_path()
    if target.exists():
        data = target.read_bytes()
        loaded = serialization.load_pem_private_key(data, password=None)
        if not isinstance(loaded, Ed25519PrivateKey):
            raise TypeError("AIVS signing key is not an Ed25519 private key")
        return loaded
    key = Ed25519PrivateKey.generate()
    _write_private_key(target, key)
    return key


def sign_head(head_hash: str, path: Path | None = None) -> str:
    """Sign the chain head hash. Returns a hex Ed25519 signature."""
    key = load_or_create_key(path)
    return key.sign(head_hash.encode("utf-8")).hex()


def verify_head(head_hash: str, signature_hex: str, public_key: Ed25519PublicKey) -> bool:
    from cryptography.exceptions import InvalidSignature

    try:
        public_key.verify(bytes.fromhex(signature_hex), head_hash.encode("utf-8"))
        return True
    except (InvalidSignature, ValueError):
        return False


def maybe_sign_head(head_hash: str) -> str | None:
    """Sign only when signing is enabled; otherwise return ``None``."""
    if not signing_enabled():
        return None
    return sign_head(head_hash)
