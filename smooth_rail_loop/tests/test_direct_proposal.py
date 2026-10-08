"""Direct rail graph and float32 geometry checks, without a running engine."""
import math
from pathlib import Path
import struct
import unittest

from lupa.lua52 import LuaRuntime
import numpy as np

from test_geometry import samples

CONTENT = Path(__file__).resolve().parents[1] / 'content/rail_loop'
TRACK = '::/infrastructure/track/standard/standard_catenary.street_template'
BRIDGE = '::/infrastructure/bridge/steel.bridge'


def add_rail_api(lua):
    lua.globals().float32 = lambda n: struct.unpack('f', struct.pack('f', n))[0]
    lua.execute('''
      api=api or {};api.type=api.type or {}
      api.type.Vec3f={new=function(x,y,z) return {x=float32(x),y=float32(y),z=float32(z)} end}
      api.type.NodeAndEntity={new=function() return {comp={}} end}
      api.type.SegmentAndEntity={new=function() return {comp={}} end}
      api.type.SimpleProposal={new=function() return {streetProposal={},constructionsToAdd={}} end}
      api.type['enum']={BaseEdgeType={NORMAL=0,BRIDGE=1,TUNNEL=2},RoadType={TRACK=1}}
      local template={laneConfigs={{nativeLane=true}},streetStyle='native-rail-style'}
      api.res={streetTemplateRep={
        find=function(name) return name:find('.street_template',1,true) and 13 or -1 end,
        get=function(index) assert(index==13);return template end},
        bridgeTypeRep={find=function(name)
          if name=='::/infrastructure/bridge/steel.bridge' then return 17 end
          if name=='::/infrastructure/bridge/stone.bridge' then return 23 end
          return -1
        end},
        tunnelTypeRep={find=function(name)
          return name=='::/infrastructure/tunnel/tunnel_a.tunnel' and 29 or -1
        end}}
    ''')


def xyz(vec):
    return np.array([vec.x, vec.y, vec.z])


class DirectProposalTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        add_rail_api(self.lua)
        self.api = self.lua.globals().api
        self.geometry = self.lua.execute((CONTENT / 'prefab_geometry.lua').read_text(encoding='utf-8'))
        self.terrain = self.lua.execute((CONTENT / 'terrain_plan.lua').read_text(encoding='utf-8'))
        self.placement = self.lua.execute((CONTENT / 'placement.lua').read_text(encoding='utf-8'))

    def build(self, kind, rotation, ground, center=(5471.5884, 4836.2344, 23.75878)):
        original, _ = self.geometry.network(kind)
        pose = self.terrain.pose(*center, rotation)
        plan = self.terrain.sample(original, pose, ground)
        segments = self.terrain.joinShortEdges(self.terrain.apply(original, plan))
        return segments, pose, self.placement.makeProposal(self.api, segments, pose, TRACK, BRIDGE)

    def test_graph_shares_junction_and_material_boundary_ids_in_every_pose(self):
        terrains = [lambda x, y: 23.75878, lambda x, y: -60., lambda x, y: 90.,
                    lambda x, y: 23.75878 + .65*(x-5471.5884) + .2*(y-4836.2344)]
        seen_types = set()
        for kind in ('raised', 'lowered'):
            for rotation in (0, .713, math.pi / 2):
                for ground in terrains:
                    with self.subTest(kind=kind, rotation=rotation, ground=ground):
                        segments, pose, proposal = self.build(kind, rotation, ground)
                        self.assertEqual(len(proposal.constructionsToAdd), 0)
                        nodes = {n.entity: n for n in proposal.streetProposal.nodesToAdd.values()}
                        edges = list(proposal.streetProposal.edgesToAdd.values())
                        ids = list(nodes) + [e.entity for e in edges]
                        self.assertEqual(len(ids), len(set(ids)))
                        self.assertTrue(all(i < 0 for i in ids))
                        self.assertEqual(len(nodes), len({tuple(xyz(n.comp.position)) for n in nodes.values()}))
                        self.assertEqual(len(edges), len(segments))
                        tags, directions, adjacency = {}, {}, {i: set() for i in nodes}
                        for source, edge in zip(segments.values(), edges):
                            c = edge.comp
                            seen_types.add(c.type)
                            self.assertEqual(c.type, {'NORMAL': 0, 'BRIDGE': 1, 'TUNNEL': 2}[source.kind])
                            self.assertEqual(c.typeIndex, {'NORMAL': 0, 'BRIDGE': 17, 'TUNNEL': 29}[source.kind])
                            self.assertEqual(edge.type, 1)
                            self.assertEqual(c.roadTemplate, TRACK)
                            self.assertEqual(c.roadType, 1)
                            self.assertEqual(c.roadStyle, 'native-rail-style')
                            self.assertTrue(c.laneConfigs[1].nativeLane)
                            adjacency[c.node0].add(c.node1)
                            adjacency[c.node1].add(c.node0)
                            for tag, node_id, pos in ((source.tag0, c.node0, c.position0),
                                                      (source.tag1, c.node1, c.position1)):
                                self.assertEqual(tags.setdefault(tag, node_id), node_id)
                                np.testing.assert_array_equal(xyz(pos), xyz(nodes[node_id].comp.position))
                            for tag, tangent in ((source.tag0, c.tangent0), (source.tag1, c.tangent1)):
                                direction = xyz(tangent) / np.linalg.norm(xyz(tangent))
                                previous = directions.setdefault(tag, direction)
                                if np.dot(previous, direction) < 0:
                                    direction = -direction
                                np.testing.assert_allclose(previous, direction, atol=1e-6)
                        self.assertEqual(len(tags), len(nodes))
                        degrees = [len(v) for v in adjacency.values()]
                        self.assertEqual(degrees.count(1), 4)
                        self.assertEqual(degrees.count(3), 2)
                        self.assertTrue(all(d in (1, 2, 3) for d in degrees))
                        for tag in ('junction:left', 'junction:right'):
                            self.assertEqual(len(adjacency[tags[tag]]), 3)
                        visited, queue = set(), [next(iter(nodes))]
                        while queue:
                            current = queue.pop()
                            if current not in visited:
                                visited.add(current)
                                queue.extend(adjacency[current] - visited)
                        self.assertEqual(visited, set(nodes))
        self.assertEqual(seen_types, {0, 1, 2})

    def test_short_world_space_edges_keep_grade_radius_and_shape_after_float32(self):
        shortest = math.inf
        for kind in ('raised', 'lowered'):
            for rotation in (0, .713, math.pi / 2):
                ground = lambda x, y: 23.75878 + .65*(x-5471.5884) + .2*(y-4836.2344)
                segments, pose, proposal = self.build(kind, rotation, ground)
                for source, edge in zip(segments.values(), proposal.streetProposal.edgesToAdd.values()):
                    c = edge.comp
                    native = self.lua.table_from({
                        'p0': xyz(c.position0).tolist(), 'p1': xyz(c.position1).tolist(),
                        't0': xyz(c.tangent0).tolist(), 't1': xyz(c.tangent1).tolist()}, recursive=True)
                    points, _, radii, grades = samples(native, 65)
                    shortest = min(shortest, float(np.linalg.norm(points[-1]-points[0])))
                    self.assertLess(float(grades.max()), .085)
                    self.assertGreater(float(radii.min()), 55)
                    for i in range(0, 65, 8):
                        point, _ = self.terrain.point(source, i / 64)
                        expected = list(self.terrain.world(point, pose).values())
                        np.testing.assert_allclose(points[i], expected, atol=.001, rtol=0)
                prepared = self.lua.table_from({'proposal': {
                    'addedNodes': proposal.streetProposal.nodesToAdd,
                    'addedSegments': proposal.streetProposal.edgesToAdd}}, recursive=True)
                issue, stats = self.placement.checkPrepared(prepared)
                self.assertIsNone(issue)
                self.assertEqual(stats.duplicateNodes, 0)
        self.assertGreater(shortest, 1, 'The sub-metre divisions in these cases must be removed')

    def test_centimetre_split_regressions_preserve_joint_direction_and_native_radius(self):
        cases = [((5471.5884, 4836.2344, 23.75878), 4.0402157106598855,
                  .7073507731614579, -.43270888601480184),
                 ((-11985.038640765399, 15556.75897394857, 1252.8276231614932),
                  5.75748517670042, -.6273201790323326, .37535239251130115)]
        for center, rotation, dx, dy in cases:
            ground = lambda x, y: center[2] + dx*(x-center[0]) + dy*(y-center[1])
            segments, _, proposal = self.build('raised', rotation, ground, center)
            directions = {}
            for source, edge in zip(segments.values(), proposal.streetProposal.edgesToAdd.values()):
                c = edge.comp
                for tag, t in ((source.tag0, c.tangent0), (source.tag1, c.tangent1)):
                    direction = xyz(t)/np.linalg.norm(xyz(t))
                    old = directions.setdefault(tag, direction)
                    if np.dot(old, direction) < 0:
                        direction = -direction
                    np.testing.assert_allclose(old, direction, atol=1e-6)
                native = self.lua.table_from({
                    'p0': xyz(c.position0).tolist(), 'p1': xyz(c.position1).tolist(),
                    't0': xyz(c.tangent0).tolist(), 't1': xyz(c.tangent1).tolist()}, recursive=True)
                _, _, radii, grades = samples(native, 65)
                self.assertGreater(float(radii.min()), 55)
                self.assertLess(float(grades.max()), .085)

    def test_missing_resource_or_inconsistent_shared_endpoint_cannot_submit(self):
        segments, pose, _ = self.build('raised', 0, lambda x, y: -60.)
        with self.assertRaisesRegex(Exception, 'track template unavailable'):
            self.placement.makeProposal(self.api, segments, pose, 'missing', BRIDGE)
        with self.assertRaisesRegex(Exception, 'structure unavailable'):
            self.placement.makeProposal(self.api, segments, pose, TRACK, 'missing')
        segments[2].p0[3] += 1
        with self.assertRaisesRegex(Exception, 'Mismatched rail junction'):
            self.placement.makeProposal(self.api, segments, pose, TRACK, BRIDGE)

    def test_prepared_duplicate_nodes_are_rejected_even_with_valid_grade(self):
        _, _, proposal = self.build('raised', 0, lambda x, y: 23.75878)
        nodes = proposal.streetProposal.nodesToAdd
        nodes[len(nodes) + 1] = self.lua.table_from({'entity': -999,
            'comp': {'position': nodes[1].comp.position}}, recursive=True)
        prepared = self.lua.table_from({'proposal': {'addedNodes': nodes,
            'addedSegments': proposal.streetProposal.edgesToAdd}}, recursive=True)
        issue, stats = self.placement.checkPrepared(prepared)
        self.assertIn('重复接点', issue)
        self.assertEqual(stats.duplicateNodes, 1)


if __name__ == '__main__':
    unittest.main()
