#!/usr/bin/env python3
"""Unit tests for scripts/overflow_reader.py — the scoped get_thread-overflow tool.

Covers the security path-guard, body extraction/compaction, and the minimal MCP
stdio handlers. Run: python3 evals/test_overflow_reader.py
"""

import importlib.util
import json
import os
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(_HERE, "..", "scripts", "overflow_reader.py")
_spec = importlib.util.spec_from_file_location("overflow_reader", _SCRIPT)
ov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ov)


def _saved(tmp, name, obj):
    """Write a fake saved get_thread JSON under a tool-results dir; return path."""
    d = os.path.join(tmp, "outputs", "sess", "tool-results")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)
    return p


THREAD = {
    "id": "abc",
    "messages": [{
        "date": "2026-06-09T02:34:17Z",
        "sender": "traveler@example.com",
        "subject": "Fwd: Your trip (SAF-CLE)",
        "plaintextBody": "add to calendar\n\n\n\nAA 6296  SAF 10:08 AM  see https://aa.com/track/abc123def\nDFW 1:01 PM",
        "htmlBody": "<html><body>ignored when plaintext present</body></html>",
    }],
}


class PathGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_allows_get_thread_result_under_tool_results(self):
        p = _saved(self.tmp, "mcp-67d2-get_thread-1781.txt", THREAD)
        self.assertTrue(ov.is_allowed_path(p))

    def test_refuses_credentials_file(self):
        creds = os.path.join(self.tmp, ".config", "caltitude")
        os.makedirs(creds, exist_ok=True)
        p = os.path.join(creds, "nextcloud.env")
        with open(p, "w") as _f:
            _f.write("NEXTCLOUD_PASSWORD=secret")
        self.assertFalse(ov.is_allowed_path(p))

    def test_refuses_non_get_thread_txt_in_tool_results(self):
        d = os.path.join(self.tmp, "tool-results")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "notes.txt")
        with open(p, "w") as _f:
            _f.write("x")
        self.assertFalse(ov.is_allowed_path(p))

    def test_refuses_traversal_out_of_tool_results(self):
        # A path that *mentions* tool-results but resolves elsewhere is rejected.
        secret = os.path.join(self.tmp, "secret.txt")
        with open(secret, "w") as _f:
            _f.write("x")
        sneaky = os.path.join(self.tmp, "tool-results", "..", "secret.txt")
        self.assertFalse(ov.is_allowed_path(sneaky))

    def test_refuses_missing_file(self):
        self.assertFalse(ov.is_allowed_path(os.path.join(self.tmp, "tool-results", "x-get_thread-1.txt")))

    def test_refuses_non_string(self):
        self.assertFalse(ov.is_allowed_path(None))
        self.assertFalse(ov.is_allowed_path(""))


class Extraction(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_extracts_plaintext_strips_urls_and_keeps_itinerary(self):
        p = _saved(self.tmp, "mcp-x-get_thread-1.txt", THREAD)
        out = ov.extract_body(p)
        self.assertIn("add to calendar", out)
        self.assertIn("AA 6296", out)
        self.assertIn("SAF", out)
        self.assertNotIn("http", out)            # URL stripped
        self.assertIn("traveler@example.com", out)  # header included
        self.assertNotIn("\n\n\n", out)           # blank-line runs collapsed

    def test_falls_back_to_html_when_no_plaintext(self):
        obj = {"messages": [{"subject": "t", "htmlBody": "<p>add to calendar</p><p>AA1 SFO JFK</p>"}]}
        p = _saved(self.tmp, "mcp-x-get_thread-2.txt", obj)
        out = ov.extract_body(p)
        self.assertIn("add to calendar", out)
        self.assertIn("AA1", out)
        self.assertNotIn("<p>", out)              # tags stripped

    def test_caps_output_length(self):
        big = {"messages": [{"subject": "t", "plaintextBody": "x " * 60000}]}
        p = _saved(self.tmp, "mcp-x-get_thread-3.txt", big)
        out = ov.extract_body(p)
        self.assertLessEqual(len(out), ov.MAX_OUTPUT_CHARS + 50)
        self.assertIn("truncated", out)

    def test_no_messages_raises(self):
        p = _saved(self.tmp, "mcp-x-get_thread-4.txt", {"id": "x", "messages": []})
        with self.assertRaises(ValueError):
            ov.extract_body(p)


class McpHandlers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_initialize_echoes_protocol_and_names_server(self):
        r = ov.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                       "params": {"protocolVersion": "2025-06-18"}})
        self.assertEqual(r["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("tools", r["result"]["capabilities"])
        self.assertEqual(r["result"]["serverInfo"]["name"], "caltitude-overflow-reader")

    def test_notifications_get_no_reply(self):
        self.assertIsNone(ov.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_tools_list_exposes_one_tool(self):
        r = ov.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = [t["name"] for t in r["result"]["tools"]]
        self.assertEqual(names, [ov.TOOL_NAME])

    def test_tools_call_reads_allowed_file(self):
        p = _saved(self.tmp, "mcp-x-get_thread-5.txt", THREAD)
        r = ov.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                       "params": {"name": ov.TOOL_NAME, "arguments": {"path": p}}})
        self.assertFalse(r["result"]["isError"])
        self.assertIn("AA 6296", r["result"]["content"][0]["text"])

    def test_tools_call_refuses_other_path(self):
        creds = os.path.join(self.tmp, "nextcloud.env")
        with open(creds, "w") as _f:
            _f.write("NEXTCLOUD_PASSWORD=secret")
        r = ov.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                       "params": {"name": ov.TOOL_NAME, "arguments": {"path": creds}}})
        self.assertTrue(r["result"]["isError"])
        self.assertIn("REFUSED", r["result"]["content"][0]["text"])
        self.assertNotIn("secret", r["result"]["content"][0]["text"])

    def test_unknown_tool_errors(self):
        r = ov.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                       "params": {"name": "nope", "arguments": {}}})
        self.assertIn("error", r)

    def test_unknown_method_errors_with_id(self):
        r = ov.handle({"jsonrpc": "2.0", "id": 5, "method": "bogus/method"})
        self.assertIn("error", r)


if __name__ == "__main__":
    unittest.main(verbosity=2)
