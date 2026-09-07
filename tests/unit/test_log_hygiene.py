"""Log-hygiene guard test (spec 019, Foundational).

No logger call in the runtime path may format a credential: bearer tokens,
API keys, passwords, or full authorization header values. Safe identifiers
(chat_id, user_id, model_id, assistant ids) are allowed.
"""

import re
from pathlib import Path

# Credential identifiers that must never appear inside a logger.* call.
_FORBIDDEN = (
    "bearer",
    "authorization",
    "api_key",
    "owui_api_key",
    "password",
    "user_password_secret",
    "tools_key",
    "tools-key",
    "x-subagent-tools-key",
    "secret",
)

# Identifiers that merely contain a forbidden substring but are safe.
_ALLOWED_SUBSTRINGS = (
    "user_id",
    "chat_id",
    "model_id",
    "assistant_id",
    "message_id",
    "client_phone",
)


def _logger_calls(source: str) -> list:
    calls = []
    for match in re.finditer(r"logger\.(debug|info|warning|error|critical)\(", source):
        depth = 1
        i = match.end()
        while i < len(source) and depth > 0:
            if source[i] == "(":
                depth += 1
            elif source[i] == ")":
                depth -= 1
            i += 1
        calls.append(source[match.start() : i])
    return calls


def _is_safe(call: str) -> bool:
    lowered = call.lower()
    for token in _FORBIDDEN:
        idx = 0
        while True:
            idx = lowered.find(token, idx)
            if idx == -1:
                break
            # Allow the token only when it sits inside a known-safe identifier.
            context = lowered[max(0, idx - 20) : idx + len(token) + 20]
            if not any(safe in context for safe in _ALLOWED_SUBSTRINGS):
                return False
            idx += len(token)
    return True


def test_no_credential_in_runtime_logs():
    """No logger call in api.py/src formats a credential value."""
    root = Path(__file__).resolve().parent.parent.parent
    targets = [root / "api.py", *sorted((root / "src").rglob("*.py"))]
    assert targets, "no runtime sources found to audit"
    offenders = []
    for path in targets:
        for call in _logger_calls(path.read_text(encoding="utf-8")):
            if not _is_safe(call):
                offenders.append(f"{path.name}: {call[:120]}")
    assert not offenders, "credential leak in logs:\n" + "\n".join(offenders)
