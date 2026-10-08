"""Exercise packaging and replacement installs without touching the game."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

from tools.package_mod import BASE_RESOURCES, MOD_RESOURCES, ROOT, ModPackage


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tf3-package-tests-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.source = self.directory / "source 模组"
        self.source.mkdir()
        self.mod_id = "xin_test_1"
        self.write(self.source / "mod.json", json.dumps({"modId": self.mod_id}))
        self.write(self.source / "strings.json", '{"zh_CN": {"name": "测试"}}')
        self.write(self.source / "content/script.lua", "return '测试'\n")
        self.write(self.source / "_metadata/modinfo.json", "{}")
        self.resources = (*BASE_RESOURCES, "strings.json")
        self.mod = ModPackage(self.source, self.resources)
        self.parent = self.directory / "game mods"

    @staticmethod
    def write(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_archive_and_install_use_the_same_filtered_runtime_files(self):
        for name in ("content/.DS_Store", "content/Thumbs.db", "content/Desktop.ini",
                     "content/._script.lua", "content/__pycache__/cache.pyc",
                     "_metadata/cache.pyo", "tests/test_dev.py", "README.md"):
            self.write(self.source / name, "excluded")
        self.write(self.source / "content/nested/extra.lua", "return {}")
        expected = {"mod.json", "strings.json", "content/script.lua",
                    "content/nested/extra.lua", "_metadata/modinfo.json"}
        archive = self.mod.package()
        with ZipFile(archive) as zipped:
            self.assertEqual(set(zipped.namelist()), {f"{self.mod_id}/{p}" for p in expected})
            self.assertEqual(zipped.read(f"{self.mod_id}/content/script.lua"),
                             (self.source / "content/script.lua").read_bytes())
        destination = self.mod.install(self.parent)
        self.assertEqual({p.relative_to(destination).as_posix()
                          for p in destination.rglob("*") if p.is_file()}, expected)

    def test_update_removes_stale_resources_but_preserves_unrelated_files(self):
        destination = self.mod.install(self.parent)
        self.write(destination / "content/obsolete.lua", "old")
        self.write(destination / "personal-note.txt", "keep")
        sibling = self.parent / "another_mod/content/script.lua"
        self.write(sibling, "keep sibling")
        self.write(self.source / "content/script.lua", "new")
        self.mod.install(self.parent)
        self.assertFalse((destination / "content/obsolete.lua").exists())
        self.assertEqual((destination / "content/script.lua").read_text(encoding="utf-8"), "new")
        self.assertEqual((destination / "personal-note.txt").read_text(encoding="utf-8"), "keep")
        self.assertEqual(sibling.read_text(encoding="utf-8"), "keep sibling")

    def test_unrecognized_destination_is_left_untouched(self):
        destination = self.parent / self.mod_id
        marker = destination / "content/keep.lua"
        self.write(marker, "keep")
        for manifest in ("not JSON", "[]", '{"modId": "someone_else_1"}'):
            with self.subTest(manifest=manifest):
                self.write(destination / "mod.json", manifest)
                with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
                    self.mod.install(self.parent)
                self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_missing_required_translation_does_not_package_or_change_install(self):
        destination = self.mod.install(self.parent)
        original = (destination / "strings.json").read_bytes()
        (self.source / "strings.json").unlink()
        with self.assertRaisesRegex(ValueError, "Missing mod resource"):
            self.mod.package()
        self.assertFalse((self.source / "dist").exists())
        with self.assertRaisesRegex(ValueError, "Missing mod resource"):
            self.mod.install(self.parent)
        self.assertEqual((destination / "strings.json").read_bytes(), original)

    def test_source_overlap_and_invalid_ids_are_rejected(self):
        for parent in (self.source, ROOT):
            with self.subTest(parent=parent), self.assertRaisesRegex(ValueError, "overlapping"):
                self.mod.install(parent)
        for mod_id in ("../escape", "a/b", "a\\b", "", None):
            self.write(self.source / "mod.json", json.dumps({"modId": mod_id}))
            with self.subTest(mod_id=mod_id), self.assertRaisesRegex(ValueError, "Invalid Mod ID"):
                ModPackage(self.source)

    def symlink(self, link, target):
        try:
            link.symlink_to(target, target_is_directory=target.is_dir())
        except OSError as error:
            self.skipTest(f"Symlink creation unavailable: {error}")

    def test_source_link_cannot_export_files_outside_the_mod(self):
        outside = self.directory / "outside.lua"
        self.write(outside, "private")
        self.symlink(self.source / "content/link.lua", outside)
        with self.assertRaisesRegex(ValueError, "linked resource"):
            self.mod.package()
        self.assertFalse((self.source / "dist").exists())

    def test_installed_file_link_is_rejected_before_any_replacement(self):
        destination = self.mod.install(self.parent)
        outside = self.directory / "outside.json"
        self.write(outside, "keep")
        (destination / "strings.json").unlink()
        self.symlink(destination / "strings.json", outside)
        self.write(self.source / "content/script.lua", "new")
        with self.assertRaisesRegex(ValueError, "linked resource"):
            self.mod.install(self.parent)
        self.assertEqual(outside.read_text(encoding="utf-8"), "keep")
        self.assertNotEqual((destination / "content/script.lua").read_text(encoding="utf-8"), "new")

    @unittest.skipUnless(os.name == "nt", "Windows junction test")
    def test_destination_junction_does_not_redirect_installation(self):
        outside = self.directory / "outside"
        self.write(outside / "mod.json", json.dumps({"modId": self.mod_id}))
        self.write(outside / "content/keep.lua", "keep")
        self.parent.mkdir()
        link = self.parent / self.mod_id
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                                capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        try:
            with self.assertRaisesRegex(ValueError, "linked destination"):
                self.mod.install(self.parent)
            self.assertEqual((outside / "content/keep.lua").read_text(encoding="utf-8"), "keep")
        finally:
            link.rmdir()  # Remove only the junction itself, not its target.

    def test_every_repository_mod_validates_and_legacy_cli_still_loads(self):
        for name, resources in MOD_RESOURCES.items():
            with self.subTest(mod=name):
                files = list(ModPackage(ROOT / name, resources).resource_files())
                self.assertTrue(files)
                result = subprocess.run(
                    [sys.executable, "-B", "-X", "utf8", str(ROOT / name / "tools/package_mod.py"), "--help"],
                    cwd=self.directory, capture_output=True, text=True, encoding="utf-8",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--install", result.stdout)


if __name__ == "__main__":
    unittest.main()
