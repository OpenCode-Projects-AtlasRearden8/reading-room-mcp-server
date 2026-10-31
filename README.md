# Reading Room MCP Server

A small, local-first MCP (Model Context Protocol) server for **one household's
reading room**: track what each person is reading with per-person progress,
hold to-be-continued bookmarks, view a lending swap grid showing who has whose
book, and get short-read suggestions filtered by page count for busy weeks.

Written in pure Python (3.10+, standard library only) and runs over **stdio**,
so any MCP client (opencode, Claude Desktop, etc.) can use it with a simple
config entry. No network, no APIs, no secrets, no personal data beyond what
you choose to put in your own JSON file.

Built by **Asdale Dynamics, LLC**. Licensed **MIT**.

> Distinct from `bookshelf-mcp-server`, which tracks one person's private
> shelf and quotes. This server is about the *shared* room: people, loans,
> bookmarks, and swapping.

## How it works

- State lives in a single JSON file (`data/library.json` by default).
- Every save first snapshots the previous file into `data/backups/`
  (auto-backup, newest 5 kept).
- Path-safety guards: relative-path traversal (`..`), path separators,
  NUL bytes, and symlinks that escape the data directory are all rejected.
- Every tool reply is plain text, so the model can read it straight into
  conversation with the household.

## Quick start

```bash
# no dependencies beyond Python 3.10+
python3 -m reading_room --help

# run tests
python3 -m unittest discover -s tests
```

## Configuring your MCP client

Example `opencode.json` (or the equivalent block in Claude Desktop's
`claude_desktop_config.json`):

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

Optional flags: `--sample` seeds the store from `sample_data/sample_shelf.json`
the first time the store is empty; `--storage-name NAME` picks a different
file name (bare file names only, cannot escape the data directory).

## Tools

| Tool | What it does |
| --- | --- |
| `room_status` | Snapshot of who is in the room and what they are reading |
| `add_person` / `remove_person` | Add or leave the household reading room |
| `add_book` / `remove_book` | Room shelf management (title, author, pages, owner) |
| `list_books` | Table of books: id, pages, owner, currently with |
| `set_reading` / `clear_reading` | Set a person's current book (resets progress) |
| `update_progress` | Record the latest page a person has reached |
| `set_bookmark` / `clear_bookmark` | Hold a to-be-continued bookmark with an optional note |
| `list_bookmarks` | All to-be-continued bookmarks in one list |
| `lend_book` / `return_book` | Mark one of someone's books as with another person |
| `swap_grid` | The lending swap grid: who has whose book |
| `suggest_short_reads` | Books nobody is reading, filtered to a max page count |

Book lookup accepts the id (`b_004`), an exact title (case-insensitive), or a
unique substring.

## Smoke-test guide (manual, offline)

You can drive the server from a plain terminal with two lines of JSON per
command. Each request is on its own line; the server replies with one line.

```bash
cd reading-room-mcp-server

printf '%s\n%s\n%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | python3 -m reading_room smoke-data
```

Expected: line 1 answers `initialize` (server name `reading-room`), the
notification gets no reply, and line 2 lists 16 tools.

Even more fun, seed the sample shelf and run a full scenario:

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"room_status","arguments":{}}}' \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"swap_grid","arguments":{}}}' \
  '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"list_bookmarks","arguments":{}}}' \
  '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"suggest_short_reads","arguments":{"max_pages":120}}}' \
  | python3 -m reading_room smoke-data --sample
```

Expected: Dana is on *The Massive AI Manual* at page 41, Fern owes Rey's
*Caretaker's Almanac*, Dana holds a to-be-continued bookmark at page 41, and
`Night Shift Poems` / `Tiny Habits, Big Weeks` head the short-read list.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

59 offline tests, zero network or filesystem fixtures beyond a temp directory:

- reading, progress, bookmarks, loans, short reads, persistence, backup rotation
- **security cases**: `..` traversal in the data dir and storage name, path
  separators in storage names, NUL bytes, symlink escapes, ownership checks,
  and type/limit validation on tool arguments

## Data, privacy, and safety

- Your JSON file and backups stay wherever you point them; nothing is uploaded.
- No secrets or API keys are needed or read.
- The sample shelf uses fictional names only.
- Corrupt files fail loudly with a pointer to the latest backup instead of
  silently overwriting your library.

## Credits

Built by **Asdale Dynamics, LLC** — beginner-friendly AI education, books,
guides, and practical tools. Learn more at
[dylanasdale.github.io](https://dylanasdale.github.io) and in the book
*The Massive AI Manual*.

Licensed under the MIT License. Copyright (c) 2026 Asdale Dynamics, LLC.
