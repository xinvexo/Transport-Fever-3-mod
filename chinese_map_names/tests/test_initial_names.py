"""Rules verified against the native first-construction naming path."""
import math
import unittest

import test_names


class InitialNameRulesTests(unittest.TestCase):
    def setUp(self):
        self.h = test_names.NamesTests("runTest")
        self.h.setUp()
        self.lua, self.g = self.h.lua, self.h.g
        self.rules = self.h.require("xin_chinese_map_names_1::/chinese_map_names/initial_names.lua")

    def tearDown(self):
        self.h.tearDown()

    def name(self, taken=(), position=(0, 0), description=None, extra=False):
        resource = description or self.g.resources.farm
        used = set(taken)
        return self.rules.make(resource, "株洲", self.lua.table_from(dict(x=position[0], y=position[1])),
                               self.lua.table_from(dict(x=0, y=0)), lambda value: value in used, lambda: extra)

    def test_final_prefix_takes_precedence_over_description(self):
        self.g.resources.farm.namePrefix = "{townName} - 原生定制名"
        self.assertEqual(self.name(), "株洲 - 原生定制名")
        self.g.resources.farm.namePrefix = ""
        self.assertEqual(self.name(), "株洲 作物农场")

    def test_empty_description_and_prefix_do_not_invent_a_type(self):
        self.g.resources.farm.description.name = ""
        value, reason = self.name()
        self.assertIsNone(value)
        self.assertIn("empty", reason)

    def test_base_name_is_used_even_far_from_town_if_it_is_available(self):
        self.assertEqual(self.name(position=(1000, 0)), "株洲 作物农场")

    def test_direction_requires_collision_and_distance_greater_than_400(self):
        base = "株洲 作物农场"
        self.assertEqual(self.name({base}, (400, 0)), base + " #1")
        for position, suffix in (((401, 0), "东"), ((0, 401), "北"), ((-401, 0), "西"), ((0, -401), "南")):
            with self.subTest(position=position):
                self.assertEqual(self.name({base}, position), base + suffix)

    def test_native_angular_gaps_and_strict_boundaries_skip_direction(self):
        base = "株洲 作物农场"
        self.assertEqual(self.name({base}, (500, 500)), base + " #1")
        for angle in (math.pi / 6, math.pi / 3, 2 * math.pi / 3, 5 * math.pi / 6,
                      -math.pi / 6, -math.pi / 3, -2 * math.pi / 3, -5 * math.pi / 6):
            with self.subTest(angle=angle):
                self.g.math.atan2 = lambda y, x, a=angle: a
                self.assertEqual(self.name({base}, (500, 0)), base + " #1")

    def test_numbers_start_at_one_and_use_first_free_full_name(self):
        base = "株洲 作物农场"
        self.assertEqual(self.name({base, base + " #1", base + " #3"}), base + " #2")
        self.assertEqual(self.name({base, base + "东", base + " #1"}, (500, 0)), base + " #2")

    def test_native_number_exhaustion_returns_base_at_999(self):
        base = "株洲 作物农场"
        taken = {base, *(base + " #" + str(n) for n in range(1, 1000))}
        self.assertEqual(self.name(taken), base)

    def test_random_land_station_branch_is_not_replaced_with_guessed_number(self):
        value, reason = self.name({"株洲 作物农场"}, extra=True)
        self.assertIsNone(value)
        self.assertIn("random station", reason)

    def test_extra_variant_gate_uses_first_subconstruction_and_terminal_modes(self):
        self.lua.execute('''
          world[10] = {industry = true}
          world[11] = {station = true, terminals = {{transportModes = {"BUS", "TRUCK"}}}}
          world[12] = {station = true, terminals = {{transportModes = {[3]=true, [8]=true}}}}
          world[13] = {station = true, terminals = {{transportModes = {"AIRCRAFT"}}}}
        ''')
        def gate(first):
            return self.rules.extraVariants(self.lua.table_from({"subconstructions": self.lua.table_from(first)}))
        self.assertFalse(gate([10, 11]))  # Standard industryutil layout.
        self.assertTrue(gate([11, 10]))
        self.assertTrue(gate([12]))
        self.assertFalse(gate([13]))
        self.assertFalse(gate([]))

    def test_collision_set_uses_station_groups_and_depot_parent_names(self):
        self.lua.execute('''
          world[1] = {town = true, name = "株洲"}
          world[10] = {construction = "farm", name = "Old Farm A", nearestTown = 1, industries={11}, subconstructions={11,12}}
          world[11] = {industry=true, parent=10, stem=10}
          world[12] = {station=true, parent=10, stem=10}
          world[13] = {group=true, stations={12}, name="Old Farm A"}
          world[20] = {construction = "farm", name = "Old Farm B", nearestTown = 1, industries={21}, subconstructions={21,22}}
          world[21] = {industry=true, parent=20, stem=20}
          world[22] = {station=true, parent=20, stem=20}
          world[23] = {group=true, stations={22}, name="Old Farm B"}
          world[90] = {group=true, name="株洲 作物农场"}
          world[91] = {construction="roadDepot", name="株洲 作物农场 #1"}
          world[92] = {depot=true, parent=91, stem=91}
        ''')
        self.h.start()
        self.h.update(4)
        self.assertEqual(self.g.world[10].name, "株洲 作物农场 #2")
        self.assertEqual(self.g.world[13].name, self.g.world[10].name)
        self.assertEqual(self.g.world[20].name, "株洲 作物农场 #3")
        self.assertEqual(self.g.world[23].name, self.g.world[20].name)
        self.assertIsNone(self.g.world[11].name)
        self.assertIsNone(self.g.world[12].name)

    def test_final_resource_table_is_cached_and_old_caption_does_not_supply_type(self):
        self.lua.execute('''
          world[1] = {town=true, name="大同"}
          world[2] = {construction="oil_well", name="Wrong Station Words", nearestTown=1}
          world[3] = {construction="oil_well", name="Another Arbitrary Caption", nearestTown=1}
          resources.oil_well.namePrefix = "{townName} - 油井"
          api.res.constructionRep.get = function() error("Do not read incomplete descriptor bindings") end
          api.engine.system.streetConnectorSystem.getConstructionClosestTown = function() error("Wrong nearest-town path") end
        ''')
        self.h.start()
        self.h.update(3)
        self.assertEqual(self.g.world[2].name, "大同 - 油井")
        self.assertEqual(self.g.world[3].name, "大同 - 油井")
        self.assertEqual(self.g.descriptorQueries, 1)
        self.assertEqual(self.g.closestTownQueries, 2)

    def test_no_town_does_not_guess_a_replacement_or_touch_random_seed(self):
        self.lua.execute('''
          world[2] = {construction="farm", name="Original Farm", nearestTown=-1}
          math.randomseed = function() error("Do not alter simulation RNG") end
        ''')
        self.h.start()
        self.h.update(3)
        self.assertEqual(self.g.world[2].name, "Original Farm")
        self.assertEqual(len(self.g.sent), 0)
        self.assertTrue(any("no named town" in line for line in self.g.logs.values()))

    def test_facility_write_waits_for_and_checks_actual_town_name(self):
        self.lua.execute('''
          deferred=true
          world[1] = {town=true, name="Old Town"}
          world[2] = {construction="farm", name="Old Farm", nearestTown=1}
        ''')
        self.h.start()
        self.h.update()
        self.assertEqual([c.entity for c in self.g.sent.values()], [1])
        self.g.flushCommands()
        self.g.world[1].name = "玩家手改城市"
        self.h.update(3)
        self.assertEqual(self.g.world[2].name, "Old Farm")
        self.assertEqual([c.entity for c in self.g.sent.values()], [1])

    def test_station_group_is_not_renamed_when_its_construction_write_fails(self):
        self.lua.execute('''
          world[1] = {town=true, name="株洲"}
          world[2] = {construction="farm", name="Old Farm", nearestTown=1, industries={3}, subconstructions={3,4}}
          world[3] = {industry=true, parent=2, stem=2}
          world[4] = {station=true, parent=2, stem=2}
          world[5] = {group=true, stations={4}, name="Old Farm"}
          failures=10
        ''')
        self.h.start()
        self.h.update(10)
        self.assertTrue(self.g.state.value.done)
        self.assertEqual(self.g.world[2].name, "Old Farm")
        self.assertEqual(self.g.world[5].name, "Old Farm")
        self.assertEqual({c.entity for c in self.g.sent.values()}, {2})
        self.assertEqual(self.g.state.value.failed, 1)

    def test_station_group_keeps_its_name_if_parent_is_changed_externally(self):
        self.lua.execute('''
          deferred=true
          world[1] = {town=true, name="株洲"}
          world[2] = {construction="farm", name="Old Farm", nearestTown=1, industries={3}, subconstructions={3,4}}
          world[3] = {industry=true, parent=2, stem=2}
          world[4] = {station=true, parent=2, stem=2}
          world[5] = {group=true, stations={4}, name="Old Farm"}
        ''')
        self.h.start()
        self.h.update()
        self.assertEqual([c.entity for c in self.g.sent.values()], [2])
        self.g.flushCommands()
        self.g.world[2].name = "玩家指定的农场"
        self.h.update(3)
        self.assertEqual(self.g.world[5].name, "Old Farm")
        self.assertEqual([c.entity for c in self.g.sent.values()], [2])
