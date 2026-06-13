#!/usr/bin/env python3
"""Minimal stdio MCP server: read an OVERSIZED saved get_thread result, scoped.

The sandboxed email-event-extractor reader can only call `get_thread`. For large
emails (lots of HTML/tracking links) the result overflows the tool-output cap, so
the harness saves it to a file under the session's `tool-results/` dir and returns
only the path. The reader has no file tool to recover it.

This server exposes ONE tool, `read_email_overflow(path)`, that the reader can use
in that case. It is deliberately narrow:

- **Path-guarded.** It only reads a file whose resolved path is under a
  `tool-results/` directory AND whose name looks like a saved `get_thread` result
  (`*get_thread*.txt`). Anything else — a credentials file, an arbitrary path, a
  `..` traversal — is refused. So even a prompt-injected reader cannot use it to
  read `~/.config/caltitude/nextcloud.env` or any other file.
- **Body-only + compacted.** It parses the saved JSON, returns each message's
  plaintext body (falling back to HTML stripped to text), with URLs removed and
  whitespace collapsed, capped so the output itself never overflows.

Pure stdlib; runs on `python3` (no network, no deps). Launched via
`scripts/run-overflow-reader.sh` from the plugin `.mcp.json`.
"""

from __future__ import annotations

import json
import os
import re
import sys

TOOL_NAME = "read_email_overflow"
# Keep well under the tool-output token cap even for dense/CJK text (~1 token/char
# worst case): our own result must not re-overflow the cap this tool exists to dodge.
MAX_OUTPUT_CHARS = 24000
_URL = re.compile(r"https?://\S+")
_TAG = re.compile(r"<[^>]+>")
_WS_RUN = re.compile(r"[ \t]{2,}")
_NL_RUN = re.compile(r"\n{3,}")


# --- security: which files may this tool read -------------------------------

def is_allowed_path(path: str) -> bool:
    """True only for a saved get_thread overflow file under a tool-results dir.

    Uses the real (symlink/.. resolved) path so traversal can't escape the rule.
    """
    if not isinstance(path, str) or not path:
        return False
    real = os.path.realpath(path)
    parts = real.split(os.sep)
    if "tool-results" not in parts:
        return False
    base = os.path.basename(real)
    if not base.endswith(".txt") or "get_thread" not in base:
        return False
    return os.path.isfile(real)


# --- body extraction + compaction -------------------------------------------

def _strip(text: str) -> str:
    text = _URL.sub("", text)              # drop URLs / tracking links
    text = _WS_RUN.sub(" ", text)           # collapse runs of spaces/tabs
    text = _NL_RUN.sub("\n\n", text)        # collapse blank-line runs
    return text.strip()


def _message_text(msg: dict) -> str:
    # Prefer the plaintext body; fall back to HTML stripped to text. Coerce to str
    # defensively in case a field arrives as a non-string.
    body = str(msg.get("plaintextBody") or msg.get("plaintext_body") or "")
    if not body.strip():
        html = str(msg.get("htmlBody") or msg.get("html_body") or "")
        body = _TAG.sub(" ", html)
    header = " | ".join(
        f"{k}: {msg.get(k)}" for k in ("subject", "sender", "date") if msg.get(k)
    )
    return (f"[{header}]\n" if header else "") + _strip(body)


def extract_body(saved_path: str) -> str:
    """Read the saved get_thread JSON and return compacted plaintext (capped)."""
    with open(saved_path, encoding="utf-8", errors="replace") as fh:
        data = json.load(fh)
    msgs = data.get("messages") if isinstance(data, dict) else None
    if not isinstance(msgs, list) or not msgs:
        raise ValueError("saved result has no messages")
    chunks = [_message_text(m) for m in msgs if isinstance(m, dict)]
    out = "\n\n----- message -----\n\n".join(c for c in chunks if c)
    if len(out) > MAX_OUTPUT_CHARS:
        out = out[:MAX_OUTPUT_CHARS] + "\n\n[...truncated...]"
    return out


# --- minimal MCP stdio server -----------------------------------------------

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Absolute path of the saved get_thread overflow file "
            "(the path get_thread returned when its result was too large).",
        }
    },
    "required": ["path"],
}
TOOL_DESC = (
    "Read the plaintext body of an email whose get_thread result was too large and "
    "was saved to a file. Pass the saved file path that get_thread returned. Only "
    "reads saved get_thread results under a tool-results directory — refuses any "
    "other path. Returns the message bodies (HTML stripped, compacted)."
)


def _result(id_, result):
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _error(id_, code, message):
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def handle(req: dict):
    """Return a response dict, or None for notifications (no reply)."""
    method = req.get("method")
    id_ = req.get("id")
    if method == "initialize":
        proto = (req.get("params") or {}).get("protocolVersion", "2025-06-18")
        return _result(id_, {
            "protocolVersion": proto,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "caltitude-overflow-reader", "version": "1.0.0"},
        })
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return _result(id_, {})
    if method == "tools/list":
        return _result(id_, {"tools": [{
            "name": TOOL_NAME, "description": TOOL_DESC, "inputSchema": INPUT_SCHEMA,
        }]})
    if method == "tools/call":
        params = req.get("params") or {}
        if params.get("name") != TOOL_NAME:
            return _error(id_, -32602, f"unknown tool: {params.get('name')}")
        path = (params.get("arguments") or {}).get("path", "")
        try:
            if not is_allowed_path(path):
                text = ("REFUSED: this tool only reads saved get_thread overflow "
                        "files under a tool-results directory.")
                is_err = True
            else:
                text = extract_body(os.path.realpath(path))
                is_err = False
        except Exception as exc:  # noqa: BLE001 - report any read/parse failure
            text, is_err = f"ERROR: {exc}", True
        return _result(id_, {"content": [{"type": "text", "text": text}],
                             "isError": is_err})
    if id_ is not None:
        return _error(id_, -32601, f"method not found: {method}")
    return None


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            continue
        resp = handle(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
