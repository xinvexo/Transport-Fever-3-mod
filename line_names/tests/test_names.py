"""Lua 5.2 behavior tests; native source contracts are optional via TF3_GAME_DIR."""

import json
import os
from pathlib import Path
import unittest
from zipfile import ZipFile

from lupa.lua52 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content/line_names"


class NamingTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute((ROOT / "tests/runtime.lua").read_text(encoding="utf-8"))
        self.g = self.lua.globals()
        translations = json.loads((ROOT / "strings.json").read_text(encoding="utf-8"))["zh_CN"]
        self.g._ = lambda key: translations.get(key, key)
        self.modules = {}
        self.g.ug_require = self.require
        self.world = self.require("xin_line_names_1::/line_names/world.lua")
        self.lua.execute((CONTENT / "naming.script.lua").read_text(encoding="utf-8"))
        self.rename = self.g.data().renameFn
        self.next_id = 1000
        for entity, name in ((1, "北京"), (2, "天津"), (3, "上海")):
            self.put(entity, TOWN={}, name=name)

    def table(self, value):
        return self.lua.table_from(value, recursive=True)

    def require(self, path):
        if path == "::/gui/main/game_react_globals.tl":
            return self.lua.eval("{getDefaultWindowApi=function() return session end}")
        if path not in self.modules:
            filename = path.split("/")[-1]
            self.modules[path] = self.lua.execute((CONTENT / filename).read_text(encoding="utf-8"))
        return self.modules[path]

    def put(self, entity=None, **components):
        if entity is None:
            entity = self.next_id
            self.next_id += 1
        self.g.components[entity] = self.table(components)
        return entity

    def stock(self, cargo, output=False):
        entity = self.put(STOCK_LIST={"stocks": [{"type": int(output)}]})
        self.g.stockCargo[entity] = self.table([[cargo]])
        return entity

    def building(self, town, cargo=1):
        pc = self.put(PERSON_CAPACITY={"capacity": 100})
        stock = self.stock(cargo)
        entity = self.put(TOWN_BUILDING={"town": town, "stockList": stock, "personCapacity": pc})
        self.g.pcBuildings[pc] = entity
        return pc, stock

    def industry(self, entity, town, name, cargo=0, output=False):
        construction = self.put(CONSTRUCTION={}, town=town)
        stock = self.stock(cargo, output)
        self.put(entity, name=name, INDUSTRY={"stockList": stock, "construction": construction},
                 PERSON_CAPACITY={"capacity": 100})
        return entity, stock

    def station(self, group, town, name=None, passenger=None, cargo=None, carriers=None):
        station = self.put(STATION={})
        self.put(group, name=name or f"站点{group}", STATION_GROUP={"stations": [station]},
                 carriers=carriers or [0])
        self.g.stationTowns[station] = town
        self.g.catchables[station] = self.table({"passenger": passenger or [], "cargo": cargo or []})
        return station

    def line(self, entity=10, groups=(200, 201), load=(7,), supported=None, used=None,
             carrier=0, name="线路1", owner=7):
        loads = [index in load for index in range(8)]
        stops = [{"stationGroup": group, "station": 0, "terminal": 0,
                  "stopConfig": {"load": loads, "maxLoad": [1] * 8}, "alternativeTerminals": []}
                 for group in groups]
        self.put(entity, LINE={"stops": stops}, name=name, owner=owner)
        self.g.capacities[entity] = self.table({
            "all": {cargo + 1: {"capacity": 20, "used": 0} for cargo in supported or []},
            "current": {cargo + 1: {"capacity": 20, "used": count} for cargo, count in (used or {}).items()},
        })
        if supported:
            vehicle = self.put(TRANSPORT_VEHICLE={"carrier": carrier})
            self.g.vehicles[entity] = self.table([vehicle])
        return entity

    def result(self, entity=10):
        return self.rename(self.table({"lineEntity": entity, "reactLine": {"path": []}}))

    def city_pair(self, second=1):
        a, _ = self.building(1)
        b, _ = self.building(second)
        self.station(200, 1, passenger=[a])
        self.station(201, second, passenger=[b])

    def test_local_and_intercity_dedicated_passenger_lines(self):
        self.city_pair()
        self.line(supported=[7])
        self.assertEqual(self.result(), "北京 - 公交01")
        b, _ = self.building(2)
        self.station(201, 2, passenger=[b])
        self.g.advance()
        self.assertEqual(self.result(), "北京 - 天津 - 客运")

    def test_intercity_passenger_numbering_depends_on_lines_not_vehicles(self):
        self.city_pair(second=2)
        self.line(supported=[7], carrier=1)
        self.assertEqual(self.result(), "北京 - 天津 - 客运")
        self.g.components[10].name = self.result()
        vehicle = self.put(TRANSPORT_VEHICLE={"carrier": 1})
        self.g.vehicles[10][2] = vehicle
        self.g.advance()
        self.assertEqual(self.result(), "北京 - 天津 - 客运")
        self.line(20, supported=[7], carrier=1)
        self.g.advance()
        self.assertEqual(self.result(10), "北京 - 天津 - 客运01")
        self.assertEqual(self.result(20), "北京 - 天津 - 客运02")

    def test_unrelated_name_collision_still_reserves_unnumbered_name(self):
        self.city_pair(second=2)
        self.line(supported=[7], carrier=1)
        self.line(20, groups=(), load=(), name="北京 - 天津 - 客运")
        self.assertEqual(self.result(10), "北京 - 天津 - 客运01")
        self.assertEqual(self.result(20), "北京 - 天津 - 客运")

    def test_dedicated_freight_uses_config_not_all_vehicle_capabilities(self):
        _, stock_a = self.industry(100, 1, "北京 煤矿", output=True)
        _, stock_b = self.industry(101, 1, "北京 钢铁厂")
        self.station(200, 1, cargo=[stock_a])
        self.station(201, 1, cargo=[stock_b])
        self.line(load=(0,), supported=[0, 1, 2], carrier=1)
        self.assertEqual(self.result(), "北京 - 煤矿 - 钢铁厂 · 煤炭01")

    def test_unambiguous_capacity_skips_current_load_but_loaded_override_is_kept(self):
        self.city_pair()
        self.lua.execute("""
            capacityReads={all=0,current=0}
            local native=api.engine.util.line.getLineCapacityUsages
            api.engine.util.line.getLineCapacityUsages=function(id,all)
                local key=all and 'all' or 'current'
                capacityReads[key]=capacityReads[key]+1
                return native(id,all)
            end
        """)
        self.line(supported=[7])
        self.assertEqual(self.result(), "北京 - 公交01")
        self.assertEqual(self.g.capacityReads.all, 1)
        self.assertEqual(self.g.capacityReads.current, 0)
        self.line(load=(7,), supported=[7, 0], used={0: 5})
        context = self.world.new()
        self.assertEqual(context.line(10).kind, "mixed")
        self.assertEqual(self.g.capacityReads.current, 1)
        self.line(load=(0, 1), supported=[0, 1], used={1: 3})
        context = self.world.new()
        self.assertEqual(context.line(10).cargo, "食品")
        self.assertEqual(self.g.capacityReads.current, 2)

    def test_factory_freight_avoids_town_building_index_until_town_delivery_is_needed(self):
        _, coal = self.industry(100, 1, "北京 煤矿", output=True)
        _, steel = self.industry(101, 2, "天津 钢铁厂")
        self.station(200, 1, cargo=[coal])
        self.station(201, 2, cargo=[steel])
        self.line(load=(0,), supported=[0])
        self.lua.execute("""
            api.engine.system.townBuildingSystem.getPersonCapacity2townBuildingMap = function()
                error('Freight previews do not need the passenger building map')
            end
            buildingMapReads=0
            local native=api.engine.system.townBuildingSystem.getTown2BuildingMap
            api.engine.system.townBuildingSystem.getTown2BuildingMap=function()
                buildingMapReads=buildingMapReads+1;return native()
            end
        """)
        self.assertEqual(self.result(), "北京 - 煤矿 - 天津 - 钢铁厂 · 煤炭01")
        self.assertEqual(self.g.buildingMapReads, 0)
        _, delivery = self.building(2)
        self.station(202, 2, cargo=[delivery])
        self.line(20, groups=(200, 202), load=(1,), supported=[1])
        self.g.advance()
        self.assertEqual(self.result(20), "北京 - 天津 · 食品01")
        self.assertEqual(self.g.buildingMapReads, 1)
        self.assertEqual(len(self.g.warnings), 0)

    def test_town_names_refresh_in_the_next_preview_plan(self):
        self.city_pair()
        self.line(10, supported=[7])
        self.line(20, supported=[7])
        self.assertEqual(self.result(10), "北京 - 公交01")
        scans = self.g.scans.LINE
        self.assertEqual(self.result(20), "北京 - 公交02")
        self.assertEqual(self.g.scans.LINE, scans)
        self.g.components[1].name = "新城"
        self.g.advance()
        self.assertEqual(self.result(10), "新城 - 公交01")
        self.assertEqual(self.result(20), "新城 - 公交02")
        self.assertEqual(self.g.scans.LINE, scans + 1)
        self.assertEqual(self.g.components[999].GAME_TIME.updateCount, 0)

    def test_interrupted_owner_index_is_rebuilt_for_the_next_line(self):
        _, first = self.building(1)
        _, second = self.building(1)
        self.station(200, 1, cargo=[first])
        self.station(201, 1, cargo=[second])
        self.line(10, load=(1,), supported=[1], name="原线路")
        self.line(20, load=(1,), supported=[1])
        self.lua.execute("""
            local failed=false
            local native=api.engine.getComponent
            api.engine.getComponent=function(id,kind)
                if kind=='TOWN_BUILDING' and not failed then
                    failed=true;error('interrupted town index')
                end
                return native(id,kind)
            end
        """)
        self.assertEqual(self.result(10), "原线路")
        self.assertEqual(self.result(20), "北京 · 食品配送01")
        self.assertEqual(len(self.g.warnings), 1)

    def test_freight_order_follows_player_stops_without_supply_inference(self):
        _, source = self.industry(100, 1, "北京 煤矿", output=True)
        _, target = self.industry(101, 1, "北京 钢铁厂")
        self.station(200, 1, cargo=[source])
        self.station(201, 1, cargo=[target])
        self.line(groups=(201, 200), load=(0,), supported=[0])
        self.assertEqual(self.result(), "北京 - 钢铁厂 - 煤矿 · 煤炭01")

    def test_local_and_cross_city_worker_services(self):
        pc, _ = self.building(1)
        industry, _ = self.industry(100, 1, "北京 食品厂", cargo=1)
        self.station(200, 1, passenger=[pc])
        self.station(201, 1, passenger=[industry])
        self.line(supported=[7])
        self.assertEqual(self.result(), "北京 - 食品厂 - 通勤01")
        self.industry(100, 2, "天津 食品厂", cargo=1)
        self.g.advance()
        self.assertEqual(self.result(), "北京 - 天津 - 食品厂 - 通勤")

    def test_factory_passenger_candidate_requires_workplaces(self):
        self.city_pair()
        industry, _ = self.industry(100, 1, "北京 食品厂")
        self.g.components[industry].PERSON_CAPACITY.capacity = 0
        self.station(201, 1, passenger=[industry])
        self.line(supported=[7])
        self.assertNotIn("通勤", self.result())

    def test_multiple_factories_and_mixed_city_coverage_keep_station_name(self):
        pc, _ = self.building(1)
        industry_a, _ = self.industry(100, 1, "食品厂")
        industry_b, _ = self.industry(101, 1, "钢铁厂")
        self.station(200, 1, passenger=[pc])
        self.station(201, 1, name="工业园", passenger=[industry_a, industry_b])
        self.line(supported=[7])
        self.assertEqual(self.result(), "北京 - 工业园 - 公交01")
        self.station(201, 1, name="工业园", passenger=[industry_a, pc])
        self.g.advance()
        self.assertEqual(self.result(), "北京 - 工业园 - 公交01")

    def test_freight_filters_unrelated_industry_using_dedicated_cargo(self):
        _, coal = self.industry(100, 1, "煤矿", output=True)
        _, food = self.industry(101, 1, "食品厂", cargo=1, output=True)
        _, steel = self.industry(102, 1, "钢铁厂")
        self.station(200, 1, cargo=[coal, food])
        self.station(201, 1, cargo=[steel])
        self.line(load=(0,), supported=[0, 1])
        self.assertEqual(self.result(), "北京 - 煤矿 - 钢铁厂 · 煤炭01")

    def test_same_cargo_multiple_factories_are_not_arbitrarily_picked(self):
        _, a = self.industry(100, 1, "一号煤矿", output=True)
        _, b = self.industry(101, 1, "二号煤矿", output=True)
        _, c = self.industry(102, 1, "钢铁厂")
        self.station(200, 1, name="煤矿总站", cargo=[a, b])
        self.station(201, 1, cargo=[c])
        self.line(load=(0,), supported=[0])
        self.assertEqual(self.result(), "北京 - 煤矿总站 - 钢铁厂 · 煤炭01")

    def test_town_delivery_uses_cargo_building_stock_owner(self):
        _, stock_a = self.building(1)
        _, stock_b = self.building(1)
        self.station(200, 1, cargo=[stock_a])
        self.station(201, 1, cargo=[stock_b])
        self.line(load=(1,), supported=[0, 1, 2])
        self.assertEqual(self.result(), "北京 · 食品配送01")

    def test_symmetric_return_leg_and_middle_city_are_preserved(self):
        for group, town in ((200, 1), (201, 2), (202, 3)):
            pc, _ = self.building(town)
            self.station(group, town, passenger=[pc])
        self.line(groups=(200, 201, 202, 201), supported=[7], carrier=1)
        self.assertEqual(self.result(), "北京 - 天津 - 上海 - 客运")
        self.line(groups=(200, 201, 200), supported=[7])
        self.g.advance()
        self.assertEqual(self.result(), "北京 - 天津 - 客运")

    def test_non_symmetric_routes_do_not_guess_a_turnaround(self):
        for group, town in ((200, 1), (201, 2), (202, 3), (203, 1)):
            pc, _ = self.building(town)
            self.station(group, town, passenger=[pc])
        self.line(groups=(200, 201, 202, 203), supported=[7], carrier=1)
        self.assertEqual(self.result(), "北京 - 天津 - 上海 - 北京 - 客运")

    def test_alternative_stations_and_primary_station_use_native_indices(self):
        self.city_pair()
        industry, _ = self.industry(100, 2, "天津 食品厂")
        station = self.put(STATION={})
        self.g.stationTowns[station] = 2
        self.g.catchables[station] = self.table({"passenger": [industry], "cargo": []})
        self.g.components[201].STATION_GROUP.stations[2] = station
        self.line(supported=[7])
        stop = self.g.components[10].LINE.stops[2]
        stop.station = 1
        self.assertEqual(self.result(), "北京 - 天津 - 食品厂 - 通勤")
        stop.alternativeTerminals = self.table([{"station": 0, "terminal": 0}])
        self.g.advance()
        result = self.result()
        self.assertNotIn("通勤", result)
        self.assertIn("站点201", result)

    def test_unknown_and_empty_lines_keep_conservative_names(self):
        self.line(groups=(), load=(), name="自定义风景线")
        self.assertEqual(self.result(), "自定义风景线")
        self.station(200, -1, name="西站")
        self.station(201, -1, name="东站")
        self.line(load=(), name="新线")
        self.g.advance()
        self.assertEqual(self.result(), "西站 - 东站 - 线路01")

    def test_ambiguous_freight_does_not_list_every_supported_cargo(self):
        self.station(200, 1)
        self.station(201, 2)
        self.line(load=(0, 1, 2), supported=[0, 1, 2])
        self.assertEqual(self.result(), "北京 - 天津 · 货运01")
        self.g.capacities[10].current = self.table({1: {"capacity": 20, "used": 10}})
        self.g.advance()
        self.assertEqual(self.result(), "北京 - 天津 · 煤炭01")

    def test_partial_apply_reload_and_other_players_do_not_steal_numbers(self):
        self.city_pair()
        self.line(10, supported=[7])
        self.line(20, supported=[7])
        self.line(5, supported=[7], owner=8, name="北京 - 公交01")
        second = self.result(20)
        self.g.components[20].name = second
        self.g.advance()
        self.assertEqual(self.result(10), "北京 - 公交01")
        self.assertEqual(self.result(20), "北京 - 公交02")
        self.g.components[10].name = self.result(10)
        self.g.session = self.table({})
        self.line(30, supported=[7])
        self.assertEqual(self.result(30), "北京 - 公交03")
        self.assertEqual(self.result(20), "北京 - 公交02")

    def test_existing_reserved_names_and_duplicate_names_do_not_collide(self):
        self.city_pair()
        self.line(10, supported=[7], name="北京 - 公交03")
        self.line(20, supported=[7], name="北京 - 公交03")
        self.line(30, groups=(), load=(), name="北京 - 公交01")
        self.assertEqual(self.result(10), "北京 - 公交03")
        self.assertEqual(self.result(20), "北京 - 公交02")
        self.assertEqual(self.result(30), "北京 - 公交01")

    def test_unrenameable_line_keeps_its_name_before_retaining_other_numbers(self):
        self.city_pair()
        self.line(10, supported=[7], name="北京 - 公交01")
        self.line(20, groups=(), load=(), name="北京 - 公交01")
        self.assertEqual(self.result(10), "北京 - 公交02")
        self.assertEqual(self.result(20), "北京 - 公交01")

    def test_temporary_collision_does_not_change_intercity_number_on_second_apply(self):
        self.city_pair(second=2)
        self.line(10, supported=[7], carrier=1)
        self.line(20, groups=(200, 200), supported=[7], name="北京 - 天津 - 客运")
        first, second = self.result(10), self.result(20)
        self.assertEqual(first, "北京 - 天津 - 客运01")
        self.g.components[10].name, self.g.components[20].name = first, second
        self.g.advance()
        self.assertEqual(self.result(10), first)
        self.assertEqual(self.result(20), second)

    def test_unselected_line_with_deleted_stations_does_not_break_other_previews(self):
        self.city_pair()
        self.line(10, supported=[7])
        self.line(20, groups=(404, 405), load=(0,), name="旧线路")
        self.assertEqual(self.result(10), "北京 - 公交01")
        self.assertEqual(self.result(20), "旧线路")

    def test_one_line_api_failure_does_not_discard_other_names_or_its_reservation(self):
        self.city_pair()
        self.line(10, supported=[7])
        self.line(20, supported=[7], name="北京 - 公交01")
        self.lua.execute("""
            local native = api.engine.util.line.getLineCapacityUsages
            api.engine.util.line.getLineCapacityUsages = function(id, all)
                if id == 20 then error('one invalid line') end
                return native(id, all)
            end
        """)
        self.assertEqual(self.result(10), "北京 - 公交02")
        scans = self.g.scans.LINE
        self.assertEqual(self.result(20), "北京 - 公交01")
        for _ in range(50):
            self.result(10)
        self.assertEqual(self.g.scans.LINE, scans)
        self.g.advance()
        self.result(10)
        self.assertEqual(self.g.scans.LINE, scans + 1)
        self.assertEqual(len(self.g.warnings), 1)

    def test_preview_reads_world_singleton_when_game_time_cannot_be_enumerated(self):
        self.city_pair()
        self.line(supported=[7], name="原来的名字")
        self.g.worldEntity = 888
        self.g.components[888] = self.g.components[999]
        self.g.components[999] = None
        self.assertEqual(self.result(), "北京 - 公交01")
        self.assertEqual(len(self.g.warnings), 0)

    def test_failed_api_read_keeps_name_without_sending_commands(self):
        self.city_pair()
        self.line(supported=[7], name="保留我的名字")
        self.g.failCatchment = True
        self.assertEqual(self.result(), "保留我的名字")
        self.assertEqual(len(self.g.warnings), 1)
        self.g.failCatchment = False
        self.g.advance()
        self.assertEqual(self.result(), "北京 - 公交01")

    def test_custom_industry_names_and_pattern_characters_are_preserved(self):
        self.g.components[1].name = "A+B"
        _, a = self.industry(100, 1, "A+B 特选煤矿", output=True)
        _, b = self.industry(101, 1, "A+B老字号钢厂")
        self.station(200, 1, cargo=[a])
        self.station(201, 1, cargo=[b])
        self.line(load=(0,), supported=[0])
        self.assertEqual(self.result(), "A+B - 特选煤矿 - A+B老字号钢厂 · 煤炭01")

    def test_resources_resolve_to_lua_data_callback_and_keep_original_schemes(self):
        self.g.resolve = lambda path: "xin_line_names_1::/line_names/" + path
        self.lua.execute((CONTENT / "component.res.lua").read_text(encoding="utf-8"))
        component = self.g.data()
        self.lua.execute((CONTENT / "scheme.res.lua").read_text(encoding="utf-8"))
        scheme = self.g.data()
        self.assertEqual(component.type, "rename_scheme_component")
        self.assertEqual(scheme.type, "rename_scheme")
        self.assertEqual(scheme.data.formatParams.name, component.data.schemeComponentNameRaw)
        self.assertEqual(component.data.renameFnDefinition.fileName,
                         "xin_line_names_1::/line_names/naming.script@renameFn")
        self.assertEqual(scheme.data.formatString, "{name}")


@unittest.skipUnless(os.environ.get("TF3_GAME_DIR"), "Set TF3_GAME_DIR to inspect native contracts")
class NativeContracts(unittest.TestCase):
    def test_native_callback_and_data_sources(self):
        game = Path(os.environ["TF3_GAME_DIR"])
        with ZipFile(game / "base/content/gui.zip") as archive:
            manager = archive.read("gui/line_vehicle_mgmt/manager_window.tl").decode("utf-8")
            cargo = archive.read("gui/main/cargo_util.tl").decode("utf-8")
            line = archive.read("gui/line_vehicle_mgmt/line_util.tl").decode("utf-8")
            industry = archive.read("gui/entity_window/industry/industry.tl").decode("utf-8")
            town = archive.read("gui/entity_window/town/town.tl").decode("utf-8")
            self.assertIn('getAllOfType("rename_scheme_component")', manager)
            self.assertIn('getAllOfType("rename_scheme")', manager)
            self.assertIn("lineEntity = line,", manager)
            self.assertIn("cargoTypeIndex - 1", cargo)
            self.assertIn("getLineCapacityUsages(locationParams.lineEntity", cargo)
            self.assertIn("getStockCargoTypes(stockListEntity, (i - 1)", cargo)
            self.assertIn("stop.station1 = v.station + 1", line)
            self.assertIn("api.engine.getComponent(api.engine.util.getWorld(), api.type.ComponentType.GAME_TIME)", industry)
            self.assertIn("api.engine.system.townBuildingSystem.getTown2BuildingMap()", town)
        engine = (game / "api/tealdef/api/engine.d.tl").read_text(encoding="utf-8")
        system = (game / "api/tealdef/api/engine/system.d.tl").read_text(encoding="utf-8")
        util = (game / "api/tealdef/api/engine/util.d.tl").read_text(encoding="utf-8")
        self.assertIn('whether to return all capacities or the capacities for the vehicles current load config', util)
        self.assertIn('getLineCapacityUsages : function(line : Engine.Entity, allCapacities : boolean)', util)
        for symbol in ("stockList : Engine.Entity", "tickCount : integer", "town : Engine.Entity"):
            self.assertIn(symbol, engine)
        for symbol in ("getStationCatchables", "getPersonCapacity2townBuildingMap",
                       "getConstructionClosestTown", "getLinesForPlayer"):
            self.assertIn(symbol, system)


if __name__ == "__main__":
    unittest.main()
