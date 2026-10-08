"""Load the real construction resources without any custom GUI objects."""
import os
from pathlib import Path
import unittest
from zipfile import ZipFile

from lupa.lua52 import LuaRuntime
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content/rail_loop"
GAME = Path(os.environ["TF3_GAME_DIR"]).expanduser() if os.environ.get("TF3_GAME_DIR") else None

PARAM_UTIL = r"""
local M = {}
function M.makeTrackTypeDefaultParam()
  return {key='trackType', yearFrom=1930, yearTo=1980, values={'simple','standard'}}
end
function M.makeTrackTypeHighSpeedParam()
  return {key='trackType', yearFrom=1980, yearTo=0, values={'simple','standard','high_speed'}}
end
function M.makeTrackCatenaryParam()
  return {key='catenary', yearFrom=1921, yearTo=0, defaultIndex=2, values={'No','Yes'}}
end
function M.getRailTrackTypes(catenary)
  local result={}
  for _,name in ipairs({'simple','standard','high_speed'}) do
    result[#result+1]='::/infrastructure/track/'..name..'/'..name..(catenary and '_catenary' or '')..'.street_template'
  end
  return result
end
return M
"""


class PrefabResourceTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.cache = {'::/scripts/construction/param_util.tl': self.lua.execute(PARAM_UTIL)}
        def require(name):
            if name not in self.cache:
                prefix = 'xin_smooth_rail_loop_1::/rail_loop/'
                if not name.startswith(prefix):
                    raise AssertionError('Unexpected runtime dependency: ' + name)
                self.cache[name] = self.lua.execute((CONTENT / name[len(prefix):]).read_text(encoding='utf-8'))
            return self.cache[name]
        self.lua.globals().require = require

    def resource(self, name):
        self.lua.execute((CONTENT / name).read_text(encoding='utf-8'))
        return self.lua.globals().data()

    def build(self, kind, params=None):
        definition = self.resource(kind + '_loop.con.lua')
        update = self.resource('prefab_loop.script.lua').updateFn
        return update(definition.updateScript.params, self.lua.table_from(params or {}))

    def test_two_prefabs_enable_native_rail_constructions_category(self):
        visible = []
        for path in sorted(CONTENT.glob('*.con.lua')):
            definition = self.resource(path.name)
            for category in definition.menuCategory.categories.values():
                self.assertEqual(category.category, 'rail_constructions')
                visible.append(definition.description.name)
        self.assertEqual(set(visible), {'高架回环', '地下回环'})
        self.assertEqual(len(visible), 2)
        for kind in ('raised', 'lowered'):
            definition = self.resource(kind + '_loop.con.lua')
            self.assertEqual(definition.updateScript.fileName, 'prefab_loop.script@updateFn')
            self.assertEqual(definition.updateScript.params.kind, kind)
            self.assertEqual(definition.availability.yearFrom, 0)
            self.assertTrue(definition.heightAdjustable)
            self.assertEqual(definition.undergroundView, kind == 'lowered')
            self.assertEqual([p.key for p in definition.params.values()], ['trackType', 'trackType', 'catenary'])
            self.assertTrue(definition.configureHudIconsScript.fileName.endswith('@configureTrackConstructionHudIconsFn'))
        self.assertFalse(list(CONTENT.glob('dynamic_*')))
        self.assertFalse(list(CONTENT.glob('*.res.lua')), 'No dynamic UI plugin should remain active')

    def test_native_track_choices_and_explicit_template_override(self):
        for kind in ('raised', 'lowered'):
            for index, name in enumerate(('simple', 'standard', 'high_speed'), 1):
                for catenary in (1, 2):
                    with self.subTest(kind=kind, track=name, catenary=catenary):
                        result = self.build(kind, {'trackType': index, 'catenary': catenary})
                        expected = f"::/infrastructure/track/{name}/{name}{'_catenary' if catenary == 2 else ''}.street_template"
                        self.assertTrue(all(group.params.type == expected for group in result.edgeLists.values()))
        custom = 'third_party::/custom.street_template'
        result = self.build('raised', {'streetTemplate': custom})
        self.assertTrue(all(group.params.type == custom for group in result.edgeLists.values()))
        self.assertIn('/simple/', self.build('raised').edgeLists[1].params.type)

    def test_complete_connected_free_track_graph_and_two_snap_ends(self):
        for kind, structure in (('raised', 'BRIDGE'), ('lowered', 'TUNNEL')):
            with self.subTest(kind=kind):
                result = self.build(kind)
                groups = list(result.edgeLists.values())
                self.assertEqual([g.edgeType or 'NORMAL' for g in groups], ['NORMAL', structure, 'NORMAL'])
                self.assertEqual(len(result.models), 0)
                self.assertEqual(len(result.groundFaces), 0)
                previous = None
                snap_positions = []
                for group in groups:
                    self.assertEqual(group.type, 'TRACK')
                    self.assertEqual(group.alignTerrain, group.edgeType is None)
                    self.assertEqual(list(group.freeNodes.values()), list(range(len(group.edges))))
                    for index in group.snapNodes.values():
                        self.assertGreaterEqual(index, 0)
                        self.assertLess(index, len(group.edges))
                        snap_positions.append(list(group.edges[index+1][1].values()))
                    for i in range(1, len(group.edges)+1, 2):
                        start, end = group.edges[i], group.edges[i+1]
                        p0, p1 = np.array(list(start[1].values())), np.array(list(end[1].values()))
                        t0, t1 = np.array(list(start[2].values())), np.array(list(end[2].values()))
                        if previous is not None:
                            np.testing.assert_allclose(previous[0], p0, atol=1e-8)
                            np.testing.assert_allclose(previous[1], t0/np.linalg.norm(t0), atol=1e-8)
                        previous = p1, t1/np.linalg.norm(t1)
                np.testing.assert_allclose(snap_positions, [[-2.5, 0, 0], [2.5, 0, 0]], atol=1e-8)
                self.assertEqual(groups[1].edgeTypeName, '::/infrastructure/bridge/stone.bridge' if kind == 'raised'
                                 else '::/infrastructure/tunnel/tunnel_a.tunnel')

    def test_legacy_saved_construction_still_loads_with_original_parameters(self):
        definition = self.resource('loop.con.lua')
        self.assertEqual(len(definition.menuCategory.categories), 0)
        self.assertEqual(definition.updateScript.fileName, 'loop.script@updateFn')
        self.assertEqual(list(definition.updateScript.params.radii.values()), [160, 200, 240, 320, 400, 500])
        result = self.resource('loop.script.lua').updateFn(definition.updateScript.params, self.lua.table())
        points = [list(endpoint[1].values()) for group in result.edgeLists.values() for endpoint in group.edges.values()]
        self.assertAlmostEqual(max(p[0] for p in points)-min(p[0] for p in points), 480, delta=1)
        self.assertTrue(all(p[2] == 0 for p in points))

    @unittest.skipUnless(GAME is not None and (GAME / 'base/content/gui.zip').is_file(), 'set TF3_GAME_DIR for native resource checks')
    def test_native_category_icons_and_bridge_tunnel_resources_exist(self):
        with ZipFile(GAME / 'base/content/gui.zip') as archive:
            self.lua.globals()['_'] = lambda value: value
            self.lua.globals().resolve = lambda value: value
            self.lua.execute(archive.read('gui/construction/menu/menu_categories/category_rail_constructions.res.lua').decode('utf-8-sig'))
            category = self.lua.globals().data()
            self.assertEqual(category.data.menu, 'TRACKS')
            self.assertEqual(category.data.category, 'rail_constructions')
            self.assertIn('gui/construction/menu/menu_categories/category_rail_constructions@2x.tga', archive.namelist())
            for name in ('infrastructure_bridge_32', 'infrastructure_tunnel_32'):
                self.assertIn(f'gui/construction/build_control/{name}@2x.tga', archive.namelist())
            hud = archive.read('gui/construction/construction_desc_hud_icons.script.tl').decode('utf-8-sig')
            self.assertIn('configureTrackConstructionHudIconsFn', hud)
        for archive_name, resource in (('bridge', 'stone.bridge.lua'), ('tunnel', 'tunnel_a.tunnel.lua')):
            with ZipFile(GAME / f'base/content/infrastructure/{archive_name}.zip') as archive:
                self.assertIn(f'{archive_name}/{resource}', archive.namelist())


if __name__ == '__main__':
    unittest.main()
