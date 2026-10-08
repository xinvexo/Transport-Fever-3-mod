"""Retain old save resources without performing vehicle renaming."""

from pathlib import Path
import unittest

from lupa.lua52 import LuaRuntime


CONTENT = Path(__file__).resolve().parents[1] / "content/line_vehicle_colors"


class RetiredNamingTests(unittest.TestCase):
    def test_old_resource_no_longer_registers_updates(self):
        lua = LuaRuntime()
        lua.execute((CONTENT / "names.gs.lua").read_text(encoding="utf-8"))
        self.assertIsNone(lua.globals().data().updateScript)

    def test_saved_update_reference_is_safe_and_does_not_access_the_game(self):
        lua = LuaRuntime()
        lua.execute("api = setmetatable({}, {__index=function() error('unexpected game access') end})")
        lua.execute((CONTENT / "names.script.lua").read_text(encoding="utf-8"))
        lua.globals().data().update(None, None, 0)


if __name__ == "__main__":
    unittest.main()
