"""Load the real construction resources without any custom GUI objects."""
import os
from pathlib import Path
import re
import struct
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
        self.lua.globals()['_'] = lambda value: value
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
        constructions = sorted(CONTENT.glob('*.con.lua'))
        self.assertEqual([path.name for path in constructions], ['lowered_loop.con.lua', 'raised_loop.con.lua'])
        for path in constructions:
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
            self.assertEqual(definition.description.icon, kind + '_loop.tga')
            self.assertEqual(definition.description.previewIcon, kind + '_loop_preview.tga')
            keys = [p.key for p in definition.params.values()]
            self.assertEqual(keys, ['trackType', 'trackType', 'catenary'] +
                             (['bridgeType'] * 2 + ['bridgeTypeModern'] * 3 if kind == 'raised' else []))
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

    def test_bridge_choice_images_match_built_resource_in_each_era(self):
        definition = self.resource('raised_loop.con.lua')
        bridge_params = [p for p in definition.params.values() if p.key.startswith('bridgeType')]
        expected = {
            1939: ['trestle', 'stone'],
            1940: ['trestle', 'stone', 'steel', 'suspension'],
            1969: ['trestle', 'stone', 'steel', 'suspension'],
            1970: ['stone', 'steel', 'concrete', 'suspension'],
            1999: ['stone', 'steel', 'concrete', 'suspension'],
            2000: ['stone', 'steel', 'concrete', 'suspension', 'cable'],
            2009: ['stone', 'steel', 'concrete', 'suspension', 'cable'],
            2010: ['stone', 'steel', 'concrete', 'suspension', 'cable', 'tarch'],
        }
        stable_values = {}
        for year, names in expected.items():
            visible = [p for p in bridge_params if (p.yearFrom == 0 or p.yearFrom <= year)
                       and (p.yearTo == 0 or year < p.yearTo)]
            self.assertEqual(len(visible), 1)
            param = visible[0]
            self.assertEqual(param.uiType, 'IconButton')
            self.assertEqual(param.location, 'Toolbar')
            self.assertEqual(param.displayMode, 'Compact')
            # Native IconButton maps the stored numeric value back to its icon.
            # The optional images callback instead takes a raw index; omit it.
            self.assertIsNone(param.images)
            self.assertEqual(len(param.tooltips), len(names))
            self.assertEqual(param.numbers[param.defaultIndex], 1)
            for index, name in enumerate(names, 1):
                resource = '::/infrastructure/bridge/' + name
                self.assertEqual(param['values'][index], resource + '.tga')
                value = param.numbers[index]
                self.assertEqual(stable_values.setdefault(name, value), value)
                bridge = self.build('raised', {param.key: value}).edgeLists[2]
                self.assertEqual(bridge.edgeTypeName, resource + '.bridge')
                self.assertEqual(self.build('lowered', {param.key: value}).edgeLists[2].edgeType, 'TUNNEL')
        for value in (None, 0, -1, 100, 1.5, 'steel'):
            params = {} if value is None else {'bridgeType': value}
            self.assertEqual(self.build('raised', params).edgeLists[2].edgeTypeName,
                             '::/infrastructure/bridge/stone.bridge')

    def test_retired_bridge_selection_resets_without_changing_saved_construction(self):
        saved = {'bridgeType': 2}
        definition = self.resource('raised_loop.con.lua')
        active = [p for p in definition.params.values() if p.key.startswith('bridgeType')
                  and p.yearFrom <= 1970 and (p.yearTo == 0 or 1970 < p.yearTo)]
        self.assertEqual(len(active), 1)
        param = active[0]
        # Native construction UI restores by key, or uses numbers[defaultIndex].
        current = {param.key: saved.get(param.key, param.numbers[param.defaultIndex])}
        self.assertEqual(self.build('raised', current).edgeLists[2].edgeTypeName,
                         '::/infrastructure/bridge/stone.bridge')
        self.assertEqual(self.build('raised', saved).edgeLists[2].edgeTypeName,
                         '::/infrastructure/bridge/trestle.bridge')

    def test_menu_images_use_native_dimensions_and_transparent_icons(self):
        for kind in ('raised', 'lowered'):
            definition = self.resource(kind + '_loop.con.lua')
            for field, size in (('icon', (240, 150)), ('previewIcon', (720, 405))):
                filename = definition.description[field].replace('.tga', '@2x.tga')
                header = (CONTENT / filename).read_bytes()[:18]
                self.assertEqual(struct.unpack_from('<HH', header, 12), size)
                if field == 'icon':
                    self.assertEqual(header[16], 32)
                    self.assertEqual(header[17] & 15, 8)

    def test_connected_loop_junctions_short_mainline_stubs_and_four_snap_ends(self):
        for kind, structure in (('raised', 'BRIDGE'), ('lowered', 'TUNNEL')):
            with self.subTest(kind=kind):
                result = self.build(kind)
                groups = list(result.edgeLists.values())
                self.assertEqual([g.edgeType or 'NORMAL' for g in groups], ['NORMAL', structure, 'NORMAL', 'NORMAL'])
                self.assertEqual(len(result.models), 0)
                self.assertEqual(len(result.groundFaces), 0)
                previous = None
                snap_positions = []
                adjacency, edges = {}, set()
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
                        if group != groups[-1] and previous is not None:
                            np.testing.assert_allclose(previous[0], p0, atol=1e-8)
                            np.testing.assert_allclose(previous[1], t0/np.linalg.norm(t0), atol=1e-8)
                        previous = p1, t1/np.linalg.norm(t1)
                        a, b = tuple(np.round(p0, 7)), tuple(np.round(p1, 7))
                        edge = tuple(sorted((a, b)))
                        self.assertNotIn(edge, edges, 'Shared mainline edges must not be duplicated')
                        edges.add(edge)
                        adjacency.setdefault(a, set()).add(b)
                        adjacency.setdefault(b, set()).add(a)
                self.assertEqual(len(snap_positions), 4)
                for x in (-2.5, 2.5):
                    self.assertEqual(len(adjacency[(x, 0., 0.)]), 3, 'A real turnout joins each through track to the loop')
                    ends = [p for p in snap_positions if p[0] == x]
                    self.assertEqual(len(ends), 2)
                    self.assertEqual(ends[0][1:], [-25., 0.])
                    self.assertEqual(ends[1][1], 25)
                    self.assertEqual(ends[1][2], 0)
                self.assertEqual(sum(len(v) == 1 for v in adjacency.values()), 4)
                self.assertEqual(sum(len(v) == 3 for v in adjacency.values()), 2)
                seen, pending = set(), [next(iter(adjacency))]
                while pending:
                    node = pending.pop()
                    if node not in seen:
                        seen.add(node)
                        pending.extend(adjacency[node] - seen)
                self.assertEqual(seen, set(adjacency), 'Every port and branch belongs to one connected network')
                for i in (1, 3, 5, 7):
                    start, end = groups[-1].edges[i], groups[-1].edges[i + 1]
                    self.assertEqual(start[1][1], end[1][1])
                    self.assertEqual(start[1][3], 0)
                    self.assertEqual(end[1][3], 0)
                    self.assertEqual(start[2][1], 0)
                    self.assertEqual(start[2][3], 0)
                self.assertEqual(groups[1].edgeTypeName, '::/infrastructure/bridge/stone.bridge' if kind == 'raised'
                                 else '::/infrastructure/tunnel/tunnel_a.tunnel')

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
            hud = archive.read('gui/construction/construction_desc_hud_icons.script.tl').decode('utf-8-sig')
            self.assertIn('configureTrackConstructionHudIconsFn', hud)
        for archive_name, resource in (('bridge', 'stone.bridge.lua'), ('tunnel', 'tunnel_a.tunnel.lua')):
            with ZipFile(GAME / f'base/content/infrastructure/{archive_name}.zip') as archive:
                self.assertIn(f'{archive_name}/{resource}', archive.namelist())

    @unittest.skipUnless(GAME is not None and (GAME / 'base/content/infrastructure/bridge.zip').is_file(),
                         'set TF3_GAME_DIR for native resource checks')
    def test_bridge_catalog_matches_native_rail_carriers_and_availability(self):
        definition = self.resource('raised_loop.con.lua')
        with ZipFile(GAME / 'base/content/infrastructure/bridge.zip') as archive:
            for param in definition.params.values():
                if not param.key.startswith('bridgeType'):
                    continue
                for icon in param['values'].values():
                    filename = icon.removeprefix('::/infrastructure/')
                    self.assertIn(filename, archive.namelist())
                    source = archive.read(filename.replace('.tga', '.bridge.lua')).decode('utf-8-sig')
                    carriers = re.search(r'carriers\s*=\s*\{([^}]+)\}', source).group(1)
                    self.assertIn('"RAIL"', carriers)
                    availability = re.search(r'availability\s*=\s*\{([^}]+)\}', source).group(1)
                    year_from = int(re.search(r'yearFrom\s*=\s*(-?\d+)', availability).group(1))
                    year_to = int(re.search(r'yearTo\s*=\s*(-?\d+)', availability).group(1))
                    self.assertLessEqual(year_from, param.yearFrom)
                    if year_to:
                        self.assertGreater(param.yearTo, 0)
                        self.assertLessEqual(param.yearTo, year_to)


if __name__ == '__main__':
    unittest.main()
