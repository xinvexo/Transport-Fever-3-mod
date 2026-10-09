"""Behavior tests in Lua 5.2; optional checks against installed native sources."""

import json
import os
from pathlib import Path
import unittest
from zipfile import ZipFile

from lupa.lua52 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content/line_vehicle_colors"
RED = (0.85, 0.1, 0.15)
BLUE = (0.1, 0.3, 0.9)
DEFAULT = (-1, -1, -1)


class ColorsTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("""
            function copy(value)
                if type(value) ~= 'table' then return value end
                local result = {}
                for key, item in pairs(value) do result[key] = copy(item) end
                return result
            end
            function vec(x, y, z)
                return {x=x, y=y, z=z, clone=function(self) return copy(self) end}
            end
            components, models, calls, warnings, queue = {}, {}, {}, {}, {}
            reject, throws, brokenRead, staleMembers = {}, {}, {}, {}
            currentPlayer, deferred, lineQueries, vehicleQueries, vehicleReads = 7, false, 0, 0, 0
            state = {value={}, subscriptions={},
                get=function(self) return copy(self.value) end,
                set=function(self,value) self.value=copy(value) end,
                hasEventSubscriptions=function(self) return next(self.subscriptions) ~= nil end,
                subscribeToNoEvents=function(self) self.subscriptions={} end,
                subscribeToEvent=function(self,name) self.subscriptions[name]=true end,
            }
            function addLine(id, color, player)
                components[id] = {LINE={name='keep line name', stops={40, 50}},
                    COLOR={color=color}, PLAYER_OWNED={player=player or 7}}
            end
            function addVehicle(id, line, parts, player)
                components[id] = {PLAYER_OWNED={player=player or 7},
                    TRANSPORT_VEHICLE={line=line, transportVehicleConfig={vehicles=parts},
                        cargo={42}, name='keep vehicle name'}}
            end
            function apply(command, callback)
                local success = not reject[command.entity] and components[command.entity] ~= nil
                if success then
                    local tv = components[command.entity].TRANSPORT_VEHICLE
                    assert(tv, 'must never paint the line itself')
                    for _, entry in ipairs(tv.transportVehicleConfig.vehicles) do
                        local meta = models[entry.part.modelId].metadata.transportVehicle
                        if not meta.noCblendMask then entry.part.color = copy(command.color) end
                    end
                end
                if callback then callback(command, success) end
            end
            function flush()
                local commands = queue
                queue = {}
                for _, entry in ipairs(commands) do apply(entry.command, entry.callback) end
            end
            log = {warning=function(message) warnings[#warnings+1] = message end}
            api = {
                type = {ComponentType={LINE='LINE', COLOR='COLOR',
                    PLAYER_OWNED='PLAYER_OWNED', TRANSPORT_VEHICLE='TRANSPORT_VEHICLE'}},
                engine = {
                    entityExists=function(id) return components[id] ~= nil end,
                    getRevision=function(id) return {num={1,0,0}} end,
                    getComponent=function(id, kind)
                        if brokenRead[id] then error('component unavailable') end
                        if kind == 'TRANSPORT_VEHICLE' then vehicleReads=vehicleReads+1 end
                        return copy(components[id] and components[id][kind])
                    end,
                    util={getPlayer=function() return currentPlayer end},
                    system={
                        lineSystem={getLinesForPlayer=function(player)
                            lineQueries=lineQueries+1
                            local result={}
                            for id, c in pairs(components) do
                                if c.LINE and c.PLAYER_OWNED.player == player then
                                    result[#result+1]=id
                                end
                            end
                            table.sort(result)
                            return result
                        end},
                        transportVehicleSystem={getLineVehicles=function(line)
                            vehicleQueries=vehicleQueries+1
                            if staleMembers[line] then return copy(staleMembers[line]) end
                            local result={}
                            for id, c in pairs(components) do
                                if c.TRANSPORT_VEHICLE and c.TRANSPORT_VEHICLE.line == line then
                                    result[#result+1]=id
                                end
                            end
                            table.sort(result)
                            return result
                        end},
                    },
                },
                res={modelRep={get=function(id) return copy(models[id]) end}},
                cmd={
                    makeEntitySetColorCmd=function(id, color)
                        assert(color.clone, 'native Vec3f required')
                        return {entity=id, color=copy(color)}
                    end,
                    sendCommand=function(command, callback)
                        assert(callback == nil, 'Callbacks are currently disallowed')
                        calls[#calls+1]=copy(command)
                        if throws[command.entity] then error('send failed') end
                        if deferred then queue[#queue+1]={command=copy(command), callback=callback}
                        else apply(command, callback) end
                    end,
                },
            }
        """)
        self.g = self.lua.globals()
        self.model(1)
        self.model(2, paintable=False)
        self.load_script()

    def load_script(self):
        self.lua.execute((CONTENT / "colors.script.lua").read_text(encoding="utf-8"))
        self.lua.execute("handlers = data()")

    def model(self, model_id, paintable=True):
        self.g.models[model_id] = self.lua.table_from(
            {"metadata": {"transportVehicle": {"noCblendMask": not paintable}}}, recursive=True
        )

    def line(self, entity=10, color=RED, owner=7):
        self.g.addLine(entity, self.g.vec(*color), owner)

    def vehicle(self, entity=100, line=10, parts=None, owner=7):
        parts = parts or [(1, DEFAULT)]
        entries = [{"part": {"modelId": model, "color": self.g.vec(*color),
                            "reversed": False, "compartment2loadConfig": [2, -1]},
                    "purchaseTime": 123, "maintenanceChange": 4} for model, color in parts]
        self.g.addVehicle(entity, line, self.lua.table_from(entries, recursive=True), owner)

    def tick(self, count=1, dt=1 / 60):
        for _ in range(count):
            self.g.handlers.update(None, self.g.state, dt)

    def event(self, name, params):
        self.g.handlers.handleEvent(None, self.g.state, "", "xin_line_vehicle_colors", name,
                                   self.lua.table_from(params, recursive=True))

    def assigned(self, entity, line, old=-1):
        self.event("vehiclesAssigned", {"entries": [{"entity": entity, "line": line,
                                                     "fromLine": old, "revision": 1}]})

    def color(self, entity, part=1):
        color = self.g.components[entity].TRANSPORT_VEHICLE.transportVehicleConfig.vehicles[part].part.color
        return tuple(color[key] for key in ("x", "y", "z"))

    def set_line_color(self, entity, color):
        self.g.components[entity].COLOR.color = self.g.vec(*color)
        self.event("lineColorChanged", {"line": entity})

    def test_existing_vehicles_follow_distinct_line_colors_without_changing_lines(self):
        self.line()
        self.line(20, BLUE)
        self.vehicle(100)
        self.vehicle(200, 20)
        self.tick()
        self.assertEqual(self.color(100), RED)
        self.assertEqual(self.color(200), BLUE)
        self.assertEqual(self.g.components[10].COLOR.color.x, RED[0])
        self.assertEqual(self.g.components[10].LINE.name, "keep line name")
        tv = self.g.components[100].TRANSPORT_VEHICLE
        self.assertEqual(tv.name, "keep vehicle name")
        self.assertEqual(tv.cargo[1], 42)
        self.assertEqual(tv.transportVehicleConfig.vehicles[1].part.compartment2loadConfig[1], 2)

    def test_simulation_updates_do_not_use_command_callbacks(self):
        self.line()
        self.vehicle()
        self.tick()
        self.assertEqual(self.color(100), RED)
        self.assertEqual(len(self.g.warnings), 0)
        self.assertEqual(len(self.g.calls), 1)

    def test_new_vehicles_on_existing_and_new_lines_are_discovered(self):
        self.line()
        self.tick()
        self.vehicle(100)
        self.line(20, BLUE)
        self.vehicle(200, 20)
        self.assigned(100, 10)
        self.assigned(200, 20)
        self.tick()
        self.assertEqual(self.color(100), RED)
        self.assertEqual(self.color(200), BLUE)

    def test_all_transport_modes_and_every_paintable_train_part(self):
        self.line()
        for index, mode in enumerate(("BUS", "TRUCK", "TRAM", "TRAIN", "SHIP", "AIRCRAFT", "HELICOPTER")):
            entity = 100 + index
            self.vehicle(entity, parts=[(1, RED), (2, DEFAULT), (1, BLUE)])
            self.g.components[entity].TRANSPORT_VEHICLE.carrier = mode
        self.tick()
        for entity in range(100, 107):
            self.assertEqual(self.color(entity, 1), RED)
            self.assertEqual(self.color(entity, 2), DEFAULT)
            self.assertEqual(self.color(entity, 3), RED)
        self.assertEqual(len(self.g.calls), 7)
        self.tick(120)
        self.assertEqual(len(self.g.calls), 7)

    def test_line_recolor_transfer_replacement_and_manual_paint_preserved_until_event(self):
        self.line()
        self.line(20, BLUE)
        self.vehicle()
        self.tick()
        self.set_line_color(10, BLUE)
        self.tick(120)
        self.assertEqual(self.color(100), BLUE)
        self.set_line_color(20, RED)
        self.g.components[100].TRANSPORT_VEHICLE.line = 20
        self.assigned(100, 20, old=10)
        self.tick(120)
        self.assertEqual(self.color(100), RED)
        self.vehicle(100, 20, parts=[(1, BLUE), (1, BLUE)])
        self.event("vehiclesReplaced", {"entries": [{"entity": 100, "line": 20,
                                                      "revision": 1, "models": [1, 1]}]})
        self.tick(120)
        self.assertEqual(self.color(100, 2), RED)
        self.g.components[100].TRANSPORT_VEHICLE.transportVehicleConfig.vehicles[1].part.color = self.g.vec(*BLUE)
        self.tick(120)
        self.assertEqual(self.color(100), BLUE)
        self.load_script()
        self.tick()
        self.assertEqual(self.color(100), BLUE)
        self.event("lineColorChanged", {"line": 20})
        self.tick()
        self.assertEqual(self.color(100), RED)

    def test_foreign_unassigned_and_unpaintable_vehicles_are_untouched(self):
        self.line()
        self.line(20, BLUE, owner=9)
        self.vehicle(100, parts=[(2, DEFAULT)])
        self.vehicle(101, owner=9)
        self.vehicle(102, line=-1)
        self.vehicle(103, line=20)
        self.tick(250)
        self.assertEqual(len(self.g.calls), 0)

    def test_matching_colors_and_small_float_rounding_do_not_resend(self):
        self.line()
        self.vehicle(parts=[(1, (RED[0] + 1e-7, *RED[1:]))])
        self.tick(250)
        self.assertEqual(len(self.g.calls), 0)
        self.assertLessEqual(self.g.lineQueries, 3)

    def test_batch_limits_and_fresh_colors_membership_deletion_between_batches(self):
        self.line()
        self.line(20, BLUE)
        for entity in range(100, 160):
            self.vehicle(entity)
        self.tick()
        self.assertEqual(len(self.g.calls), 16)
        self.set_line_color(10, BLUE)
        self.g.components[116] = None
        self.g.components[117].TRANSPORT_VEHICLE.line = -1
        self.g.components[118].TRANSPORT_VEHICLE.line = 20
        self.set_line_color(20, RED)
        self.g.components[119].PLAYER_OWNED.player = 9
        self.tick()
        self.assertLessEqual(len(self.g.calls), 32)
        self.tick(5)
        self.assertEqual(self.color(117), DEFAULT)
        self.assertEqual(self.color(118), RED)
        self.assertEqual(self.color(119), DEFAULT)
        self.assertEqual(self.color(120), BLUE)
        self.tick(130)
        self.assertEqual(self.color(100), BLUE)

    def test_unchanged_fleets_and_empty_lines_have_bounded_work(self):
        self.line()
        for entity in range(100, 200):
            self.vehicle(entity, parts=[(1, RED)])
        self.tick()
        self.assertEqual(self.g.vehicleReads, 32)
        self.assertEqual(len(self.g.calls), 0)
        self.tick(5)
        previous = self.g.vehicleReads
        self.tick(200)
        self.assertEqual(self.g.vehicleReads, previous)
        self.lua.execute("components={}; vehicleQueries=0; state.value={}")
        self.load_script()
        for entity in range(10, 40):
            self.line(entity)
        self.tick()
        self.assertEqual(self.g.vehicleQueries, 8)

    def test_deferred_command_failure_retries_only_pending_vehicle(self):
        self.line()
        self.vehicle()
        self.g.deferred = True
        self.g.reject[100] = True
        self.tick()
        self.assertEqual(len(self.g.calls), 1)
        self.assertEqual(self.color(100), DEFAULT)
        self.g.flush()
        self.g.reject[100] = False
        self.tick()
        self.assertEqual(len(self.g.calls), 2)
        self.g.flush()
        self.assertEqual(self.color(100), RED)
        self.tick(120)
        self.assertEqual(len(self.g.calls), 2)

    def test_failed_command_stops_after_bounded_retries_and_can_be_requeued(self):
        self.line()
        self.vehicle()
        self.g.reject[100] = True
        self.tick(250)
        self.assertEqual(len(self.g.calls), 8)
        self.assertEqual(self.color(100), DEFAULT)
        self.g.reject[100] = False
        self.tick(120)
        self.assertEqual(len(self.g.calls), 8)
        self.assertEqual(self.color(100), DEFAULT)
        self.assigned(100, 10)
        self.tick()
        self.assertEqual(len(self.g.calls), 9)
        self.assertEqual(self.color(100), RED)
        self.tick(120)
        self.assertEqual(len(self.g.calls), 9)

    def test_one_bad_vehicle_does_not_block_others_and_can_recover(self):
        self.line()
        for entity in range(100, 104):
            self.vehicle(entity)
        self.g.brokenRead[100] = True
        self.g.throws[101] = True
        self.tick()
        self.assertEqual(self.color(102), RED)
        self.assertEqual(self.color(103), RED)
        self.assertEqual(len(self.g.warnings), 2)
        self.g.brokenRead[100] = False
        self.g.throws[101] = False
        self.tick(120)
        self.assertEqual(self.color(100), RED)
        self.assertEqual(self.color(101), RED)

    def test_invalid_or_missing_line_color_is_skipped_and_later_recovers(self):
        self.line(color=(-1, 0, 0))
        self.vehicle()
        self.tick()
        self.assertEqual(len(self.g.calls), 0)
        self.set_line_color(10, (float("nan"), 0, 0))
        self.tick(120)
        self.assertEqual(len(self.g.calls), 0)
        self.g.components[10].COLOR = None
        self.tick(120)
        self.assertEqual(len(self.g.calls), 0)
        self.line()
        self.event("lineColorChanged", {"line": 10})
        self.tick(120)
        self.assertEqual(self.color(100), RED)

    def test_deleted_line_is_not_recolored_from_stale_members(self):
        self.line()
        for entity in range(100, 140):
            self.vehicle(entity)
        self.tick()
        self.g.components[10] = None
        self.tick(2)
        self.assertEqual(len(self.g.calls), 16)

    def test_script_reload_and_paused_updates_resynchronize_without_saved_cache(self):
        self.line()
        self.vehicle()
        self.tick()
        self.set_line_color(10, BLUE)
        self.load_script()
        self.tick(dt=0)
        self.assertEqual(self.color(100), BLUE)
        self.vehicle(101)
        self.assigned(101, 10)
        self.tick(120, dt=0)
        self.assertEqual(self.color(101), BLUE)

    def test_assignment_waits_for_target_and_idle_does_not_scan_any_fleet(self):
        self.line()
        self.vehicle()
        self.tick()
        self.g.components[100].TRANSPORT_VEHICLE.transportVehicleConfig.vehicles[1].part.color = self.g.vec(*BLUE)
        self.vehicle(101, line=-1)
        self.assigned(101, 10)
        self.tick()
        self.assertEqual(self.color(101), DEFAULT)
        self.g.components[101].TRANSPORT_VEHICLE.line = 10
        self.tick()
        self.assertEqual(self.color(101), RED)
        self.assertEqual(self.color(100), BLUE)
        before = (self.g.lineQueries, self.g.vehicleQueries, self.g.vehicleReads, len(self.g.calls))
        self.tick(1000)
        self.assertEqual((self.g.lineQueries, self.g.vehicleQueries, self.g.vehicleReads, len(self.g.calls)), before)

    def test_failed_assignment_expires_without_touching_old_line_paint(self):
        self.line()
        self.line(20, BLUE)
        self.vehicle()
        self.tick()
        self.assigned(100, 20, old=10)
        self.tick(50)
        self.assertEqual(self.color(100), RED)
        self.assertIsNone(self.g.state.value.vehicles)
        self.g.components[100].TRANSPORT_VEHICLE.line = 20
        self.tick(50)
        self.assertEqual(self.color(100), RED)

    def test_repeated_events_merge_and_reused_entity_is_not_painted(self):
        self.line()
        self.tick()
        self.vehicle()
        for _ in range(20):
            self.assigned(100, 10)
        self.tick()
        self.assertEqual(len(self.g.calls), 1)
        self.vehicle(101)
        self.event("vehiclesAssigned", {"entries": [{"entity": 101, "line": 10, "revision": 99}]})
        self.tick()
        self.assertEqual(self.color(101), DEFAULT)

    def test_large_fleet_shares_line_reads_within_each_bounded_batch(self):
        self.line()
        for entity in range(100, 612):
            self.vehicle(entity)
        self.lua.execute("""
            lineReads = 0
            local getComponent = api.engine.getComponent
            api.engine.getComponent = function(entity, kind)
                if entity == 10 then lineReads = lineReads + 1 end
                return getComponent(entity, kind)
            end
        """)
        for _ in range(32):
            before = len(self.g.calls)
            self.tick()
            self.assertEqual(len(self.g.calls) - before, 16)
        self.assertIsNone(self.g.state.value.vehicles)
        self.assertLessEqual(self.g.lineReads, 3 * 32 + 2)
        self.assertEqual([entry.entity for entry in self.g.calls.values()], list(range(100, 612)))

    def test_pending_state_reload_preserves_attempts_and_command_order(self):
        self.line()
        for entity in range(100, 164):
            self.vehicle(entity)
        self.tick()
        self.g.state.value.vehicles[116].attempts = 5
        self.g.reject[116] = True
        self.load_script()
        self.tick()
        self.assertEqual(self.g.state.value.vehicles[116].attempts, 6)
        self.g.reject[116] = False
        self.load_script()
        self.tick(4)
        self.assertIsNone(self.g.state.value.vehicles)
        self.assertEqual(len(self.g.calls), 65)
        for entity in range(100, 164):
            self.assertEqual(self.color(entity), RED)

    def test_manifest_and_game_script_entry(self):
        manifest = json.loads((ROOT / "mod.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["modId"], "xin_line_vehicle_colors_1")
        self.lua.execute((CONTENT / "colors.gs.lua").read_text(encoding="utf-8"))
        self.assertEqual(self.g.data().updateScript.fileName, "colors.script@update")


@unittest.skipUnless(os.environ.get("TF3_GAME_DIR"), "Set TF3_GAME_DIR to check native API contracts")
class NativeContractTests(unittest.TestCase):
    def test_native_coloring_command_component_and_model_capability(self):
        game = Path(os.environ["TF3_GAME_DIR"])
        cmd = (game / "api/tealdef/api/cmd.d.tl").read_text(encoding="utf-8")
        self.assertIn("makeEntitySetColorCmd : function(entity : Engine.Entity, color : Vec3f)", cmd)
        system = (game / "api/tealdef/api/engine/system.d.tl").read_text(encoding="utf-8")
        self.assertIn("getLinesForPlayer : function(playerEntity : Engine.Entity)", system)
        self.assertIn("getLineVehicles : function(lineEntity : Engine.Entity)", system)
        with ZipFile(game / "base/content/gui.zip") as archive:
            line = archive.read("gui/entity_window/line/line.tl").decode("utf-8")
            self.assertIn("api.type.ComponentType.COLOR", line)
            self.assertIn("color.color:clone()", line)
            manager = archive.read("gui/line_vehicle_mgmt/manager_window.tl").decode("utf-8")
            self.assertIn("transportVehicle.transportVehicleConfig.vehicles", manager)
            self.assertIn("api.res.modelRep.get(vehicle.part.modelId).metadata.transportVehicle", manager)
            self.assertIn("not tv.noCblendMask", manager)
            self.assertIn("api.cmd.makeEntitySetColorCmd(vehicleEAR.entity, selectedColor)", manager)
            vehicle = archive.read("gui/line_vehicle_mgmt/vehicle_react_util.tl").decode("utf-8")
            self.assertIn("transportVehiclePart.part.color:clone()", vehicle)


if __name__ == "__main__":
    unittest.main()
