import unittest
from collections import defaultdict
from pathlib import Path

from lupa.lua52 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]


class TrackWorld:
    def __init__(self, crossing_clearance=0):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.components = {}
        self.connections = defaultdict(list)
        self.street_connections = defaultdict(list)
        self.crossing_clearance = crossing_clearance
        self.owners = {}
        self.hosts = {}
        self.signals = {}
        self.lengths = {}
        self.lua.execute("""
            local function clone(value)
                if type(value) ~= "table" then return value end
                local copy = {}
                for key, item in pairs(value) do copy[key] = clone(item) end
                return copy
            end
            cloneBaseEdge = clone
            api = {
                type = {
                    ComponentType = setmetatable({}, {
                        __index = function(_, key) return key end
                    }),
                    enum = { EdgeObjectType = { SIGNAL = "signal" } },
                    Signal = { Type = {
                        SIGNAL = "path", ONE_WAY_SIGNAL = "one_way", WAYPOINT = "waypoint"
                    } },
                    EdgeId = { new = function(entity, index)
                        return { entity = entity, index = index }
                    end },
                    SegmentAndEntity = { new = function() return {} end },
                    SimpleProposal = { new = function() return { streetProposal = {} } end },
                    SimpleStreetProposal = {
                        EdgeObject = { new = function() return {} end }
                    },
                },
                engine = {
                    system = {
                        streetSystem = {}, streetConnectorSystem = {}, signalSystem = {}
                    },
                    util = { getPlayer = function() return 7 end },
                },
                res = { constructionRep = {} },
            }
        """)
        api = self.lua.globals().api
        api.engine.getComponent = lambda entity, kind: self.components.get((entity, kind))
        api.engine.system.streetSystem.getNodeTrackSegments = (
            lambda node: self.table(self.connections[node])
        )
        api.engine.system.streetSystem.getNodeStreetSegments = (
            lambda node: self.table(self.street_connections[node])
        )
        api.res.constructionRep.find = lambda name: 1
        api.res.constructionRep.get = lambda identifier: self.table({
            "edgeObject": {"minDistToCrossing": self.crossing_clearance}
        })
        api.engine.system.streetConnectorSystem.getConstructionEntityForEdge = (
            lambda edge: self.owners.get(edge, -1)
        )
        api.engine.system.streetSystem.getEdgeForEdgeObject = (
            lambda entity: self.hosts.get(entity, -1)
        )
        api.engine.system.signalSystem.getSignal = self.get_signal
        spacing = self.lua.execute((ROOT / "content/auto_signal/spacing.lua").read_text())
        self.lua.globals().ug_require = lambda path: spacing
        self.network = self.lua.execute((ROOT / "content/auto_signal/network.lua").read_text())

    def table(self, value):
        return self.lua.table_from(value, recursive=True)

    def add_edge(self, entity, node0, node1, length, owner=None):
        self.components[entity, "BASE_EDGE"] = self.table({
            "node0": node0, "node1": node1, "objects": [],
            "roadType": "TRACK", "roadTemplate": "standard_track",
            "tangent0": [length, 0, 0], "tangent1": [length, 0, 0],
        })
        self.components[entity, "BASE_EDGE"].clone = self.lua.globals().cloneBaseEdge
        self.components[entity, "PLAYER_OWNED"] = self.table({"player": 7})
        self.connections[node0].append(entity)
        self.connections[node1].append(entity)
        self.lengths[entity] = length
        self.set_transport_edges(entity, 1)
        if owner is not None:
            self.owners[entity] = owner

    def set_transport_edges(self, entity, count):
        self.components[entity, "TRANSPORT_NETWORK"] = self.table({
            "edges": [{"geometry": {"length": self.lengths[entity] / count}}
                      for _ in range(count)]
        })

    def add_signal(self, entity, edge, reversed=False, kind="path", fraction=0.25):
        index = 0
        while (edge, index, reversed) in self.signals:
            index += 1
        self.signals[edge, index, reversed] = entity
        current_count = len(self.components[edge, "TRANSPORT_NETWORK"].edges)
        self.set_transport_edges(edge, max(current_count, index + 1))
        self.hosts[entity] = edge
        self.components[entity, "EDGE_OBJECT"] = self.table({
            "param": fraction,
            "edgeObjectConstruction": "base::/infrastructure/signal/signal_path_a.con",
        })
        self.components[entity, "SIGNAL_LIST"] = self.table({"signals": [{"type": kind}]})
        self.add_object(entity, edge, "signal")

    def add_object(self, entity, edge, kind):
        objects = self.components[edge, "BASE_EDGE"].objects
        objects[len(objects) + 1] = self.table([entity, kind])

    def get_signal(self, edge_id, reversed):
        entity = self.signals.get((edge_id.entity, edge_id.index, reversed), -1)
        return self.table({"entity": entity, "index": 0})

    def plan(self, signal, minimum=300):
        result = self.network.plan(signal, minimum)
        if isinstance(result, tuple):
            raise AssertionError(f"Planning failed: {result[1]}")
        return result


def sequence(table):
    return [table[index] for index in range(1, len(table) + 1)]


def removals(plan):
    return {entity for step in sequence(plan.steps) for entity in sequence(step.remove)}


def layout(plan):
    return [(step.edge, step.left, tuple(sequence(step.positions)))
            for step in sequence(plan.steps)]


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.world = TrackWorld()

    def make_open_section(self):
        # The middle edge has opposite node order, while the route remains continuous.
        self.world.add_edge(101, 10, 20, 400)
        self.world.add_edge(102, 30, 20, 300)
        self.world.add_edge(103, 30, 40, 350)

    def test_corridor_follows_the_whole_section_with_mixed_node_order(self):
        self.make_open_section()
        for seed in (101, 102, 103):
            segments, closed = self.world.network.corridor(seed)
            self.assertFalse(closed)
            self.assertEqual([s.entity for s in sequence(segments)], [101, 102, 103])
            self.assertEqual([s.forward for s in sequence(segments)], [True, False, True])

    def test_junction_limits_the_selected_corridor(self):
        self.make_open_section()
        self.world.add_edge(104, 20, 50, 400)
        segments, closed = self.world.network.corridor(101)
        self.assertFalse(closed)
        self.assertEqual([s.entity for s in sequence(segments)], [101])

    def test_station_track_is_a_boundary_and_cannot_be_a_seed(self):
        self.make_open_section()
        self.world.owners[102] = 900
        segments, closed = self.world.network.corridor(101)
        self.assertFalse(closed)
        self.assertEqual([s.entity for s in sequence(segments)], [101])
        result, reason = self.world.network.corridor(102)
        self.assertIsNone(result)
        self.assertIn("construction", reason)

    def test_signal_replacement_respects_route_direction(self):
        self.make_open_section()
        self.world.add_signal(1001, 101, False, "one_way")
        self.world.add_signal(1002, 102, True)
        self.world.add_signal(1003, 103, False)
        self.world.add_signal(1101, 102, False)
        self.world.add_signal(1102, 103, True)
        plan = self.world.plan(1001)
        self.assertEqual(removals(plan), {1001, 1002, 1003})
        self.assertEqual([step.left for step in sequence(plan.steps)], [True, False, True])
        self.assertTrue(plan.oneWay)
        self.assertEqual(plan.count, 4)
        positions = []
        for step in sequence(plan.steps):
            for fraction in sequence(step.positions):
                if step.edge == 101:
                    positions.append(400 * fraction)
                elif step.edge == 102:
                    positions.append(400 + 300 * (1 - fraction))
                else:
                    positions.append(700 + 350 * fraction)
        self.assertAlmostEqual(positions[0], 10)
        self.assertAlmostEqual(positions[-1], 1040)
        for before, after in zip(positions, positions[1:]):
            self.assertGreaterEqual(after - before, 300)

    def test_layout_is_independent_of_the_clicked_signal(self):
        self.make_open_section()
        self.world.add_signal(1001, 101, False, fraction=0.2)
        self.world.add_signal(1002, 102, True, fraction=0.7)
        self.world.add_signal(1003, 103, False, fraction=0.9)
        expected = layout(self.world.plan(1001))
        self.assertEqual(layout(self.world.plan(1002)), expected)
        self.assertEqual(layout(self.world.plan(1003)), expected)

    def test_reversing_the_chosen_direction_replaces_the_other_signals(self):
        self.make_open_section()
        self.world.add_signal(1001, 101, False)
        self.world.add_signal(1002, 102, False)
        self.world.add_signal(1003, 103, True)
        plan = self.world.plan(1002)
        self.assertEqual(removals(plan), {1002, 1003})
        self.assertEqual([step.left for step in sequence(plan.steps)], [False, True, False])

    def test_loop_has_stable_layout_and_minimum_gap_across_the_seam(self):
        self.world.add_edge(101, 10, 20, 350)
        self.world.add_edge(102, 30, 20, 350)
        self.world.add_edge(103, 30, 10, 350)
        self.world.add_signal(1001, 101, False)
        self.world.add_signal(1002, 102, True)
        self.world.add_signal(1003, 103, False)
        for edge in (101, 102, 103):
            segments, closed = self.world.network.corridor(edge)
            self.assertTrue(closed)
            self.assertEqual(len(segments), 3)
        first = self.world.plan(1001)
        self.assertEqual(first.count, 3)
        self.assertEqual(layout(first), layout(self.world.plan(1002)))
        self.assertEqual(layout(first), layout(self.world.plan(1003)))
        positions = []
        for step in sequence(first.steps):
            for fraction in sequence(step.positions):
                if step.edge == 101:
                    positions.append(350 * fraction)
                elif step.edge == 102:
                    positions.append(350 + 350 * (1 - fraction))
                else:
                    positions.append(700 + 350 * fraction)
        gaps = [after - before for before, after in zip(positions, positions[1:])]
        gaps.append(1050 - positions[-1] + positions[0])
        self.assertTrue(all(gap >= 300 for gap in gaps))

    def test_short_section_places_one_signal_at_its_center(self):
        self.world.add_edge(101, 10, 20, 100)
        self.world.add_signal(1001, 101, fraction=0.1)
        plan = self.world.plan(1001)
        self.assertEqual(plan.count, 1)
        self.assertAlmostEqual(plan.steps[1].positions[1], 0.5)
        self.assertEqual(removals(plan), {1001})

    def test_road_crossing_clearance_is_kept_for_both_spacing_choices(self):
        # With only joint clearance, 226 m spacing puts a signal at 462 m,
        # just 2 m beyond the road crossing at 460 m.
        self.world.add_edge(101, 10, 20, 460)
        self.world.add_edge(102, 20, 30, 550)
        self.world.add_edge(103, 30, 40, 366)
        self.world.street_connections[20] = [9001, 9002]
        self.world.crossing_clearance = 20
        self.world.add_signal(1001, 101)
        offsets = {101: 0, 102: 460, 103: 1010}
        for minimum, expected_count in [(100, 14), (226, 6)]:
            with self.subTest(minimum=minimum):
                plan = self.world.plan(1001, minimum)
                positions = [
                    offsets[step.edge] + fraction * self.world.lengths[step.edge]
                    for step in sequence(plan.steps)
                    for fraction in sequence(step.positions)
                ]
                self.assertEqual(len(positions), expected_count)
                self.assertAlmostEqual(positions[0], 10)
                self.assertAlmostEqual(positions[-1], 1366)
                for position in positions:
                    self.assertGreaterEqual(abs(position - 460), 20 - 1e-8)
                for before, after in zip(positions, positions[1:]):
                    self.assertGreaterEqual(after - before, minimum - 1e-8)

    def test_crossing_clearance_extends_across_short_adjacent_segments(self):
        self.world.add_edge(101, 10, 20, 300)
        self.world.add_edge(102, 20, 30, 5)
        self.world.add_edge(103, 30, 40, 5)
        self.world.add_edge(104, 40, 50, 730)
        self.world.street_connections[20] = [9001, 9002]
        self.world.crossing_clearance = 35
        self.world.add_signal(1001, 104)
        offsets = {101: 0, 102: 300, 103: 305, 104: 310}
        plan = self.world.plan(1001, 100)
        positions = [
            offsets[step.edge] + fraction * self.world.lengths[step.edge]
            for step in sequence(plan.steps)
            for fraction in sequence(step.positions)
        ]
        self.assertEqual(len(positions), 10)
        self.assertAlmostEqual(positions[0], 10)
        self.assertAlmostEqual(positions[-1], 1030)
        for position in positions:
            self.assertGreaterEqual(abs(position - 300), 35 - 1e-8)
        for before, after in zip(positions, positions[1:]):
            self.assertGreaterEqual(after - before, 100 - 1e-8)

    def test_loop_crossing_clearance_wraps_across_the_section_origin(self):
        self.world.add_edge(101, 10, 20, 200)
        self.world.add_edge(102, 20, 30, 200)
        self.world.add_edge(103, 30, 10, 200)
        self.world.street_connections[10] = [9001, 9002]
        self.world.crossing_clearance = 150
        self.world.add_signal(1001, 101)
        offsets = {101: 0, 102: 200, 103: 400}
        plan = self.world.plan(1001, 100)
        positions = [
            offsets[step.edge] + fraction * self.world.lengths[step.edge]
            for step in sequence(plan.steps)
            for fraction in sequence(step.positions)
        ]
        self.assertEqual(len(positions), 4)
        for position in positions:
            self.assertGreaterEqual(min(position, 600 - position), 150 - 1e-8)
        gaps = [after - before for before, after in zip(positions, positions[1:])]
        gaps.append(600 - positions[-1] + positions[0])
        self.assertTrue(all(gap >= 100 - 1e-8 for gap in gaps))

    def test_two_arc_loop_has_the_same_layout_from_either_seed(self):
        self.world.add_edge(101, 10, 20, 525)
        self.world.add_edge(102, 10, 20, 525)
        upper = self.world.components[101, "BASE_EDGE"]
        lower = self.world.components[102, "BASE_EDGE"]
        upper.tangent0 = self.world.table({"x": 200, "y": 300, "z": 0})
        upper.tangent1 = self.world.table({"x": 200, "y": -300, "z": 0})
        lower.tangent0 = self.world.table({"x": 200, "y": -300, "z": 0})
        lower.tangent1 = self.world.table({"x": 200, "y": 300, "z": 0})
        self.world.add_signal(1001, 101, False)
        self.world.add_signal(1002, 102, True)
        first = self.world.plan(1001)
        second = self.world.plan(1002)
        self.assertEqual(first.count, 3)
        self.assertEqual(layout(first), layout(second))

    def test_proposal_preserves_reverse_signals_and_other_track_objects(self):
        self.world.add_edge(101, 10, 20, 700)
        self.world.add_signal(1001, 101, False, "one_way")
        self.world.add_signal(1002, 101, True)
        self.world.add_object(2001, 101, "other_object")
        plan = self.world.plan(1001)
        proposal = self.world.network.proposal(plan).streetProposal
        self.assertEqual(sequence(proposal.edgesToRemove), [101])
        self.assertEqual(sequence(proposal.edgeObjectsToRemove), [1001])
        self.assertEqual(len(proposal.edgesToAdd), 1)
        self.assertEqual(len(proposal.edgeObjectsToAdd), plan.count)
        replacement = proposal.edgesToAdd[1]
        retained = {obj[1] for obj in sequence(replacement.comp.objects) if obj[1] >= 0}
        self.assertEqual(retained, {1002, 2001})
        self.assertEqual(replacement.comp.node0, 10)
        self.assertEqual(replacement.comp.node1, 20)
        self.assertEqual(replacement.comp.roadTemplate, "standard_track")
        self.assertEqual(replacement.playerOwned.player, 7)
        for added in sequence(proposal.edgeObjectsToAdd):
            self.assertEqual(added.edgeEntity, replacement.entity)
            self.assertTrue(added.oneWay)
            self.assertTrue(added.left)
            self.assertEqual(added.model, plan.model)
            self.assertGreater(added.param, 0)
            self.assertLess(added.param, 1)
        # Preparing a proposal must not mutate the still-live original edge.
        original_objects = self.world.components[101, "BASE_EDGE"].objects
        self.assertEqual({obj[1] for obj in sequence(original_objects)}, {1001, 1002, 2001})

    def test_same_direction_waypoint_is_preserved(self):
        self.world.add_edge(101, 10, 20, 700)
        self.world.add_signal(1001, 101, False)
        self.world.add_signal(2001, 101, False, "waypoint")
        plan = self.world.plan(1001)
        self.assertEqual(removals(plan), {1001})
        proposal = self.world.network.proposal(plan).streetProposal
        retained = {obj[1] for obj in sequence(proposal.edgesToAdd[1].comp.objects)}
        self.assertIn(2001, retained)


if __name__ == "__main__":
    unittest.main()
