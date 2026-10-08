"""Terrain classification of real Lua curves, and native-preview commit guards."""
import math
from pathlib import Path
import unittest

from lupa.lua52 import LuaRuntime
import numpy as np

import test_integration as integration
from test_geometry import samples

CONTENT = Path(__file__).resolve().parents[1] / 'content/rail_loop'


class TerrainTests(unittest.TestCase):
    def setUp(self):
        self.harness = integration.PrefabResourceTests()
        self.harness.setUp()
        self.lua = self.harness.lua
        self.geometry = self.lua.execute((CONTENT / 'prefab_geometry.lua').read_text(encoding='utf-8'))
        self.terrain = self.lua.execute((CONTENT / 'terrain_plan.lua').read_text(encoding='utf-8'))

    def test_flat_ridge_and_valley_choose_structures_independent_of_mode(self):
        for kind in ('raised', 'lowered'):
            edges, _ = self.geometry.network(kind)
            pose = self.terrain.pose(1000, 2000, 30, math.pi / 3)
            cases = [
                (lambda x, y: 30., {'NORMAL', 'BRIDGE'} if kind == 'raised' else {'NORMAL', 'TUNNEL'}),
                (lambda x, y: -40., {'BRIDGE'}),
                (lambda x, y: 100., {'TUNNEL'}),
                (lambda x, y: 30. + .65*(x-1000) + .2*(y-2000), {'NORMAL', 'BRIDGE', 'TUNNEL'}),
            ]
            for ground, expected in cases:
                with self.subTest(kind=kind, expected=expected):
                    plan = self.terrain.sample(edges, pose, ground)
                    planned = self.terrain.apply(edges, plan)
                    self.assertEqual({e.kind for e in planned.values()}, expected)
                    result = self.harness.build(kind, {'xinTerrainPlan': plan, 'xinGeometryVersion': 1})
                    self.assertEqual({g.edgeType or 'NORMAL' for g in result.edgeLists.values()}, expected)
                    self.assertEqual(sum(len(g.snapNodes) for g in result.edgeLists.values()), 4)
                    for group in result.edgeLists.values():
                        self.assertEqual(group.alignTerrain, group.edgeType is None)
                        self.assertEqual(len(group.freeNodes), 0)

    def test_world_transform_is_used_and_saved_plan_needs_no_live_terrain(self):
        edges, _ = self.geometry.network('raised')
        pose = self.terrain.pose(600, -900, 40, math.pi / 2)
        np.testing.assert_allclose(list(self.terrain.world(self.lua.table_from([10, 20, 3]), pose).values()),
                                   [580, -890, 43], atol=1e-8)
        def sample(x, y):
            self.assertLess(abs(x-600), 220)
            self.assertLess(abs(y+900), 100)
            return 40. + .65*(x-600)
        plan = self.terrain.sample(edges, pose, sample)
        saved = self.lua.table_from({'xinTerrainPlan': plan, 'xinGeometryVersion': 1})
        result = self.harness.resource('prefab_loop.script.lua').updateFn(
            self.lua.table_from({'kind': 'raised'}), saved)
        self.assertTrue(any(g.edgeType == 'BRIDGE' for g in result.edgeLists.values()))
        self.assertTrue(any(g.edgeType == 'TUNNEL' for g in result.edgeLists.values()))
        changed = self.terrain.sample(edges, pose, lambda x, y: 200.)
        self.assertFalse(self.terrain.equal(plan, changed))
        self.assertTrue(self.terrain.equal(plan, plan))

    def test_splitting_at_structure_entries_preserves_curves_and_junctions(self):
        for kind in ('raised', 'lowered'):
            edges, _ = self.geometry.network(kind)
            plan = self.terrain.sample(edges, self.terrain.pose(0, 0, 0, 0),
                                       lambda x, y: float(.65*x + .2*y))
            result = self.terrain.apply(edges, plan)
            positions = {}
            for edge in result.values():
                p, t, radius, grade = samples(edge, 101)
                self.assertGreater(float(radius.min()), 55)
                self.assertLess(float(grade.max()), .085)
                self.assertGreater(float(np.linalg.norm(p[-1] - p[0])), .009)
                for tag, point in ((edge.tag0, p[0]), (edge.tag1, p[-1])):
                    if tag in positions:
                        np.testing.assert_allclose(positions[tag], point, atol=1e-8)
                    positions[tag] = point
            np.testing.assert_allclose(positions['junction:left'], [-2.5, 0, 0], atol=1e-8)
            np.testing.assert_allclose(positions['junction:right'], [2.5, 0, 0], atol=1e-8)
            self.assertEqual(sum(bool(e.snap0) + bool(e.snap1) for e in result.values()), 4)

    def test_invalid_terrain_and_mismatched_plan_fail_without_flat_ground_fallback(self):
        edges, _ = self.geometry.network('raised')
        for value in (None, float('nan'), float('inf')):
            with self.assertRaises(Exception):
                self.terrain.sample(edges, self.terrain.pose(0, 0, 0, 0), lambda x, y: value)
        with self.assertRaises(Exception):
            self.terrain.apply(edges, self.lua.table())

    def test_short_entry_does_not_turn_a_long_bridge_or_tunnel_into_deep_earthwork(self):
        edge = self.lua.table_from({'p0': [0, 0, 0], 'p1': [12, 0, 0],
                                   't0': [12, 0, 0], 't1': [12, 0, 0]}, recursive=True)
        edges = self.lua.table_from([edge])
        pose = self.terrain.pose(1000, 2000, 30, 0)
        for ground, code in ((lambda x, y: 39.75 + .65*(x-1000), 3),
                             (lambda x, y: 25.25 - .65*(x-1000), 2)):
            plan = self.terrain.sample(edges, pose, ground)
            self.assertEqual(len(plan[1]), 2)
            self.assertEqual(plan[1][1][3], 1)
            self.assertAlmostEqual(plan[1][1][2] * 12, .25 / .65, places=5)
            self.assertEqual(plan[1][2][3], code)
            self.assertGreater((plan[1][2][2] - plan[1][2][1]) * 12, 10)

    def test_narrow_terrain_spike_is_not_silently_buried_inside_a_bridge(self):
        edge = self.lua.table_from({'p0': [0, 0, 0], 'p1': [12, 0, 0],
                                   't0': [12, 0, 0], 't1': [12, 0, 0]}, recursive=True)
        edges = self.lua.table_from([edge])
        ground = lambda x, y: -6 + 20 * max(0, 1-abs(x-1)/.8)
        plan = self.terrain.sample(edges, self.terrain.pose(0, 0, 0, 0), ground)
        self.assertEqual({piece[3] for piece in plan[1].values()}, {1, 2, 3})
        covering_peak = [piece for piece in plan[1].values() if piece[1] <= 1/12 <= piece[2]]
        self.assertEqual(len(covering_peak), 1)
        self.assertEqual(covering_peak[0][3], 3)

    def test_short_transition_keeps_full_preview_plan_for_native_validation(self):
        # Previously the 0.4m ground piece could neither be widened nor merged,
        # so the planner threw before it could create any preview proposal.
        edge = self.lua.table_from({'p0': [0, 0, 0], 'p1': [1.8, 0, 0],
                                   't0': [1.8, 0, 0], 't1': [1.8, 0, 0]}, recursive=True)
        edges = self.lua.table_from([edge])
        plan = self.terrain.sample(edges, self.terrain.pose(0, 0, 0, 0), lambda x, y: -4.6-x)
        self.assertEqual(len(plan[1]), 2)
        self.assertAlmostEqual(plan[1][1][2] * 1.8, .4, places=5)
        parts = self.terrain.apply(edges, plan)
        self.assertEqual([part.kind for part in parts.values()], ['NORMAL', 'BRIDGE'])
        np.testing.assert_allclose(list(parts[1].p1.values()), list(parts[2].p0.values()), atol=1e-9)
        np.testing.assert_allclose(list(parts[2].p1.values()), [1.8, 0, 0], atol=1e-9)

    def test_joining_short_edges_preserves_portals_turnouts_and_short_material_runs(self):
        for kind in ('raised', 'lowered'):
            network, _ = self.geometry.network(kind)
            plan = self.terrain.sample(network, self.terrain.pose(0, 0, 0, 0),
                                       lambda x, y: .65*x + .2*y)
            source = self.terrain.apply(network, plan)
            joined = self.terrain.joinShortEdges(source)
            self.assertLess(len(joined), len(source))
            def boundaries(edges):
                materials, positions, degrees = {}, {}, {}
                for edge in edges.values():
                    for tag, point in ((edge.tag0, edge.p0), (edge.tag1, edge.p1)):
                        materials.setdefault(tag, set()).add(edge.kind)
                        positions[tag] = list(point.values())
                        degrees[tag] = degrees.get(tag, 0) + 1
                return {tag: positions[tag] for tag in positions
                        if len(materials[tag]) > 1 or degrees[tag] != 2}
            self.assertEqual(boundaries(source), boundaries(joined))
        # A genuinely short bridge between ground tracks must not disappear.
        edge = self.lua.table_from({'p0': [0, 0, 0], 'p1': [12, 0, 0],
            't0': [12, 0, 0], 't1': [12, 0, 0], 'tag0': 'start', 'tag1': 'end'}, recursive=True)
        source = self.terrain.apply(self.lua.table_from([edge]),
            self.lua.table_from([[[0, .49, 1], [.49, .51, 2], [.51, 1, 1]]], recursive=True))
        joined = self.terrain.joinShortEdges(source)
        self.assertEqual(len(joined), 3)
        self.assertEqual(joined[2].kind, 'BRIDGE')


class PlacementTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().placement = self.lua.execute((CONTENT / 'placement.lua').read_text(encoding='utf-8'))

    def test_stale_hover_rotation_cancel_and_double_click_cannot_build(self):
        self.lua.execute('''
          local state = placement.session()
          local first = state:replace('position-a', {})
          assert(not state:take('position-a'))
          local second = state:replace('position-b-rotated', {})
          assert(not state:validated(first, {}, true))
          assert(not state:take('position-b-rotated'))
          local prepared = {}
          assert(state:validated(second, prepared, true))
          assert(not state:take('position-a'))
          assert(state:take('position-b-rotated') == prepared)
          assert(not state:take('position-b-rotated'))
          state:close()
          assert(not state:validated(second, {}, true))
          assert(not state:take('position-b-rotated'))
        ''')

    def test_engine_changed_grade_is_rejected_even_when_lua_design_was_valid(self):
        self.lua.execute('''
          local function edge(grade)
            return {type=1, comp={position0={x=0,y=0,z=0}, position1={x=0,y=100,z=grade*100},
              tangent0={x=0,y=100,z=grade*100}, tangent1={x=0,y=100,z=grade*100}}}
          end
          assert(not placement.checkPrepared({proposal={addedSegments={edge(.08)}}}))
          for _, grade in ipairs({.20156, .74879, .12546, .47240}) do
            assert(placement.checkPrepared({proposal={addedSegments={edge(grade)}}}))
          end
          assert(placement.checkPrepared({proposal={addedSegments={}}}))
        ''')

if __name__ == '__main__':
    unittest.main()
