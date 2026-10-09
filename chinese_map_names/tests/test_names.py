"""Exercise new-map migration in Lua 5.2 and, optionally, the native generators."""

import json
import os
from pathlib import Path
import unittest
from zipfile import ZipFile

from lupa.lua52 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"
GAME = os.environ.get("TF3_GAME_DIR")


class NamesTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.g = self.lua.globals()
        self.lua.execute((ROOT / "tests/runtime.lua").read_text(encoding="utf-8"))
        self.modules = {}
        self.lists = {
            "::/names/china/zh_CN/towns.lua": self.lua.table_from(["北京", "上海", "北京", "广州"]),
            "::/names/china/zh_CN/streets.lua": self.lua.table_from(["人民路", "中山路"]),
        }
        self.g.ug_require = self.require
        self.events = self.resource("chinese_map_names/events.script.lua")
        self.g.events = self.events
        self.planner = self.require("xin_chinese_map_names_1::/chinese_map_names/plan.lua")

    def tearDown(self):
        self.assertEqual(self.g.unsafeNameCommands, 0, "Submitted a rename without an existing NAME component")

    def require(self, name):
        if name in self.lists:
            return self.lists[name]
        if name == "::/scripts/stringutil.lua":
            if name not in self.modules:
                if GAME:
                    with ZipFile(Path(GAME) / "base/content/scripts.zip") as archive:
                        self.modules[name] = self.lua.execute(archive.read("scripts/stringutil.lua").decode("utf-8-sig"))
                else:
                    self.modules[name] = self.lua.execute('''return {interp = function(s, values)
                      local result = s:gsub("(%b{})", function(w) return values[w:sub(2, -2)] or w end)
                      return result
                    end}''')
            return self.modules[name]
        if name not in self.modules:
            path = name.split("::/", 1)[1]
            self.modules[name] = self.lua.execute((CONTENT / path).read_text(encoding="utf-8"))
        return self.modules[name]

    def resource(self, path):
        self.lua.execute((CONTENT / path).read_text(encoding="utf-8"))
        return self.g.data()

    def start(self):
        self.lua.execute('events.handleEvent({}, state, "", "", "initNewGameFromMap")')

    def update(self, count=1):
        for _ in range(count):
            self.events.update(self.lua.table(), self.g.state)

    def plan(self):
        return self.planner.build(*self.lists.values())

    def assert_chinese(self, entity):
        value = self.g.api.engine.util.getEntityName(entity)
        self.assertTrue(self.planner.hasChinese(value), value)
        self.assertFalse(self.planner.needsChineseName(value), value)

    def test_writable_existing_and_generated_names_use_chinese(self):
        self.lua.execute('''
          world[1] = {town = true, name = "Oxford"}
          world[2] = {street = true, name = "High Street"}
          world[3] = {street = true, display = "High Street"}
          world[4] = {person = true, name = "John Smith"}
          world[5] = {person = true, display = "Cached Resident"}
          world[6] = {person = true, name = "王宁"}
          world[7] = {industry = true, stem = 1, suffix = " 煤矿"}
        ''')
        self.start()
        self.update(3)
        self.assertTrue(self.g.state.value.done)
        for entity in (1, 2, 4, 6, 7):
            self.assert_chinese(entity)
        self.assertIsNone(self.g.world[3].name)
        self.assertIsNone(self.g.world[5].name)
        self.assertEqual(self.g.state.value.audit.remaining, 2)
        self.assertEqual(self.g.world[6].name, "王宁")
        self.assertIsNone(self.g.world[7].name)  # Inherited names stay inherited.
        self.assertEqual(self.g.state.value.renamed, 3)
        self.assertTrue(all(command.force for command in self.g.sent.values()))
        self.g.world[1].name = "玩家城市"
        self.start()
        self.update()
        self.assertEqual(self.g.world[1].name, "玩家城市")
        generator = self.resource("chinese_map_names/person.script.lua").generate
        for _ in range(30):
            name = generator(self.lua.table(), self.lua.table_from({"isMale": True}))
            self.assertTrue(self.planner.hasChinese(name))
            self.assertNotIn(" ", name)

    def test_regular_load_editor_and_unrelated_events_do_not_migrate(self):
        self.lua.execute('world[1] = {town = true, name = "Oxford"}')
        self.update(2)
        for event in ("initNewGame", "initMission", "handleLegacy"):
            self.events.handleEvent(self.lua.table(), self.g.state, "", "", event)
        self.events.handleEvent(self.lua.table(), self.g.state, "", "other", "initNewGameFromMap")
        self.g.editor = True
        self.start()
        self.update()
        self.assertEqual(len(self.g.sent), 0)
        self.assertEqual(self.g.world[1].name, "Oxford")

    def test_pre_run_selects_own_scheme_and_preserves_editor(self):
        hook = self.resource("mod.script.lua").preRunFn
        for editor in (False, True):
            config = self.lua.table_from({"nameId": "original", "climate": "tropical"})
            mods = self.lua.table_from({"": self.lua.table_from({"isMapEditor": editor})})
            hook(self.lua.table(), self.lua.table(), mods, config)
            expected = "original" if editor else "xin_chinese_map_names_1::/chinese_map_names/chinese.names"
            self.assertEqual(config.nameId, expected)
            self.assertEqual(config.climate, "tropical")

    def test_initial_industry_name_is_complete_and_children_inherit(self):
        self.lua.execute('''
          world[1] = {town = true, name = "Oxford"}
          world[10] = {construction = "coal", name = "An arbitrary original title", nearestTown = 1, industries = {11}}
          world[11] = {industry = true, stem = 10, parent = 10}
          world[20] = {group = true, name = "My independent station group"}
        ''')
        self.start()
        self.update(3)
        expected = self.g.world[1].name + " 煤矿"
        self.assertEqual(self.g.world[10].name, expected)
        self.assertEqual(self.g.api.engine.util.getEntityName(11), expected)
        self.assertIsNone(self.g.world[11].name)
        self.assertEqual(self.g.world[20].name, "My independent station group")

    def test_native_lists_exhaustion_duplicates_and_determinism(self):
        self.lua.execute('''
          world[1] = {town = true, name = "北京"}
          for i = 2, 10 do world[i] = {town = true, name = "Town " .. i} end
        ''')
        first, second = self.plan(), self.plan()
        names = [entry.after for entry in first.values()]
        self.assertEqual(len(names), len(set(names)))
        self.assertNotIn("北京", names)
        self.assertEqual(names, [entry.after for entry in second.values()])

    def test_command_failure_retries_and_reports_final_failure(self):
        self.lua.execute('world[1] = {town = true, name = "Oxford"}; failures = 10')
        self.start()
        self.update(9)
        self.assertEqual(len(self.g.sent), 3)
        self.assertEqual(self.g.state.value.failed, 1)
        self.assertTrue(self.g.state.value.done)
        self.assertEqual(self.g.world[1].name, "Oxford")

    def test_plan_preparation_retries_without_new_event(self):
        original = self.planner.build
        self.planner.build = self.lua.eval('function() error("Resources not ready") end')
        self.start()
        self.update()
        self.assertEqual(self.g.state.value.prepareAttempts, 1)
        self.planner.build = original
        self.lua.execute('world[1] = {town = true, name = "Oxford"}')
        self.update(2)
        self.assertTrue(self.g.state.value.done)
        self.assertTrue(self.planner.hasChinese(self.g.world[1].name))

    def test_batching_state_write_cost_and_resume(self):
        self.lua.execute('''
          for i = 1, 130 do world[i] = {person = true, name = "Resident " .. i} end
        ''')
        self.start()
        self.update()
        self.assertEqual(len(self.g.sent), 64)
        self.assertLessEqual(self.g.saves, 3)  # Do not copy a large queue per resident.
        self.g.events = self.events = self.resource("chinese_map_names/events.script.lua")
        self.update()
        self.assertEqual(len(self.g.sent), 128)
        self.g.world[129] = None
        self.g.world[130].name = "用户改名"
        self.update(2)
        self.assertTrue(self.g.state.value.done)
        self.assertEqual(self.g.state.value.renamed, 128)
        self.assertEqual(self.g.state.value.skipped, 2)
        self.assertIsNone(self.g.state.value.entries)

    def test_mixed_scripts_and_empty_name_component_are_converted(self):
        self.lua.execute('''
          world[1] = {town = true, name = "Oxford 城"}
          world[2] = {street = true, name = "High Street 路"}
          world[3] = {person = true, name = "John 王"}
          world[4] = {person = true, name = "王 Иван"}
          world[5] = {town = true, name = "", display = "Cambridge"}
          world[6] = {town = true, name = "北京（东）"}
        ''')
        self.start()
        self.update(3)
        for entity in range(1, 7):
            self.assert_chinese(entity)
        self.assertEqual(self.g.world[6].name, "北京（东）")
        self.assertEqual(self.g.state.value.skipped, 0)

    def test_depots_maintenance_warehouses_headquarters_and_independent_buildings(self):
        self.lua.execute('''
          world[1] = {town = true, name = "Oxford"}
          world[10] = {construction = "roadDepot", name = "Oxford Road Depot", nearestTown = 1}
          world[11] = {depot = true, stem = 10, parent = 10}
          world[20] = {construction = "maintenance", name = "Oxford Maintenance Building", nearestTown = 1}
          world[21] = {depot = true, stem = 20, parent = 20, maintenancePool = 5}
          world[30] = {construction = "warehouse", name = "Oxford Warehouse", nearestTown = 1}
          world[31] = {warehouse = true, stem = 30, parent = 30}
          world[40] = {construction = "hq", name = "Oxford Headquarters", nearestTown = 1}
          world[50] = {construction = "landmark", name = "Neuschwanstein"}
          world[60] = {construction = "signal", name = "Oxford Signal #3", nearestTown = 1}
        ''')
        self.start()
        self.update(4)
        for entity in (10, 11, 20, 21, 30, 31, 40, 60):
            self.assert_chinese(entity)
        for entity in (11, 21, 31):
            self.assertIsNone(self.g.world[entity].name)  # Do not freeze child names.
        self.assertIn("道路车库", self.g.world[10].name)
        self.assertIn("维护设施", self.g.world[20].name)
        self.assertIn("仓库", self.g.world[30].name)
        self.assertIn("总部", self.g.world[40].name)
        self.assertEqual(self.g.world[60].name, self.g.world[1].name + " 信号灯")
        self.assertEqual(self.g.world[50].name, self.g.world[1].name + " 新天鹅堡")
        self.assertEqual(self.g.state.value.audit.remaining, 0)

    def test_unsafe_computed_suffixes_are_reported_without_forced_overrides(self):
        self.lua.execute('''
          world[1] = {town = true, name = "Oxford"}
          for i = 2, 65 do world[i] = {street = true, name = "Road " .. i} end
          world[66] = {street = true, stem = 1, suffix = " Road"}
          world[67] = {group = true, stem = 1, suffix = " Port"}
          world[68] = {group = true, stem = 1, suffix = " 港口"}
          world[69] = {group = true, display = "Oxford Port"}
          world[70] = {person = true, display = "John Smith"}
        ''')
        self.start()
        self.update()
        self.g.world[70].name = "My Custom Name"
        self.update(4)
        self.assert_chinese(68)
        for entity in (66, 67, 68, 69):
            self.assertIsNone(self.g.world[entity].name)
        self.assertEqual(self.g.world[70].name, "My Custom Name")
        self.assertEqual(self.g.state.value.audit.remaining, 4)

    def test_station_group_without_a_construction_is_not_given_an_invented_type(self):
        self.lua.execute('''
          world[1] = {town = true, name = "北京"}
          world[2] = {group = true, name = "北京 West"}
          world[3] = {group = true, name = "北京 North Station"}
        ''')
        self.start()
        self.update(3)
        self.assertEqual(self.g.world[2].name, "北京 West")
        self.assertEqual(self.g.world[3].name, "北京 North Station")

    def test_default_numbered_lines_vehicles_and_bounded_unknown_name_audit(self):
        self.lua.execute('''
          world[1] = {line = true, name = "Line 7"}
          world[2] = {vehicle = true, name = "Train 5"}
          world[3] = {vehicle = true, display = "Road Vehicle 8"}
          world[4] = {player = true, name = "Alice运输"}
          world[5] = {line = true, name = "My Scenic Route"}
          for i = 6, 25 do world[i] = {name = "Unknown " .. i} end
        ''')
        self.start()
        self.update(3)
        self.assertEqual(self.g.world[1].name, "线路7")
        self.assertEqual(self.g.world[2].name, "火车5")
        self.assertIsNone(self.g.world[3].name)
        self.assertEqual(self.g.world[4].name, "Alice运输")
        self.assertEqual(self.g.world[5].name, "My Scenic Route")
        report = self.g.state.value.audit
        self.assertEqual(report.remaining, 22)
        self.assertEqual(report.identities, 1)
        self.assertEqual(len(report.samples), 10)
        self.assertTrue(any("Remaining" in message for message in self.g.logs.values()))

    def test_parent_sources_precede_smaller_child_entity_ids(self):
        self.lua.execute('''
          world[1] = {town = true, name = "Oxford"}
          world[2] = {group = true, stem = 10}
          world[10] = {station = true, stem = 20, parent = 20}
          world[11] = {depot = true, stem = 20, parent = 20}
          world[12] = {industry = true, stem = 20, parent = 20}
          world[20] = {construction = "coal", name = "Oxford", nearestTown = 1}
        ''')
        self.start()
        self.update(3)
        self.assertEqual(self.g.state.value.renamed, 2)
        for entity in (2, 11, 12):
            self.assertIsNone(self.g.world[entity].name)
            self.assertEqual(self.g.api.engine.util.getEntityName(entity), self.g.world[20].name + (" 站点" if entity == 2 else ""))
        self.assertIsNone(self.g.world[10].name)
        self.assertEqual(self.g.api.engine.util.getEntityName(10), self.g.world[20].name + " 站点")
        self.g.world[20].name = "后续手动改名"
        self.assertEqual(self.g.api.engine.util.getEntityName(2), "后续手动改名 站点")

    def test_old_name_words_do_not_select_the_native_town_or_facility_type(self):
        self.lua.execute('''
          world[1] = {town = true, name = "North Bend"}
          world[2] = {town = true, name = "Bend"}
          world[3] = {construction = "farm", nearestTown = 1, name = "Bend North Station"}
        ''')
        self.start()
        self.update(3)
        self.assertEqual(self.g.world[3].name, self.g.world[1].name + " 作物农场")
        self.assertGreater(self.g.closestTownQueries, 0)

    def test_restricted_native_iteration_keeps_towns_streets_and_factories(self):
        self.lua.execute('''
          unsupportedKinds.construction, unsupportedKinds.name = true, true
          world[1] = {town = true, name = "Oxford"}
          world[2] = {street = true, name = "High Street"}
          world[3] = {construction = "coal", name = "Oxford", nearestTown = 1}
          world[4] = {industry = true, stem = 3, parent = 3, suffix = " 煤矿"}
        ''')
        self.start()
        self.update(3)
        self.assertTrue(self.g.state.value.done)
        for entity in range(1, 5):
            self.assert_chinese(entity)
        self.assertIsNone(self.g.world[4].name)
        self.assertEqual(self.g.state.value.audit.remaining, 0)
        self.assertEqual(self.g.fullScans, 2)  # One snapshot for planning, one for the final audit.
        self.assertEqual(self.g.enumerationCalls.vehicle, 2)  # Cached within each scan pass.

    def test_failed_scan_cannot_reuse_stale_entities_on_retry(self):
        self.lua.execute('''
          world[1] = {town = true, name = "Oxford"}
          world[2] = {street = true, name = "High Street"}
          savedGetComponent = api.engine.getComponent
          api.engine.getComponent = function(entity, kind)
            if fullScans > 0 and kind == "street" then error("simulated component read failure") end
            return savedGetComponent(entity, kind)
          end
        ''')
        with self.assertRaisesRegex(Exception, "simulated component read failure"):
            self.plan()
        self.lua.execute('''
          api.engine.getComponent = savedGetComponent
          world[2] = nil
          world[3] = {street = true, name = "New Road"}
        ''')
        entities = {entry.entity for entry in self.plan().values()}
        self.assertEqual(entities, {1, 3})
        self.assertEqual(self.g.fullScans, 2)

    def test_older_failed_job_is_retired_without_touching_old_names(self):
        self.lua.execute('''
          world[1] = {town = true, name = "Oxford"}
          world[2] = {street = true, name = "High Street"}
          world[3] = {construction = "coal", name = "Oxford Coal Mine", nearestTown = 1}
          state:set({started = true, prepareAttempts = 3, cursor = 1, renamed = 0,
            failed = 0, skipped = 0, retained = 0})
        ''')
        self.update(3)
        self.assertTrue(self.g.state.value.done)
        self.assertEqual(self.g.state.value.stoppedByRevision, 8)
        self.assertEqual(len(self.g.sent), 0)
        self.assertEqual(self.g.fullScans, 0)
        self.assertEqual(self.g.world[1].name, "Oxford")
        self.assertEqual(self.g.world[3].name, "Oxford Coal Mine")

    def test_recovery_does_not_start_ordinary_or_completed_save_jobs(self):
        self.lua.execute('world[1] = {town = true, name = "Keep my town"}')
        for saved in ('{prepareAttempts = 3}', '{started = true, done = true, prepareAttempts = 3}'):
            with self.subTest(saved=saved):
                self.lua.execute('state:set(' + saved + ')')
                self.update(2)
                self.assertEqual(self.g.world[1].name, "Keep my town")
                self.assertEqual(len(self.g.sent), 0)
                self.assertIsNone(self.g.state.value.prepareRevision)

    def test_unrelated_enumeration_errors_remain_visible_and_retries_stay_bounded(self):
        self.lua.execute('''
          api.engine.getEntitiesWithComponent = function() error("unexpected engine fault") end
        ''')
        self.start()
        self.update(6)
        self.assertEqual(self.g.state.value.prepareAttempts, 3)
        self.assertEqual(self.g.fullScans, 0)
        self.assertEqual(len(self.g.sent), 0)
        self.assertTrue(any("unexpected engine fault" in line for line in self.g.logs.values()))
        self.g.events = self.events = self.resource("chinese_map_names/events.script.lua")
        self.update(2)
        self.assertEqual(self.g.state.value.prepareAttempts, 3)

    def test_game_unpack_behavior_does_not_leak_pcall_success_into_plan(self):
        self.lua.execute('world[1] = {town = true, name = "Oxford"}')
        # Reproduce why the old pack/unpack wrapper produced boolean entries.
        kind = self.lua.eval('''function()
          local results = table.pack(pcall(function() return {} end))
          local first = table.unpack(results, 2, results.n)
          return type(first)
        end''')()
        self.assertEqual(kind, "boolean")
        result = self.plan()
        self.assertEqual(result[1].entity, 1)
        self.start()
        self.update(3)
        self.assertTrue(self.g.state.value.done)
        self.assertEqual(self.g.state.value.audit.remaining, 0)

    def test_current_job_invalid_queue_is_rebuilt_without_relying_on_unpack(self):
        for invalid in ("true", "false", "42", '\"broken\"'):
            with self.subTest(invalid=invalid):
                self.lua.execute('''
                  world[1] = {town = true, name = "Oxford"}
                  state:set({started = true, prepareRevision = 8, prepareAttempts = 1,
                    entries = ''' + invalid + ''', cursor = 1, renamed = 0, failed = 0, skipped = 0, retained = 0})
                ''')
                self.update(3)
                self.assertTrue(self.g.state.value.done)
                self.assertEqual(self.g.state.value.prepareRevision, 8)
                self.assert_chinese(1)

    def test_invalid_plan_output_is_not_persisted_and_logs_are_bounded(self):
        original = self.planner.build
        self.planner.build = self.lua.eval('function() return true end')
        self.start()
        self.update(12)
        self.assertIsNone(self.g.state.value.entries)
        self.assertEqual(self.g.state.value.prepareAttempts, 3)
        self.assertEqual(len(self.g.sent), 0)
        warnings = [line for line in self.g.logs.values() if "invalid plan result" in line]
        self.assertEqual(len(warnings), 3)
        self.planner.build = original

    def test_malformed_plan_entries_are_rejected_before_save(self):
        self.planner.build = self.lua.eval('function() return {true} end')
        self.start()
        self.update()
        self.assertIsNone(self.g.state.value.entries)
        self.assertEqual(len(self.g.sent), 0)
        self.assertEqual(self.g.state.value.prepareAttempts, 1)

    def test_deferred_rename_waits_for_readback_before_children_or_success_count(self):
        self.lua.execute('''
          deferred = true
          world[1] = {town = true, name = "Oxford"}
          world[10] = {industry = true, stem = 20, parent = 20, suffix = " 煤矿"}
          world[20] = {construction = "coal", name = "Oxford", nearestTown = 1}
        ''')
        self.start()
        self.update()
        self.assertEqual(len(self.g.sent), 1)  # Confirm the changed town name before naming its factory.
        self.assertEqual(self.g.state.value.renamed, 0)
        self.assertIsNone(self.g.world[10].name)
        self.g.flushCommands()
        self.update()
        self.assertEqual(len(self.g.sent), 2)
        self.assertEqual(self.g.state.value.renamed, 1)
        self.assertIsNone(self.g.world[10].name)
        self.g.flushCommands()
        self.update(2)
        self.assertTrue(self.g.state.value.done)
        self.assertEqual(self.g.state.value.renamed, 2)
        self.assertIsNone(self.g.world[10].name)
        self.assertEqual(self.g.state.value.failed, 0)
        self.assert_chinese(10)

    def test_sedona_factory_is_in_first_batch_ahead_of_thousands_of_residents(self):
        self.lua.execute('''
          deferred = true
          world[1] = {town = true, name = "Sedona"}
          world[2] = {industry = true, stem = 3, subParent = 3, suffix = " 伐木营地"}
          world[3] = {construction = "forest", name = "Sedona", nearestTown = 1}
          for i = 100, 3039 do world[i] = {person = true, name = "Resident " .. i} end
        ''')
        self.start()
        self.update()
        self.assertEqual(len(self.g.sent), 64)
        submitted = {command.entity: command.name for command in self.g.sent.values()}
        self.assertNotIn(3, submitted)  # Its town rename is still pending.
        self.assertEqual(self.g.state.value.renamed, 0)
        self.assertIsNone(self.g.world[2].name)
        self.g.flushCommands()
        self.update()
        self.g.flushCommands()
        self.assert_chinese(1)
        self.assertEqual(self.g.api.engine.util.getEntityName(2), self.g.world[1].name + " 伐木营地")
        self.assertIsNone(self.g.world[2].name)
        self.assertFalse(bool(self.g.state.value.done))  # Factory is done while residents remain.

    def test_older_pending_queue_is_not_replayed(self):
        self.lua.execute('''
          world[1] = {town = true, name = "株洲"}
          world[3] = {construction = "farm", name = "株洲 车站 2", nearestTown = 1}
          state:set({started = true, prepareRevision = 6, cursor = 1, renamed = 1,
            skipped = 0, failed = 0, retained = 0, entries = {
              {entity = 3, before = "株洲 车站 2", after = "株洲 作物农场", attempts = 0}
            }})
        ''')
        self.update(200)
        self.assertEqual(self.g.world[3].name, "株洲 车站 2")
        self.assertEqual(len(self.g.sent), 0)
        self.assertEqual(self.g.fullScans, 0)
        self.assertIsNone(self.g.state.value.entries)

    def test_completed_old_maps_are_never_repaired_or_rescanned(self):
        self.lua.execute('''
          world[1] = {town = true, name = "大同"}
          world[3] = {construction = "oil_well", name = "大同 车站 2", nearestTown = 1}
          state:set({started = true, done = true, prepareRevision = 4})
        ''')
        self.update(200)
        self.assertEqual(self.g.world[3].name, "大同 车站 2")
        self.assertEqual(len(self.g.sent), 0)
        self.assertEqual(dict(self.g.enumerationCalls), {})
        self.assertEqual(self.g.fullScans, 0)
        self.assertEqual(len(self.g.logs), 0)

    def test_waiting_for_street_stem_does_not_block_independent_factory_batch(self):
        self.lua.execute('''
          deferred = true
          world[1] = {town = true, name = "Sedona"}
          world[2] = {street = true, name = "High Street"}
          world[3] = {group = true, stem = 2, suffix = " 车站"}
          world[4] = {construction = "forest", name = "Sedona", nearestTown = 1}
          world[5] = {industry = true, stem = 4, subParent = 4, suffix = " 伐木营地"}
        ''')
        self.start()
        self.update()
        self.assertEqual({c.entity for c in self.g.sent.values()}, {1, 2})
        self.assertIsNone(self.g.world[3].name)
        self.g.flushCommands()
        self.update()
        self.g.flushCommands()
        self.update(2)
        self.assertTrue(self.g.state.value.done)
        self.assertIsNone(self.g.world[3].name)
        self.assertIsNone(self.g.world[5].name)
        self.assert_chinese(3)

    def test_pending_commands_are_not_duplicated_before_the_next_readback_window(self):
        self.lua.execute('''
          deferred = true
          for i = 1, 100 do world[i] = {person = true, name = "Resident " .. i} end
        ''')
        self.start()
        self.update(2)
        self.assertEqual(len(self.g.sent), 100)
        self.assertEqual(len({c.entity for c in self.g.sent.values()}), 100)
        self.g.flushCommands()
        self.update(2)
        self.assertTrue(self.g.state.value.done)
        self.assertEqual(self.g.state.value.renamed, 100)

    def test_nameless_targets_are_excluded_from_all_new_queue_sources(self):
        self.lua.execute('''
          world[1] = {town = true, name = "Sedona"}
          world[57546] = {station = true, stem = 1, suffix = " Station"}
          world[4] = {person = true, display = "John Smith"}
          world[5] = {street = true, display = "High Street"}
          world[6] = {line = true, display = "Line 1"}
          world[7] = {vehicle = true, display = "Train 1"}
          world[8] = {construction = "forest", display = "Sedona Logging Camp", nearestTown = 1}
          world[9] = {industry = true, parent = 8, stem = 8}
        ''')
        entries = self.plan()
        self.assertEqual({entry.entity for entry in entries.values()}, {1})
        self.start()
        self.update(3)
        self.assertTrue(self.g.state.value.done)
        self.assertEqual({command.entity for command in self.g.sent.values()}, {1})
        self.assertGreater(self.g.state.value.audit.remaining, 0)

    def test_crash_station_57546_in_legacy_queue_never_receives_a_forced_name(self):
        self.lua.execute('''
          deferred = true
          world[1] = {town = true, name = "长沙"}
          world[57545] = {construction = "forest", name = "Sedona Logging Camp", nearestTown = 1}
          world[57546] = {station = true, parent = 57545, stem = 57545, suffix = " Station"}
          state:set({started = true, prepareRevision = 8, cursor = 1, renamed = 0, skipped = 0,
            failed = 0, retained = 0, entries = {
              {entity = 57546, before = "Sedona Logging Camp Station", after = "长沙 车站", readDisplay = true, attempts = 0},
              {entity = 57545, before = "Sedona Logging Camp", after = "长沙 伐木场", readDisplay = false, attempts = 0}
            }})
        ''')
        self.update()
        self.assertEqual([command.entity for command in self.g.sent.values()], [57545])
        self.assertIsNone(self.g.world[57546].name)
        self.g.flushCommands()
        self.update(3)
        self.assertTrue(self.g.state.value.done)
        self.assertEqual(self.g.world[57545].name, "长沙 伐木场")
        self.assertIsNone(self.g.world[57546].name)
        self.assertEqual(self.g.state.value.missingName, 1)
        self.assertEqual([command.entity for command in self.g.sent.values()], [57545])

    def test_nameless_station_cannot_redirect_its_full_title_onto_shared_town(self):
        self.lua.execute('''
          world[1] = {town = true, name = "长沙"}
          world[57546] = {station = true, stem = 1, suffix = " Station"}
          state:set({started = true, prepareRevision = 8, cursor = 1, renamed = 0, skipped = 0,
            failed = 0, retained = 0, entries = {
              {entity = 57546, before = "长沙 Station", after = "长沙 车站", readDisplay = true, attempts = 0}
            }})
        ''')
        self.update(3)
        self.assertTrue(self.g.state.value.done)
        self.assertEqual(self.g.world[1].name, "长沙")
        self.assertIsNone(self.g.world[57546].name)
        self.assertEqual(len(self.g.sent), 0)
        self.assertEqual(self.g.state.value.skipped, 1)

    def test_component_is_rechecked_at_submission_after_display_read(self):
        self.lua.execute('''
          world[42] = {person = true, name = "", display = "John Smith"}
          local original = api.engine.util.getEntityName
          api.engine.util.getEntityName = function(entity)
            local value = original(entity)
            if entity == 42 then world[42].name = nil end
            return value
          end
          state:set({started = true, prepareRevision = 8, cursor = 1, renamed = 0, skipped = 0,
            failed = 0, retained = 0, entries = {
              {entity = 42, before = "John Smith", after = "王宁", readDisplay = true, attempts = 0}
            }})
        ''')
        self.update(3)
        self.assertTrue(self.g.state.value.done)
        self.assertIsNone(self.g.world[42].name)
        self.assertEqual(len(self.g.sent), 0)
        self.assertEqual(self.g.state.value.skipped, 1)

    def test_completed_revision_five_does_not_start_a_new_scan_for_safety_update(self):
        self.lua.execute('''
          world[57546] = {station = true, display = "Sedona Station"}
          state:set({started = true, done = true, prepareRevision = 5})
          api.engine.getEntitiesWithComponent = function() error("Completed jobs must not rescan") end
          api.engine.forEachEntity = function() error("Completed jobs must not rescan") end
        ''')
        self.update(200)
        self.assertEqual(len(self.g.sent), 0)
        self.assertEqual(self.g.fullScans, 0)
        self.assertEqual(len(self.g.logs), 0)

    def test_first_creation_complete_name_is_shared_by_industry_owner_and_group(self):
        for kind, title, town in (("farm", "作物农场", "株洲"),
                                  ("livestock_farm", "牲畜养殖场", "株洲"),
                                  ("oil_well", "油井", "大同"),
                                  ("oil_platform", "采油平台", "大同")):
            with self.subTest(kind=kind):
                self.setUp()
                self.lua.execute('''
                  world[1] = {town = true, name = "''' + town + '''"}
                  world[2] = {construction = "''' + kind + '''", name = "Original Place",
                    nearestTown = 1, industries = {3}, stations = {4}, subconstructions = {3, 4}}
                  world[3] = {industry = true, industryConstruction = 2, stem = 2}
                  world[4] = {station = true, parent = 2, stem = 2}
                  world[5] = {group = true, stations = {4}, name = "Original Place Terminal"}
                  api.engine.system.streetConnectorSystem.getConstructionClosestTown = function()
                    error("Use the verified native first-naming town query")
                  end
                ''')
                self.start()
                self.update(3)
                expected = town + " " + title
                self.assertEqual(self.g.world[2].name, expected)
                self.assertEqual(self.g.world[5].name, expected)
                self.assertEqual(self.g.api.engine.util.getEntityName(3), expected)
                self.assertNotIn("车站", expected)
                self.assertIsNone(self.g.world[3].name)
                self.assertIsNone(self.g.world[4].name)
                self.assertEqual(self.g.unsafeNameCommands, 0)

    def test_factory_name_does_not_depend_on_global_industry_enumeration_or_old_suffix(self):
        self.lua.execute('''
          world[1] = {town = true, name = "大同"}
          world[2] = {construction = "oil_platform", name = "Original Place #2",
            nearestTown = 1, industries = {3}}
          world[3] = {industry = true, industryConstruction = 2, stem = 2}
          local enumerate = api.engine.getEntitiesWithComponent
          api.engine.getEntitiesWithComponent = function(kind)
            if kind == "industry" then return {} end
            return enumerate(kind)
          end
        ''')
        self.start()
        self.update(3)
        self.assertEqual(self.g.world[2].name, "大同 采油平台")
        self.assertEqual(self.g.api.engine.util.getEntityName(3), "大同 采油平台")

    def test_station_reference_does_not_reclassify_fixed_farm_name(self):
        self.lua.execute('''
          world[1] = {town = true, name = "Oxford"}
          world[10] = {construction = "unknown_farm", name = "Oxford Farm", nearestTown = 1}
          world[20] = {construction = "station_con", name = "株洲 车站", nearestTown = 1}
          world[30] = {station = true, stem = 10, parent = 20}
          world[31] = {group = true, stations = {30}, name = "My Loading Point"}
        ''')
        self.start()
        self.update(3)
        self.assertEqual(self.g.world[10].name, "Oxford Farm")
        self.assertEqual(self.g.world[20].name, "株洲 车站")
        self.assertEqual(self.g.world[31].name, "My Loading Point")
        self.assertIsNone(self.g.world[30].name)
        self.assertTrue(any("descriptor not found" in line for line in self.g.logs.values()))

    @unittest.skipUnless(GAME, "Set TF3_GAME_DIR for native translation-template checks")
    def test_real_native_templates_supply_facility_titles(self):
        import gettext

        with (Path(GAME) / "base/strings/zh_CN/LC_MESSAGES/base.mo").open("rb") as file:
            translations = gettext.GNUTranslations(file)
        self.g._ = translations.gettext
        self.lua.execute('''
          world[1] = {town = true, name = "Oxford"}
          world[2] = {construction = "roadDepot", name = "Oxford Road Depot", nearestTown = 1}
          world[3] = {construction = "signal", name = "Oxford Signal #3", nearestTown = 1}
        ''')
        self.start()
        self.update(3)
        town = self.g.world[1].name
        self.assertEqual(self.g.world[2].name,
                         translations.gettext("{townName} Road Depot").replace("{townName}", town))
        self.assertEqual(self.g.world[3].name,
                         translations.gettext("{townName} {constructionName}")
                         .replace("{townName}", town).replace("{constructionName}", "信号灯"))

    @unittest.skipUnless(GAME, "Set TF3_GAME_DIR for native runtime compatibility checks")
    def test_real_game_unpack_override_allows_plan_and_audit_to_finish(self):
        with ZipFile(Path(GAME) / "base/content/base.zip") as archive:
            init = archive.read("base/init.lua").decode("utf-8-sig")
        start = init.index("local unpackhelper")
        end = init.index("function ug_require_cleanup", start)
        self.lua.execute(init[start:end])
        self.lua.execute('''
          world[1] = {town = true, name = "Oxford"}
          world[2] = {street = true, name = "High Street"}
          world[3] = {construction = "coal", name = "Oxford", nearestTown = 1}
          world[4] = {industry = true, stem = 3, parent = 3, suffix = " 煤矿"}
        ''')
        self.start()
        self.update(3)
        self.assertTrue(self.g.state.value.done)
        self.assertEqual(self.g.state.value.failed, 0)
        self.assertEqual(self.g.state.value.audit.remaining, 0)
        for entity in range(1, 5):
            self.assert_chinese(entity)

    def test_scheme_label_follows_locale_but_name_lists_stay_chinese(self):
        translations = json.loads((ROOT / 'strings.json').read_text(encoding='utf-8'))
        for locale, expected in (('en', 'Chinese (preset maps)'), ('zh_CN', '中文（预设地图）')):
            with self.subTest(locale=locale):
                self.g._ = translations[locale].__getitem__
                scheme = self.resource('chinese_map_names/chinese.names.lua')
                self.assertEqual(scheme.name, expected)
                for key in ('townNamesScript', 'streetNamesScript'):
                    self.assertEqual(scheme[key].params.path, 'china')
                    self.assertEqual(scheme[key].params.languages.fallback, 'zh_CN')

    @unittest.skipUnless(GAME, "Set TF3_GAME_DIR for native name-generator checks")
    def test_native_generators_and_real_lists(self):
        with ZipFile(Path(GAME) / "base/content/names.zip") as archive:
            native = {}

            def native_require(name):
                path = name.split("::/", 1)[-1]
                if path == "personnameutil.lua":
                    path = "names/personnameutil.lua"
                if path not in native:
                    native[path] = self.lua.execute(archive.read(path).decode("utf-8-sig"))
                return native[path]

            self.g.require = native_require
            self.lua.execute(archive.read("names/names.script.lua").decode("utf-8-sig"))
            generators = self.g.data()
            scheme = self.resource("chinese_map_names/chinese.names.lua")
            for key, function in (("townNamesScript", generators.townsNameScriptFn),
                                  ("streetNamesScript", generators.streetsNameScriptFn)):
                for language in ("zh_CN", "en"):
                    result = function(scheme[key].params,
                                      self.lua.table_from({"num": 20, "lang": language}))
                    self.assertEqual(len(result), 20)
                    self.assertTrue(all(self.planner.hasChinese(name) for name in result.values()))
            self.lua.execute('world[1] = {town = true, name = "Oxford"}')
            result = self.planner.build(native_require("::/names/china/zh_CN/towns.lua"),
                                        native_require("::/names/china/zh_CN/streets.lua"))
            self.assertTrue(self.planner.hasChinese(result[1].after))


if __name__ == "__main__":
    unittest.main()
