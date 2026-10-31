# STATUS.md — reading-room-mcp-server

Built: October 31, 2026 by Asdale Dynamics, LLC.

## What was built

A small MCP (Model Context Protocol) server for one household's reading room,
in pure Python standard library, speaking newline-delimited JSON-RPC 2.0 over
stdio. No third-party dependencies, no network, no secrets, no personal data
(sample shelf uses fictional names only).

### Directory layout

```
reading_room/__init__.py            package version
reading_room/library.py             core logic: state, validation, storage, backups, path safety
reading_room/server.py              MCP protocol layer + 16 tool definitions
reading_room/__main__.py            CLI entry: python3 -m reading_room [data_dir] [--sample]
sample_data/sample_shelf.json       seed shelf (8 books, 3 people, 2 loans, 1 bookmark)
tests/test_library.py               41 offline unit tests + security cases
tests/test_server.py                18 protocol-level tests (offline, in-process)
LICENSE                             MIT, Copyright (c) 2026 Asdale Dynamics, LLC
README.md                           overview, config example, smoke-test guide
.gitignore                          keeps data/, __pycache__/, *.bak out of git
```

### Features

- **People & per-person progress**: `add_person`, `remove_person`,
  `set_reading`, `clear_reading`, `update_progress` (absolute page, rejects
  past-the-end values, celebrates 100%).
- **To-be-continued bookmarks**: `set_bookmark` (page + optional note),
  `clear_bookmark`, `list_bookmarks`.
- **Lending swap grid**: `lend_book`, `return_book`, `swap_grid` — a fixed
  width table of every book, its owner, who holds it, and who is reading it;
  loaned books are flagged `[loaned]`.
- **Short-read suggestions**: `suggest_short_reads(max_pages, limit)` — books
  nobody is currently reading, sorted shortest first.
- Plus `room_status`, `add_book`, `remove_book`, `list_books`.

### Storage, backups, and path safety

- Single JSON store: `data/library.json` by default; directory and file name
  are CLI parameters.
- Auto-backup on every save: the previous file is copied to
  `data/backups/library-<stamp>.bak`, newest 5 kept (`--keep` behavior is a
  constructor parameter; default 5).
- Path safety (all enforced and unit-tested):
  - data directory may not contain `..` segments or NUL bytes;
  - the storage file name must be a single bare component (no `/`, `\`, `.`,
    `..`, NUL);
  - symlinks whose real path escapes the data directory are rejected at load;
  - load-time validation rejects malformed state shapes and unknown/duplicate
    book ids; corrupt JSON fails loudly and points at the backups instead of
    being silently overwritten.

## How to run it

```bash
# tests
python3 -m unittest discover -s tests

# server over stdio (defaults to ./data)
python3 -m reading_room reading-room-data

# seed the fictional sample shelf on first empty run
python3 -m reading_room smoke-data --sample < input.ndjson
```

MCP client config example (opencode / Claude Desktop style):

```json
{
  "mcp": {
    "reading-room": {
      "type": "local",
      "command": ["python3", "-m", "reading_room", "reading-room-data"]
    }
  }
}
```

## Verification results (actual runs)

- `python3 -m unittest discover -s tests` → **Ran 59 tests ... OK**
  (including 13 security-focused tests).
- `python3 -m py_compile reading_room/*.py tests/*.py` → clean (exit 0).
- README smoke test #1 (`initialize` + `tools/list` over stdio): initialize
  replies with `serverInfo: {"name": "reading-room", "version": "1.0.0"}`,
  the `notifications/initialized` notification correctly gets no reply, and
  `tools/list` returns 16 tools. Exit code 0.
- README smoke test #2 (`--sample` seeded scenario): `room_status` shows Dana
  on *The Massive AI Manual* at page 41/420; `swap_grid` flags
  *The Caretaker's Almanac* and *Night Shift Poems* `[loaned]`;
  `list_bookmarks` shows Dana's page-41 note; `suggest_short_reads(120)`
  returns *Night Shift Poems* (72p), *Tiny Habits, Big Weeks* (96p),
  *Chess in Small Doses* (120p). All outputs matched the README verbatim.
- Path-safety via CLI: `python3 -m reading_room ../oops` →
  `reading-room: data directory may not contain '..' path segments` (exit 2).
- No fixes outstanding; issues found during verification (Path-like data dirs
  rejected, argument destructuring in a test, one-save-only backup case) were
  fixed and re-run to green.

## Known gaps / future ideas

- Progress is a single absolute page per person (no date-by-date history).
- The swap grid is plain fixed-width text; no pretty markdown rendering.
- Backup retention is fixed at 5 via the constructor; no CLI flag yet.
- No `books/secrets`-style locking: concurrent writers assume the household
  runs one server instance at a time.
- Loans are per-book, not per-copy (fine for a single physical shelf).
- No packaging (`pyproject.toml`); run it in place with Python 3.10+.
