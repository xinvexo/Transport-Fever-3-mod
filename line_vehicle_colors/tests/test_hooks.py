"""GUI command completion notices; no dependence on widget lifetime or polling."""

import os
from pathlib import Path
import unittest
from zipfile import ZipFile

from lupa.lua52 import LuaRuntime


CONTENT = Path(__file__).resolve().parents[1] / "content/line_vehicle_colors"


class HookTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("""
            events, calls, messages, world, modules = {}, {}, {}, {}, {}
            engineHelper={}
            world[10]={LINE={},revision=1}
            world[20]={LINE={},revision=1}
            world[100]={TRANSPORT_VEHICLE={line=-1},revision=1}
            modules['::/gui/main/engine_react_util.tl']=engineHelper
            modules['::/gui/main/react.lua']={RegisterPluginRecipe=function(_,name,fn)
                recipeCount=(recipeCount or 0)+1; return fn
            end}
            modules['::/gui/main/mod_entry_point.tl']={ModEntryPointExtension={}}
            function ug_require(name) assert(modules[name],name); return modules[name] end
            log={message=function(s) messages[#messages+1]=s end, warning=function(s) messages[#messages+1]=s end}
            api={type={ComponentType={LINE='LINE',TRANSPORT_VEHICLE='TRANSPORT_VEHICLE'}},
                engine={entityExists=function(id) return world[id]~=nil end,
                    getComponent=function(id,kind) return world[id][kind] end,
                    getRevision=function(id) return {num={world[id].revision,0,0}} end},
                cmd={}}
            api.cmd.makeVehicleSetLineCmd=function(entity,line,stop)
                return {kind='assign',entity=entity,line=line,stop=stop}
            end
            api.cmd.makeEntitySetColorCmd=function(entity,color)
                return {kind='color',entity=entity,color=color}
            end
            api.cmd.makeVehicleReplaceCmd=function(entity,config,cost)
                return {kind='replace',entity=entity,config=config,cost=cost}
            end
            api.cmd.makeScriptingSendEventCmd=function(src,id,name,params)
                return {kind='event',src=src,id=id,name=name,params=params}
            end
            api.cmd.sendCommand=function(command,callback,progress)
                if command.kind=='event' then
                    if failEvent then error('event unavailable') end
                    events[#events+1]=command
                else calls[#calls+1]={command=command,callback=callback,progress=progress} end
                return 'native result'
            end
            function complete(index,success)
                local call=calls[index]
                if success and call.command.kind=='assign' then
                    world[call.command.entity].TRANSPORT_VEHICLE.line=call.command.line
                end
                if call.callback then call.callback(call.command,success,{{call.command.entity}}) end
            end
        """)
        self.g = self.lua.globals()
        self.hooks = self.lua.execute((CONTENT / "hooks.lua").read_text(encoding="utf-8"))
        self.g.modules["xin_line_vehicle_colors_1::/line_vehicle_colors/hooks.lua"] = self.hooks
        self.hooks.installGui()

    def test_depot_and_other_line_dispatch_notify_only_after_success(self):
        for old in (-1, 20):
            self.g.world[100].TRANSPORT_VEHICLE.line = old
            count = len(self.g.events)
            self.lua.execute("api.cmd.sendCommand(api.cmd.makeVehicleSetLineCmd(100,10,3))")
            self.assertEqual(len(self.g.events), count)
            self.g.complete(len(self.g.calls), True)
            event = self.g.events[len(self.g.events)]
            self.assertEqual(event.name, "vehiclesAssigned")
            self.assertEqual(event.params.entries[1].entity, 100)
            self.assertEqual(event.params.entries[1].line, 10)
            self.assertEqual(self.g.calls[len(self.g.calls)].command.stop, 3)

    def test_current_line_purchase_final_assignment_is_captured(self):
        self.lua.execute("""
            world[101]={TRANSPORT_VEHICLE={line=-1},revision=1}
            -- The native buy callback submits this same command with the new ID.
            api.cmd.sendCommand(api.cmd.makeVehicleSetLineCmd(101,20,0))
        """)
        self.g.complete(1, True)
        self.assertEqual(self.g.events[1].params.entries[1].entity, 101)
        self.assertEqual(self.g.events[1].params.entries[1].line, 20)

    def test_line_color_notifies_even_if_original_widget_callback_returns_early(self):
        self.lua.execute("""
            local command=api.cmd.makeEntitySetColorCmd(10,{x=1,y=0,z=0})
            local result=api.cmd.sendCommand(command,function(result,success,entities)
                callbackCount=(callbackCount or 0)+1
                callbackResult=result; callbackSuccess=success; callbackEntities=entities
                if widgetClosed then return end
            end,'progress token')
            assert(result=='native result')
            widgetClosed=true
        """)
        self.g.complete(1, True)
        self.assertEqual(self.g.events[1].name, "lineColorChanged")
        self.assertEqual(self.g.callbackCount, 1)
        self.assertTrue(self.g.callbackSuccess)
        self.assertEqual(self.g.callbackEntities[1][1], 10)
        self.assertEqual(self.g.calls[1].progress, "progress token")

    def test_manual_vehicle_color_failed_assignment_and_failed_replacement_do_not_notify(self):
        self.lua.execute("""
            api.cmd.sendCommand(api.cmd.makeEntitySetColorCmd(100,{x=1,y=0,z=0}))
            api.cmd.sendCommand(api.cmd.makeVehicleSetLineCmd(100,10,0))
            api.cmd.sendCommand(api.cmd.makeVehicleReplaceCmd(100,{},true))
        """)
        self.g.complete(1, True)
        self.g.complete(2, False)
        self.g.complete(3, False)
        self.assertEqual(len(self.g.events), 0)

    def test_successful_replacement_notifies_only_that_vehicle(self):
        self.g.world[100].TRANSPORT_VEHICLE.line = 10
        self.lua.execute("api.cmd.sendCommand(api.cmd.makeVehicleReplaceCmd(100,{},true))")
        self.g.complete(1, True)
        self.assertEqual(self.g.events[1].name, "vehiclesReplaced")
        self.assertEqual(self.g.events[1].params.entries[1].entity, 100)
        self.assertTrue(self.g.calls[1].command.cost)

    def test_no_duplicate_install_and_unrelated_commands_are_unchanged(self):
        self.hooks.installGui()
        self.lua.execute("""
            unrelatedCallback=function() end
            api.cmd.sendCommand({kind='unrelated'},unrelatedCallback,'other progress')
            api.cmd.sendCommand(api.cmd.makeVehicleSetLineCmd(100,10,0))
        """)
        self.lua.execute("assert(calls[1].callback==unrelatedCallback)")
        self.g.complete(2, True)
        self.assertEqual(len(self.g.events), 1)

    def test_notification_failure_does_not_suppress_original_callback(self):
        self.lua.execute("""
            failEvent=true
            api.cmd.sendCommand(api.cmd.makeVehicleSetLineCmd(100,10,0),function()
                callbackCount=(callbackCount or 0)+1
            end)
        """)
        self.g.complete(1, True)
        self.assertEqual(self.g.callbackCount, 1)

    def test_reused_entity_and_superseded_assignment_do_not_notify(self):
        self.lua.execute("api.cmd.sendCommand(api.cmd.makeEntitySetColorCmd(10,{}))")
        self.g.world[10].revision = 2
        self.g.complete(1, True)
        self.lua.execute("""
            api.cmd.sendCommand(api.cmd.makeVehicleSetLineCmd(100,10,0))
            world[100].TRANSPORT_VEHICLE.line=20
            calls[2].callback(calls[2].command,true,{})
        """)
        self.assertEqual(len(self.g.events), 0)

    def test_gui_entry_registers_once(self):
        source = (CONTENT / "ui_entry.script.lua").read_text(encoding="utf-8")
        self.lua.execute(source)
        self.lua.execute(source)
        self.assertEqual(self.g.recipeCount, 1)
        self.lua.execute((CONTENT / "ui_entry.res.lua").read_text(encoding="utf-8"))
        self.assertEqual(self.g.data().type, "react-plugin ::ModEntryPointExtension")

    def test_hook_installation_failure_does_not_break_native_gui_loading(self):
        self.lua.execute("""
            engineHelper.__xinLineVehicleColorCommands=nil
            local original=api.cmd
            api.cmd=setmetatable({}, {__index=original,
                __newindex=function() error('read-only command module') end})
        """)
        self.lua.execute((CONTENT / "ui_entry.script.lua").read_text(encoding="utf-8"))
        self.assertEqual(self.g.recipeCount, 1)
        self.assertTrue(any("Could not install" in text for text in self.g.messages.values()))


@unittest.skipUnless(os.environ.get("TF3_GAME_DIR"), "Set TF3_GAME_DIR for native hook contracts")
class NativeHookTests(unittest.TestCase):
    def test_native_gui_submits_tracked_commands_and_exposes_results(self):
        game = Path(os.environ["TF3_GAME_DIR"])
        api = (game / "api/tealdef/api/cmd.d.tl").read_text(encoding="utf-8")
        for constructor in ("makeVehicleSetLineCmd", "makeEntitySetColorCmd", "makeVehicleReplaceCmd"):
            self.assertIn(constructor + " : function", api)
        with ZipFile(game / "base/content/gui.zip") as archive:
            manager = archive.read("gui/line_vehicle_mgmt/manager_window.tl").decode("utf-8")
            self.assertIn("api.cmd.makeVehicleSetLineCmd(", manager)
            self.assertIn("api.cmd.makeEntitySetColorCmd(colorAndEntity.entity, colorAndEntity.color)", manager)
            vehicle = archive.read("gui/line_vehicle_mgmt/vehicle_react_util.tl").decode("utf-8")
            self.assertIn("api.cmd.makeVehicleReplaceCmd(change.vehicleEntity, change.config)", vehicle)
            self.assertIn("api.cmd.makeVehicleSetLineCmd(", vehicle)


if __name__ == "__main__":
    unittest.main()
