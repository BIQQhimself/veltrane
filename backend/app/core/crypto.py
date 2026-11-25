"""Envelope encryption for provider credentials.

A random 256-bit DEK encrypts each credential payload. The DEK is itself wrapped
with the process KEK (``VELTRANE_MASTER_ENCRYPTION_KEY``). Rotating the KEK only
requires re-wrapping DEKs, never re-encrypting payloads.

Every ciphertext is bound to an AAD string (``org:<id>|connection:<id>``) so a
row copied from one tenant to another fails to decrypt.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
from dataclasses import asdict, dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

NONCE_BYTES = 12
DEK_BYTES = 32


class DecryptionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Envelope:
    kek_version: int
    wrapped_dek: str
    dek_nonce: str
    nonce: str
    ciphertext: str

    def as_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> "Envelope":
        data = json.loads(raw)
        return cls(
            kek_version=int(data["kek_version"]),
            wrapped_dek=data["wrapped_dek"],
            dek_nonce=data["dek_nonce"],
            nonce=data["nonce"],
            ciphertext=data["ciphertext"],
        )


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"))


def _kek() -> AESGCM:
    return AESGCM(settings.ensure_master_key())


def _kek_aad(version: int) -> bytes:
    return f"veltrane-kek-v{version}".encode()


def encrypt_json(payload: dict, *, aad: str) -> Envelope:
    dek = secrets.token_bytes(DEK_BYTES)
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(dek).encrypt(nonce, json.dumps(payload).encode(), aad.encode())
    dek_nonce = os.urandom(NONCE_BYTES)
    wrapped = _kek().encrypt(
        dek_nonce, dek, _kek_aad(settings.kek_version) + b"|" + aad.encode()
    )
    return Envelope(
        kek_version=settings.kek_version,
        wrapped_dek=_b64(wrapped),
        dek_nonce=_b64(dek_nonce),
        nonce=_b64(nonce),
        ciphertext=_b64(ciphertext),
    )


def decrypt_json(envelope: Envelope, *, aad: str) -> dict:
    try:
        dek = _kek().decrypt(
            _unb64(envelope.dek_nonce),
            _unb64(envelope.wrapped_dek),
            _kek_aad(envelope.kek_version) + b"|" + aad.encode(),
        )
        plaintext = AESGCM(dek).decrypt(_unb64(envelope.nonce), _unb64(envelope.ciphertext), aad.encode())
    except (InvalidTag, ValueError) as exc:  # pragma: no cover - depends on key state
        raise DecryptionError("Credential payload could not be decrypted") from exc
    return json.loads(plaintext)


def generate_master_key_b64() -> str:
    """Utility used by tooling/tests to mint a master key."""
    return base64.b64encode(secrets.token_bytes(32)).decode()


def mask_secret(value: str | None, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep:
        return "•" * len(value)
    return "•" * max(4, len(value) - keep) + value[-keep:]
