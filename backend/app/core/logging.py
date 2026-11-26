from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

from app.core.config import settings

REDACT_KEYS = {
    "password",
    "api_key",
    "apiKey",
    "secret",
    "token",
    "authorization",
    "passphrase",
    "refresh_token",
    "access_token",
    "mfa_secret",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update({k: ("[redacted]" if k in REDACT_KEYS else v) for k, v in extra.items()})
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
