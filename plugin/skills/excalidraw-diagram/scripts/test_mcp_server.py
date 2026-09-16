# tested-by: REQ-EXCALIDRAW-852  # tested-by: ARCH-EXCALIDRAW-032
"""
Tests for mcp_server.py. Most call handle() with decoded messages, so the protocol
is checked without a process; one launches the real server to prove that stdout
carries nothing but JSON-RPC lines — the failure a direct call cannot see.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

import mcp_server

HERE = os.path.dirname(os.path.abspath(__file__))
GRAPH = {
    "name": "tiny",
    "direction": "LR",
    "seed": 3,
    "nodes": [{"id": "a", "label": "Client"}, {"id": "b", "label": "API"},
              {"id": "c", "label": "Store"}],
    "edges": [{"src": "a", "dst": "b"}, {"src": "b", "dst": "c"}],
}


def request(method, params=None, msg_id=1):
    """Answer one request through the server's handler."""
    message = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        message["params"] = params
    return mcp_server.handle(message)


def call(name, arguments):
    """Call a tool and return the tools/call result."""
    return request("tools/call", {"name": name, "arguments": arguments})["result"]


class TestProtocol(unittest.TestCase):
    """REQ-EXCALIDRAW-852: handshake, dispatch and argument errors."""

    def test_initialize_echoes_a_supported_version(self):  # verifies: REQ-EXCALIDRAW-852#CASE-1
        result = request("initialize", {"protocolVersion": "2024-11-05"})["result"]
        self.assertEqual(result["protocolVersion"], "2024-11-05")
        self.assertEqual(result["serverInfo"]["name"], "excalidraw-diagram")
        self.assertNotEqual(result["serverInfo"]["version"], "0.0.0")
        self.assertIn("tools", result["capabilities"])

    def test_initialize_offers_latest_otherwise(self):  # verifies: REQ-EXCALIDRAW-852#CASE-1
        result = request("initialize", {"protocolVersion": "1999-01-01"})["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")

    def test_notification_gets_no_response(self):  # verifies: REQ-EXCALIDRAW-852#CASE-1
        self.assertIsNone(mcp_server.handle(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_ping(self):  # verifies: REQ-EXCALIDRAW-852#CASE-1
        self.assertEqual(request("ping")["result"], {})

    def test_tools_list_names_the_four_tools(self):  # verifies: REQ-EXCALIDRAW-852#CASE-1
        tools = request("tools/list")["result"]["tools"]
        self.assertEqual(sorted(t["name"] for t in tools),
                         ["build_scene", "discover_repo", "graph_schema", "render_html"])
        for tool in tools:
            self.assertEqual(tool["inputSchema"]["type"], "object")
            self.assertFalse(tool["inputSchema"]["additionalProperties"])

    def test_unknown_method(self):  # verifies: REQ-EXCALIDRAW-852#CASE-1
        self.assertEqual(request("resources/list")["error"]["code"], -32601)

    def test_unknown_tool(self):  # verifies: REQ-EXCALIDRAW-852#CASE-1
        response = request("tools/call", {"name": "nope", "arguments": {}})
        self.assertEqual(response["error"]["code"], -32602)

    def test_missing_or_mistyped_argument(self):  # verifies: REQ-EXCALIDRAW-852#CASE-1
        missing = request("tools/call", {"name": "build_scene", "arguments": {"graph": {}}})
        self.assertEqual(missing["error"]["code"], -32602)
        wrong = request("tools/call", {"name": "render_html", "arguments": {"scene_path": 3}})
        self.assertEqual(wrong["error"]["code"], -32602)

    def test_unparseable_line(self):  # verifies: REQ-EXCALIDRAW-852#CASE-1
        response = mcp_server.handle_line("{not json")
        self.assertEqual(response["error"]["code"], -32700)
        self.assertIsNone(response["id"])


class TestTools(unittest.TestCase):
    """REQ-EXCALIDRAW-852: each tool reaches the builder and reports back."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_build_scene_writes_both_files(self):  # verifies: REQ-EXCALIDRAW-852#CASE-2  # verifies: ARCH-EXCALIDRAW-032#CASE-6
        result = call("build_scene", {"graph": GRAPH, "out_dir": self.tmp})
        self.assertFalse(result["isError"], result)
        for ext in (".excalidraw", ".html"):
            path = os.path.join(self.tmp, "tiny" + ext)
            self.assertTrue(os.path.isfile(path))
            self.assertIn(path, result["content"][0]["text"])

    def test_printed_warnings_join_the_result(self):  # verifies: REQ-EXCALIDRAW-852#CASE-2
        def noisy(_args):
            print("gate says out")
            print("gate says err", file=sys.stderr)
            return "done"
        saved = mcp_server.TOOLS["graph_schema"]
        mcp_server.TOOLS["graph_schema"] = saved[:2] + (noisy,)
        try:
            text = call("graph_schema", {})["content"][0]["text"]
        finally:
            mcp_server.TOOLS["graph_schema"] = saved
        self.assertIn("gate says out", text)
        self.assertIn("gate says err", text)

    def test_failing_build_is_a_tool_error(self):  # verifies: REQ-EXCALIDRAW-852#CASE-3
        graph = dict(GRAPH, edges=[{"src": "a", "dst": "ghost"}])
        response = request("tools/call", {"name": "build_scene",
                                          "arguments": {"graph": graph, "out_dir": self.tmp}})
        self.assertNotIn("error", response)
        text = response["result"]["content"][0]["text"]
        self.assertTrue(response["result"]["isError"])
        self.assertIn("ghost", text)
        self.assertNotIn("\n", text)

    def test_render_html_and_discover_repo(self):  # verifies: REQ-EXCALIDRAW-852#CASE-4
        call("build_scene", {"graph": GRAPH, "out_dir": self.tmp, "name": "src"})
        html_dir = os.path.join(self.tmp, "html")
        rendered = call("render_html", {"scene_path": os.path.join(self.tmp, "src.excalidraw"),
                                        "out_dir": html_dir})
        self.assertFalse(rendered["isError"], rendered)
        self.assertTrue(os.path.isfile(os.path.join(html_dir, "src.html")))

        repo = os.path.join(self.tmp, "repo")
        os.makedirs(repo)
        with open(os.path.join(repo, "app.py"), "w", encoding="utf-8") as fh:
            fh.write("def main():\n    pass\n")
        stub = os.path.join(self.tmp, "make_repo.py")
        found = call("discover_repo", {"repo": repo, "out_path": stub})
        self.assertFalse(found["isError"], found)
        self.assertTrue(os.path.isfile(stub))

    def test_graph_schema_comes_from_the_doc(self):  # verifies: REQ-EXCALIDRAW-852#CASE-5
        result = call("graph_schema", {})
        self.assertFalse(result["isError"], result)
        text = result["content"][0]["text"]
        self.assertIn('"nodes"', text)
        self.assertIn('"edges"', text)

    def test_graph_schema_missing_doc_is_a_tool_error(self):  # verifies: REQ-EXCALIDRAW-852#CASE-5
        saved = mcp_server.BUILDER_API_MD
        mcp_server.BUILDER_API_MD = os.path.join(self.tmp, "absent.md")
        try:
            self.assertTrue(call("graph_schema", {})["isError"])
        finally:
            mcp_server.BUILDER_API_MD = saved


class TestStdio(unittest.TestCase):
    """REQ-EXCALIDRAW-852: the real process speaks only protocol on stdout."""

    def test_stdout_carries_only_protocol(self):  # verifies: REQ-EXCALIDRAW-852#CASE-6
        lines = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                        "clientInfo": {"name": "test", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ]
        stdin = "".join(json.dumps(m) + "\n" for m in lines) + "{broken\n"
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", os.path.join(HERE, "mcp_server.py")],
            input=stdin.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        out = proc.stdout.decode("utf-8").splitlines()
        responses = [json.loads(line) for line in out]
        self.assertEqual([r.get("id") for r in responses], [1, 2, None])
        self.assertEqual(responses[2]["error"]["code"], -32700)


if __name__ == "__main__":
    unittest.main()
