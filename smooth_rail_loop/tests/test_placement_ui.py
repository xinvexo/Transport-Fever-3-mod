"""Exercise the GUI adapter's lifecycle with Lua 5.2 (not an in-game test)."""
from pathlib import Path
import os
import re
import unittest
from zipfile import ZipFile

from lupa.lua52 import LuaRuntime

CONTENT = Path(__file__).resolve().parents[1] / 'content/rail_loop'
GAME = Path(os.environ['TF3_GAME_DIR']) if os.environ.get('TF3_GAME_DIR') else None

GUI = r'''
local memories, cursor, memory, activeName = {}, 0
steps, unmounts, inputConfigs = {}, {}, {}
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
function recordInput(id,config)
  assert(activeName=='XinRailLoopLifecycle', 'Input handlers must be registered on the native menu recipe')
  inputConfigs[activeName][id]=config
end
react={useRef=slot,useState=slot,
  onStep=function(fn) steps[activeName]=fn end,
  onUnmount=function(fn) unmounts[activeName]=fn end,
  RegisterRecipe=function(name,fn)
    return function(params)
      activeName=name; cursor=0; memories[name]=memories[name] or {}; memory=memories[name]
      inputConfigs[name]={}
      local result=fn(params)
      activeName=nil
      if type(result)=='table' and result.kind==nil then
        return {kind='Recipe',params={children=result}}
      end
      return result
    end
  end,
  useInputAction=recordInput,
  iaHandler=function(handler,enabled,prompt,repeated,isActive)
    return {handlerFn=handler,isEnabledFn=enabled,promptTextOverride=prompt,mode=repeated and 1 or 0,isActive=isActive}
  end,
  RegisterPluginRecipe=function(_,_,fn) return fn end}
local allowed={
  Component={},FloatingLayout={children=true},TextView={text=true,meta=true},
  Selector={filter=true,stopOnMenuBack=true,onProcessMouseEvent=true},
  ProposalViewer={simpleProposal=true,proposalId=true,entityForRefundableContext=true,onCreateProposalData=true},
  ActionTooltip={recipe=true,param=true},ActionDescriptor={children=true,onBack=true,tool=true}}
builtin={}
function declareBuiltin(name)
  return function(params)
    local keys=allowed[name]
    if keys then for key in pairs(params) do assert(keys[key],name..' has no '..key) end end
    if name=='ConstructionAction' then
      nativeCalls=nativeCalls+1
      return {kind='Native',params=params}
    end
    return {kind=name,params=params}
  end
end
for name in pairs(allowed) do builtin[name]=declareBuiltin(name) end
nativeCalls, nativeKeys, aborted, commands, refunded=0,0,0,0,0
builtin.ConstructionAction=declareBuiltin('ConstructionAction')
defs={{resName='xin_smooth_rail_loop_1::/rail_loop/raised_loop.con'},
      {resName='xin_smooth_rail_loop_1::/rail_loop/lowered_loop.con'},
      {resName='::/stations/unrelated.con'}}
menu={height=0,rotation=0}
util={getConstructionDefinitions=function() return defs end,
  getActionParams=function(definition)
    return {constructionActionParams={
      constructionBuilder={params={trackType=1,catenary=1},height=menu.height,rotation=menu.rotation},
      inputActions={constructRaise='raiseOrLower',constructLower='raiseOrLower',constructOpt1='rotation',constructOpt2='rotation'},
      inputActionsHandler=function(key) nativeKeys=nativeKeys+1;lastNativeKey=key;menu.rotation=menu.rotation+.1 end}}
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
function press(id)
  local handler=inputConfigs.XinRailLoopLifecycle[id]
  assert(handler,'Missing input action: '..id)
  if not handler.isEnabledFn or handler.isEnabledFn() then handler.handlerFn();return true end
  return false
end
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
        if GAME is not None:
            with ZipFile(GAME / 'base/content/gui.zip') as archive:
                source = archive.read('gui/main/builtin.lua').decode('utf-8-sig')
                react_source = archive.read('gui/main/react.lua').decode('utf-8-sig')
            # Load the shipped export table. These factories replace native
            # rendering only; they do not invent or enable exported names.
            for name in set(re.findall(r'react\.(DeclareBuiltin\w*)\s*\(', source)):
                self.lua.globals().react[name] = self.lua.globals().declareBuiltin
            self.lua.execute('''
              react.builtin={}
              local function namespace()
                return setmetatable({}, {__index=function(t,k) local v=namespace();rawset(t,k,v);return v end})
              end
              api.gui.react={params={builtin=namespace()},detail={IAHandle={new=function() return {mode=0} end}}}
            ''')
            empty = self.lua.table()
            self.lua.globals().require = lambda name: self.lua.globals().react if name == 'react.lua' else empty
            self.lua.globals().ug_require = lambda name: empty
            self.lua.globals().builtin = self.lua.execute(source)
            # Execute the shipped hook implementations too; only their native
            # component context and IAHandle storage are replaced in this test.
            hook_source = []
            for name in ('useInputAction', 'iaHandler'):
                match = re.search(r'\b' + name + r'\s*=\s*(function\b[\s\S]*?\n\tend),', react_source)
                self.assertIsNotNone(match, 'Missing shipped React hook: ' + name)
                hook_source.append(name + '=' + match.group(1))
            hooks = self.lua.execute('''
              local function useComponentInternals()
                return {setInputActionConfig=function(_,id,config) recordInput(id,config) end}
              end
              local function fixIsEnabledBool(fn) return fn end
              return {''' + ','.join(hook_source) + '}')
            for name in ('useInputAction', 'iaHandler'):
                self.lua.globals().react[name] = hooks[name]
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
          assert(builtin.SimpleInputActions==nil)
          assert(#find(root,'FloatingLayout')==0)
          press('constructOpt1')
          assert(nativeKeys==1)
        ''')

    def test_no_pointer_no_build_and_stale_preview_after_rotation_cannot_apply(self):
        self.lua.execute('''
          local root=render(defs[1]);step();root=render(defs[1]);validate(root)
          menu.rotation=.5;root=render(defs[1])
          press('IA_APPLY')
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
          press('IA_APPLY')
          press('IA_APPLY')
          assert(commands==1)
          root.params.onBack();assert(aborted==1)
          pending({resultEntities={{123,1}},proposal={proposal={}}},true)
          assert(refunded==1)
          validate(root)
          press('IA_APPLY')
          assert(commands==1)
        ''')

    def test_menu_bindings_forward_native_ids_repeat_keys_and_disable_after_exit(self):
        self.lua.execute('''
          local root=render(defs[1])
          for _,id in ipairs({'constructRaise','constructLower','constructOpt1','constructOpt2'}) do
            local handler=inputConfigs.XinRailLoopLifecycle[id]
            assert(handler.mode==1)
            assert(press(id) and lastNativeKey==id)
          end
          assert(inputConfigs.XinRailLoopLifecycle.IA_APPLY.mode==0)
          assert(not press('IA_APPLY'))
          root.params.onBack()
          assert(not press('constructOpt1') and not press('IA_APPLY'))
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
