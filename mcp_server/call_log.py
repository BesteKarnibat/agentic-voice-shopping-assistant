"""Tool-call log: one JSON line per call (request, response or error) in data/logs/tool_calls.jsonl.

Covers both tools. The ProofAgent failure analysis reads this file to separate tool failures from
routing and answer failures. Logging never breaks a tool call.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone

from config.paths import TOOL_CALLS_LOG

log = logging.getLogger("mcp-server")
_lock = threading.Lock()


def log_call(tool: str, arguments: dict, response: dict | None, error: str | None, duration_ms: int) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "request": arguments,
        "ok": error is None,
        "response": response,
        "error": error,
        "duration_ms": duration_ms,
    }
    try:
        with _lock:
            TOOL_CALLS_LOG.parent.mkdir(parents=True, exist_ok=True)
            with TOOL_CALLS_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:  # noqa: BLE001
        log.exception("could not write the tool-call log")
