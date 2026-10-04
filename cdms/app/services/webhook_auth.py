"""Optional HMAC verification for inbound webhooks."""

from __future__ import annotations

import base64
import hashlib
import hmac


def compute_hmac_sha256_base64(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def verify_webhook_signature(
    body: bytes,
    secret: str | None,
    provided_header: str | None,
) -> bool:
    if not secret:
        return True
    if not provided_header:
        return False
    expected = compute_hmac_sha256_base64(body, secret)
    return hmac.compare_digest(expected, provided_header.strip())
