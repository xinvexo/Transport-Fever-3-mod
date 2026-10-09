import math
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
        self.node_positions = {}
        self.transport_opposite = {}
        self.native_sides = {}
        self.next_entity = 10000
        self.lua.execute("""
            local function clone(value)
                if type(value) ~= "table" then return value end
                local copy = {}
                for key, item in pairs(value) do copy[key] = clone(item) end
                return copy
            end
            cloneBaseEdge = clone
            function makeTransform(columns)
                return { cols = function(_, index)
                    assert(index >= 0 and index <= 3, 'native matrix columns are zero based')
                    return columns[index+1]
                end }
            end
            warnings = {}
            log = { warning = function(message) warnings[#warnings+1] = message end }
            api = {
                type = {
                    ComponentType = setmetatable({}, {
                        __index = function(_, key) return key end
                    }),
                    enum = {
                        EdgeObjectType = { SIGNAL = "signal" },
                        RoadType = { TRACK = "TRACK" },
                    },
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
                        streetSystem = {}, streetConnectorSystem = {}, signalSystem = {},
                    },
                    util = { getPlayer = function() return 7 end, transport = {} },
                },
                res = { constructionRep = {} },
            }
        """)
        api = self.lua.globals().api
        api.engine.entityExists = self.entity_exists
        api.engine.getComponent = self.component
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
        # A reverse lookup cannot enumerate stacked signals. The production
        # code must use each entity's own data, never this single-result API.
        api.engine.system.signalSystem.getSignal = self.lua.eval("function() error('ambiguous reverse lookup used') end")
        api.engine.util.transport.calcPosition = self.transport_position
        spacing = self.lua.execute((ROOT / "content/auto_signal/spacing.lua").read_text(encoding="utf-8"))
        geometry = self.lua.execute((ROOT / "content/auto_signal/geometry.lua").read_text(encoding="utf-8"))
        self.geometry = geometry
        self.lua.globals().ug_require = lambda path: geometry if path.endswith("geometry.lua") else spacing
        self.network = self.lua.execute((ROOT / "content/auto_signal/network.lua").read_text(encoding="utf-8"))

    def entity_exists(self, entity):
        return any(key[0] == entity for key in self.components)

    def component(self, entity, kind):
        assert self.entity_exists(entity), "getComponent requires an existing entity"
        return self.components.get((entity, kind))

    def table(self, value):
        return self.lua.table_from(value, recursive=True)

    def add_edge(self, entity, node0, node1, length, owner=None):
        if node0 not in self.node_positions:
            self.node_positions[node0] = self.node_positions.get(node1, -length) + length
        if node1 not in self.node_positions:
            self.node_positions[node1] = self.node_positions[node0] + length
        self.components[entity, "BASE_EDGE"] = self.table({
            "node0": node0, "node1": node1, "objects": [],
            "roadType": "TRACK", "roadTemplate": "standard_track",
            "laneConfigs": [{"width": 5}],
            "tangent0": [length, 0, 0], "tangent1": [length, 0, 0],
        })
        self.components[entity, "BASE_EDGE"].clone = self.lua.globals().cloneBaseEdge
        self.set_geometry(entity, (self.node_positions[node0], 0, 0),
                          (self.node_positions[node1], 0, 0))
        self.components[entity, "PLAYER_OWNED"] = self.table({"player": 7})
        self.connections[node0].append(entity)
        self.connections[node1].append(entity)
        self.lengths[entity] = length
        self.set_transport_edges(entity, 1)
        if owner is not None:
            self.owners[entity] = owner

    def set_geometry(self, entity, start, end, tangent0=None, tangent1=None):
        base = self.components[entity, "BASE_EDGE"]
        tangent = tuple(b-a for a, b in zip(start, end))
        for key, vector in (("position0", start), ("position1", end),
                            ("tangent0", tangent0 or tangent), ("tangent1", tangent1 or tangent)):
            base[key] = self.table(dict(zip(("x", "y", "z"), vector)))
        if (entity, "TRANSPORT_NETWORK") in self.components:
            self.set_transport_edges(entity, len(self.components[entity, "TRANSPORT_NETWORK"].edges))

    def world_position(self, entity, t):
        base = self.components[entity, "BASE_EDGE"]
        return tuple((2*t**3-3*t*t+1)*base.position0[axis]
                     + (t**3-2*t*t+t)*base.tangent0[axis]
                     + (-2*t**3+3*t*t)*base.position1[axis]
                     + (t**3-t*t)*base.tangent1[axis] for axis in ("x", "y", "z"))

    def transport_position(self, data, t):
        p = self.world_position(data.entity, data.first+(data.last-data.first)*t)
        return self.table(dict(zip(("x", "y", "z"), p)))

    def set_transport_opposite(self, entity, opposite):
        # Native mission guarantees alignment for one lane only. Exercise the
        # general case with multiple lane configurations and independent TN order.
        self.components[entity, "BASE_EDGE"].laneConfigs = self.table([{"width": 2.5}, {"width": 2.5}])
        self.transport_opposite[entity] = opposite
        self.set_transport_edges(entity, len(self.components[entity, "TRANSPORT_NETWORK"].edges))

    def add_road(self, entity, node, width=18, angle=90):
        other = entity + 100000
        self.add_edge(entity, node, other, 100)
        self.connections[node].remove(entity)
        self.connections[other].remove(entity)
        self.street_connections[node].append(entity)
        self.street_connections[other].append(entity)
        base = self.components[entity, "BASE_EDGE"]
        base.roadType = "STREET"
        base.laneConfigs = self.table([{"width": width/2}, {"width": width/2}])
        x = self.node_positions[node]
        radians = math.radians(angle)
        self.set_geometry(entity, (x, 0, 0), (x+100*math.cos(radians), 100*math.sin(radians), 0))

    def set_transport_edges(self, entity, count):
        entries = []
        for index in range(count):
            first, last = index/count, (index+1)/count
            if self.transport_opposite.get(entity):
                first, last = last, first
            entries.append({"geometry": {"length": self.lengths[entity]/count,
                                          "entity": entity, "first": first, "last": last}})
        self.components[entity, "TRANSPORT_NETWORK"] = self.table({
            "edges": entries
        })

    def add_signal(self, entity, edge, reversed=False, kind="path", fraction=0.25, native_left=None, pose_axis=0):
        index = 0
        while (edge, index, reversed) in self.signals:
            index += 1
        self.signals[edge, index, reversed] = entity
        current_count = len(self.components[edge, "TRANSPORT_NETWORK"].edges)
        self.set_transport_edges(edge, max(current_count, index + 1))
        self.hosts[entity] = edge
        if native_left is None:
            native_left = bool(reversed) != bool(self.transport_opposite.get(edge))
        self.native_sides[entity] = native_left
        base = self.components[edge, "BASE_EDGE"]
        t = fraction
        tangent = [(6*t*t-6*t)*base.position0[axis] + (3*t*t-4*t+1)*base.tangent0[axis]
                   + (-6*t*t+6*t)*base.position1[axis] + (3*t*t-2*t)*base.tangent1[axis]
                   for axis in ("x", "y", "z")]
        norm = sum(v*v for v in tangent)**0.5
        x = tuple(v/norm*(-1 if native_left else 1) for v in tangent)
        y = (-x[1], x[0], 0)
        if pose_axis == 1:
            x, y = y, x
        columns = self.table([dict(zip(("x", "y", "z"), v))
                              for v in (x, y, (0, 0, 1), self.world_position(edge, fraction))])
        self.components[entity, "EDGE_OBJECT"] = self.table({
            "param": fraction,
            "edgeObjectConstruction": "base::/infrastructure/signal/signal_path_a.con",
            "params": {"oneWay": 1 if kind == "one_way" else 2},
        })
        self.components[entity, "EDGE_OBJECT"].transf = self.lua.globals().makeTransform(columns)
        self.components[entity, "SIGNAL_LIST"] = self.table({"signals": [{"type": kind}]})
        self.add_object(entity, edge, "signal")

    def add_object(self, entity, edge, kind):
        objects = self.components[edge, "BASE_EDGE"].objects
        objects[len(objects) + 1] = self.table([entity, kind])

    def get_signal(self, edge_id, reversed):
        entity = self.signals.get((edge_id.entity, edge_id.index, reversed), -1)
        return self.table({"entity": entity, "index": 0})

    def plan(self, signal, gap=300):
        result = self.network.plan(signal, gap, self.source(signal))
        if isinstance(result, tuple):
            raise AssertionError(f"Planning failed: {result[1]}")
        return result

    def source(self, signal):
        base = self.components[self.hosts[signal], "BASE_EDGE"]
        return self.table({"left": self.native_sides[signal], "node0": base.node0, "node1": base.node1})

    def apply_plan(self, plan):
        created = []
        for step in sequence(plan.steps):
            removed = set(sequence(step.remove))
            base = self.components[step.edge, "BASE_EDGE"]
            base.objects = self.table([sequence(o) for o in sequence(base.objects) if o[1] not in removed])
            for entity in removed:
                self.components.pop((entity, "EDGE_OBJECT"), None)
                self.components.pop((entity, "SIGNAL_LIST"), None)
                self.components.pop((entity, "MODEL_INSTANCE_LIST"), None)
                self.hosts.pop(entity, None)
                self.native_sides.pop(entity, None)
            self.signals = {key: entity for key, entity in self.signals.items() if entity not in removed}
            for param in sequence(step.positions):
                self.next_entity += 1
                entity = self.next_entity
                query_reversed = bool(step.left) != bool(self.transport_opposite.get(step.edge))
                self.add_signal(entity, step.edge, query_reversed,
                                "one_way" if plan.oneWay else "path", param, native_left=step.left)
                created.append(entity)
        return created


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

    def assert_northbound_world_layout(self, world, plan):
        proposal = world.network.proposal(plan).streetProposal
        edge_map = {-index: step.edge for index, step in enumerate(sequence(plan.steps), 1)}
        positions = []
        for obj in sequence(proposal.edgeObjectsToAdd):
            entity = edge_map[obj.edgeEntity]
            positions.append(world.world_position(entity, obj.param)[1])
            base = world.components[entity, "BASE_EDGE"]
            # The native mission's direction check uses left = not forward.
            heading_y = (base.position1.y-base.position0.y) * (-1 if obj.left else 1)
            self.assertGreater(heading_y, 0, "Generated signal must still face north")
        for actual, expected in zip(sorted(positions), [149, 449, 749, 1049]):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(len(positions), 4)

    def test_northbound_lane_keeps_heading_and_anchors_before_north_junction(self):
        self.world.add_edge(101, 10, 20, 1050)
        self.world.set_geometry(101, (0, 0, 0), (0, 1050, 0))
        self.world.add_signal(1001, 101, False)
        self.assert_northbound_world_layout(self.world, self.world.plan(1001))

    def test_opposite_transport_geometry_does_not_reverse_upbound_anchor(self):
        for nodes in ((10, 90), (90, 10)):
            with self.subTest(nodes=nodes):
                world = TrackWorld()
                world.add_edge(101, *nodes, 1050)
                world.set_geometry(101, (0, 0, 0), (0, 1050, 0))
                world.set_transport_opposite(101, True)  # transport runs south
                world.add_signal(1001, 101, True)  # requested opposite: north
                self.assert_northbound_world_layout(world, world.plan(1001))

    def test_mixed_base_and_transport_directions_preserve_same_world_heading(self):
        self.make_open_section()
        self.world.set_geometry(101, (0, 0, 0), (0, 400, 0))
        self.world.set_geometry(102, (0, 700, 0), (0, 400, 0))
        self.world.set_geometry(103, (0, 700, 0), (0, 1050, 0))
        for edge, opposite in ((101, True), (102, True), (103, False)):
            self.world.set_transport_opposite(edge, opposite)
        self.world.add_signal(1001, 101, True)
        self.world.add_signal(1002, 102, False)
        self.world.add_signal(1003, 103, False)
        self.world.add_signal(1101, 102, True)  # physically southbound: keep it
        for seed in (1001, 1002, 1003):
            plan = self.world.plan(seed)
            self.assertEqual(removals(plan), {1001, 1002, 1003})
            self.assert_northbound_world_layout(self.world, plan)

    def test_transport_subedges_are_calibrated_independently(self):
        self.world.add_edge(101, 10, 20, 1050)
        self.world.set_geometry(101, (0, 0, 0), (0, 1050, 0))
        self.world.set_transport_opposite(101, True)
        self.world.add_signal(1001, 101, True)
        self.world.add_signal(1002, 101, True)
        self.world.add_signal(1101, 101, False)
        for seed in (1001, 1002):
            plan = self.world.plan(seed)
            self.assertEqual(removals(plan), {1001, 1002})
            self.assert_northbound_world_layout(self.world, plan)

    def test_single_lane_uses_native_direction_contract_without_spatial_api(self):
        self.world.add_edge(101, 10, 20, 1050)
        self.world.set_geometry(101, (0, 0, 0), (0, 1050, 0))
        self.world.add_signal(1001, 101, False)
        self.world.lua.execute("api.engine.util.transport = nil")
        self.assert_northbound_world_layout(self.world, self.world.plan(1001))

    def test_manual_proposal_side_is_authoritative_even_if_reverse_lookup_disagrees(self):
        self.world.add_edge(101, 10, 20, 1050)
        self.world.set_geometry(101, (0, 0, 0), (0, 1050, 0))
        # Deliberately contradictory lookup direction: only the native manual
        # proposal and actual source pose describe the player's choice.
        self.world.add_signal(1001, 101, True, native_left=False)
        self.assert_northbound_world_layout(self.world, self.world.plan(1001))

    def test_repeated_builds_replace_only_same_direction_and_leave_opposite_duplicates_untouched(self):
        self.world.add_edge(101, 10, 20, 1050)
        self.world.set_geometry(101, (0, 0, 0), (0, 1050, 0))
        self.world.add_signal(1101, 101, True, fraction=0.5, native_left=True)
        self.world.add_signal(1102, 101, True, fraction=0.5, native_left=True)
        previous = set()
        for iteration in range(4):
            source = 2000+iteration
            self.world.add_signal(source, 101, True, fraction=0.4, native_left=False)
            plan = self.world.plan(source)
            self.assertEqual(removals(plan), previous | {source})
            self.assert_northbound_world_layout(self.world, plan)
            previous = set(self.world.apply_plan(plan))
            retained = {obj[1] for obj in sequence(self.world.components[101, "BASE_EDGE"].objects)}
            self.assertEqual(retained, previous | {1101, 1102})
            self.assertEqual(len(retained), 6)

    def test_only_same_direction_stacks_are_rebuilt_opposite_stacks_are_untouched(self):
        self.world.add_edge(101, 10, 20, 1050)
        for entity in (1001, 1002, 1003):
            self.world.add_signal(entity, 101, fraction=0.999, native_left=False)
        self.world.add_signal(1101, 101, True, fraction=0.999, native_left=True)
        self.world.add_signal(1102, 101, True, fraction=0.999, native_left=True)
        self.world.add_signal(1201, 101, False, "waypoint", fraction=0.999)
        self.world.add_signal(2000, 101, fraction=0.4, native_left=False)
        plan = self.world.plan(2000)
        self.assertEqual(removals(plan), {1001, 1002, 1003, 2000})
        created = set(self.world.apply_plan(plan))
        remaining = {obj[1] for obj in sequence(self.world.components[101, "BASE_EDGE"].objects)}
        self.assertEqual(remaining, created | {1101, 1102, 1201})

    def test_native_side_is_normalized_if_engine_reverses_base_node_order(self):
        self.world.add_edge(101, 90, 10, 1050)
        self.world.set_geometry(101, (0, 0, 0), (0, 1050, 0))
        self.world.add_signal(1001, 101, native_left=False)
        original = self.world.source(1001)
        base = self.world.components[101, "BASE_EDGE"]
        base.node0, base.node1 = 10, 90
        self.world.set_geometry(101, (0, 1050, 0), (0, 0, 0))
        self.world.components[1001, "EDGE_OBJECT"].param = 0.75
        plan = self.world.network.plan(1001, 300, original)
        self.assert_northbound_world_layout(self.world, plan)

    def test_missing_captured_side_never_falls_back_to_guessing(self):
        self.world.add_edge(101, 10, 20, 1050)
        self.world.add_signal(1001, 101)
        plan, reason = self.world.network.plan(1001, 300)
        self.assertIsNone(plan)
        self.assertIn("native placement direction unavailable", reason)

    def test_one_way_value_comes_from_the_manual_parameter_not_a_reverse_blocker(self):
        self.world.add_edge(101, 10, 20, 1050)
        self.world.add_signal(1001, 101)
        self.world.components[1001, "SIGNAL_LIST"].signals = self.world.table(
            [{"type": "one_way"}, {"type": "path"}])
        self.assertFalse(self.world.plan(1001).oneWay)
        self.world.components[1001, "EDGE_OBJECT"].params.oneWay = 1
        self.assertTrue(self.world.plan(1001).oneWay)

    def test_native_signal_models_can_replace_each_other_without_changing_heading(self):
        self.world.add_edge(101, 10, 20, 1050)
        self.world.add_signal(1001, 101, native_left=False)
        self.world.add_signal(1002, 101, native_left=False)
        self.world.components[1001, "EDGE_OBJECT"].edgeObjectConstruction = "base::/infrastructure/signal/signal_path_c.con"
        plan = self.world.plan(1001)
        self.assertEqual(removals(plan), {1001, 1002})
        self.assertEqual(plan.model, "base::/infrastructure/signal/signal_path_c.con")


    def test_unknown_custom_model_orientation_does_not_risk_deleting_reverse_lights(self):
        self.world.add_edge(101, 10, 20, 1050)
        self.world.add_signal(1001, 101, native_left=False)
        self.world.add_signal(1101, 101, True, native_left=True, pose_axis=1)
        self.world.components[1101, "EDGE_OBJECT"].edgeObjectConstruction = "custom::/rotated_signal.con"
        plan, reason = self.world.network.plan(1001, 300, self.world.source(1001))
        self.assertIsNone(plan)
        self.assertIn("custom signal orientations", reason)
        self.assertEqual({obj[1] for obj in sequence(self.world.components[101, "BASE_EDGE"].objects)}, {1001, 1101})

    def test_signals_beyond_section_boundary_are_not_removed(self):
        self.world.add_edge(101, 10, 20, 1050)
        self.world.add_edge(102, 20, 30, 500)
        self.world.add_edge(103, 20, 40, 400)
        self.world.add_signal(1001, 101)
        self.world.add_signal(1101, 101, True)
        self.world.add_signal(1201, 102)
        self.world.add_signal(1202, 103, True)
        plan = self.world.plan(1001)
        proposal = self.world.network.proposal(plan).streetProposal
        self.assertEqual(removals(plan), {1001})
        self.assertEqual(sequence(proposal.edgesToRemove), [101])
        self.assertEqual(set(sequence(proposal.edgeObjectsToRemove)), {1001})

    def test_duplicate_references_request_native_removal_only_once(self):
        self.world.add_edge(101, 10, 20, 1050)
        self.world.add_signal(1001, 101)
        self.world.add_signal(1101, 101)
        self.world.add_object(1101, 101, "signal")
        proposal = self.world.network.proposal(self.world.plan(1001)).streetProposal
        self.assertEqual(sequence(proposal.edgeObjectsToRemove), [1001, 1101])

    def test_opposite_objects_are_retained_with_their_original_ids_and_settings(self):
        self.world.add_edge(101, 10, 20, 1050)
        self.world.add_signal(1001, 101, native_left=False)
        self.world.add_signal(1101, 101, True, "one_way", fraction=0.999, native_left=True)
        self.world.add_signal(1102, 101, True, "one_way", fraction=0.999, native_left=True)
        original_first = self.world.components[1101, "EDGE_OBJECT"]
        original_second = self.world.components[1102, "EDGE_OBJECT"]
        plan = self.world.plan(1001)
        self.assertEqual(removals(plan), {1001})
        self.world.apply_plan(plan)
        self.assertIs(self.world.components[1101, "EDGE_OBJECT"], original_first)
        self.assertIs(self.world.components[1102, "EDGE_OBJECT"], original_second)
        self.assertEqual(original_first.params.oneWay, 1)
        self.assertEqual(original_second.params.oneWay, 1)

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

    def test_layout_is_independent_of_the_clicked_signal(self):
        self.make_open_section()
        self.world.add_signal(1001, 101, False, fraction=0.2)
        self.world.add_signal(1002, 102, True, fraction=0.7)
        self.world.add_signal(1003, 103, False, fraction=0.9)
        expected = layout(self.world.plan(1001))
        self.assertEqual(layout(self.world.plan(1002)), expected)
        self.assertEqual(layout(self.world.plan(1003)), expected)

    def test_reversing_the_chosen_direction_only_replaces_that_direction(self):
        self.make_open_section()
        self.world.add_signal(1001, 101, False)
        self.world.add_signal(1002, 102, False)
        self.world.add_signal(1003, 103, True)
        plan = self.world.plan(1002)
        self.assertEqual(removals(plan), {1002, 1003})
        self.assertEqual([step.left for step in sequence(plan.steps)], [True, False, True])

    def test_proposal_replaces_same_direction_and_preserves_reverse_and_other_objects(self):
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
            self.assertFalse(added.left)
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

    def test_1050_meter_section_uses_exact_gap_from_forward_endpoint(self):
        self.make_open_section()
        self.world.add_signal(1001, 101, False, "one_way", fraction=0.5)
        self.world.add_signal(1002, 102, True)
        self.world.add_signal(1101, 102, False)
        plan = self.world.plan(1001, 300)
        self.assertEqual(sequence(plan.positions), [149, 449, 749, 1049])
        self.assertEqual(removals(plan), {1001, 1002})
        self.assertTrue(plan.oneWay)
        self.assertEqual([step.left for step in sequence(plan.steps)], [False, True, False])
        physical = []
        for step in sequence(plan.steps):
            for fraction in sequence(step.positions):
                physical.append(
                    400*fraction if step.edge == 101 else
                    400+300*(1-fraction) if step.edge == 102 else 700+350*fraction
                )
        for actual, expected in zip(physical, sequence(plan.positions)):
            self.assertAlmostEqual(actual, expected)

    def test_reverse_direction_anchors_at_the_other_endpoint(self):
        self.make_open_section()
        self.world.add_signal(1001, 101, True)
        self.world.add_signal(1002, 102, False)
        first = self.world.plan(1001, 300)
        self.assertEqual(sequence(first.positions), [1, 301, 601, 901])
        self.assertEqual(layout(first), layout(self.world.plan(1002, 300)))

    def test_clicked_500_meter_position_is_only_a_trigger(self):
        self.world.add_edge(101, 10, 20, 1050)
        self.world.add_signal(1001, 101, fraction=500/1050)
        plan = self.world.plan(1001, 200)
        self.assertEqual(sequence(plan.positions), [49, 249, 449, 649, 849, 1049])
        self.assertNotIn(500, sequence(plan.positions))
        self.assertEqual(removals(plan), {1001})

    def test_short_section_has_one_signal_at_directional_end(self):
        self.world.add_edge(101, 10, 20, 100)
        self.world.add_signal(1001, 101)
        self.world.add_signal(1002, 101, True)
        self.assertEqual(sequence(self.world.plan(1001).positions), [99])
        self.assertEqual(sequence(self.world.plan(1002).positions), [1])

    def test_regular_edge_joints_do_not_restart_spacing(self):
        self.world.add_edge(101, 10, 20, 20)
        self.world.add_edge(102, 30, 20, 60)
        self.world.add_edge(103, 30, 40, 40)
        self.world.add_signal(1001, 101)
        plan = self.world.plan(1001, 50)
        self.assertEqual(sequence(plan.positions), [19, 69, 119])
        middle = next(step for step in sequence(plan.steps) if step.edge == 102)
        self.assertAlmostEqual(middle.positions[1], 1-49/60)

    def test_fixed_position_on_ordinary_joint_is_not_moved_or_duplicated(self):
        self.world.add_edge(101, 10, 20, 449)
        self.world.add_edge(102, 20, 30, 601)
        self.world.add_signal(1001, 101)
        plan = self.world.plan(1001, 300)
        self.assertEqual(sequence(plan.positions), [149, 449, 749, 1049])
        self.assertEqual(sum(len(step.positions) for step in sequence(plan.steps)), 4)
        self.assertEqual(plan.steps[1].positions[2], 1)

    def test_road_crossing_moves_target_and_counts_next_gap_from_it(self):
        self.world.add_edge(101, 10, 20, 450)
        self.world.add_edge(102, 20, 30, 600)
        self.world.add_road(9001, 20)
        self.world.crossing_clearance = 20
        self.world.add_signal(1001, 101)
        self.assertEqual(sequence(self.world.plan(1001, 300).positions), [130, 430, 749, 1049])

    def test_resource_clearance_can_move_a_blocked_first_light(self):
        self.world.add_edge(101, 10, 20, 1050)
        self.world.add_road(9001, 20)
        self.world.crossing_clearance = 20
        self.world.add_signal(1001, 101)
        self.assertEqual(sequence(self.world.plan(1001, 300).positions), [130, 430, 730, 1030])

    def test_no_space_or_excessive_signal_count_preserves_seed(self):
        self.world.add_edge(101, 10, 20, 2000)
        self.world.add_signal(1001, 101)
        self.world.geometry.forSegment = self.world.lua.eval(
            "function() error('rejected layout must not sample track curves') end"
        )
        plan, reason = self.world.network.plan(1001, 1, self.world.source(1001))
        self.assertIsNone(plan)
        self.assertIn("count limit", reason)
        self.world.crossing_clearance = 3000
        self.world.add_road(9001, 10)
        plan, reason = self.world.network.plan(1001, 300, self.world.source(1001))
        self.assertIsNone(plan)
        self.assertIn("no room", reason)
        self.assertEqual(self.world.components[101, "BASE_EDGE"].objects[1][1], 1001)

    def test_sparse_layout_samples_only_used_edges_and_rechecks_topology_next_plan(self):
        for index in range(9):
            self.world.add_edge(101 + index, index + 1, index + 2, 100)
        self.world.add_signal(1001, 105)
        self.world.add_signal(1002, 101, reversed=True)
        self.world.lua.globals().geometryModule = self.world.geometry
        self.world.lua.execute("""
            sampledEdges = {}
            local forSegment = geometryModule.forSegment
            geometryModule.forSegment = function(segment)
                if not segment.geometry then
                    sampledEdges[segment.entity] = (sampledEdges[segment.entity] or 0) + 1
                end
                return forSegment(segment)
            end
        """)
        queried = defaultdict(int)

        def query(node):
            queried[node] += 1
            return self.world.table(self.world.connections[node])

        self.world.lua.globals().api.engine.system.streetSystem.getNodeTrackSegments = query
        plan = self.world.plan(1001)
        self.assertEqual(sequence(plan.positions), [299, 599, 899])
        self.assertEqual(dict(self.world.lua.globals().sampledEdges),
                         {101: 1, 103: 1, 105: 1, 106: 1, 109: 1})
        self.assertEqual(dict(queried), {node: 1 for node in range(1, 11)})

        # A later event must read fresh topology and curve data. A branch added
        # at node 6 now ends the source section after only five track segments.
        self.world.add_edge(901, 6, 100, 50)
        queried.clear()
        plan = self.world.plan(1001)
        self.assertEqual(sequence(plan.sourceEdges), [101, 102, 103, 104, 105])
        self.assertEqual(sequence(plan.positions), [199, 499])
        self.assertEqual(dict(queried), {node: 1 for node in range(1, 7)})
        self.assertEqual(self.world.lua.globals().sampledEdges[105], 2)

    def test_removed_signal_is_rejected_without_reading_invalid_entity(self):
        plan, reason = self.world.network.plan(1001, 300, self.world.table({"left": False}))
        self.assertIsNone(plan)
        self.assertIn("no longer exists", reason)

    def test_removed_track_aborts_proposal_without_reading_invalid_entity(self):
        self.world.add_edge(101, 10, 20, 1000)
        self.world.add_signal(1001, 101)
        plan = self.world.plan(1001)
        for key in list(self.world.components):
            if key[0] == 101:
                del self.world.components[key]
        proposal, reason = self.world.network.proposal(plan)
        self.assertIsNone(proposal)
        self.assertIn("track changed", reason)

    def test_native_signal_without_declared_clearance_still_avoids_road_width(self):
        self.world.add_edge(101, 10, 20, 749)
        self.world.add_edge(102, 20, 30, 301)
        self.world.add_road(9001, 20, width=18)
        self.world.add_signal(1001, 101)
        segments, closed = self.world.network.corridor(101)
        self.assertFalse(closed)
        self.assertEqual(len(segments), 2)
        plan = self.world.plan(1001)
        self.assertEqual(sequence(plan.positions), [139, 439, 739, 1049])
        self.assertEqual(plan.count, 4)

    def test_wide_and_skew_roads_use_their_actual_width_and_angle(self):
        self.world.add_edge(101, 10, 20, 749)
        self.world.add_edge(102, 20, 30, 301)
        self.world.add_road(9001, 20, width=40)
        self.world.add_signal(1001, 101)
        self.assertEqual(sequence(self.world.plan(1001).positions), [128, 428, 728, 1049])
        road = self.world.components[9001, "BASE_EDGE"]
        road.laneConfigs = self.world.table([{"width": 10}, {"width": 10}])
        self.world.set_geometry(9001, (749, 0, 0), (849, 100, 0))
        self.assertEqual(sequence(self.world.plan(1001).positions), [133, 433, 733, 1049])

    def test_road_width_native_vector_matches_native_script_access(self):
        self.world.add_edge(101, 10, 20, 749)
        self.world.add_edge(102, 20, 30, 301)
        self.world.add_road(9001, 20, width=18)
        self.world.components[9001, "BASE_EDGE"].laneConfigs = None
        self.world.components[9001, "BASE_EDGE"].laneConfigs_native = self.world.lua.eval("""
            { size = function() return 4 end,
              at = function(_, index) return { width = ({3, 6, 6, 3})[index] } end }
        """)
        self.world.add_signal(1001, 101)
        self.assertEqual(sequence(self.world.plan(1001).positions), [139, 439, 739, 1049])

    def test_reverse_direction_moves_past_the_crossing_in_reverse_placement_order(self):
        self.world.add_edge(101, 10, 20, 301)
        self.world.add_edge(102, 30, 20, 749)
        self.world.add_road(9001, 20, width=18)
        self.world.add_signal(1001, 101, True)
        self.world.add_signal(1002, 102, False)
        plan = self.world.plan(1001)
        self.assertEqual(sequence(plan.positions), [1, 311, 611, 911])
        self.assertEqual(layout(plan), layout(self.world.plan(1002)))

    def test_road_bridge_with_separate_nodes_does_not_change_ground_signal_positions(self):
        self.world.add_edge(101, 10, 20, 749)
        self.world.add_edge(102, 20, 30, 301)
        self.world.add_road(9001, 40, width=40)
        self.world.set_geometry(9001, (749, -50, 10), (749, 50, 10))
        self.world.add_signal(1001, 101)
        self.assertEqual(sequence(self.world.plan(1001).positions), [149, 449, 749, 1049])

    def test_neighbouring_tracks_do_not_move_signal_positions(self):
        self.world.add_edge(101, 10, 20, 100)
        self.world.add_edge(102, 30, 40, 100)
        self.world.set_geometry(102, (0, 2.5, 0), (100, 2.5, 0))
        self.world.add_signal(1001, 101)
        self.assertEqual(sequence(self.world.plan(1001, 50).positions), [49, 99])

    def test_closed_track_has_no_endpoint_and_keeps_original_signals(self):
        self.world.add_edge(101, 10, 20, 350)
        self.world.add_edge(102, 20, 30, 350)
        self.world.add_edge(103, 30, 10, 350)
        self.world.add_signal(1001, 101)
        segments, closed = self.world.network.corridor(101)
        self.assertTrue(closed)
        self.assertEqual(len(segments), 3)
        plan, reason = self.world.network.plan(1001, 300, self.world.source(1001))
        self.assertIsNone(plan)
        self.assertIn("no forward endpoint", reason)
        self.assertEqual(self.world.components[101, "BASE_EDGE"].objects[1][1], 1001)

    def test_two_arc_closed_track_is_also_left_unchanged(self):
        self.world.add_edge(101, 10, 20, 500)
        self.world.add_edge(102, 10, 20, 500)
        self.world.add_signal(1001, 101)
        self.world.add_signal(1002, 102)
        for signal in (1001, 1002):
            plan, reason = self.world.network.plan(signal, 300, self.world.source(signal))
            self.assertIsNone(plan)
            self.assertIn("no forward endpoint", reason)

    def test_actual_positions_on_nonuniform_spline_keep_meter_spacing(self):
        self.world.add_edge(101, 10, 20, 100)
        self.world.set_geometry(101, (0, 0, 0), (100, 0, 0), (10, 0, 0), (100, 0, 0))
        self.world.add_signal(1001, 101)
        plan = self.world.plan(1001, 25)
        proposal = self.world.network.proposal(plan)
        actual = []
        for obj in sequence(proposal.streetProposal.edgeObjectsToAdd):
            t = obj.param
            actual.append(100*(-2*t**3+3*t**2)+10*(t**3-2*t**2+t)+100*(t**3-t**2))
        for got, expected in zip(actual, [24, 49, 74, 99]):
            self.assertAlmostEqual(got, expected, delta=0.01)
        for a, b in zip(actual, actual[1:]):
            self.assertAlmostEqual(b-a, 25, delta=0.02)


if __name__ == "__main__":
    unittest.main()
