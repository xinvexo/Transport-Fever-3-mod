"""Exercise the GUI adapter's lifecycle with Lua 5.2 (not an in-game test)."""
from pathlib import Path
import unittest

from lupa.lua52 import LuaRuntime

CONTENT = Path(__file__).resolve().parents[1] / 'content/rail_loop'

GUI = r'''
local memories, cursor, memory, activeName = {}, 0
steps, unmounts = {}, {}
local function slot(value)
  cursor=cursor+1
  if not memory[cursor] then
    local o={value=value}
    function o:get() return self.value end
    function o:old() return self.value end
    function o:set(v) self.value=v end
    memory[cursor]=o
  end
  return memory[cursor]
end
react={useRef=slot,useState=slot,
  onStep=function(fn) steps[activeName]=fn end,
  onUnmount=function(fn) unmounts[activeName]=fn end,
  RegisterRecipe=function(name,fn)
    return function(params)
      activeName=name; cursor=0; memories[name]=memories[name] or {}; memory=memories[name]
      return fn(params)
    end
  end,
  RegisterPluginRecipe=function(_,_,fn) return fn end}
local allowed={
  Component={},FloatingLayout={children=true},TextView={text=true,meta=true},
  Selector={filter=true,stopOnMenuBack=true,onProcessMouseEvent=true},
  SimpleInputActions={inputActions=true,inputActionsHandler=true},
  ProposalViewer={simpleProposal=true,proposalId=true,entityForRefundableContext=true,onCreateProposalData=true},
  ActionTooltip={recipe=true,param=true},ActionDescriptor={children=true,onBack=true,tool=true}}
builtin={}
for name,keys in pairs(allowed) do
  builtin[name]=function(params)
    for key in pairs(params) do assert(keys[key],name..' has no '..key) end
    return {kind=name,params=params}
  end
end
nativeCalls, nativeKeys, aborted, commands, refunded=0,0,0,0,0
builtin.ConstructionAction=function(params) nativeCalls=nativeCalls+1;return {kind='Native',params=params} end
defs={{resName='xin_smooth_rail_loop_1::/rail_loop/raised_loop.con'},
      {resName='xin_smooth_rail_loop_1::/rail_loop/lowered_loop.con'},
      {resName='::/stations/unrelated.con'}}
menu={height=0,rotation=0}
util={getConstructionDefinitions=function() return defs end,
  getActionParams=function(definition)
    return {constructionActionParams={
      constructionBuilder={params={trackType=1,catenary=1},height=menu.height,rotation=menu.rotation},
      inputActions={constructRaise='raiseOrLower',constructOpt1='rotation'},
      inputActionsHandler=function(key) nativeKeys=nativeKeys+1;menu.rotation=menu.rotation+.1 end}}
  end}
mouseValid=true; mouse={x=100,y=200,z=0}
local function obj() return {} end
api={type={SimpleProposal={new=obj,ConstructionEntity={new=obj}},Context={new=obj},
  Vec2f={new=function(x,y) return {x=x,y=y} end},
  Vec4f={new=function(...) return {...} end},Mat4f={new=function(...) return {...} end}},
  engine={terrain={isValidCoordinate=function() return true end,getHeightAt=function() return 0 end},
    util={getYear=function() return 1944 end,getPlayer=function() return 7 end,
      finance={getPlayersBalance=function() return 1e9 end}}},
  gui={mouse={hasTerrainPosition=function() return mouseValid end,getTerrainPosition=function() return mouse end,
    Event={Type={Clicked=1}}},construction={getRefundableEntities=function() return nil end,
      updateRefundableEntities=function() refunded=refunded+1 end}},
  cmd={makeWorldBuildProposalCmd=function(proposal) return {proposal=proposal} end,
    sendCommand=function(command,callback) commands=commands+1;pending=callback end},
  util={formatMoney=function(value) return '$'..value end}}
log={warning=function(message) lastWarning=message end}
_=function(s) return s end
function render(definition)
  local p=util.getActionParams(definition)
  return builtin.ActionDescriptor{children={builtin.ConstructionAction(p.constructionActionParams)}}
end
function find(node,kind,result)
  result=result or {}
  if node.kind==kind then result[#result+1]=node end
  for _,child in ipairs(node.params and node.params.children or {}) do find(child,kind,result) end
  return result
end
function step() steps.XinRailLoopTerrainPlacement() end
function validate(root)
  local p={proposal={addedSegments={{type=1,comp={
    position0={x=0,y=0,z=0},position1={x=0,y=100,z=8},
    tangent0={x=0,y=100,z=8},tangent1={x=0,y=100,z=8}}}}}}
  find(root,'ProposalViewer')[1].params.onCreateProposalData({costs=100,errorState={messages={},critical=false}},p)
end
'''


class PlacementUiTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(GUI)
        modules = {
            '::/gui/main/react.lua': self.lua.globals().react,
            '::/gui/main/builtin.lua': self.lua.globals().builtin,
            '::/gui/main/mod_entry_point.tl': self.lua.table_from({'ModEntryPointExtension': 'entry'}),
            '::/gui/construction/construction_react_util.tl': self.lua.globals().util,
        }
        for name in ('prefab_geometry.lua', 'terrain_plan.lua', 'placement.lua'):
            modules['xin_smooth_rail_loop_1::/rail_loop/' + name] = self.lua.execute((CONTENT / name).read_text(encoding='utf-8'))
        self.lua.globals().ug_require = lambda path: modules[path]
        self.lua.execute((CONTENT / 'ui_entry.script.lua').read_text(encoding='utf-8'))
        self.lua.execute('''
          local list=util.getConstructionDefinitions()
          assert(list[3].customAction==nil)
          list[1].customAction.recipe{definition=list[1],isActive=true,abort=function() aborted=aborted+1 end}
        ''')

    def test_one_native_descriptor_one_viewer_and_unrelated_tools_untouched(self):
        self.lua.execute('''
          local original=render(defs[3])
          assert(nativeCalls==1 and #find(original,'Native')==1)
          assert(original.params.onBack==nil)
          local root=render(defs[1]); step();root=render(defs[1])
          assert(nativeCalls==1)
          assert(#find(root,'ActionDescriptor')==1 and #find(root,'ProposalViewer')==1)
          assert(#find(root,'Native')==0)
          local input=find(root,'SimpleInputActions')[1].params
          input.inputActionsHandler('constructOpt1')
          assert(nativeKeys==1)
        ''')

    def test_no_pointer_no_build_and_stale_preview_after_rotation_cannot_apply(self):
        self.lua.execute('''
          local root=render(defs[1]);step();root=render(defs[1]);validate(root)
          menu.rotation=.5;root=render(defs[1])
          find(root,'SimpleInputActions')[1].params.inputActionsHandler('IA_APPLY')
          assert(commands==0)
          step();root=render(defs[1]);validate(root)
          mouseValid=false
          find(root,'Selector')[1].params.onProcessMouseEvent{type=1,button=0}
          assert(commands==0)
          step();root=render(defs[1]);assert(#find(root,'ProposalViewer')==0)
        ''')

    def test_escape_invalidates_callbacks_but_successful_pending_build_keeps_refund(self):
        self.lua.execute('''
          local root=render(defs[1]);step();root=render(defs[1]);validate(root)
          local input=find(root,'SimpleInputActions')[1].params
          input.inputActionsHandler('IA_APPLY')
          input.inputActionsHandler('IA_APPLY')
          assert(commands==1)
          root.params.onBack();assert(aborted==1)
          pending({resultEntities={{123,1}},proposal={proposal={}}},true)
          assert(refunded==1)
          validate(root)
          input.inputActionsHandler('IA_APPLY')
          assert(commands==1)
        ''')

    def test_height_offset_uses_world_terrain_once_not_rendered_preview_height(self):
        self.lua.execute('''
          mouse.z=100;menu.height=5
          local root=render(defs[1]);step();root=render(defs[1])
          local proposal=find(root,'ProposalViewer')[1].params.simpleProposal
          assert(proposal.constructionsToAdd[1].transf[4][3]==5)
          mouse.z=105;step();root=render(defs[1])
          proposal=find(root,'ProposalViewer')[1].params.simpleProposal
          assert(proposal.constructionsToAdd[1].transf[4][3]==5)
        ''')


if __name__ == '__main__':
    unittest.main()
