from pathlib import Path
import unittest

from lupa.lua52 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]


class IntegrationTests(unittest.TestCase):
    def test_native_menu_and_proposal_lifecycle(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().MOD = (ROOT / 'content/rail_loop').as_posix()
        lua.execute((ROOT / 'tests/integration.lua').read_text(encoding='utf-8'))
