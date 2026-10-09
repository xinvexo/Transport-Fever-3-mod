# Lua 5.2 tests for the existing-station overlay, not native renderer tests.
import os
from pathlib import Path
import re
import unittest
from zipfile import ZipFile

from lupa.lua52 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / 'content/clear_catchment'
GAME = Path(os.environ['TF3_GAME_DIR']) if os.environ.get('TF3_GAME_DIR') else None

STUB = """
function copy(value)
  if type(value) ~= 'table' then return value end
  local result = {}
  for k,v in pairs(value) do result[k] = copy(v) end
  return result
end
nativeSettings = {borderAlpha=0.75,borderAlphaPassive=0.25,borderWidth=4,
  innerAlpha=0.1,buildingAlpha=0.6,godrayAlpha=0.8,godrayAlphaPassive=0.2,
  personBaseColor={x=0.1,y=0.8,z=0.2},cargoBaseColor={x=0.2,y=0.5,z=0.9},
  inactiveColor={x=0.3,y=0.3,z=0.3},unreachableColor={x=0.7,y=0.7,z=0.7},
  deleteColor={x=1,y=0,z=0},noiseColor={x=1,y=0.5,z=0}}
nativeArea = {isVisible=false,entity=-1,person=false,cargo=false,maintenance=false,
  noise=false,pollution=false,addGodrays=false,carriers={'native-default'},displaySettings=nativeSettings}
resources = {
  {edgeObject={catchmentPassengers=true,catchmentCargo=true,catchmentAreaRadius=160}},
  {edgeObject={catchmentCargo=true,catchmentAreaRadius=160}},
  {edgeObject={catchmentPassengers=true,catchmentAreaRadius=160}},
  {edgeObject={catchmentPassengers=false,catchmentCargo=false}},
}
resourceIds={['stop.con']=1,['cargo-stop.con']=2,['bus-stop.con']=3,['sign.con']=4}
entities={[31]={stations={101},depots={}},[32]={stations={},depots={201}}}
api={type={ComponentType={STATION_GROUP=1,CONSTRUCTION=2,TOWN=3,INDUSTRY=4},
  Vec3f={new=function(x,y,z) return {x=x,y=y,z=z} end},
  LayerConfig={new=copy,
    CatchmentAreaRenderableConfig={new=function(value) return copy(value or nativeArea) end},
    CatchmentAreaDisplaySettings={new=function(value) return copy(value or nativeSettings) end}}},
  res={constructionRep={find=function(name) return resourceIds[name] or -1 end,
    get=function(id) return resources[id] end}},
  engine={entityExists=function(id) return entities[id]~=nil end,
    getComponent=function(id,kind) assert(kind==2);return entities[id] end}}
original={constructionActionParams={edgeObjectBuilder={radius=160}},
  hudIconManagerParams={station=true},custom={keep=true},
  layerConfig={undergroundMode=true,colorPassFn={keep=true},buildingRenderableConfig={keep=true},
    catchmentAreaRenderableConfig=copy(nativeArea)}}
original.layerConfig.catchmentAreaRenderableConfig.entity=31
original.layerConfig.catchmentAreaRenderableConfig.carriers={2}
original.layerConfig.catchmentAreaRenderableConfig.displaySettings.borderWidth=2
station={action='ACTION_CONSTRUCTION_BUILDER',hudIcons={showDistricts=true,componentTypes={1,3,4}}}
stop={action='ACTION_STREET_TERMINAL_BUILDER',resName='stop.con'}
module={action='ACTION_MODULE_BUILDER'}
function ug_require(path)
  assert(path=='xin_clear_catchment_1::/clear_catchment/target.lua',path)
  return target
end
"""


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(STUB)
        self.lua.globals().target = self.lua.execute((CONTENT / 'target.lua').read_text(encoding='utf-8'))
        self.lua.globals().appearance = self.lua.execute((CONTENT / 'appearance.lua').read_text(encoding='utf-8'))

    def test_overlay_deepens_existing_hues_adds_fill_and_keeps_geometry(self):
        self.lua.execute("""
          local result=appearance.apply(stop,original)
          local c=result.layerConfig.catchmentAreaRenderableConfig
          local s=c.displaySettings
          assert(c.isVisible and c.person and c.cargo and c.entity==-1)
          assert(c.carriers[1]=='native-default')
          assert(s.borderAlpha==1 and s.borderAlphaPassive==1 and s.borderWidth==2)
          for _,key in ipairs({'personBaseColor','cargoBaseColor','inactiveColor','unreachableColor'}) do
            local originalColor=nativeSettings[key]
            for _,channel in ipairs({'x','y','z'}) do
              assert(s[key][channel] >= 0 and s[key][channel] < originalColor[channel])
              assert(math.abs(s[key][channel] / originalColor[channel] - s[key].x / originalColor.x) < 1e-8)
            end
          end
          assert(s.deleteColor.x==nativeSettings.deleteColor.x and s.noiseColor.y==nativeSettings.noiseColor.y)
          assert(not c.maintenance and not c.noise and not c.pollution and not c.addGodrays)
          assert(s.innerAlpha==0.80 and s.buildingAlpha==0 and s.godrayAlpha==0 and s.godrayAlphaPassive==0)
          assert(result.layerConfig.colorPassFn.keep and result.layerConfig.buildingRenderableConfig.keep)
          assert(result.layerConfig.undergroundMode)
          assert(result.constructionActionParams==original.constructionActionParams)
          assert(result.hudIconManagerParams==original.hudIconManagerParams and result.custom==original.custom)
          assert(result.constructionActionParams.edgeObjectBuilder.radius==160)
          assert(resources[1].edgeObject.catchmentAreaRadius==160)
          assert(not original.layerConfig.catchmentAreaRenderableConfig.isVisible)
        """)

    def test_only_station_tools_receive_the_overlay(self):
        self.lua.execute("""
          local function check(definition,entity,expected)
            assert(target.isStation(definition,entity)==expected)
            assert((appearance.apply(definition,original,entity)~=original)==expected)
          end
          check(station,nil,true)
          for name,expected in pairs({['stop.con']=true,['cargo-stop.con']=true,
            ['bus-stop.con']=true,['sign.con']=false,['missing.con']=false}) do
            check({action='ACTION_STREET_TERMINAL_BUILDER',resName=name},nil,expected)
          end
          check(nil,nil,false)
          for _,action in ipairs({'ACTION_BULLDOZER','ACTION_STREET_BUILDER_UPGRADER',
            'ACTION_TRACK_BUILDER_UPGRADER','ACTION_TERRAIN_MODIFIER_RAISE'}) do
            check({action=action},nil,false)
          end
          for _,hud in ipairs({{}, {componentTypes={1}}, {showDistricts=true,componentTypes={3,4}}}) do
            check({action='ACTION_CONSTRUCTION_BUILDER',hudIcons=hud},nil,false)
          end
          check({action='ACTION_CONSTRUCTION_BUILDER'},nil,false)
          for _,action in ipairs({'ACTION_MODULE_BUILDER','ACTION_MODULE_BULLDOZER'}) do
            for _,entity in ipairs({31,32,99}) do check({action=action},entity,entity==31) end
            check({action=action},nil,false)
          end
          local empty={custom=true}
          assert(appearance.apply(station,empty)==empty)
        """)

    def test_preferred_layer_keeps_other_fields_and_uses_construction_overlay_style(self):
        self.lua.execute("""
          local enhanced=appearance.apply(station,original).layerConfig
          local preferred=copy(original.layerConfig)
          preferred.colorMap={terrain=true}
          preferred.colorPassFn={other=true}
          preferred.catchmentAreaRenderableConfig.displaySettings.borderWidth=9
          preferred.catchmentAreaRenderableConfig.displaySettings.personBaseColor.x=0.99
          local merged=appearance.mergeLayer(enhanced,preferred)
          assert(merged.colorMap.terrain and merged.colorPassFn.other)
          local c=merged.catchmentAreaRenderableConfig
          assert(c.isVisible and c.person and c.cargo and c.entity==-1)
          assert(c.displaySettings.borderWidth==2)
          assert(math.abs(c.displaySettings.personBaseColor.x - 0.065) < 1e-8)
          assert(c.displaySettings.innerAlpha==0.80)
          assert(preferred.catchmentAreaRenderableConfig.displaySettings.borderWidth==9)
          assert(not preferred.catchmentAreaRenderableConfig.isVisible)
          assert(appearance.mergeLayer(enhanced,enhanced)==enhanced)
          assert(appearance.mergeLayer(enhanced,nil)==nil)
        """)

    def install_hooks(self):
        self.lua.execute("""
          calls=0
          construction={getActionParams=function(...)
            calls=calls+1;arguments=table.pack(...)
            if nativeActionFailure then error(nativeActionFailure) end
            return original
          end,mergeLayerConfig=function(fromConstruction,preferred)
            if nativeMergeFailure then error(nativeMergeFailure) end
            return preferred or fromConstruction
          end}
          function ug_require(path)
            if path:find('construction_react_util',1,true) then return construction end
            if path:find('appearance.lua',1,true) then return appearance end
            if path:find('mod_entry_point',1,true) then return {ModEntryPointExtension='extension'} end
            if path:find('react.lua',1,true) then
              return {RegisterPluginRecipe=function(extension,name,fn)
                assert(extension=='extension' and name=='XinClearCatchmentEntry');return fn
              end}
            end
            error(path)
          end
          messages={}
          log={message=function(message) messages[#messages+1]=message end}
        """)
        self.lua.execute((CONTENT / 'ui_entry.script.lua').read_text(encoding='utf-8'))

    def test_hooks_forward_entity_and_do_not_leak_overlay_to_later_actions(self):
        self.install_hooks()
        self.lua.execute("""
          assert(data().entry()==nil)
          local result=construction.getActionParams(module,'params','repo',false,nil,31,'callback','sublist')
          assert(calls==1 and arguments.n==8 and arguments[5]==nil and arguments[6]==31)
          assert(arguments[7]=='callback' and arguments[8]=='sublist')
          local preferred=copy(original.layerConfig)
          preferred.colorMap={keep=true}
          local merged=construction.mergeLayerConfig(result.layerConfig,preferred)
          assert(merged.colorMap.keep and merged.catchmentAreaRenderableConfig.isVisible)
          local count=#messages
          for i=1,20 do construction.mergeLayerConfig(result.layerConfig,preferred) end
          assert(#messages==count)
          local road=construction.getActionParams({action='ACTION_STREET_BUILDER_UPGRADER'})
          assert(road==original)
          assert(construction.mergeLayerConfig(road.layerConfig,preferred)==preferred)
          assert(not preferred.catchmentAreaRenderableConfig.isVisible)
          assert(construction.getActionParams(module,'params','repo',false,nil,32)==original)
        """)

    def test_partial_overlay_failure_cannot_modify_native_colors(self):
        self.install_hooks()
        self.lua.execute("""
          local calls=0
          local messageCount=#messages
          local new=api.type.Vec3f.new
          api.type.Vec3f.new=function(...)
            calls=calls+1
            if calls==3 then error('color conversion failed') end
            return new(...)
          end
          assert(construction.getActionParams(station)==original)
          assert(calls==3)
          local config=original.layerConfig.catchmentAreaRenderableConfig
          assert(not config.isVisible and config.entity==31 and config.carriers[1]==2)
          assert(config.displaySettings.personBaseColor.x==0.1)
          assert(config.displaySettings.cargoBaseColor.y==0.5)
          assert(config.displaySettings.innerAlpha==0.1)
          assert(construction.getActionParams(station)==original and calls==3)
          assert(#messages==messageCount+1, 'Disable and report the failing enhancement once')
        """)

    def test_merge_failure_preserves_preferred_layer_and_stops_enhancement(self):
        self.install_hooks()
        self.lua.execute("""
          local enhanced=construction.getActionParams(station)
          local preferred=copy(original.layerConfig)
          preferred.colorMap={other=true}
          local attempts=0
          appearance.mergeLayer=function()
            attempts=attempts+1;error('incompatible preferred layer')
          end
          local count=#messages
          for i=1,10 do assert(construction.mergeLayerConfig(enhanced.layerConfig,preferred)==preferred) end
          assert(attempts==1 and #messages==count+1)
          assert(preferred.colorMap.other and not preferred.catchmentAreaRenderableConfig.isVisible)
          assert(construction.getActionParams(station)==original)
        """)

    def test_native_hook_errors_are_not_mistaken_for_overlay_errors(self):
        self.install_hooks()
        self.lua.execute("""
          nativeActionFailure='native action failure'
          local ok,failure=pcall(construction.getActionParams,station)
          assert(not ok and tostring(failure):find(nativeActionFailure,1,true))
          nativeActionFailure=nil
          local enhanced=construction.getActionParams(station)
          assert(enhanced~=original)
          nativeMergeFailure='native merge failure'
          ok,failure=pcall(construction.mergeLayerConfig,enhanced.layerConfig,nil)
          assert(not ok and tostring(failure):find(nativeMergeFailure,1,true))
          nativeMergeFailure=nil
          assert(construction.getActionParams(station)~=original)
        """)


@unittest.skipUnless(GAME, 'Set TF3_GAME_DIR to check shipped GUI/API contracts')
class NativeContractTests(unittest.TestCase):
    def test_native_station_and_overlay_contracts(self):
        with ZipFile(GAME / 'base/content/gui.zip') as archive:
            util=archive.read('gui/construction/construction_react_util.tl').decode('utf-8')
            hud=archive.read('gui/construction/construction_desc_react_util.tl').decode('utf-8')
            infrastructure=archive.read('gui/layers/layer_infrastructure.tl').decode('utf-8')
            ui=archive.read('gui/construction/construction.tl').decode('utf-8')
        station_hud=hud.split('getStationHudIconsConfig = function',1)[1].split('\nend',1)[0]
        self.assertIn('api.type.ComponentType.STATION_GROUP',station_hud)
        self.assertIn('showDistricts = true',station_hud)
        self.assertIn('catchmentAreaRenderableConfig.isVisible = true',infrastructure)
        self.assertIn('catchmentAreaRenderableConfig.entity = -1',infrastructure)
        self.assertIn('construction_react_util.getActionParams(',ui)
        self.assertIn('mergeLayerConfig(actionParams.layerConfig, layerToolLayerConfig:old())',ui)
        self.assertRegex(util,r'refParams : .*?, entity : Engine.Entity')
        self.assertRegex(ui,r'builtin.LayerConfig\s*{\s*config = finalLayerConfig')

    def test_api_fields_and_roadside_stop_resources_exist(self):
        types=(GAME/'api/tealdef/api/type.d.tl').read_text(encoding='utf-8')
        settings=re.search(r'record CatchmentAreaDisplaySettings\b(.*?)\n\s*end',types,re.S).group(1)
        for field in ('personBaseColor','cargoBaseColor','inactiveColor','unreachableColor'):
            self.assertRegex(settings,rf'\b{field}\s*:\s*Vec3f')
        for field in ('borderAlpha','borderAlphaPassive','innerAlpha','buildingAlpha','godrayAlpha','godrayAlphaPassive'):
            self.assertRegex(settings,rf'\b{field}\s*:\s*number')
        config=re.search(r'record CatchmentAreaRenderableConfig\b(.*?)\n\s*end',types,re.S).group(1)
        for field in ('isVisible','person','cargo','maintenance','noise','pollution','addGodrays'):
            self.assertRegex(config,rf'\b{field}\s*:\s*boolean')
        self.assertRegex(types,r'catchmentPassengers\s*:\s*boolean')
        self.assertRegex(types,r'catchmentCargo\s*:\s*boolean')
        with ZipFile(GAME/'base/content/stations/street.zip') as archive:
            stop=archive.read('street/small_stops/small_mid.con.lua').decode('utf-8')
        self.assertRegex(stop,r'catchmentPassengers\s*=\s*true')
        self.assertRegex(stop,r'catchmentCargo\s*=\s*true')


if __name__=='__main__':
    unittest.main()
