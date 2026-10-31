import json

from . import __version__
from .library import LIBRARY_VERSION, Library, LibraryError

PROTOCOL_VERSION = "2024-11-05"

DESCRIPTION = (
    "Tracking server for one household reading room. People, per-person reading "
    "progress, to-be-continued bookmarks, a lending swap grid (who has whose book), "
    "and short-read suggestions filtered by page count."
)


def _person_schema():
    return {"name": {"type": "string", "description": "Person's name"}}


def _query_schema():
    return {
        "query": {
            "type": "string",
            "description": "Book id (e.g. b_004) or title; unique substring works",
        }
    }


TOOLS = [
    {
        "name": "room_status",
        "description": "Snapshot of who is in the room and what they are reading, at what page.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "add_person",
        "description": "Add a member of the household to the reading room.",
        "inputSchema": {"type": "object", "properties": _person_schema(), "required": ["name"]},
    },
    {
        "name": "remove_person",
        "description": "Remove a person and release any books they were holding on loan.",
        "inputSchema": {"type": "object", "properties": _person_schema(), "required": ["name"]},
    },
    {
        "name": "add_book",
        "description": "Add a book to the shared room shelf.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Book title"},
                "author": {"type": "string", "description": "Author (optional)"},
                "pages": {"type": "integer", "description": "Total page count"},
                "owner": {"type": "string", "description": "Owner's name; empty means house shelf"},
            },
            "required": ["title", "pages"],
        },
    },
    {
        "name": "remove_book",
        "description": "Remove a book that is not on loan and not being read.",
        "inputSchema": {"type": "object", "properties": _query_schema(), "required": ["query"]},
    },
    {
        "name": "list_books",
        "description": "List every book on the room shelf with id, page count, owner and holder.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "set_reading",
        "description": "Set which book a person is currently reading (resets their progress).",
        "inputSchema": {
            "type": "object",
            "properties": {"person": {"type": "string", "description": "Person's name"},
                           "query": {"type": "string", "description": "Book id or title"}},
            "required": ["person", "query"],
        },
    },
    {
        "name": "clear_reading",
        "description": "Close a person's current book (progress is reset).",
        "inputSchema": {"type": "object", "properties": _person_schema(), "required": ["person"]},
    },
    {
        "name": "update_progress",
        "description": "Record how far a person has read in their current book (absolute page).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "person": {"type": "string", "description": "Person's name"},
                "pages_read": {"type": "integer", "description": "Latest page reached"},
            },
            "required": ["person", "pages_read"],
        },
    },
    {
        "name": "set_bookmark",
        "description": "Hold a to-be-continued bookmark for a person's current book, with an optional note.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "person": {"type": "string", "description": "Person's name"},
                "page": {"type": "integer", "description": "Page they paused on"},
                "note": {"type": "string", "description": "Optional note, e.g. where the story left off"},
            },
            "required": ["person", "page"],
        },
    },
    {
        "name": "clear_bookmark",
        "description": "Clear a person's to-be-continued bookmark.",
        "inputSchema": {"type": "object", "properties": _person_schema(), "required": ["person"]},
    },
    {
        "name": "list_bookmarks",
        "description": "All to-be-continued bookmarks in the room.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "lend_book",
        "description": "Mark that someone's book is on loan to another person in the room.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Book id or title"},
                           "to_person": {"type": "string", "description": "Who is holding it"},
                           },
            "required": ["query", "to_person"],
        },
    },
    {
        "name": "return_book",
        "description": "Mark a book as back on its owner's shelf.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Book id or title"},
                           "from_person": {"type": "string", "description": "Optional: the returning holder"}},
            "required": ["query"],
        },
    },
    {
        "name": "swap_grid",
        "description": "Show the lending swap grid: who has whose book, and who is inside each book.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "suggest_short_reads",
        "description": "Suggest books nobody is reading, filtered by a maximum page count, for busy weeks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_pages": {"type": "integer", "description": "Only books at or under this page count"},
                "limit": {"type": "integer", "description": "How many to suggest (default 5)"},
            },
            "required": ["max_pages"],
        },
    },
]

TOOL_HANDLERS = {
    "room_status": lambda lib, args: lib.status(),
    "add_person": lambda lib, args: lib.add_person(args["name"]),
    "remove_person": lambda lib, args: lib.remove_person(args["name"]),
    "add_book": lambda lib, args: lib.add_book(
        args["title"], args.get("author", ""), args["pages"], args.get("owner", "")
    ),
    "remove_book": lambda lib, args: lib.remove_book(args["query"]),
    "list_books": lambda lib, args: lib.books_table(),
    "set_reading": lambda lib, args: lib.set_reading(args["person"], args["query"]),
    "clear_reading": lambda lib, args: lib.clear_reading(args["person"]),
    "update_progress": lambda lib, args: lib.update_progress(args["person"], args["pages_read"]),
    "set_bookmark": lambda lib, args: lib.set_bookmark(args["person"], args["page"], args.get("note", "")),
    "clear_bookmark": lambda lib, args: lib.clear_bookmark(args["person"]),
    "list_bookmarks": lambda lib, args: lib.list_bookmarks(),
    "lend_book": lambda lib, args: lib.lend(args["query"], args["to_person"]),
    "return_book": lambda lib, args: lib.return_book(args["query"], args.get("from_person")),
    "swap_grid": lambda lib, args: lib.swap_grid(),
    "suggest_short_reads": lambda lib, args: lib.suggest_short_reads(
        args["max_pages"], args.get("limit", 5)
    ),
}


class ReadingRoomServer:
    def __init__(self, library):
        self.library = library

    @property
    def initialize_result(self):
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "reading-room", "version": __version__},
        }

    def tools_list(self):
        return {
            "tools": [
                {
                    "name": tool["name"],
                    "description": tool["description"],
                    "inputSchema": tool["inputSchema"],
                }
                for tool in TOOLS
            ]
        }

    def call_tool(self, name, arguments):
        if name not in TOOL_HANDLERS:
            return {"isError": True, "content": [{"type": "text", "text": f"Unknown tool {name!r}"}]}
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return {
                "isError": True,
                "content": [{"type": "text", "text": "Tool arguments must be an object"}],
            }
        try:
            text = TOOL_HANDLERS[name](self.library, arguments)
        except LibraryError as exc:
            return {"isError": True, "content": [{"type": "text", "text": str(exc)}]}
        except KeyError as exc:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Missing tool argument: {exc.args[0]}"}],
            }
        except (TypeError, ValueError) as exc:
            return {"isError": True, "content": [{"type": "text", "text": f"Invalid arguments: {exc}"}]}
        except Exception as exc:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Storage or internal error: {exc}"}],
            }
        return {"isError": False, "content": [{"type": "text", "text": str(text)}]}

    def _error(self, request_id, code, message):
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    def _result(self, request_id, result):
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def handle(self, message):
        if isinstance(message, str) or isinstance(message, int) or message is None:
            return self._error(None, -32600, "Invalid request")
        if not isinstance(message, dict):
            return self._error(None, -32600, "Invalid request")
        method = message.get("method")
        if not isinstance(method, str):
            return self._error(None, -32600, "Missing method")
        request_id = message.get("id")
        if request_id is None:
            return None
        try:
            if method == "initialize":
                return self._result(request_id, self.initialize_result)
            if method == "ping":
                return self._result(request_id, {})
            if method == "tools/list":
                return self._result(request_id, self.tools_list())
            if method == "tools/call":
                params = message.get("params") or {}
                if not isinstance(params, dict):
                    return self._error(request_id, -32602, "Invalid params")
                name = params.get("name")
                if not isinstance(name, str):
                    return self._error(request_id, -32602, "tools/call needs a tool name")
                return self._result(request_id, self.call_tool(name, params.get("arguments")))
            return self._error(request_id, -32601, f"Method not found: {method}")
        except LibraryError as exc:
            return self._error(request_id, -32603, f"Storage error: {exc}")

    def serve(self, stdin, stdout):
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                response = self._error(None, -32700, "Parse error")
            else:
                response = self.handle(message)
            if response is None:
                continue
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()
