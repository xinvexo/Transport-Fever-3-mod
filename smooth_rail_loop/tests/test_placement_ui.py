"""Native customAction lifecycle with shipped Lua exports, not an engine test."""
from pathlib import Path
import os
import re
import unittest
from zipfile import ZipFile

from lupa.lua52 import LuaRuntime

CONTENT = Path(__file__).resolve().parents[1] / 'content/rail_loop'
GAME = Path(os.environ['TF3_GAME_DIR']) if os.environ.get('TF3_GAME_DIR') else None

GUI = r'''
local memories, cursor, memory, activeName, activeInstance = {}, 0
steps, unmounts, inputConfigs, internals, bindings = {}, {}, {}, {}, {}
local function slot(value)
  cursor=cursor+1
  if not memory[cursor] then
    local o={value=value,expired=false}
    function o:hasExpired() return self.expired end
    function o:get() assert(not self.expired,'Expired ref read');return self.value end
    function o:old() assert(not self.expired,'Expired state read');return self.value end
    function o:set(v) assert(not self.expired,'Expired state write');self.value=v end
    memory[cursor]=o
  end
  return memory[cursor]
end
function componentInternals()
  assert(activeName=='XinRailLoopMenu','Handlers belong to the menu recipe')
  return internals[activeInstance]
end
react={useRef=slot,useState=slot,
  onStep=function(fn) steps[activeInstance]=fn end,
  onUnmount=function(fn) unmounts[activeInstance]=fn end,
  RegisterRecipe=function(name,fn)
    return function(params)
      activeName=name
      activeInstance=name..'/'..(params.definition and params.definition.resName or '')
      cursor=0;memories[activeInstance]=memories[activeInstance] or {};memory=memories[activeInstance]
      inputConfigs[activeInstance]={}
      local instance=activeInstance
      internals[instance]={setInputActionConfig=function(_,id,config) inputConfigs[instance][id]=config end}
      local result=fn(params)
      activeName,activeInstance=nil,nil
      return result
    end
  end,
  useInputAction=function(id,config) componentInternals():setInputActionConfig(id,config) end,
  iaHandler=function(handler,enabled,prompt,repeated,isActive)
    return {handlerFn=handler,isEnabledFn=enabled,promptTextOverride=prompt,mode=repeated and 1 or 0,isActive=isActive}
  end,
  setForceFocusable=function(v) componentInternals().forceFocusable=v end,
  setRestrictMouseFocus=function(v) componentInternals().restrictMouseFocus=v end,
  RegisterPluginRecipe=function(_,_,fn) return fn end}
local allowed={Component={},BoxLayout={children=true,orientation=true},TextView={text=true,meta=true},
  Selector={filter=true,onProcessMouseEvent=true},
  ProposalViewer={simpleProposal=true,proposalId=true,entityForRefundableContext=true,onCreateProposalData=true},
  EdgeRenderable={edges=true,ignoreDepth=true},
  LayerConfig={config=true},ActionTooltip={recipe=true,param=true},ActionDescriptor={children=true,onBack=true,tool=true}}
function declareBuiltin(name)
  return function(params)
    local keys=allowed[name]
    if keys then for key in pairs(params) do assert(keys[key],name..' has no '..key) end end
    if name=='ConstructionAction' then nativeCalls=nativeCalls+1;return {kind='Native',params=params} end
    return {kind=name,params=params}
  end
end
builtin={}
for name in pairs(allowed) do builtin[name]=declareBuiltin(name) end
nativeCalls,aborted,commands,refunded=0,0,0,0
builtin.ConstructionAction=declareBuiltin('ConstructionAction')
defs={{resName='xin_smooth_rail_loop_1::/rail_loop/raised_loop.con'},
      {resName='xin_smooth_rail_loop_1::/rail_loop/lowered_loop.con'},
      {resName='::/stations/unrelated.con'}}
menu={height=0,rotation=0,trackType=1,catenary=1}
util={getConstructionDefinitions=function() return defs end,
      getActionParams=function() return {constructionActionParams={constructionBuilder={}}} end}
mouseValid=true;mouse={x=100,y=200,z=0}
local function obj() return {} end
api={type={SimpleProposal={new=obj,ConstructionEntity={new=obj}},Context={new=obj},LayerConfig={new=obj},
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
diagnostics={}
log={warning=function(message) lastWarning=message end,
     message=function(message) diagnostics[#diagnostics+1]=message end}
_=function(s) return s end
function instance(definition) return 'XinRailLoopMenu/'..definition.resName end
function mount(definition,active)
  local layout=definition.customAction.recipe{
    definition=definition,isActive=active,getCurrentParams=function() return menu end,
    gameCtx={preferredLayerConfig={get=function() return preferredLayer end}},
    abort=function() aborted=aborted+1 end,
    setActionFn=function(fn,key) bindings[definition.resName]={fn=fn,key=key} end}
  assert(layout.kind=='BoxLayout','Recipe child must be a layout')
  return layout
end
function render(definition)
  if definition.customAction then
    mount(definition,true)
    return bindings[definition.resName].fn()
  end
  return builtin.ActionDescriptor{children={builtin.ConstructionAction(util.getActionParams(definition).constructionActionParams)}}
end
function unmount(definition)
  local id=instance(definition)
  unmounts[id]()
  for _,ref in ipairs(memories[id]) do ref.expired=true end
  memories[id]=nil;inputConfigs[id]={}
end
function find(node,kind,result)
  result=result or {}
  if node.kind==kind then result[#result+1]=node end
  for _,child in ipairs(node.params and node.params.children or {}) do find(child,kind,result) end
  return result
end
function step(definition) steps[instance(definition or defs[1])]() end
function press(definition)
  local handler=inputConfigs[instance(definition or defs[1])].IA_APPLY
  if handler and (not handler.isEnabledFn or handler.isEnabledFn()) then handler.handlerFn();return true end
  return false
end
function validate(root)
  local prepared={proposal={addedSegments={{type=1,comp={
    position0={x=0,y=0,z=0},position1={x=0,y=100,z=8},
    tangent0={x=0,y=100,z=8},tangent1={x=0,y=100,z=8}}}}}}
  find(root,'ProposalViewer')[1].params.onCreateProposalData({costs=100,errorState={messages={},critical=false}},prepared)
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
            hook_source = []
            names = ('useInputAction', 'iaHandler', 'setForceFocusable', 'setRestrictMouseFocus')
            for name in names:
                match = re.search(r'\b' + name + r'\s*=\s*(function\b[^\n]*?\bend),', react_source)
                if match is None:
                    match = re.search(r'\b' + name + r'\s*=\s*(function\b[\s\S]*?\n\tend),', react_source)
                self.assertIsNotNone(match, 'Missing shipped React hook: ' + name)
                hook_source.append(name + '=' + match.group(1))
            hooks = self.lua.execute('''
              local useComponentInternals=componentInternals
              local function fixIsEnabledBool(fn) return fn end
              return {''' + ','.join(hook_source) + '}')
            for name in names:
                self.lua.globals().react[name] = hooks[name]
        self.lua.execute('''
          builtin.type=builtin.type or {}
          builtin.type.EdgeRenderable=builtin.type.EdgeRenderable or {}
          builtin.type.EdgeRenderable.Edge={new=function(geometry)
            assert(geometry.native,'Renderer must reuse native geometry')
            return {edgeGeometry=geometry}
          end}
        ''')
        modules = {
            '::/gui/main/react.lua': self.lua.globals().react,
            '::/gui/main/builtin.lua': self.lua.globals().builtin,
            '::/gui/main/mod_entry_point.tl': self.lua.table_from({'ModEntryPointExtension': 'entry'}),
            '::/gui/construction/construction_react_util.tl': self.lua.globals().util,
        }
        for name in ('prefab_geometry.lua', 'terrain_plan.lua', 'placement.lua'):
            modules['xin_smooth_rail_loop_1::/rail_loop/' + name] = self.lua.execute((CONTENT / name).read_text(encoding='utf-8'))
        self.lua.globals().ug_require = lambda path: modules[path]
        self.lua.execute('originalAction=builtin.ConstructionAction;originalDescriptor=builtin.ActionDescriptor;originalParams=util.getActionParams')
        self.lua.execute((CONTENT / 'ui_entry.script.lua').read_text(encoding='utf-8'))
        self.lua.execute('util.getConstructionDefinitions()')

    def test_native_factories_untouched_and_one_descriptor_one_viewer(self):
        self.lua.execute('''
          assert(originalAction==builtin.ConstructionAction)
          assert(originalDescriptor==builtin.ActionDescriptor)
          assert(originalParams==util.getActionParams)
          assert(defs[3].customAction==nil)
          assert(#find(render(defs[3]),'Native')==1 and nativeCalls==1)
          local root=render(defs[1]);step();root=render(defs[1])
          assert(nativeCalls==1 and #find(root,'Native')==0)
          assert(#find(root,'ActionDescriptor')==1 and #find(root,'ProposalViewer')==1)
          assert(builtin.SimpleInputActions==nil)
        ''')

    def test_tool_changes_and_expired_callbacks_do_not_reuse_old_action_children(self):
        self.lua.execute('''
          for i=1,12 do
            local definition=defs[i%2+1]
            local root=render(definition);step(definition);root=render(definition)
            local oldAction=bindings[definition.resName].fn
            local oldPreview=find(root,'ProposalViewer')[1]
            mount(definition,false)
            assert(#oldAction().params.children==0)
            assert(not press(definition))
            unmount(definition)
            oldPreview.params.onCreateProposalData({},nil) -- must not read expired refs
            assert(#oldAction().params.children==0)
            root=render(definition);step(definition);root=render(definition)
            assert(#find(root,'ProposalViewer')==1)
            assert(#oldAction().params.children==0)
            unmount(definition)
          end
          assert(commands==0)
        ''')

    def test_binding_key_is_stable_while_menu_height_rotation_and_cursor_change(self):
        self.lua.execute('''
          local root=render(defs[1]);local key=bindings[defs[1].resName].key
          menu.height=5;menu.rotation=90;mouse.z=105;mouse.x=500
          root=render(defs[1]);step();root=render(defs[1])
          assert(bindings[defs[1].resName].key==key)
          local con=find(root,'ProposalViewer')[1].params.simpleProposal.constructionsToAdd[1]
          assert(con.transf[4][1]==500 and con.transf[4][3]==5)
          assert(math.abs(con.transf[1][1])<1e-8 and math.abs(con.transf[1][2]+1)<1e-8)
          assert(menu.xinTerrainPlan==nil)
        ''')

    def test_rebuilt_definition_gets_new_native_action_identity(self):
        self.lua.execute('''
          render(defs[1]);local previous=bindings[defs[1].resName].key
          local replacement={resName=defs[1].resName,customAction=defs[1].customAction}
          render(replacement)
          assert(bindings[replacement.resName].key~=previous)
        ''')

    def test_reactivation_without_menu_unmount_rejects_old_session_callbacks(self):
        self.lua.execute('''
          local root=render(defs[1]);step();root=render(defs[1]);validate(root)
          local oldAction=bindings[defs[1].resName].fn
          press();assert(commands==1)
          mount(defs[1],false)
          root=render(defs[1]);step();root=render(defs[1]);validate(root)
          assert(#oldAction().params.children==0)
          pending({resultEntities={{123,1}},proposal={proposal={}}},true)
          assert(refunded==1)
          press();assert(commands==2)
        ''')

    def test_stale_cursor_and_rotation_preview_cannot_apply(self):
        self.lua.execute('''
          local root=render(defs[1]);step();root=render(defs[1]);validate(root)
          menu.rotation=45;assert(not press() or commands==0)
          root=render(defs[1]);step();root=render(defs[1]);validate(root)
          mouseValid=false
          find(root,'Selector')[1].params.onProcessMouseEvent{type=1,button=0}
          assert(commands==0)
          step();root=render(defs[1]);assert(#find(root,'ProposalViewer')==0)
        ''')

    def test_escape_then_pending_success_keeps_refund_without_touching_dead_ui(self):
        self.lua.execute('''
          local root=render(defs[1]);step();root=render(defs[1]);validate(root)
          press();press();assert(commands==1)
          local oldAction=bindings[defs[1].resName].fn
          root.params.onBack();assert(aborted==1)
          unmount(defs[1])
          pending({resultEntities={{123,1}},proposal={proposal={}}},true)
          assert(refunded==1 and #oldAction().params.children==0)
          validate(root)
          assert(commands==1)
        ''')

    def test_menu_and_cost_error_tooltips_have_layout_roots(self):
        self.lua.execute('''
          for _,active in ipairs({false,true}) do assert(mount(defs[1],active).kind=='BoxLayout') end
          local root=render(defs[1]);step();root=render(defs[1]);validate(root)
          root=render(defs[1]);local tooltip=find(root,'ActionTooltip')[1].params
          assert(tooltip.recipe(tooltip.param).kind=='BoxLayout')
          find(root,'ProposalViewer')[1].params.onCreateProposalData(
            {costs=0,errorState={critical=true,messages={'无法建造'}}},nil)
          root=render(defs[1]);tooltip=find(root,'ActionTooltip')[1].params
          local layout=tooltip.recipe(tooltip.param)
          assert(layout.kind=='BoxLayout' and find(layout,'TextView')[1].params.text:find('无法建造',1,true))
        ''')

    def test_native_underground_toggle_and_preferred_layer_remain_available(self):
        self.lua.execute('''
          menu.undergroundMode=1
          local root=render(defs[2])
          assert(find(root,'LayerConfig')[1].params.config.undergroundMode)
          preferredLayer={custom=true}
          root=render(defs[2]);assert(find(root,'LayerConfig')[1].params.config==preferredLayer)
        ''')

    def test_failed_terrain_sampling_keeps_preview_but_never_commits_fallback(self):
        self.lua.execute('''
          api.engine.terrain.getHeightAt=function(p)
            if p.x==mouse.x and p.y==mouse.y then return 0 end
            error('Terrain sample unavailable')
          end
          local root=render(defs[1]);step();root=render(defs[1])
          assert(#find(root,'ProposalViewer')==1)
          validate(root);root=render(defs[1])
          assert(#find(root,'ProposalViewer')==1)
          local tooltip=find(root,'ActionTooltip')[1].params
          assert(tooltip.param.text:find('仅显示预览',1,true))
          press();assert(commands==0)
          api.engine.terrain.getHeightAt=function() return 0 end
          mouse.x=mouse.x+1;step();root=render(defs[1]);validate(root)
          press();assert(commands==1)
          local logText=table.concat(diagnostics,'\\n')
          assert(logText:find('proposal generated',1,true))
          assert(logText:find('proposal viewer attached',1,true))
          assert(logText:find('proposal checked: allowed=true',1,true))
        ''')

    def test_native_rejection_keeps_candidate_visible_and_blocks_apply(self):
        self.lua.execute('''
          local root=render(defs[1]);step();root=render(defs[1])
          find(root,'ProposalViewer')[1].params.onCreateProposalData(
            {costs=0,errorState={critical=true,messages={'碰撞'}}},nil)
          root=render(defs[1])
          assert(#find(root,'ProposalViewer')==1)
          assert(find(root,'ActionTooltip')[1].params.param.text:find('碰撞',1,true))
          press();assert(commands==0)
        ''')

    def test_rejected_native_tracks_get_red_overlay_without_extra_proposal_viewer(self):
        self.lua.execute('''
          local root=render(defs[1]);step();root=render(defs[1])
          local geom={native=true,length=100}
          local prepared={proposal={addedSegments={{entity=-1,type=1,comp={
            position0={x=0,y=0,z=0},position1={x=0,y=100,z=0},
            tangent0={x=0,y=100,z=0},tangent1={x=0,y=100,z=0}}}}}}
          local data={costs=0,errorState={critical=true,messages={'无法建造'}},
            entity2tn={[-1]={edges={{geometry=geom}}}}}
          find(root,'ProposalViewer')[1].params.onCreateProposalData(data,prepared)
          root=render(defs[1])
          assert(#find(root,'ProposalViewer')==1)
          local overlay=find(root,'EdgeRenderable')[1].params
          assert(overlay.ignoreDepth and #overlay.edges==1)
          assert(overlay.edges[1].edgeGeometry==geom and overlay.edges[1].colors[1][1]==1)
          press();assert(commands==0)
          mouse.x=mouse.x+2;step();root=render(defs[1])
          assert(#find(root,'EdgeRenderable')==0, 'Old location must not keep its overlay')
        ''')


if __name__ == '__main__':
    unittest.main()
