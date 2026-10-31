import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .library import DEFAULT_STORAGE_NAME, Library, LibraryError
from .server import ReadingRoomServer


def _seed_from_sample(library, sample_path):
    with open(sample_path, encoding="utf-8") as handle:
        sample = json.load(handle)
    library.state = sample
    library.save()
    return sample_path


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python3 -m reading_room",
        description="Reading Room MCP server (stdio) for one household.",
    )
    parser.add_argument(
        "data_dir",
        nargs="?",
        default="data",
        help="Directory for the JSON store and backups (default: ./data)",
    )
    parser.add_argument(
        "--storage-name",
        default=DEFAULT_STORAGE_NAME,
        help="File name for the JSON store inside data_dir",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Seed the store from sample_data/sample_shelf.json if empty",
    )
    parser.add_argument("--version", action="version", version=f"reading-room {__version__}")
    args = parser.parse_args(argv)
    try:
        library = Library(args.data_dir, storage_name=args.storage_name)
    except LibraryError as exc:
        print(f"reading-room: {exc}", file=sys.stderr)
        return 2
    if args.sample:
        sample_path = Path(__file__).resolve().parent.parent / "sample_data" / "sample_shelf.json"
        if not library.state["books"] and not library.state["people"]:
            _seed_from_sample(library, sample_path)
            print(f"reading-room: seeded from {sample_path}", file=sys.stderr)
    server = ReadingRoomServer(library)
    server.serve(sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
