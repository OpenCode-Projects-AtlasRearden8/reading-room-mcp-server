import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from reading_room.library import (
    BACKUPS_DIRNAME,
    Library,
    LibraryError,
    new_state,
)


class LibraryTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.data_dir = self.base / "data"

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, **kwargs):
        return Library(self.data_dir, **kwargs)


class PeopleTests(LibraryTestCase):
    def test_add_and_list_person(self):
        lib = self.make()
        self.assertEqual(lib.add_person("Dana"), "Welcome, Dana!")
        self.assertEqual(lib.people, ["Dana"])

    def test_add_duplicate_person_rejected(self):
        lib = self.make()
        lib.add_person("Dana")
        with self.assertRaises(LibraryError):
            lib.add_person("Dana")

    def test_remove_person_releases_loans(self):
        lib = self.make()
        lib.add_person("Dana")
        lib.add_person("Rey")
        lib.add_book("Short Book", "A. Author", 90, owner="Dana")
        lib.lend("Short Book", "Rey")
        lib.remove_person("Rey")
        self.assertNotIn("b_001", lib.state["loans"])
        with self.assertRaises(LibraryError):
            lib.lend("Short Book", "Ghost Ghostington")


class BooksTests(LibraryTestCase):
    def test_add_book_and_ids_increment(self):
        lib = self.make()
        lib.add_book("Book One", "", 100, owner="")
        lib.add_book("Book Two", "Writer", 200, owner="")
        ids = [b["id"] for b in lib.state["books"]]
        self.assertEqual(ids, ["b_001", "b_002"])

    def test_pages_must_be_positive(self):
        lib = self.make()
        for bad in (0, -5, "12", 1.5, True, None):
            with self.assertRaises(LibraryError):
                lib.add_book("Bad Pages", "", bad, owner="")

    def test_owner_must_exist(self):
        lib = self.make()
        with self.assertRaises(LibraryError):
            lib.add_book("Missing Owner", "", 120, owner="Nobody")

    def test_find_by_id_title_and_substring(self):
        lib = self.make()
        lib.add_book("The Long Quiet", "Writer", 300, owner="")
        self.assertEqual(lib._book("b_001")["title"], "The Long Quiet")
        self.assertEqual(lib._book("the long quiet")["title"], "The Long Quiet")
        self.assertEqual(lib._book("long quiet")["title"], "The Long Quiet")
        with self.assertRaises(LibraryError):
            lib._book("not a book")

    def test_ambiguous_substring_rejected(self):
        lib = self.make()
        lib.add_book("Quiet Days", "", 100, owner="")
        lib.add_book("Quiet Nights", "", 100, owner="")
        with self.assertRaises(LibraryError):
            lib._book("Quiet")


class ReadingAndProgressTests(LibraryTestCase):
    def setUp(self):
        super().setUp()
        self.lib = self.make()
        self.lib.add_person("Dana")
        self.lib.add_person("Rey")
        self.lib.add_book("Tiny Treatise", "Writer", 120, owner="Dana")
        self.book = self.lib.state["books"][0]

    def test_set_reading_switch_resets_progress(self):
        self.lib.add_book("Second Book", "", 80, owner="")
        self.lib.set_reading("Dana", "b_001")
        self.lib.update_progress("Dana", 50)
        self.lib.set_reading("Dana", "Second Book")
        self.assertEqual(self.lib.state["people"]["Dana"]["pages_read"], 0)

    def test_progress_beyond_end_rejected(self):
        self.lib.set_reading("Dana", "Tiny Treatise")
        with self.assertRaises(LibraryError):
            self.lib.update_progress("Dana", 121)

    def test_reaching_end_reports_finished(self):
        self.lib.set_reading("Dana", "Tiny Treatise")
        message = self.lib.update_progress("Dana", 120)
        self.assertIn("finished", message.lower())

    def test_update_progress_without_current_book(self):
        with self.assertRaises(LibraryError):
            self.lib.update_progress("Rey", 5)

    def test_progress_persists(self):
        self.lib.set_reading("Dana", "Tiny Treatise")
        self.lib.update_progress("Dana", 42)
        reloaded = self.make()
        self.assertEqual(reloaded.state["people"]["Dana"]["pages_read"], 42)


class BookmarkTests(LibraryTestCase):
    def setUp(self):
        super().setUp()
        self.lib = self.make()
        self.lib.add_person("Fern")
        self.lib.add_book("The Interrupted Tale", "", 200, owner="")

    def test_bookmark_requires_current_book(self):
        with self.assertRaises(LibraryError):
            self.lib.set_bookmark("Fern", 17, "right before the reunion")

    def test_bookmark_set_list_clear(self):
        self.lib.set_reading("Fern", "The Interrupted Tale")
        message = self.lib.set_bookmark("Fern", 17, "right before the reunion")
        self.assertIn("To-be-continued", message)
        listing = self.lib.list_bookmarks()
        self.assertIn("Fern", listing)
        self.assertIn("page 17/200", listing)
        self.assertIn("right before the reunion", listing)
        self.lib.clear_bookmark("Fern")
        listing = self.lib.list_bookmarks()
        self.assertIn("No bookmarks", listing)

    def test_bookmark_past_end_rejected(self):
        self.lib.set_reading("Fern", "The Interrupted Tale")
        with self.assertRaises(LibraryError):
            self.lib.set_bookmark("Fern", 201)

    def test_text_length_limits(self):
        self.lib.set_reading("Fern", "The Interrupted Tale")
        with self.assertRaises(LibraryError):
            self.lib.set_bookmark("Fern", 5, "x" * 500)
        with self.assertRaises(LibraryError):
            self.lib.add_book("T" * 500, "", 10, owner="")


class LendingTests(LibraryTestCase):
    def setUp(self):
        super().setUp()
        self.lib = self.make()
        self.lib.add_person("Dana")
        self.lib.add_person("Rey")
        self.lib.add_book("Circle Book", "", 80, owner="Dana")
        self.lib.add_book("Square Book", "", 130, owner="Rey")

    def test_lend_and_return(self):
        message = self.lib.lend("Circle Book", "Rey")
        self.assertIn("now with Rey", message)
        self.assertLessEqual(len(self.lib.swap_grid()), 10000)
        self.assertIn("Rey", self.lib.swap_grid())
        self.assertIn("[loaned]", self.lib.swap_grid())
        back = self.lib.return_book("Circle Book")
        self.assertIn("came back from Rey", back)

    def test_cannot_lend_to_owner(self):
        with self.assertRaises(LibraryError):
            self.lib.lend("Circle Book", "Dana")

    def test_return_not_loaned_rejected(self):
        with self.assertRaises(LibraryError):
            self.lib.return_book("Circle Book")

    def test_return_from_wrong_holder_rejected(self):
        self.lib.lend("Circle Book", "Rey")
        with self.assertRaises(LibraryError):
            self.lib.return_book("Circle Book", from_person="Dana")

    def test_swap_grid_shows_holders(self):
        self.lib.lend("Circle Book", "Rey")
        grid = self.lib.swap_grid()
        self.assertIn("Circle Book", grid)
        self.assertIn("Rey", grid)
        self.assertIn("Dana", grid)


class ShortReadsTests(LibraryTestCase):
    def setUp(self):
        super().setUp()
        self.lib = self.make()
        self.lib.add_person("Dana")
        self.lib.add_book("Slim Volume", "", 80, owner="")
        self.lib.add_book("Medium Read", "", 250, owner="")
        self.lib.add_book("Doorstop", "", 900, owner="")

    def test_filters_by_pages_and_excludes_current_reads(self):
        self.lib.add_book("Currently Reading", "", 60, owner="")
        self.lib.set_reading("Dana", "Currently Reading")
        result = self.lib.suggest_short_reads(300)
        self.assertIn("Slim Volume", result)
        self.assertIn("Medium Read", result)
        self.assertNotIn("Doorstop", result)
        self.assertNotIn("Currently Reading", result)

    def test_respects_limit(self):
        result = self.lib.suggest_short_reads(900, limit=2)
        self.assertEqual(result.count(" - "), 2)

    def test_bad_limits_rejected(self):
        with self.assertRaises(LibraryError):
            self.lib.suggest_short_reads(100, limit=0)
        with self.assertRaises(LibraryError):
            self.lib.suggest_short_reads(0)

    def test_first_page_counts(self):
        self.lib.add_book("Page One Hundred", "", 100, owner="")
        result = self.lib.suggest_short_reads(100)
        self.assertIn("Page One Hundred", result)
        second = self.lib.suggest_short_reads(99)
        self.assertNotIn("Page One Hundred", second)


class StorageAndBackupTests(LibraryTestCase):
    def test_persistence_across_instances(self):
        lib = self.make()
        lib.add_person("Dana")
        lib.add_book("Kept Book", "", 99, owner="")
        reloaded = self.make()
        self.assertEqual([b["title"] for b in reloaded.books], ["Kept Book"])
        self.assertEqual(reloaded.people, ["Dana"])

    def test_auto_backup_created_and_rotated(self):
        lib = self.make(keep_backups=2)
        lib.add_person("A")
        lib.add_person("B")
        lib.add_person("C")
        backups = list((self.data_dir / BACKUPS_DIRNAME).glob("*.bak"))
        self.assertTrue(backups, "expected backups directory to fill")
        self.assertLessEqual(len(backups), 2)
        self.assertGreaterEqual(len(backups), 1)

    def test_backup_regenerates_state(self):
        lib = self.make(keep_backups=3)
        lib.add_person("Remember Me")
        reloaded = self.make(keep_backups=3)
        self.assertIn("Remember Me", reloaded.people)

    def test_corrupt_file_raises_clear_error(self):
        lib = self.make()
        lib.add_person("Dana")
        lib.path.write_text("{not json")
        with self.assertRaises(LibraryError) as ctx:
            self.make()
        self.assertIn("valid JSON", str(ctx.exception))

    def test_corrupt_file_backup_survives(self):
        lib = self.make()
        lib.add_person("Dana")
        lib.add_person("Rey")
        lib.path.write_text("{definitely not json")
        with self.assertRaises(LibraryError):
            self.make()
        backups = list((self.data_dir / BACKUPS_DIRNAME).glob("*.bak"))
        self.assertTrue(backups)
        recovered = [b for b in backups if json.loads(b.read_text())["people"]]
        self.assertTrue(recovered)

    def test_invalid_structure_rejected(self):
        lib = self.make()
        lib.path.write_text(json.dumps({"people": [], "books": {}, "loans": []}))
        with self.assertRaises(LibraryError):
            self.make()


class SecurityTests(LibraryTestCase):
    def test_data_dir_rejects_parent_traversal(self):
        with self.assertRaises(LibraryError):
            Library("../outside")

    def test_data_dir_rejects_nul_byte(self):
        with self.assertRaises(LibraryError):
            Library("data\x00evil")

    def test_storage_name_rejects_dot_dot(self):
        with self.assertRaises(LibraryError):
            self.make(storage_name="../evil.json")

    def test_storage_name_rejects_subdirectory(self):
        with self.assertRaises(LibraryError):
            self.make(storage_name="sub/dir.json")

    def test_storage_name_rejects_dot_and_dotdot(self):
        with self.assertRaises(LibraryError):
            self.make(storage_name=".")
        with self.assertRaises(LibraryError):
            self.make(storage_name="..")

    def test_storage_name_rejects_backslash(self):
        with self.assertRaises(LibraryError):
            self.make(storage_name="..\\evil.json")

    def test_storage_name_rejects_nul_byte(self):
        with self.assertRaises(LibraryError):
            self.make(storage_name="file\x00.json")

    def test_symlink_escape_rejected(self):
        lib = self.make()
        lib.add_person("Dana")
        outside = self.base / "outside.json"
        outside.write_text(json.dumps(new_state()))
        link = self.data_dir / "linked.json"
        link.symlink_to(outside)
        with self.assertRaises(LibraryError):
            Library(self.data_dir, storage_name="linked.json")

    def test_moved_storage_file_rejected_on_reload(self):
        lib = self.make(storage_name="library.json")
        lib.add_person("Dana")
        moved = self.base / "moved.json"
        shutil.move(lib.path, moved)
        link = self.data_dir / "library.json"
        link.symlink_to(moved)
        with self.assertRaises(LibraryError):
            Library(self.data_dir)

    def test_names_nul_byte_rejected(self):
        lib = self.make()
        with self.assertRaises(LibraryError):
            lib.add_person("Da\x00na")

    def test_names_whitespace_only_rejected(self):
        lib = self.make()
        with self.assertRaises(LibraryError):
            lib.add_person("   ")

    def test_names_trimmed(self):
        lib = self.make()
        lib.add_person("  Dana  ")
        reloaded = self.make()
        self.assertEqual(reloaded.people, ["Dana"])
        self.assertIn("Dana", reloaded.people)


if __name__ == "__main__":
    unittest.main()
