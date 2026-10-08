"""Verify platform-independent encoding using a tiny temporary game archive."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from tidy_fields.tools import import_farms


class ImportTests(unittest.TestCase):
    def test_utf8_bom_and_crlf_input_produce_utf8_lf_source(self):
        with tempfile.TemporaryDirectory(prefix="tf3-import-tests-") as directory:
            root = Path(directory)
            game = root / "game"
            industries = game / "base/content/industries"
            industries.mkdir(parents=True)
            source = 'local generatedData = { name = "农场", model = "farm.mdl" }\r\n--End Generated'
            with ZipFile(industries / "farm.zip", "w") as archive:
                archive.writestr("farm/farm.script.lua", source.encode("utf-8-sig"))
            with patch.object(import_farms, "ROOT", root / "mod"), patch.object(import_farms, "FARMS", ("farm",)):
                import_farms.import_farms(game)
            output = (root / "mod/content/tidy_fields/generated/farm.script.lua").read_bytes()
            self.assertNotIn(b"\r", output)
            self.assertFalse(output.startswith(b"\xef\xbb\xbf"))
            text = output.decode("utf-8")
            self.assertIn('name = "农场"', text)
            self.assertIn('"::/industries/farm/farm.mdl"', text)


if __name__ == "__main__":
    unittest.main()
