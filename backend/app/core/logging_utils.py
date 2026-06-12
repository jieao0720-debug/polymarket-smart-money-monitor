"""Logging setup with secret redaction.

development-rules.md #2: signatures / API keys / passphrases / signed payloads must never
reach logs. A filter scrubs common secret-shaped keys and long hex signatures.
"""
from __future__ import annotations

import logging
import re

# key=value / "key": "value" pairs for sensitive names, plus long hex blobs (signatures).
_SENSITIVE_KEY_RE = re.compile(
    r"(?i)(\"?)(signature|secret|passphrase|api[_-]?key|private[_-]?key|mnemonic"
    r"|authorization|poly_signature|poly_passphrase|poly_api_key)"
    r"(\"?\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s,}\]]+)"
)
_LONG_HEX_RE = re.compile(r"0x[0-9a-fA-F]{96,}")


def redact(text: str) -> str:
    text = _SENSITIVE_KEY_RE.sub(
        lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}\"[REDACTED]\"", text)
    return _LONG_HEX_RE.sub("0x[REDACTED_HEX]", text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            redacted = redact(msg)
            if redacted != msg:
                record.msg = redacted
                record.args = ()
        except Exception:  # pragma: no cover - never break logging
            pass
        return True


def configure_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for handler in logging.getLogger().handlers:
        handler.addFilter(RedactingFilter())
