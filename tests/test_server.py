import io
import json
import tempfile
import unittest
import unittest.mock

from reading_room.library import Library
from reading_room.server import ReadingRoomServer, TOOLS


def rpc(method, params=None, request_id=1):
    message = {"jsonrpc": "2.0", "method": method, "id": request_id}
    if params is not None:
        message["params"] = params
    return message


class ServerProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.library = Library(self.tmp.name)
        self.server = ReadingRoomServer(self.library)

    def tearDown(self):
        self.tmp.cleanup()

    def handle(self, message):
        raw = json.dumps(message) if not isinstance(message, str) else message
        self.assertIsInstance(raw, str)
        out = io.StringIO()
        inp = io.StringIO(raw + "\n")
        self.server.serve(inp, out)
        return out.getvalue().strip()

    def test_initialize(self):
        response = json.loads(self.handle(rpc("initialize", {})))
        result = response["result"]
        self.assertEqual(result["serverInfo"]["name"], "reading-room")
        self.assertTrue(result["protocolVersion"])
        self.assertIn("tools", result["capabilities"])

    def test_tools_list(self):
        response = json.loads(self.handle(rpc("tools/list")))
        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertTrue({"room_status", "swap_grid", "list_bookmarks",
                         "suggest_short_reads"} <= names)
        self.assertEqual(len(names), len(TOOLS))
        for tool in response["result"]["tools"]:
            self.assertIn("inputSchema", tool)
            self.assertEqual(tool["inputSchema"]["type"], "object")

    def test_ping(self):
        response = json.loads(self.handle(rpc("ping")))
        self.assertEqual(response["result"], {})

    def test_tool_call_add_person(self):
        params = {"name": "add_person", "arguments": {"name": "Dana"}}
        response = json.loads(self.handle(rpc("tools/call", params)))
        self.assertFalse(response["result"]["isError"])
        self.assertIn("Dana", response["result"]["content"][0]["text"])

    def test_tool_round_trip_end_to_end(self):
        steps = [
            ("add_person", {"name": "Dana"}, "Welcome"),
            ("add_book", {"title": "Short Stories", "pages": 95}, "b_001"),
        ]
        for tool, arguments, expected in steps:
            response = json.loads(self.handle(rpc("tools/call", {"name": tool, "arguments": arguments})))
            self.assertIn(expected, response["result"]["content"][0]["text"])
        response = json.loads(self.handle(rpc("tools/call", {
            "name": "suggest_short_reads",
            "arguments": {"max_pages": 100},
        })))
        self.assertIn("Short Stories", response["result"]["content"][0]["text"])
        listing = json.loads(self.handle(rpc("tools/call", {
            "name": "list_bookmarks", "arguments": {},
        })))
        self.assertIn("No bookmarks", listing["result"]["content"][0]["text"])

    def test_tool_error_returns_is_error(self):
        params = {"name": "add_person", "arguments": {}}
        response = json.loads(self.handle(rpc("tools/call", params)))
        self.assertTrue(response["result"]["isError"])
        self.assertIn("name", response["result"]["content"][0]["text"])

    def test_unknown_tool_is_error(self):
        params = {"name": "definitely_not_a_tool", "arguments": {}}
        response = json.loads(self.handle(rpc("tools/call", params)))
        self.assertTrue(response["result"]["isError"])

    def test_unknown_method(self):
        response = json.loads(self.handle(rpc("sleep/forever")))
        self.assertEqual(response["error"]["code"], -32601)

    def test_notification_returns_none(self):
        notification = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        self.assertEqual(self.server.handle(notification), None)

    def test_parse_error_line(self):
        out_text = self.handle("{not json")
        response = json.loads(out_text)
        self.assertEqual(response["error"]["code"], -32700)

    def test_blank_lines_ignored(self):
        out = io.StringIO()
        inp = io.StringIO("\n\n")
        self.server.serve(inp, out)
        self.assertEqual(out.getvalue(), "")

    def test_non_object_message_rejected(self):
        response = json.loads(self.handle(json.dumps([1, 2, 3])))
        self.assertEqual(response["error"]["code"], -32600)

    def test_missing_method_rejected(self):
        response = json.loads(self.handle(json.dumps({"jsonrpc": "2.0", "id": 1})))
        self.assertEqual(response["error"]["code"], -32600)

    def test_tool_arguments_not_object_rejected(self):
        params = {"name": "add_person", "arguments": "Dana"}
        response = json.loads(self.handle(rpc("tools/call", params)))
        self.assertTrue(response["result"]["isError"])


class ServerStorageSafetyTests(unittest.TestCase):
    def test_server_reports_storage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = Library(tmp)
            library.add_person("Dana")
            server = ReadingRoomServer(library)
            with unittest.mock.patch.object(
                type(library), "save",
                side_effect=Exception("disk exploded"),
            ):
                response = self.call(server, "add_person", {"name": "Rey"})
        self.assertTrue(response["result"]["isError"])

    @staticmethod
    def call(server, tool, arguments):
        import io
        out = io.StringIO()
        message = {"jsonrpc": "2.0", "method": "tools/call", "id": 1,
                   "params": {"name": tool, "arguments": arguments}}
        server.serve(io.StringIO(json.dumps(message) + "\n"), out)
        return json.loads(out.getvalue())


if __name__ == "__main__":
    unittest.main()
