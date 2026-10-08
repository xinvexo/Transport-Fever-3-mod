"""Exercise packaging and replacement installs without touching the game."""

import json
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from tools.package_mod import BASE_RESOURCES, MOD_RESOURCES, ROOT, ModPackage
from tools import package_mod


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


class PackageCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tf3-package-cli-tests-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / "repository"
        self.parent = self.directory / "game mods"
        for name, resources in MOD_RESOURCES.items():
            source = self.root / name
            PackageTests.write(source / "mod.json", json.dumps({"modId": f"xin_{name}_1"}))
            PackageTests.write(source / "content/script.lua", f"return '{name}'")
            PackageTests.write(source / "_metadata/modinfo.json", "{}")
            if "strings.json" in resources:
                PackageTests.write(source / "strings.json", "{}")

    def run_cli(self, arguments):
        output = StringIO()
        with patch.object(package_mod, "ROOT", self.root), redirect_stdout(output), redirect_stderr(output):
            package_mod.main(arguments)
        return output.getvalue()

    def assert_installed(self, names):
        self.assertEqual({path.name for path in self.parent.iterdir()}, {f"xin_{name}_1" for name in names})
        for name in MOD_RESOURCES:
            archive = self.root / name / "dist" / f"xin_{name}_1.zip"
            self.assertEqual(archive.exists(), name in names)
            if name in names:
                self.assertEqual((self.parent / f"xin_{name}_1/content/script.lua").read_text(encoding="utf-8"),
                                 f"return '{name}'")

    def test_omitting_mod_selection_installs_all_mods(self):
        self.run_cli(["--install", str(self.parent)])
        self.assert_installed(set(MOD_RESOURCES))

    def test_named_selection_installs_only_requested_mods(self):
        self.run_cli(["--mods", "auto_signal", "tidy_fields", "--install", str(self.parent)])
        self.assert_installed({"auto_signal", "tidy_fields"})

    def test_existing_single_mod_command_remains_supported(self):
        self.run_cli(["auto_signal", "--install", str(self.parent)])
        self.assert_installed({"auto_signal"})

    def test_positional_selection_can_straddle_install_option(self):
        self.run_cli(["auto_signal", "--install", str(self.parent), "station_rows"])
        self.assert_installed({"auto_signal", "station_rows"})

    def test_repeated_selection_processes_each_mod_once(self):
        output = self.run_cli(["--install", str(self.parent), "--mods", "auto_signal", "auto_signal",
                               "--mods", "tidy_fields"])
        self.assert_installed({"auto_signal", "tidy_fields"})
        self.assertEqual(output.count("Packaged:"), 2)
        self.assertEqual(output.count("Installed:"), 2)

    def test_invalid_or_conflicting_selection_has_no_filesystem_side_effects(self):
        for arguments in (["--mods", "auto_signal", "unknown"], ["auto_signal", "unknown"],
                          ["auto_signal", "--mods", "tidy_fields"], ["--mods"]):
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit) as error:
                self.run_cli([*arguments, "--install", str(self.parent)])
            self.assertEqual(error.exception.code, 2)
            self.assertFalse(self.parent.exists())
            self.assertEqual(list(self.root.glob("*/dist")), [])

    def test_no_arguments_packages_all_without_installing(self):
        self.run_cli([])
        self.assertFalse(self.parent.exists())
        for name in MOD_RESOURCES:
            self.assertTrue((self.root / name / "dist" / f"xin_{name}_1.zip").is_file())


if __name__ == "__main__":
    unittest.main()
