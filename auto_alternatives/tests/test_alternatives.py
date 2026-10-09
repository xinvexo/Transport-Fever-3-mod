from pathlib import Path
import unittest

from lupa.lua52 import LuaRuntime, lua_type


CONTENT = Path(__file__).resolve().parents[1] / "content/auto_alternatives"
BUS, TRUCK, TRAM, TRAIN, SHIP, AIRCRAFT, HELICOPTER, ELECTRIC_TRAIN, ELECTRIC_TRAM = range(9)


def terminal(mode=BUS, cargo=False, tag=None):
    result = {
        "transportModes": {mode: True, "CARGO" if cargo else "PERSON": True},
        "passengersLoad": not cargo,
        "passengersUnload": not cargo,
        "cargoLoad": cargo,
        "cargoUnload": cargo,
    }
    if tag is not None:
        result["tag"] = tag
    return result


def stop(group, station=0, platform=0, alternatives=()):
    return {
        "stationGroup": group,
        "station": station,
        "terminal": platform,
        "alternativeTerminals": [
            {"station": s, "terminal": t} for s, t in alternatives
        ],
        "loadMode": 2,
        "minWaitingTime": 12,
        "maxWaitingTime": 70,
        "maxAdditionalWaitingTime": 19,
        "waypoints": [901, 902],
        "stopConfig": {
            "load": [True, False, True],
            "maxLoad": [0.5, 0, 1],
            "forceUnload": True,
            "destroyForConfigChange": False,
            "destroyForRefresh": True,
        },
    }


def alternatives(stops, index=0):
    return [
        (item["station"], item["terminal"])
        for item in stops[index]["alternativeTerminals"]
    ]


class AlternativesTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("""
            function copy(value)
                if type(value) ~= 'table' then return value end
                local result = {}
                for key, item in pairs(value) do result[key] = copy(item) end
                return result
            end
            components, stationGroups, calls, warnings, rejected = {}, {}, {}, {}, {}
            modules, originalCalls, originalStops = {}, {}, {}
            state = {
                value = {},
                get = function(self) return copy(self.value) end,
                set = function(self, value) self.value = copy(value) end,
                subscriptions = {},
                hasEventSubscriptions = function(self) return next(self.subscriptions) ~= nil end,
                subscribeToEvent = function(self, event) self.subscriptions[event] = true end,
                subscribeToNoEvents = function(self) self.subscriptions = {} end,
            }
            log = {warning = function(message) warnings[#warnings + 1] = message end,
                message = function(message) end}
            api = {
                engine = {
                    entityExists = function(entity) return components[entity] ~= nil end,
                    getComponent = function(entity, kind)
                        assert(components[entity], 'getComponent requires an existing entity')
                        return copy(components[entity][kind])
                    end,
                    util = {getPlayer = function() return 7 end},
                    system = {
                        stationGroupSystem = {getStationGroup = function(station)
                            return stationGroups[station]
                        end},
                        lineSystem = {getLinesForStationGroup = function(group)
                            local result = {}
                            for entity, component in pairs(components) do
                                if component.LINE then
                                    for index, stop in ipairs(component.LINE.stops) do
                                        if stop.stationGroup == group then
                                            result[#result + 1] = entity
                                            break
                                        end
                                    end
                                end
                            end
                            return result
                        end},
                    },
                },
                type = {
                    enum = {TransportMode = {PERSON = 'PERSON', CARGO = 'CARGO',
                        BUS = 0, TRUCK = 1, TRAM = 2, TRAIN = 3, SHIP = 4,
                        AIRCRAFT = 5, HELICOPTER = 6, ELECTRIC_TRAIN = 7, ELECTRIC_TRAM = 8}},
                    ComponentType = {LINE = 'LINE', STATION = 'STATION',
                        STATION_GROUP = 'STATION_GROUP', EDGE_OBJECT = 'EDGE_OBJECT',
                        CONSTRUCTION = 'CONSTRUCTION', PLAYER_OWNED = 'PLAYER_OWNED'},
                    Line = {new = function(line) return copy(line) end},
                    StationTerminal = {new = function(station, platform)
                        return {station = station, terminal = platform}
                    end},
                },
                cmd = {
                    makeLineUpdateCmd = function(entity, line)
                        return {entity = entity, line = copy(line)}
                    end,
                    sendCommand = function(command)
                        calls[#calls + 1] = copy(command)
                        if rejected[command.entity] then error('line update rejected') end
                        components[command.entity].LINE = copy(command.line)
                    end,
                },
            }
            lineUtil = {autoAssignTerminals = function(entity, path)
                originalCalls[#originalCalls + 1] = {entity = entity, path = copy(path)}
                return copy(originalStops)
            end}
            modules['::/gui/main/react.lua'] = {
                RegisterPluginRecipe = function(extension, name, recipe) return recipe end,
            }
            modules['::/gui/main/mod_entry_point.tl'] = {ModEntryPointExtension = {}}
            function ug_require(name)
                if name == '::/gui/line_vehicle_mgmt/line_util.tl' then return lineUtil end
                assert(modules[name], 'unexpected module ' .. name)
                return modules[name]
            end
        """)
        for name in ("selection", "assignment"):
            self.lua.globals().modules[
                f"xin_auto_alternatives_1::/auto_alternatives/{name}.lua"
            ] = self.lua.execute((CONTENT / f"{name}.lua").read_text(encoding="utf-8"))
        self.lua.execute((CONTENT / "ui_entry.script.lua").read_text(encoding="utf-8"))
        self.lua.execute("uiEntry = data().entry; uiEntry()")
        self.lua.execute((CONTENT / "events.script.lua").read_text(encoding="utf-8"))
        self.lua.execute("handlers = data()")
        self.tick()

    def table(self, value):
        return self.lua.table_from(value, recursive=True)

    def plain(self, value):
        if lua_type(value) != "table":
            return value
        items = {key: self.plain(item) for key, item in value.items()}
        if set(items) == set(range(1, len(items) + 1)):
            return [items[index] for index in range(1, len(items) + 1)]
        return items

    def group(self, entity, *station_terminals):
        station_ids = [entity * 10 + i for i in range(len(station_terminals))]
        self.lua.globals().components[entity] = self.table(
            {"STATION_GROUP": {"stations": station_ids}}
        )
        for station_index, (station_id, terminals) in enumerate(zip(station_ids, station_terminals)):
            self.lua.globals().components[station_id] = self.table(
                {"STATION": {"tag": 100 + station_index, "terminals": [
                    {**item, "tag": item.get("tag", 1000 + index)}
                    for index, item in enumerate(terminals)
                ]}}
            )
            self.lua.globals().stationGroups[station_id] = entity
        return station_ids

    def line(self, entity, stops, mode=BUS, player=7):
        self.lua.globals().components[entity] = self.table({
            "PLAYER_OWNED": {"player": player},
            "LINE": {
                "stops": stops,
                "vehicleInfo": {"transportModes": {mode: True, "PERSON": True, "CARGO": True}},
                "customFilters": True,
                "reservationPriority": 3,
            },
        })

    def construction(self, entity, stations):
        self.lua.globals().components[entity] = self.table(
            {"CONSTRUCTION": {"stations": stations}}
        )

    def rebuilding(self, *constructions):
        self.proposal = {
            "toRemove": list(constructions),
            "old2new": {entity: index for index, entity in enumerate(constructions)},
        }
        self.lua.globals().handlers.handleEvent(
            None, self.lua.globals().state, None,
            "apply_command", "onPreBuildProposal",
            self.table([self.proposal]),
        )

    def built(self, *constructions):
        self.lua.globals().handlers.handleEvent(
            None, self.lua.globals().state, None,
            "apply_command", "onPostBuildProposal",
            self.table([self.proposal, {}, list(constructions)]),
        )

    def tick(self):
        self.lua.globals().handlers.update(None, self.lua.globals().state)

    def saved_line(self, entity):
        return self.plain(self.lua.globals().components[entity].LINE)

    def path(self, stops, new=False):
        result = []
        for item in stops:
            via = {"stationGroup": item["stationGroup"],
                   "station1": item["station"] + 1, "terminal1": item["terminal"] + 1}
            if not new:
                via["alternativeTerminals"] = item["alternativeTerminals"]
            result.append({"stop": via})
        return result

    def auto_assign(self, stops, entity=1, path=None):
        self.lua.globals().originalStops = self.table(stops)
        return self.plain(self.lua.globals().lineUtil.autoAssignTerminals(
            entity, self.table(path if path is not None else self.path(stops, new=True))
        ))

    def test_modes_respect_rail_exclusion_and_isolate_mixed_hubs(self):
        for name, mode in zip(
            ("bus", "truck", "tram", "train", "ship", "aircraft", "helicopter", "electric_train", "electric_tram"),
            range(9),
        ):
            with self.subTest(mode=name):
                self.setUp()
                cargo = mode == TRUCK
                wrong_mode = (mode + 1) % 9
                primary = terminal(mode, cargo)
                primary["transportModes"][wrong_mode] = True
                self.group(100,
                    [terminal(mode, not cargo)],
                    [terminal(wrong_mode, cargo), primary, terminal(mode, cargo)],
                    [terminal(mode, cargo)],
                )
                self.group(200, [terminal(mode, cargo), terminal(mode, cargo)])
                rail = mode in (TRAIN, ELECTRIC_TRAIN)
                original = [stop(100, 1, 1, alternatives=[(2, 0)] if rail else []), stop(200)]
                self.line(1, original, mode)
                result = self.auto_assign(original)
                self.assertEqual(alternatives(result), [(2, 0)] if rail else [(1, 2), (2, 0)])
                self.assertEqual(alternatives(result, 1), [] if rail else [(0, 1)])

    def test_new_lines_without_vehicle_modes_use_primary_station_modes(self):
        cases = [
            (None, BUS, False, {}),
            (-1, TRUCK, True, {}),
            (1, BUS, False, {BUS: False, TRUCK: False}),
            (1, TRAIN, False, {"PERSON": True}),
            (None, ELECTRIC_TRAIN, False, {}),
            (None, ELECTRIC_TRAM, False, {}),
            (1, TRUCK, True, {"CARGO": True}),
        ]
        for entity, mode, cargo, modes in cases:
            with self.subTest(entity=entity, mode=mode, modes=modes):
                self.setUp()
                self.group(100, [terminal(mode, cargo), terminal(mode, cargo)],
                    [terminal((mode + 1) % 9, cargo)])
                self.group(200, [terminal(mode, cargo), terminal(mode, cargo)])
                original = [stop(100), stop(200)]
                if entity == 1:
                    self.line(1, original, mode)
                    self.lua.globals().components[1].LINE.vehicleInfo.transportModes = self.table(modes)
                result = self.auto_assign(original, entity)
                expected = [] if mode in (TRAIN, ELECTRIC_TRAIN) else [(0, 1)]
                self.assertEqual(alternatives(result), expected)
                self.assertEqual(alternatives(result, 1), expected)

    def test_gui_preserves_original_assignment_and_settings(self):
        self.group(100, [terminal(), terminal(), terminal()])
        self.group(200, [terminal(), terminal()])
        self.line(1, [stop(100), stop(200)])
        original = [stop(100, platform=2, alternatives=[(0, 1)]), stop(200)]
        original[0]["minWaitingTime"] = 43
        original[0]["stopConfig"]["maxLoad"] = [0.25, 0.75, 1]
        path = self.path(original)
        path.insert(1, {"waypoint": {"tag": 91}})
        result = self.auto_assign(original, path=path)
        self.assertEqual(self.lua.eval("#originalCalls"), 1)
        self.assertEqual(self.lua.eval("originalCalls[1].entity"), 1)
        self.assertEqual(self.plain(self.lua.eval("originalCalls[1].path")), path)
        self.assertEqual(alternatives(result), [(0, 1), (0, 0)])
        self.assertEqual(alternatives(result, 1), [])
        for old_stop, new_stop in zip(original, result):
            old_stop.pop("alternativeTerminals")
            new_stop.pop("alternativeTerminals")
        self.assertEqual(result, original)
        self.assertEqual(self.lua.eval("#calls"), 0)

    def test_gui_failure_after_first_stop_preserves_full_native_assignment(self):
        self.group(100, [terminal(), terminal()])
        self.group(200, [terminal(), terminal()])
        original = [stop(100), stop(200)]
        self.lua.execute("""
            local getComponent = api.engine.getComponent
            api.engine.getComponent = function(entity, kind)
                if entity == 200 then error('station data unavailable') end
                return getComponent(entity, kind)
            end
        """)
        result = self.auto_assign(original, entity=None)
        self.assertEqual(result, original)
        self.assertEqual(self.lua.eval("#warnings"), 1)
        self.assertIn("station data unavailable", self.lua.eval("warnings[1]"))

    def test_repeated_visits_share_only_current_assignment_station_snapshot(self):
        self.group(100, [terminal(), terminal()])
        self.lua.execute("""
            reads = {}
            local getComponent = api.engine.getComponent
            api.engine.getComponent = function(entity, kind)
                reads[entity] = (reads[entity] or 0) + 1
                return getComponent(entity, kind)
            end
        """)
        original = [stop(100), stop(100, platform=1)]
        result = self.auto_assign(original, entity=None)
        self.assertEqual(alternatives(result), [(0, 1)])
        self.assertEqual(alternatives(result, 1), [(0, 0)])
        self.assertEqual(self.lua.eval("reads[100]"), 1)
        self.assertEqual(self.lua.eval("reads[1000]"), 2)
        self.group(100, [terminal(), terminal(), terminal()])
        result = self.auto_assign(original, entity=None)
        self.assertEqual(alternatives(result), [(0, 1), (0, 2)])
        self.assertEqual(self.lua.eval("reads[100]"), 2)


    def test_removed_previous_station_is_not_read_during_preferred_change(self):
        self.group(100, [terminal(), terminal()])
        original = [stop(100)]
        self.line(1, original)
        self.lua.globals().components[1000] = None
        edited = [stop(100, platform=1)]
        self.assertEqual(self.auto_assign(edited, path=self.path(edited)), edited)
        self.assertEqual(self.lua.eval("#warnings"), 0)

    def test_single_and_double_roadside_stops_do_not_become_terminal_choices(self):
        self.group(100, [terminal(), terminal()], [terminal()])
        self.group(200, [terminal()], [terminal()])
        self.group(300, [terminal()])
        for entity in (1001, 2000, 2001, 3000):
            self.lua.globals().components[entity].EDGE_OBJECT = self.table({"type": "STOP"})
        original = [stop(100), stop(200), stop(300)]
        self.line(1, original)
        result = self.auto_assign(original)
        self.assertEqual(alternatives(result), [(0, 1)])
        self.assertEqual(alternatives(result, 1), [])
        self.assertEqual(alternatives(result, 2), [])

    def test_manual_unused_choices_survive_edits_and_later_expansion(self):
        for kept in ([], [(0, 2)]):
            with self.subTest(kept=kept):
                self.setUp()
                stations = self.group(100, [terminal() for _ in range(4)])
                self.group(200, [terminal(), terminal()])
                self.construction(500, stations)
                self.line(1, [stop(100, alternatives=[(0, 1), (0, 2)]), stop(200)])
                edited = [stop(100, alternatives=kept), stop(200)]
                result = self.auto_assign(edited, path=self.path(edited))
                self.assertEqual(alternatives(result), kept)
                self.assertEqual(alternatives(result, 1), [])
                self.line(1, result)
                result[0]["minWaitingTime"] = 35
                result = self.auto_assign(result, path=self.path(result))
                self.assertEqual(alternatives(result), kept)
                self.line(1, result)
                self.rebuilding(500)
                self.group(100, [terminal() for _ in range(5)])
                self.built(500)
                self.tick()
                saved = self.saved_line(1)["stops"]
                self.assertEqual(alternatives(saved), kept + [(0, 4)])
                self.assertEqual(saved[0]["minWaitingTime"], 35)

    def test_expansion_updates_only_affected_stops_and_player_lines(self):
        stations = self.group(100, [terminal(), terminal()], [terminal(TRUCK, True)])
        self.group(200, [terminal(), terminal()])
        self.construction(500, stations)
        self.construction(501, [])
        self.line(1, [
            stop(100, alternatives=[(1, 0)]),
            stop(200),
            stop(100, platform=1),
        ])
        self.line(2, [stop(100), stop(200)])
        self.line(3, [stop(200), stop(200, platform=1)])
        self.line(4, [stop(100), stop(200)], player=8)
        before = {entity: self.saved_line(entity) for entity in range(1, 5)}
        self.rebuilding(500, 501)
        self.group(100, [terminal(), terminal(), terminal()], [terminal(TRUCK, True)])
        self.built(500, 501)
        self.tick()
        self.assertTrue(self.lua.eval("state.subscriptions.onPreBuildProposal"))
        self.assertTrue(self.lua.eval("state.subscriptions.onPostBuildProposal"))
        self.assertEqual(self.lua.eval("#calls"), 2)
        first = self.saved_line(1)
        self.assertEqual(alternatives(first["stops"]), [(1, 0), (0, 2)])
        self.assertEqual(alternatives(first["stops"], 2), [(0, 2)])
        for entity in (1, 2):
            after = self.saved_line(entity)
            self.assertEqual(after["stops"][1], before[entity]["stops"][1])
            for old_stop, new_stop in zip(before[entity]["stops"], after["stops"]):
                old_stop.pop("alternativeTerminals")
                new_stop.pop("alternativeTerminals")
            self.assertEqual(after, before[entity])
        for entity in (3, 4):
            self.assertEqual(self.saved_line(entity), before[entity])

    def test_repeated_construction_events_merge_and_apply_latest_expansion(self):
        for mode, cargo in ((BUS, False), (TRUCK, True), (TRAM, False),
                            (TRAIN, False), (SHIP, True), (AIRCRAFT, False),
                            (HELICOPTER, False), (ELECTRIC_TRAIN, False),
                            (ELECTRIC_TRAM, False)):
            with self.subTest(mode=mode):
                self.setUp()
                stations = self.group(100, [terminal(mode, cargo) for _ in range(2)])
                self.group(200, [terminal(mode, cargo) for _ in range(2)])
                self.construction(500, stations)
                rail = mode in (TRAIN, ELECTRIC_TRAIN)
                self.line(1, [stop(100, alternatives=[(0, 1)] if rail else []), stop(200)], mode)
                self.rebuilding(500)
                self.group(100, [terminal(mode, cargo) for _ in range(3)])
                self.built(500)
                self.rebuilding(500)
                self.group(100, [terminal(mode, cargo) for _ in range(4)])
                self.built(500)
                self.tick()
                self.assertEqual(self.lua.eval("#calls"), 0 if rail else 1)
                self.assertEqual(alternatives(self.saved_line(1)["stops"]), [(0, 1)] if rail else [(0, 2), (0, 3)])
                self.rebuilding(500)
                self.built(500)
                self.tick()
                self.assertEqual(self.lua.eval("#calls"), 0 if rail else 1)
                self.rebuilding(500)
                self.group(100, [terminal(mode, cargo) for _ in range(5)])
                self.built(500)
                self.tick()
                self.assertEqual(self.lua.eval("#calls"), 0 if rail else 2)
                self.assertEqual(alternatives(self.saved_line(1)["stops"]), [(0, 1)] if rail else [(0, 2), (0, 3), (0, 4)])

    def test_rebuilt_station_expansion_and_preferred_terminal_change(self):
        stations = self.group(100, [terminal(), terminal()])
        self.group(200, [terminal()])
        self.construction(500, stations)
        self.line(1, [stop(100, alternatives=[(0, 1)]), stop(200)])
        self.rebuilding(500)
        self.lua.globals().components[1777] = self.table({
            "STATION": {"tag": 100, "terminals": [
                terminal(tag=999), terminal(tag=1000), terminal(tag=1001)]},
        })
        self.lua.globals().components[100].STATION_GROUP.stations = self.table([1777])
        self.lua.globals().stationGroups[1777] = 100
        self.lua.globals().components[1000] = None
        self.lua.globals().components[500] = None
        self.construction(501, [1777])
        self.line(1, [stop(100, platform=1, alternatives=[(0, 2)]), stop(200)])
        self.built(501)
        self.tick()
        self.assertEqual(alternatives(self.saved_line(1)["stops"]), [(0, 2), (0, 0)])

        preferred = self.saved_line(1)["stops"]
        preferred[0]["terminal"] = 2
        result = self.auto_assign(preferred, path=self.path(preferred))
        self.assertEqual(result[0]["terminal"], 2)
        self.assertEqual(alternatives(result), [(0, 0), (0, 1)])

    def test_batches_read_latest_primary_and_wait_settings_when_processed(self):
        stations = self.group(100, [terminal(), terminal()])
        self.group(200, [terminal(), terminal()])
        self.construction(500, stations)
        for entity in range(1, 11):
            self.line(entity, [stop(100), stop(200)])
        self.rebuilding(500)
        self.group(100, [terminal(), terminal(), terminal()])
        self.built(500)
        self.tick()
        self.assertEqual(self.lua.eval("#calls"), 8)
        processed = {call["entity"] for call in self.plain(self.lua.globals().calls)}
        remaining = set(range(1, 11)) - processed
        entity = min(remaining)
        edited = stop(100, platform=1)
        edited["minWaitingTime"] = 43
        edited["maxWaitingTime"] = 180
        edited["maxAdditionalWaitingTime"] = 60
        edited["stopConfig"]["maxLoad"] = [0.25, 0.75, 1]
        self.lua.globals().components[entity].LINE.stops[1] = self.table(edited)
        self.tick()
        self.assertEqual(self.lua.eval("#calls"), 10)
        self.assertEqual(alternatives(self.saved_line(entity)["stops"]), [(0, 2)])
        actual = self.saved_line(entity)["stops"][0]
        actual.pop("alternativeTerminals")
        edited.pop("alternativeTerminals")
        self.assertEqual(actual, edited)

    def test_rejected_update_leaves_component_intact_and_other_lines_progress(self):
        stations = self.group(100, [terminal(), terminal()])
        self.group(200, [terminal(), terminal()])
        self.construction(500, stations)
        for entity in (1, 2):
            self.line(entity, [stop(100), stop(200)])
        self.lua.globals().rejected[1] = True
        before = self.saved_line(1)
        self.rebuilding(500)
        self.group(100, [terminal(), terminal(), terminal()])
        self.built(500)
        self.tick()
        self.assertEqual(self.saved_line(1), before)
        self.assertEqual(alternatives(self.saved_line(2)["stops"]), [(0, 2)])
        self.assertEqual(self.lua.eval("#calls"), 2)
        self.assertEqual(self.lua.eval("#warnings"), 1)


if __name__ == "__main__":
    unittest.main()
