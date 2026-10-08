"""Check the native zoning-color pipeline without running the game renderer."""
import os
from pathlib import Path
import re
import unittest
from zipfile import ZipFile

from lupa.lua52 import LuaRuntime

CONTENT = Path(__file__).resolve().parents[1] / 'content/bulldozer_lines'
GAME = Path(os.environ['TF3_GAME_DIR']) if os.environ.get('TF3_GAME_DIR') else None

STUB = '''
function copy(value)
  if type(value) ~= 'table' then return value end
  local result = {}
  for key, item in pairs(value) do result[key] = copy(item) end
  return result
end
local function new(value) return value and copy(value) or {} end
districtColors = {Residential={min='green1',max='green2'},
  Commercial={min='blue1',max='blue2'}, Industrial={min='yellow1',max='yellow2'}}
fallback = {Surface='surface',Details='details'}
api = {type={LayerConfig={new=new,
  ColorPassFn={new=new,CargoColor={new=new},BaseRangeColor={new=function(values,override)
    return {minMax=values,overrideColorMap=override}
  end}},BuildingRenderableConfig={new=new}}},
  gui={genericRep={find=function(name) return name end,get=function(name)
    if name=='::/game_mechanics/towns/district_colors.gres' then return {data=districtColors} end
    assert(name=='::/gui/layers/layer_colors.gres')
    return {data={Construction={Fallback=fallback}}}
  end}}}
function ug_require(path)
  if path=='::/gui/main/color_util.tl' then return {toVec4=function(color) return {source=color} end} end
  assert(path=='::/gui/layers/layer_react_util.tl')
  return {createDefaultFallbackColor=function(surface,details)
    assert(surface==fallback.Surface and details==fallback.Details)
    return {surface=surface,details=details}
  end}
end
original = {constructionActionParams={bulldozer={native=true}},hudIconManagerParams={station=true},
  layerConfig={undergroundMode=false,colorPassFnForBuildingRenderableOnly=false,
    buildingRenderableConfig={isVisible=false,includeTownBuildingMainModel=false,includeStations=true},
    catchmentAreaRenderableConfig={keep=true},contours={keep=true}}}
'''


class BuildingColorTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(STUB)
        self.lua.globals().colors = self.lua.execute((CONTENT / 'building_colors.lua').read_text(encoding='utf-8'))

    def test_surface_uses_native_palette_on_buildings_and_preserves_other_state(self):
        self.lua.execute('''
          local result=colors.apply({action='ACTION_BULLDOZER'},original)
          local layer=result.layerConfig
          local painter=layer.colorPassFn.townBuildingPainter
          assert(painter.residential.minMax[1].source=='green1')
          assert(painter.commercial.minMax[2].source=='blue2')
          assert(painter.industrial.minMax[1].source=='yellow1')
          assert(painter.includePassengers and painter.numBuildingLevels==1)
          assert(layer.colorPassFnForBuildingRenderableOnly)
          assert(layer.buildingRenderableConfig.isVisible and layer.buildingRenderableConfig.includeTownBuildingMainModel)
          assert(layer.buildingRenderableConfig.includeStations)
          assert(layer.catchmentAreaRenderableConfig.keep and layer.contours.keep)
          assert(result.constructionActionParams==original.constructionActionParams)
          assert(result.hudIconManagerParams==original.hudIconManagerParams)
          assert(original.layerConfig.colorPassFn==nil)
          assert(not original.layerConfig.buildingRenderableConfig.isVisible)
        ''')

    def test_underground_background_and_other_painters_survive(self):
        self.lua.execute('''
          original.layerConfig.undergroundMode=true
          original.layerConfig.colorPassFn={fallbackColor={underground=true},transportNetworkPainter={keep=true}}
          local layer=colors.apply({action='ACTION_BULLDOZER'},original).layerConfig
          assert(layer.undergroundMode and not layer.colorPassFnForBuildingRenderableOnly)
          assert(layer.colorPassFn.fallbackColor.underground)
          assert(layer.colorPassFn.transportNetworkPainter.keep)
          assert(original.layerConfig.colorPassFn.townBuildingPainter==nil)
        ''')

    def test_switching_tools_returns_unmodified_native_layers(self):
        self.lua.execute('''
          for i=1,3 do
            colors.apply({action='ACTION_BULLDOZER'},original)
            for _,action in ipairs({'ACTION_CONSTRUCTION_BUILDER','ACTION_MODULE_BULLDOZER','ACTION_STREET_TERMINAL_BUILDER'}) do
              assert(colors.apply({action=action},original)==original)
            end
            assert(original.layerConfig.colorPassFn==nil)
          end
          assert(colors.apply(nil,original)==original)
          local noLayer={custom=true}
          assert(colors.apply({action='ACTION_BULLDOZER'},noLayer)==noLayer)
        ''')

    def test_entry_chains_existing_layer_hook_and_forwards_arguments(self):
        self.lua.execute('''
          calls=0
          construction={getActionParams=function(...)
            calls=calls+1;assert(select('#',...)==8)
            local definition,params,repository,gamepad,ref,entity,callback,sublist=...
            assert(params=='params' and repository=='repo' and gamepad==false)
            assert(ref==nil and entity==nil and callback=='callback' and sublist=='sublist')
            return original
          end}
          local builtin={Window={},ActionDescriptor=function(value) return value end}
          local react={RegisterWrapperRecipe=function(_,_,fn) return fn end,
            RegisterRecipe=function(_,fn) return fn end,RegisterPluginRecipe=function(_,_,fn) return fn end}
          function ug_require(path)
            if path=='::/gui/main/builtin.lua' then return builtin end
            if path=='::/gui/main/react.lua' then return react end
            if path=='::/gui/construction/construction_react_util.tl' then return construction end
            if path:find('/building_colors.lua',1,true) then return colors end
            return {}
          end
          log={message=function() end}
        ''')
        self.lua.execute((CONTENT / 'ui_entry.script.lua').read_text(encoding='utf-8'))
        self.lua.execute('''
          local result=construction.getActionParams({action='ACTION_BULLDOZER'},'params','repo',false,nil,nil,'callback','sublist')
          assert(calls==1 and result.layerConfig.colorPassFn.townBuildingPainter)
          assert(result.constructionActionParams==original.constructionActionParams)
        ''')


@unittest.skipUnless(GAME, 'Set TF3_GAME_DIR to check native zoning resources')
class NativeBuildingColorTests(unittest.TestCase):
    def test_shipped_station_pipeline_and_value_types_match(self):
        with ZipFile(GAME / 'base/content/gui.zip') as archive:
            native = archive.read('gui/construction/construction_react_util.tl').decode('utf-8')
        self.assertIn('::/game_mechanics/towns/district_colors.gres', native)
        self.assertIn('cargoColor.includePassengers = true', native)
        self.assertIn('cargoColor.numBuildingLevels = 1', native)
        self.assertIn('buildingRenderableConfig.includeTownBuildingMainModel = true', native)
        types = (GAME / 'api/tealdef/api/type.d.tl').read_text(encoding='utf-8')
        self.assertIn('new : function(ColorPassFn)', types)
        self.assertIn('new : function(BuildingRenderableConfig)', types)
        for field in ('residential','commercial','industrial'):
            self.assertRegex(types, rf'\b{field}\s*:\s*BaseRangeColor')
        with ZipFile(GAME / 'base/content/game_mechanics.zip') as archive:
            resource = archive.read('game_mechanics/towns/district_colors.gres.lua').decode('utf-8')
        for group in ('Residential','Commercial','Industrial'):
            self.assertRegex(resource, rf'colors\.{group}\.min\s*=')
            self.assertRegex(resource, rf'colors\.{group}\.max\s*=')


if __name__ == '__main__':
    unittest.main()
