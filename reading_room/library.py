import json
import os
import shutil
import time
from pathlib import Path

LIBRARY_VERSION = 1
DEFAULT_KEEP_BACKUPS = 5
BACKUPS_DIRNAME = "backups"
DEFAULT_STORAGE_NAME = "library.json"
MAX_NAME_LEN = 80
MAX_TEXT_LEN = 400
MAX_PAGES_LEN = 50000
PERSON_NEW_KEY_LEN_NAMES = ("people", "books", "loans")


class LibraryError(ValueError):
    pass


def new_state():
    return {"version": LIBRARY_VERSION, "people": {}, "books": [], "loans": {}}


def resolve_data_dir(data_dir):
    if isinstance(data_dir, os.PathLike):
        data_dir = os.fspath(data_dir)
    if not isinstance(data_dir, str) or not data_dir.strip():
        raise LibraryError("data directory must be a non-empty string")
    if "\x00" in data_dir:
        raise LibraryError("data directory contains a NUL byte")
    parts = Path(data_dir).parts
    if ".." in parts:
        raise LibraryError("data directory may not contain '..' path segments")
    root = Path(data_dir).expanduser().resolve()
    return root


def _storage_path(root, name):
    if not isinstance(name, str) or not name:
        raise LibraryError("storage file name must be a non-empty string")
    if "\x00" in name:
        raise LibraryError("storage file name contains a NUL byte")
    if name in (".", ".."):
        raise LibraryError("storage file name may not be '.' or '..'")
    if "/" in name or "\\" in name or os.sep in name:
        raise LibraryError("storage file name may not contain path separators")
    candidate = root / name
    real = Path(os.path.realpath(candidate))
    if _is_relative_to(real, Path(os.path.realpath(root))) is False:
        raise LibraryError("storage file escapes the data directory")
    return candidate


def _is_relative_to(path, base):
    return path == base or base in path.parents


def _clean_text(value, field, max_len=MAX_TEXT_LEN, allow_empty=False):
    if not isinstance(value, str):
        raise LibraryError(f"{field} must be a string")
    if "\x00" in value:
        raise LibraryError(f"{field} contains a NUL byte")
    v = value.strip()
    if not v and not allow_empty:
        raise LibraryError(f"{field} must not be empty")
    if len(v) > max_len:
        raise LibraryError(f"{field} is too long (max {max_len} characters)")
    return v


def _clean_int(value, field, minimum, maximum=MAX_PAGES_LEN):
    if isinstance(value, bool) or not isinstance(value, int):
        raise LibraryError(f"{field} must be an integer")
    if value < minimum:
        raise LibraryError(f"{field} must be at least {minimum}")
    if value > maximum:
        raise LibraryError(f"{field} is unreasonably large (max {maximum})")
    return value


def _clean_pages(value):
    return _clean_int(value, "pages", minimum=1)


class Library:
    def __init__(self, data_dir, storage_name=DEFAULT_STORAGE_NAME,
                 keep_backups=DEFAULT_KEEP_BACKUPS, fsck=True):
        self.root = resolve_data_dir(data_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.keep_backups = _clean_int(keep_backups, "keep_backups", minimum=0)
        self.path = _storage_path(self.root, storage_name)
        self.state = self.load()

    def load(self):
        if not self.path.exists():
            return new_state()
        try:
            self.path.read_text(encoding="utf-8")
        except OSError as exc:
            raise LibraryError(f"cannot read storage file: {exc}") from exc
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise LibraryError(
                "storage file is not valid JSON; a pre-save backup may exist in "
                f"{BACKUPS_DIRNAME} ({exc})"
            ) from exc
        if not _is_relative_to(Path(os.path.realpath(self.path)),
                               Path(os.path.realpath(self.root))):
            raise LibraryError("storage file escapes the data directory")
        return self._normalize(data)

    def _normalize(self, data):
        if not isinstance(data, dict):
            raise LibraryError("storage file must contain a JSON object")
        state = new_state()
        people = data.get("people", {})
        if not isinstance(people, dict):
            raise LibraryError("'people' in storage must be an object")
        for name, record in people.items():
            cleaned = _clean_text(name, "person name", MAX_NAME_LEN)
            self._validate_person_record(record, context=f"person {cleaned!r}")
            state["people"][cleaned] = record
        books = data.get("books", [])
        if not isinstance(books, list):
            raise LibraryError("'books' in storage must be an array")
        ids = set()
        for book in books:
            if not isinstance(book, dict):
                raise LibraryError("each book in storage must be an object")
            book_id = _clean_text(book.get("id", ""), "book id", 40)
            if book_id in ids:
                raise LibraryError(f"duplicate book id {book_id!r} in storage")
            ids.add(book_id)
            book.setdefault("author", "")
            book["pages"] = _clean_pages(book.get("pages"))
            state["books"].append(book)
        loans = data.get("loans", {})
        if not isinstance(loans, dict):
            raise LibraryError("'loans' in storage must be an object")
        for book_id, holder in loans.items():
            if book_id not in ids:
                raise LibraryError(f"loan references unknown book {book_id!r}")
            _clean_text(holder, "loan holder", MAX_NAME_LEN)
            state["loans"][book_id] = holder
        return state

    @staticmethod
    def _validate_person_record(record, context):
        if not isinstance(record, dict):
            raise LibraryError(f"{context} must be an object")
        if "reading" in record and record["reading"] is not None \
                and not isinstance(record["reading"], str):
            raise LibraryError(f"{context} has an invalid reading field")
        pages_read = record.get("pages_read", 0)
        if isinstance(pages_read, bool) or not isinstance(pages_read, int) or pages_read < 0:
            raise LibraryError(f"{context} has an invalid pages_read field")
        bookmark = record.get("bookmark")
        if bookmark is not None:
            if not isinstance(bookmark, dict) or not \
                    isinstance(bookmark.get("page"), int) or bookmark["page"] < 1:
                raise LibraryError(f"{context} has an invalid bookmark")

    def save(self):
        self._backup()
        tmp_path = self.path.with_name(self.path.name + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(self.state, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp_path, self.path)

    def _backup(self):
        if not self.path.exists():
            return
        backups_dir = self.root / BACKUPS_DIRNAME
        backups_dir.mkdir(parents=True, exist_ok=True)
        stem = self.path.stem
        stamp = str(time.time_ns())
        shutil.copy2(self.path, backups_dir / f"{stem}-{stamp}.bak")
        backups = sorted(backups_dir.glob("*.bak"))
        for old in backups[:-self.keep_backups] if self.keep_backups else backups:
            try:
                old.unlink()
            except OSError:
                pass

    @property
    def people(self):
        return list(self.state["people"].keys())

    @property
    def books(self):
        return list(self.state["books"])

    def _person(self, name):
        cleaned = _clean_text(name, "person name", MAX_NAME_LEN)
        if cleaned not in self.state["people"]:
            raise LibraryError(f"unknown person {cleaned!r}")
        return cleaned, self.state["people"][cleaned]

    def _book(self, query):
        cleaned = _clean_text(query, "book id or title")
        for book in self.state["books"]:
            if book["id"] == cleaned:
                return book
        lowered = cleaned.lower()
        for book in self.state["books"]:
            if book["title"].lower() == lowered:
                return book
        substring = [book for book in self.state["books"] if lowered in book["title"].lower()]
        if len(substring) == 1:
            return substring[0]
        if len(substring) > 1:
            titles = ", ".join(b["title"] for b in substring)
            raise LibraryError(f"book query {cleaned!r} is ambiguous: {titles}")
        raise LibraryError(f"no book matching {cleaned!r}")

    def add_person(self, name):
        cleaned = _clean_text(name, "person name", MAX_NAME_LEN)
        if cleaned in self.state["people"]:
            raise LibraryError(f"person {cleaned!r} is already in the room")
        self.state["people"][cleaned] = {"reading": None, "pages_read": 0, "bookmark": None}
        self.save()
        return f"Welcome, {cleaned}!"

    def remove_person(self, name):
        cleaned, _ = self._person(name)
        del self.state["people"][cleaned]
        for book_id, holder in list(self.state["loans"].items()):
            if holder == cleaned:
                del self.state["loans"][book_id]
        self.save()
        return f"{cleaned} left the reading room."

    def add_book(self, title, author="", pages=None, owner=""):
        title_clean = _clean_text(title, "book title")
        author_clean = _clean_text(author, "book author", allow_empty=True)
        pages_clean = _clean_pages(pages)
        owner_clean = _clean_text(owner, "book owner", MAX_NAME_LEN, allow_empty=True)
        if owner_clean and owner_clean not in self.state["people"]:
            raise LibraryError(f"owner {owner_clean!r} is not in the room yet; add them first")
        next_num = 1
        existing = {b["id"] for b in self.state["books"]}
        while f"b_{next_num:03d}" in existing:
            next_num += 1
        book_id = f"b_{next_num:03d}"
        book = {
            "id": book_id,
            "title": title_clean,
            "author": author_clean,
            "pages": pages_clean,
            "owner": owner_clean,
        }
        self.state["books"].append(book)
        self.save()
        return f"Added {book_id} {title_clean!r} ({pages_clean} pages)."

    def remove_book(self, query):
        book = self._book(query)
        if book["id"] in self.state["loans"]:
            raise LibraryError("this book is on loan; can't remove from the room")
        for person, record in self.state["people"].items():
            if record.get("reading") == book["id"]:
                raise LibraryError(f"{person} is currently reading this book; clear it first")
        self.state["books"].remove(book)
        self.save()
        return f"Removed {book['id']} {book['title']!r}."

    def set_reading(self, person, query):
        cleaned, record = self._person(person)
        book = self._book(query)
        if record.get("reading") == book["id"]:
            return f"{cleaned} is already reading {book['title']!r}."
        record["reading"] = book["id"]
        record["pages_read"] = 0
        record["bookmark"] = None
        self.save()
        return f"{cleaned} starts reading {book['title']!r} ({book['pages']} pages)."

    def clear_reading(self, person):
        cleaned, record = self._person(person)
        if not record.get("reading"):
            raise LibraryError(f"{cleaned} is not reading anything right now")
        book = self._find_book_by_id(record["reading"])
        record["reading"] = None
        record["pages_read"] = 0
        self.save()
        if book:
            return f"{cleaned} closed {book['title']!r}."
        record["bookmark"] = None
        return f"{cleaned} closed their previous book."

    def _find_book_by_id(self, book_id):
        for book in self.state["books"]:
            if book["id"] == book_id:
                return book
        return None

    def update_progress(self, person, pages_read):
        cleaned, record = self._person(person)
        book_id = record.get("reading")
        if not book_id:
            raise LibraryError(f"{cleaned} has no current book; use set_reading first")
        book = self._find_book_by_id(book_id)
        value = _clean_int(pages_read, "pages_read", minimum=0)
        if book and value > book["pages"]:
            raise LibraryError(
                f"that's past the end of {book['title']!r} ({book['pages']} pages total)"
            )
        record["pages_read"] = value
        self.save()
        total = book["pages"] if book else value
        percent = round(100 * value / total) if total else 0
        detail = book["title"] if book else "unknown book"
        if book and value >= total:
            return f"{cleaned} finished {detail!r}! ({value}/{total} pages, 100%)"
        return f"{cleaned} is at page {value} of {detail!r} ({value}/{total}, {percent}%)."

    def set_bookmark(self, person, page, note=""):
        cleaned, record = self._person(person)
        book_id = record.get("reading")
        if not book_id:
            raise LibraryError(f"{cleaned} has no current book to bookmark")
        book = self._find_book_by_id(book_id)
        value = _clean_int(page, "bookmark page", minimum=1)
        if book and value > book["pages"]:
            raise LibraryError(
                f"page {value} is past the end of {book['title']!r} ({book['pages']} pages)"
            )
        note_clean = _clean_text(note, "bookmark note", allow_empty=True)
        record["bookmark"] = {"page": value, "note": note_clean}
        self.save()
        label = book["title"] if book else "current book"
        suffix = f' - "{note_clean}"' if note_clean else ""
        return f"To-be-continued: {cleaned} paused {label!r} at page {value}{suffix}."

    def clear_bookmark(self, person):
        cleaned, record = self._person(person)
        if not record.get("bookmark"):
            raise LibraryError(f"{cleaned} has no bookmark set")
        record["bookmark"] = None
        self.save()
        return f"Cleared {cleaned}'s bookmark."

    def list_bookmarks(self):
        lines = []
        for name, record in self.state["people"].items():
            bm = record.get("bookmark")
            if not bm:
                continue
            book = self._find_book_by_id(record.get("reading")) if record.get("reading") else None
            title = book["title"] if book else "unknown book"
            note = f' - "{bm["note"]}"' if bm.get("note") else ""
            lines.append(f"{name}: {title!r} paused at page {bm['page']}/{book['pages'] if book else '?'}{note}")
        if not lines:
            return "No bookmarks. Nobody is paused right now."
        return "To-be-continued bookmarks:\n" + "\n".join(f" - {l}" for l in lines)

    def lend(self, query, to_person):
        book = self._book(query)
        holder, _ = self._person(to_person)
        if book["owner"] == holder:
            raise LibraryError(f"{holder} already owns {book['title']!r}")
        if self.state["loans"].get(book["id"]) == holder:
            return f"{holder} already has {book['title']!r}."
        self.state["loans"][book["id"]] = holder
        self.save()
        owner = book["owner"] or "the house shelf"
        return f"{book['title']!r} is now with {holder} (belongs to {owner})."

    def return_book(self, query, from_person=None):
        book = self._book(query)
        holder = self.state["loans"].get(book["id"])
        if not holder:
            raise LibraryError(f"{book['title']!r} is not on loan; it's at home")
        if from_person:
            cleaned, _ = self._person(from_person)
            if cleaned != holder:
                raise LibraryError(f"{book['title']!r} is with {holder}, not {cleaned}")
            holder = cleaned
        del self.state["loans"][book["id"]]
        self.save()
        return f"{book['title']!r} came back from {holder}."

    def swap_grid(self):
        header = f"{'Book':<30} {'Owner':<14} {'Currently with':<16} {'In use by':<14}"
        lines = [header, "-" * len(header)]
        for book in self.state["books"]:
            holder = self.state["loans"].get(book["id"]) or book["owner"] or "house shelf"
            reader = None
            for name, record in self.state["people"].items():
                if record.get("reading") == book["id"]:
                    reader = name
                    break
            marker = " [loaned]" if book["id"] in self.state["loans"] else ""
            title = (book["title"] + marker)[:30]
            lines.append(f"{title:<30} {(book['owner'] or 'house'):<14} {holder:<16} {reader or '-':<14}")
        return "Reading room swap grid:\n" + "\n".join(lines)

    def suggest_short_reads(self, max_pages, limit=5):
        limit_clean = _clean_int(limit, "limit", minimum=1, maximum=100)
        max_clean = _clean_pages(max_pages)
        reading_ids = {r.get("reading") for r in self.state["people"].values() if r.get("reading")}
        candidates = [
            b for b in self.state["books"]
            if b["pages"] <= max_clean and b["id"] not in reading_ids
        ]
        candidates.sort(key=lambda b: (b["pages"], b["title"]))
        if not candidates:
            return f"No short reads at or under {max_clean} pages (that nobody is already reading)."
        lines = [f"Short reads for a busy week, all at or under {max_clean} pages ({limit_clean} max):"]
        for book in candidates[:limit_clean]:
            holder = self.state["loans"].get(book["id"]) or book["owner"] or "house shelf"
            lines.append(
                f" - {book['title']!r} by {book['author'] or 'unknown'} "
                f"({book['pages']} pages, currently with {holder})"
            )
        return "\n".join(lines)

    def books_table(self):
        header = f"{'ID':<8} {'Title':<32} {'Pages':<6} {'Owner':<14} {'With':<14}"
        lines = [header, "-" * len(header)]
        for book in self.state["books"]:
            holder = self.state["loans"].get(book["id"]) or book["owner"] or "house shelf"
            title = book["title"][:32]
            lines.append(
                f"{book['id']:<8} {title:<32} {book['pages']:<6} "
                f"{(book['owner'] or 'house'):<14} {holder:<14}"
            )
        if len(lines) == 2:
            return "The room shelf is empty."
        return "Room shelf:\n" + "\n".join(lines)

    def status(self):
        lines = [
            f"Reading room snapshot ({len(self.state['books'])} books, "
            f"{len(self.state['people'])} people)",
            "Who is reading what:",
        ]
        any_activity = False
        for name, record in self.state["people"].items():
            book = self._find_book_by_id(record.get("reading")) if record.get("reading") else None
            if book:
                any_activity = True
                lines.append(
                    f" - {name}: {book['title']!r} at page "
                    f"{record.get('pages_read', 0)}/{book['pages']}"
                )
            else:
                lines.append(f" - {name}: between books")
        if not self.state["people"]:
            lines.append(" - (nobody in the room yet)")
        return "\n".join(lines)
