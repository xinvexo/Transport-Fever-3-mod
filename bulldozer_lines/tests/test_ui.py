"""Exercise selection and GUI lifecycles with Lua 5.2, not the native renderer."""
import os
from pathlib import Path
import re
import unittest
from zipfile import ZipFile

from lupa.lua52 import LuaRuntime

CONTENT = Path(__file__).resolve().parents[1] / 'content/bulldozer_lines'
GAME = Path(os.environ['TF3_GAME_DIR']) if os.environ.get('TF3_GAME_DIR') else None

HARNESS = r'''
names = {[11]='Sedona [Bus]', [22]='Payson', [33]='Sedona Cargo'}
entities = {11,22,33}
visible = {[11]=true,[22]=false,[33]=true}
carrierSets = {[11]={[1]=true},[22]={[3]=true},[33]={[4]=true}}
reads={names=0,filters=0,visible=0,sorts=0}
local nativeSort=table.sort
table.sort=function(...) reads.sorts=reads.sorts+1;return nativeSort(...) end
api = {engine = {entityExists=function(id) return names[id] ~= nil end,
  util={getPlayer=function() return 7 end, getEntityName=function(id)
    reads.names=reads.names+1;return names[id]
  end},
  system={lineSystem={getLinesForPlayer=function(player) assert(player==7);return entities end}}}}
api.type = {['enum']={Carrier={ROAD=1,TRAM=2,RAIL=3,WATER=4,AIR=5}}}
firedEvents, pendingEvents, eventHandlers, dirty = {}, {}, {}, {}
api.gui = {fireReactEvent=function() error('Use react.fireEvent(source,name,param)') end,
  byEntity={isLineEmptyOrVisible=function(id) reads.visible=reads.visible+1;return visible[id] or false end},
  byId={resetMovedWindowPosition=function(id)
    assert(id=='xin.bulldozer.lines');resetCount=(resetCount or 0)+1
  end},
  genericRep={find=function(path) return path end,get=function(path)
    if path=='::/gui/main/default_colors.gres' then
      return {data={BaseMedium={0.1,0.15,0.2,1},BaseVeryLight={0.3,0.4,0.5,1},
        NeutralLight={0.8,0.8,0.8,1},Invisible={0,0,0,0}}}
    end
    assert(path=='::/gui/main/transparency.gres')
    return {data={VeryHigh=0.1,High=0.3,Medium=0.5}}
  end}}
colorUtil={withTransparencyRaw=function(c,a) return {c[1],c[2],c[3],a} end}
nativeLines={filterLine=function(allowed,id)
  reads.filters=reads.filters+1
  for _,carrier in ipairs(allowed) do if carrierSets[id][carrier] then return true end end
  return false
end}
-- A comparator stand-in, not an implementation of the game's language rules.
-- Sorting cases below inject engine results to verify delegation and caching.
langUtil={compareStrings=function(a,b)
  if a==b then return 0 end
  return a<b and -1 or 1
end}
recipes, memories, mountFns, unmountFns, timers, steps, subscriptions = {}, {}, {}, {}, {}, {}, {}
renderCounts={}
local current, cursor, mounted, generation = nil, 0, {}, 0
local function slot(value,kind)
  cursor = cursor + 1
  local memory = memories[current]
  if not memory[cursor] then
    local state = {value=value, expired=false,kind=kind,owner=current}
    function state:old() assert(not self.expired);return self.value end
    function state:get() assert(not self.expired);return self.value end
    function state:set(v)
      assert(not self.expired)
      if self.value==v then return end
      self.value=v
      if self.kind~='ref' then dirty[self.owner]=true end
      -- A ref does not redraw its owner, but native mirror/dependent states
      -- subscribed to that ref do receive its updates.
      for dependent,sources in pairs(subscriptions) do
        local notify=sources[self]
        if type(notify)=='function' then notify(v)
        elseif notify then dirty[dependent]=true end
      end
    end
    function state:transform(fn) self:set(fn(self:old())) end
    function state:hasExpired() return self.expired end
    memory[cursor] = state
  end
  assert(memory[cursor].kind==kind, "React hook slot changed kind: "..current..":"..cursor)
  return memory[cursor]
end
local function register(name,fn)
  recipes[name] = fn
  return function(params) return {recipe=name,params=params or {}} end
end
react = {RegisterRecipe=register,
  RegisterWrapperRecipe=function(name,_,fn) return register(name,fn) end,
  RegisterPluginRecipe=function(_,name,fn) return register(name,fn) end,
  useState=function(v) return slot(v,'state') end, useRef=function(v) return slot(v,'ref') end,
  useMirrorState=function(state)
    assert(current and not state:hasExpired())
    local mirror=slot(nil,'mirror')
    mirror.old=function() return state:old() end
    subscriptions[current]=subscriptions[current] or {}
    subscriptions[current][state]=true
    return mirror
  end,
  useDependentState=function(state,transform)
    assert(current and not state:hasExpired())
    local dependent=slot(nil,'dependent')
    local owner=current
    dependent.value=transform(dependent.value,state:old())
    subscriptions[current]=subscriptions[current] or {}
    subscriptions[current][state]=function(value)
      local nextValue=transform(dependent.value,value)
      if nextValue~=dependent.value then dependent.value=nextValue;dirty[owner]=true end
    end
    return dependent
  end,
  onStep=function(fn) steps[current]=fn end,
  onMount=function(fn) mountFns[current]=fn end,
  onUnmount=function(fn) unmountFns[current]=fn end,
  onEvent=function(name,fn)
    eventHandlers[current]=eventHandlers[current] or {};eventHandlers[current][name]=fn
  end,
  fireEvent=function(source,name,param)
    assert(source==nil);firedEvents[#firedEvents+1]=name
    pendingEvents[#pendingEvents+1]={name,param}
  end}
function flushEvents()
  while #pendingEvents>0 do
    local queue=pendingEvents;pendingEvents={}
    for _,event in ipairs(queue) do
      if event[1]=='closeConstructionWindow' then
        activeTool=previousTool;activeVariant=previousVariant
        react.fireEvent(nil,'constructionMenuActive',{active=false})
      end
      for _,handlers in pairs(eventHandlers) do
        if handlers[event[1]] then handlers[event[1]](event[1],event[2]) end
      end
    end
  end
end
function changeTool(tool,variant)
  activeTool=tool;activeVariant=variant
  react.fireEvent(nil,'constructionMenuActive',{active=tool and tool.name=='Construction' or false})
  flushEvents()
end
function render(name,params,key)
  local previous,previousCursor=current,cursor
  current=key or name;generation=generation+1;cursor=0;memories[current]=memories[current] or {}
  renderCounts[current]=(renderCounts[current] or 0)+1
  dirty[current]=nil
  local result=recipes[name](params or {})
  if not mounted[current] then
    mounted[current]=true
    if mountFns[current] then mountFns[current]() end
  end
  current=previous;cursor=previousCursor
  return result
end
function unmount(key)
  if unmountFns[key] then unmountFns[key]() end
  for _,state in ipairs(memories[key] or {}) do state.expired=true end
  memories[key]=nil;mounted[key]=nil
  steps[key]=nil;timers[key]=nil;mountFns[key]=nil;unmountFns[key]=nil;eventHandlers[key]=nil
  subscriptions[key]=nil;dirty[key]=nil
end
windows, added, removed = {}, 0, 0
windowApi = {
  addSingletonWindow=function(recipe,params)
    added=added+1;windows[recipe]=params;windowRecipe=recipe;windowParams=params
    if onWindowAdded then onWindowAdded() end
  end,
  removeAllWindows=function(recipe)
    removed=removed+1;windows[recipe]=nil
    unmount('XinBulldozerLineWindow')
    local keys={};for key in pairs(memories) do if key:find('cell:',1,true) then keys[#keys+1]=key end end
    for _,key in ipairs(keys) do unmount(key) end
    cellParams={};cellNodes={};tableIdentities={}
    if onWindowRemoved then onWindowRemoved() end
  end}
activeTool, activeVariant = {name='Construction'}, 'bulldozer'
globals = {getDefaultWindowApi=function() return windowApi end,
  getDefaultToolStackApi=function()
    return {getActiveTool=function() return activeTool,activeVariant end}
  end}
local function equal(a,b)
  if type(a)~='table' or type(b)~='table' then return a==b end
  for k,v in pairs(a) do if not equal(v,b[k]) then return false end end
  for k in pairs(b) do if a[k]==nil then return false end end
  return true
end
engine = {useStepStateTimer=function(fn,interval,equals)
  assert(interval==0.5)
  local initial
  if not memories[current][cursor+1] then initial=fn(nil) end
  local state=slot(initial,'state');timers[current]=function()
    local nextValue=fn(state:old())
    if not (equals or equal)(nextValue,state:old()) then state:set(nextValue) end
  end
  return state
end}
local allowed = {
  Component={layout=true},
  Window={id=true,title=true,initialX=true,initialY=true,compact=true,movable=true,closable=true,
    autoFocusOnBecomingVisible=true,autoVisibilityOnFocusChange=true,onClose=true,content=true},
  BoxLayout={orientation=true,children=true},
  FloatingLayout={children=true},
  FloatingLayoutChild={h=true,v=true,item=true},
  CheckBox={value=true,label=true,onValueChange=true,triStateSupport=true},
  TextInputField={placeholderText=true,value=true,onTyping=true,onValueChange=true,onCancel=true,maxLength=true},
  TextView={text=true,tooltipWhenClipped=true}, Button={content=true,onClick=true},
  ToggleButton={content=true,value=true,onValueChange=true},
  ImageView={path=true,scaling=true},
  TableLayout={columnWeights=true,rows=true},Row={cells=true},
  ColumnDesc={name=true,recipe=true,weight=true},
  DataTable={columns=true,rowKeys=true,userParam=true,disableSortKey=true,
    scrollPolicyHorizontal=true,scrollPolicyVertical=true},
  LineViewer={selectable=true,showLines=true,hiddenLinesTransparent=true,showTerminals=true,
    fadingMinHeight=true,fadingDeltaHeight=true},
}
builtin = {type={Orientation={Horizontal=1,Vertical=2},
  ImageViewScaling={AutoFit=1},
  ScrollBarPolicy={AsNeeded=1,AlwaysOff=2,AsNeededButAlwaysReserveSpace=3},LineVisualization={new=function() return {} end}}}
cellParams={};cellNodes={};tableIdentities={};tableCreationCount=0
for name,fields in pairs(allowed) do
  builtin[name]=function(params)
    for field in pairs(params) do assert(field=='meta' or fields[field],name..': '..field) end
    local node={kind=name,params=params,owner=current,generation=generation}
    if name=='DataTable' then
      local tableKey=current..':'..params.meta.localKey
      if not tableIdentities[tableKey] then tableIdentities[tableKey]={};tableCreationCount=tableCreationCount+1 end
      node.identity=tableIdentities[tableKey]
      local keep={};for _,id in ipairs(params.rowKeys) do keep['cell:'..id]=true end
      local gone={};for key in pairs(cellParams) do if not keep[key] then gone[#gone+1]=key end end
      for _,key in ipairs(gone) do unmount(key);cellParams[key]=nil;cellNodes[key]=nil end
      node.cells={}
      for _,id in ipairs(params.rowKeys) do
        local key='cell:'..id
        -- Real DataTable retains the FIRST userParam for surviving cells.
        cellParams[key]=cellParams[key] or {rowKey=id,colKey=1,userParam=params.userParam}
        if not cellNodes[key] or dirty[key] then
          local row=params.columns[1].params.recipe(cellParams[key])
          cellNodes[key]=render(row.recipe,row.params,key)
        end
        node.cells[#node.cells+1]=cellNodes[key]
      end
    end
    return node
  end
end
builtin.ActionFn=register('ActionFn',function(params) return params.fn and params.fn() end)
builtin.ActionDescriptor=function(...)
  local params=select(select('#',...),...)
  for _,node in pairs(params.children or {}) do
    assert(node.recipe==nil, 'Action collector requires native configuration nodes')
    assert(node.owner==current and node.generation==generation, 'Action node belongs to a different render')
  end
  return {kind='ActionDescriptor',args=table.pack(...),params=params}
end
lineUI={ColorWidget=function(params) return {kind='ColorWidget',params=params} end,
  LocateButton=function(params) return {kind='LocateButton',params=params} end}
log={message=function() end}
_=function(text) return text end
function ug_require(path)
  local modules={
    ['::/gui/main/builtin.lua']=builtin, ['::/gui/main/react.lua']=react,
    ['::/gui/main/mod_entry_point.tl']={ModEntryPointExtension={}},
    ['::/gui/main/game_react_globals.tl']=globals, ['::/gui/main/engine_react_util.tl']=engine,
    ['::/gui/line_vehicle_mgmt/line_react_util.tl']=lineUI,
    ['::/gui/main/color_util.tl']=colorUtil,
    ['::/gui/line_vehicle_mgmt/line_util.tl']=nativeLines,
    ['::/scripts/lang_util.tl']=langUtil,
    ['xin_bulldozer_lines_1::/bulldozer_lines/lines.lua']=lines,
    ['::/gui/construction/construction_react_util.tl']={getActionParams=function() return {} end},
    ['xin_bulldozer_lines_1::/bulldozer_lines/building_colors.lua']={apply=function(_,result) return result end},
  }
  assert(modules[path],path);return modules[path]
end
function find(node,kind,result)
  result=result or {}
  if type(node) ~= 'table' then return result end
  if node.kind == kind then result[#result+1]=node.params end
  local p=node.params or {}
  if p.content then find(p.content,kind,result) end
  if p.layout then find(p.layout,kind,result) end
  if p.item then find(p.item,kind,result) end
  for _,child in pairs(p.children or {}) do find(child,kind,result) end
  for _,child in pairs(p.rows or {}) do find(child,kind,result) end
  for _,child in pairs(p.cells or {}) do find(child,kind,result) end
  for _,child in pairs(node.cells or {}) do find(child,kind,result) end
  return result
end
function checks(window)
  local result={}
  for _,checkbox in ipairs(find(window,'CheckBox')) do
    if not checkbox.meta or checkbox.meta.localKey~='select-all' then result[#result+1]=checkbox end
  end
  return result
end
function headerCheck(window)
  for _,checkbox in ipairs(find(window,'CheckBox')) do
    if checkbox.meta and checkbox.meta.localKey=='select-all' then return checkbox end
  end
end
function assertShown(viewer,expected)
  assert(viewer.kind=='LineViewer')
  local p=viewer.params
  assert(p.selectable==false and p.hiddenLinesTransparent==false and p.showTerminals==false)
  assert(#p.showLines==#expected)
  for i,id in ipairs(expected) do assert(p.showLines[i].entity==id) end
end
local function nativeAction(params)
  react.useState({constructionDefinition=true});react.useState({layer=true})
  if params.selector then
    react.useRef(-1)
    return builtin.ActionDescriptor{tool='selector',children={}}
  end
  sourceChild={kind='ConstructionAction',owner=current,generation=generation,params={native=true}}
  sourceParams={tool=params.tool or 'construction-menu-bulldozer',
    children={sourceChild},onBack=function() end}
  if params.ref then return builtin.ActionDescriptor(params.ref,sourceParams) end
  return builtin.ActionDescriptor(sourceParams)
end
recipes.TestNativeAction=function(params)
  local node=builtin.ActionFn{localKey='native',fn=function() return nativeAction(params) end}
  return recipes.ActionFn(node.params)
end
function drawBulldozer()
  local action=render('TestNativeAction')
  return action.params.children[2]
end
'''


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(HARNESS)
        self.lua.globals().lines = self.lua.execute((CONTENT / 'lines.lua').read_text(encoding='utf-8'))
        self.lua.execute((CONTENT / 'ui_entry.script.lua').read_text(encoding='utf-8'))
        self.lua.execute("render('XinBulldozerLinesEntry'); flushEvents()")

    def test_native_name_comparison_drives_numeric_and_chinese_order(self):
        self.lua.execute('''
          names={[11]='线路10',[22]='线路2',[33]='重庆1',[44]='北京1'}
          entities={11,33,22,44}
          -- Deliberately differs from UTF-8 order. The real Chinese ordering
          -- belongs to the engine; this fixture only checks that it is obeyed.
          local rank={['北京1']=1,['重庆1']=2,['线路2']=3,['线路10']=4}
          local comparisons=0
          langUtil.compareStrings=function(a,b)
            comparisons=comparisons+1
            return (rank[a]-rank[b])*7
          end
          local snapshot=lines.read({carriers={}})
          assert(comparisons>0)
          for i,id in ipairs({44,33,22,11}) do assert(snapshot[i].entity==id) end
          windowParams.lines:set(snapshot)
          local window=render('XinBulldozerLineWindow',windowParams)
          local keys=find(window,'DataTable')[1].rowKeys
          for i,id in ipairs({44,33,22,11}) do assert(keys[i]==id) end
          local calls=comparisons
          visible[11]=false
          local nextSnapshot=lines.read({carriers={},onlyVisible=true},snapshot)
          assert(comparisons==calls, 'Visibility changes retain the native name order')
          names[11]='线路1';rank['线路1']=2.5
          nextSnapshot=lines.read({carriers={}},nextSnapshot)
          assert(comparisons>calls and nextSnapshot[3].entity==11 and nextSnapshot[4].entity==22)
        ''')

    def test_first_selector_to_bulldozer_keeps_native_hook_slots(self):
        self.lua.execute('''
          unmount('XinBulldozerLinesEntry')
          changeTool(nil)
          for _,entryFirst in ipairs({false,true}) do
            unmount('TestNativeAction')
            if entryFirst then render('XinBulldozerLinesEntry') end
            render('TestNativeAction',{selector=true})
            assert(memories.TestNativeAction[4]:get()==-1)
            if not entryFirst then render('XinBulldozerLinesEntry') end
            changeTool({name='Construction'},'bulldozer')
            assertShown(drawBulldozer(),{22,33,11})
            assert(memories.TestNativeAction[4]:get()==-1, 'Native selector ref must remain untouched')
            render('TestNativeAction',{selector=true})
            assertShown(drawBulldozer(),{22,33,11})
            changeTool(nil)
            unmount('XinBulldozerLinesEntry')
          end
        ''')

    def test_selection_redraws_only_the_changed_row_without_engine_queries(self):
        self.lua.execute('''
          local window=render('XinBulldozerLineWindow',windowParams)
          find(window,'ToggleButton')[1].onValueChange(1)
          find(window,'ToggleButton')[3].onValueChange(1)
          window=render('XinBulldozerLineWindow',windowParams)
          local beforeNames,beforeFilters,beforeVisible=reads.names,reads.filters,reads.visible
          local first,second=renderCounts['cell:22'],renderCounts['cell:11']
          checks(window)[1].onValueChange(1)
          window=render('XinBulldozerLineWindow',windowParams)
          render('XinBulldozerLinesEntry');flushEvents()
          assertShown(drawBulldozer(),{22})
          assert(renderCounts['cell:22']==first+1)
          assert(renderCounts['cell:11']==second, 'Unchanged row must retain its native cell')
          find(window,'TextInputField')[1].onTyping('Sedona')
          window=render('XinBulldozerLineWindow',windowParams)
          assert(#checks(window)==1)
          assert(reads.names==beforeNames and reads.filters==beforeFilters and reads.visible==beforeVisible)
        ''')

    def test_window_aggregation_checks_each_entity_once_and_keeps_row_subscriptions(self):
        self.lua.execute('''
          local snapshot=lines.read({carriers={}})
          local native=api.engine.entityExists
          local checks=0
          api.engine.entityExists=function(id) checks=checks+1;return native(id) end
          local shown,keys,rows,value=lines.windowData(snapshot,{carriers={}},'',{[22]=true},{})
          assert(checks==3 and #shown==3 and value==-1 and keys[1]==22)
          checks=0
          local _,_,unchanged=lines.windowData(snapshot,{carriers={}},'',{},rows)
          assert(checks==3 and unchanged==rows)
          names[33]=nil
          checks=0
          shown,keys,rows,value=lines.windowData(snapshot,{carriers={}},'Sedona',{[11]=true},rows)
          assert(checks==3 and #shown==1 and keys[1]==11 and value==1)
          assert(rows[33]==nil and rows[11].index==1 and rows[22]==nil)
        ''')

    def test_filter_event_reads_once_then_table_and_action_reuse_snapshot(self):
        self.lua.execute('''
          local window=render('XinBulldozerLineWindow',windowParams)
          local buttons=find(window,'ToggleButton')
          buttons[6].onValueChange(1)
          local beforeNames,beforeFilters,beforeVisible=reads.names,reads.filters,reads.visible
          buttons[1].onValueChange(1)
          assert(reads.names==beforeNames+3 and reads.filters==beforeFilters+3 and reads.visible==beforeVisible+3)
          window=render('XinBulldozerLineWindow',windowParams)
          render('XinBulldozerLinesEntry');flushEvents()
          assertShown(drawBulldozer(),{11})
          assert(reads.names==beforeNames+3 and reads.filters==beforeFilters+3 and reads.visible==beforeVisible+3)
          buttons[1].onValueChange(1)
          assert(reads.names==beforeNames+3, 'Repeated native value notifications should do no work')
          buttons[1].onValueChange(0)
          assertShown(drawBulldozer(),{33,11})
        ''')

    def test_camera_refresh_reuses_order_but_rename_and_entity_changes_resort(self):
        self.lua.execute('''
          local filters={carriers={},onlyVisible=true}
          local old=lines.read(filters)
          assert(lines.read(filters,old)==old, 'An unchanged snapshot retains its identity')
          local sorts=reads.sorts
          visible[11]=false;entities={33,11,22}
          local nextSnapshot=lines.read(filters,old)
          assert(reads.sorts==sorts and nextSnapshot[1].entity==22 and nextSnapshot[3].entity==11)
          assert(nextSnapshot[1]==old[1] and nextSnapshot[2]==old[2] and nextSnapshot[3]~=old[3])
          names[33]='Aardvark'
          nextSnapshot=lines.read(filters,nextSnapshot)
          assert(reads.sorts==sorts+1 and nextSnapshot[1].entity==33)
          names[22]=nil;names[44]='Alpha';visible[44]=true;entities={44,33,11}
          nextSnapshot=lines.read(filters,nextSnapshot)
          assert(reads.sorts==sorts+2 and #nextSnapshot==3)
          assert(nextSnapshot[1].entity==33 and nextSnapshot[2].entity==44)
        ''')

    def test_row_order_subscription_handles_child_before_parent_render(self):
        self.lua.execute('''
          local window=render('XinBulldozerLineWindow',windowParams)
          find(window,'TextInputField')[1].onTyping('Sedona')
          cellNodes['cell:33']=render('XinBulldozerLineRow',cellParams['cell:33'],'cell:33')
          assert(cellNodes['cell:33'].params.meta.class:find('alternate'))
          window=render('XinBulldozerLineWindow',windowParams)
          local rows=find(window,'Button')
          assert(not rows[1].meta.class:find('alternate'))
          assert(rows[2].meta.class:find('alternate'))
          assert(cellParams['cell:33'].userParam.rows:get()[33].index==1)
        ''')

    def test_empty_search_keeps_table_but_unmounts_removed_rows(self):
        self.lua.execute('''
          local window=render('XinBulldozerLineWindow',windowParams)
          local tableParams=find(window,'DataTable')[1]
          local oldCell=memories['cell:33'][1]
          find(window,'TextInputField')[1].onTyping('no matching line')
          window=render('XinBulldozerLineWindow',windowParams)
          local empty=find(window,'DataTable')[1]
          assert(empty and #empty.rowKeys==0 and empty.meta.localKey==tableParams.meta.localKey)
          assert(empty.meta.class:find('empty') and oldCell:hasExpired())
          assert(memories['cell:33']==nil and tableCreationCount==1)
          find(window,'TextInputField')[1].onCancel()
          window=render('XinBulldozerLineWindow',windowParams)
          assert(tableCreationCount==1 and #checks(window)==3)
          assert(not find(window,'DataTable')[1].meta.class:find('empty'))
        ''')

    def test_refresh_targets_only_bulldozer_and_unchanged_entry_stays_quiet(self):
        self.lua.execute('''
          render('TestNativeAction',{tool='management'},'ManagerAction')
          render('TestNativeAction',{selector=true},'SelectorAction')
          drawBulldozer()
          local window=render('XinBulldozerLineWindow',windowParams)
          checks(window)[1].onValueChange(1)
          render('XinBulldozerLinesEntry');flushEvents()
          assert(dirty.TestNativeAction and not dirty.ManagerAction and not dirty.SelectorAction)
          drawBulldozer()
          local count=#firedEvents
          render('XinBulldozerLinesEntry');flushEvents()
          assert(#firedEvents==count and not dirty.TestNativeAction)
          find(window,'TextInputField')[1].onTyping('Sedona')
          render('XinBulldozerLineWindow',windowParams)
          assert(#firedEvents==count and not dirty.TestNativeAction, 'Search only affects the panel')
        ''')

    def test_old_window_callbacks_cannot_close_or_modify_reopened_panel(self):
        self.lua.execute('''
          local old=render('XinBulldozerLineWindow',windowParams)
          local oldParams=windowParams
          changeTool(nil)
          changeTool({name='Construction'},'bulldozer')
          local newParams=windowParams
          old.params.onClose()
          checks(old)[1].onValueChange(1)
          find(old,'Button')[1].onClick()
          find(old,'ToggleButton')[1].onValueChange(1)
          find(old,'TextInputField')[1].onTyping('stale')
          assert(newParams.isCurrent() and not oldParams.isCurrent())
          assert(next(newParams.selected:old())==nil and next(newParams.filters:old().carriers)==nil)
          local window=render('XinBulldozerLineWindow',newParams)
          assert(#checks(window)==3)
          unmount('XinBulldozerLinesEntry')
          old.params.onClose();checks(old)[1].onValueChange(1)
          find(old,'Button')[1].onClick()
          assert(next(windows)==nil)
        ''')

    def test_x_returns_to_shelved_manager_and_pending_close_does_not_reopen(self):
        self.lua.execute('''
          local manager={name='Manager',selection={77},visible=false}
          previousTool=manager
          local window=render('XinBulldozerLineWindow',windowParams)
          window.params.onClose()
          render('XinBulldozerLinesEntry')
          assert(added==1 and next(windows)==nil and drawBulldozer()==nil)
          flushEvents()
          assert(activeTool==manager and manager.selection[1]==77)
          changeTool({name='Construction'},'bulldozer')
          assert(added==2 and windowParams.isCurrent())
        ''')

    def test_rapid_lifecycle_events_and_reentrant_window_api_are_idempotent(self):
        self.lua.execute('''
          changeTool(nil)
          onWindowAdded=function() render('XinBulldozerLinesEntry') end
          onWindowRemoved=function() render('XinBulldozerLinesEntry') end
          for _=1,3 do
            changeTool({name='Construction'},'bulldozer')
            local before=added
            react.fireEvent(nil,'constructionMenuActive',{active=true});flushEvents()
            assert(added==before)
            local window=render('XinBulldozerLineWindow',windowParams)
            window.params.onClose();window.params.onClose();flushEvents()
            assert(next(windows)==nil)
          end
          changeTool({name='Construction'},'bulldozer')
          local old=windowParams
          react.fireEvent(nil,'constructionMenuActive',{active=false})
          react.fireEvent(nil,'constructionMenuActive',{active=true})
          flushEvents()
          assert(not old.isCurrent() and windowParams.isCurrent())
        ''')

    def test_inactive_snapshot_does_not_scan_lines_and_no_frame_tool_poll(self):
        self.lua.execute('''
          changeTool(nil)
          local native=api.engine.system.lineSystem.getLinesForPlayer
          api.engine.system.lineSystem.getLinesForPlayer=function() error('inactive line scan') end
          timers.XinBulldozerLinesEntry()
          render('XinBulldozerLinesEntry')
          assert(next(steps)==nil)
          api.engine.system.lineSystem.getLinesForPlayer=native
          changeTool({name='Construction'},'bulldozer')
          assertShown(drawBulldozer(),{22,33,11})
        ''')

    def test_existing_table_cells_update_names_selection_and_striping_after_filter(self):
        self.lua.execute('''
          local window=render('XinBulldozerLineWindow',windowParams)
          local original=cellParams['cell:33'].userParam
          checks(window)[2].onValueChange(1)
          window=render('XinBulldozerLineWindow',windowParams)
          names[33]='Sedona ' .. string.rep('Long Name ',80)
          timers.XinBulldozerLinesEntry()
          window=render('XinBulldozerLineWindow',windowParams)
          assert(cellParams['cell:33'].userParam==original)
          local rows=find(window,'Button')
          assert(rows[2].meta.class:find('alternate') and rows[2].meta.class:find('selected'))
          find(window,'TextInputField')[1].onTyping('Sedona')
          window=render('XinBulldozerLineWindow',windowParams)
          rows=find(window,'Button')
          assert(rows[1].meta.class:find('selected') and not rows[1].meta.class:find('alternate'))
          assert(rows[2].meta.class:find('alternate'))
          local name=rows[1].content.params.rows[1].params.cells[3].params
          assert(name.text==names[33] and name.tooltipWhenClipped==names[33])
          local tableParams=find(window,'DataTable')[1]
          assert(tableParams.scrollPolicyHorizontal==builtin.type.ScrollBarPolicy.AlwaysOff)
          assert(tableParams.scrollPolicyVertical==builtin.type.ScrollBarPolicy.AsNeededButAlwaysReserveSpace)
        ''')

    def test_only_bulldozer_is_augmented_and_native_action_is_preserved(self):
        self.lua.execute('''
          local ref={ref=true}
          local result=render('TestNativeAction',{ref=ref})
          assert(result.args.n==2 and result.args[1]==ref)
          assert(result.params.onBack==sourceParams.onBack)
          assert(result.params.children[1]==sourceChild and #result.params.children==2)
          assert(result.params.children[2].kind=='LineViewer')
          assert(#sourceParams.children==1)
          assert(#memories.TestNativeAction==3, 'Fixed prefix plus two native states')
          for _,tool in ipairs({'management','construction-menu-road','construction-menu-module-bulldozer'}) do
            local other=render('TestNativeAction',{tool=tool})
            assert(other.params==sourceParams and #other.params.children==1)
          end
        ''')

    def test_search_is_literal_and_preserves_selection_outside_results(self):
        self.lua.execute('''
          drawBulldozer()
          local window=render('XinBulldozerLineWindow',windowParams)
          checks(window)[1].onValueChange(1)
          find(window,'TextInputField')[1].onTyping('[BUS]')
          window=render('XinBulldozerLineWindow',windowParams)
          assert(#checks(window)==1 and checks(window)[1].meta.localKey=='line-check-11')
          assertShown(drawBulldozer(),{22})
          assert(#find(window,'DataTable')==1 and #find(window,'ColorWidget')==1)
        ''')

    def test_deleted_lines_are_removed_and_empty_world_never_uses_empty_viewer(self):
        self.lua.execute('''
          drawBulldozer()
          windowParams.selected:set({[22]=true})
          names[22]=nil
          assertShown(drawBulldozer(),{33,11})
          timers.XinBulldozerLinesEntry()
          local window=render('XinBulldozerLineWindow',windowParams)
          assert(#checks(window)==2)
          names={}
          assert(drawBulldozer()==nil)
          timers.XinBulldozerLinesEntry()
          window=render('XinBulldozerLineWindow',windowParams)
          assert(#checks(window)==0)
        ''')

    def test_switching_tools_closes_panel_and_reentering_resets_selection(self):
        self.lua.execute('''
          windowParams.selected:set({[11]=true})
          assertShown(drawBulldozer(),{11})
          for _,variant in ipairs({'road','module-bulldozer'}) do
            changeTool(activeTool,variant)
            assert(next(windows)==nil)
            changeTool(activeTool,'bulldozer')
            assert(next(windows)~=nil)
            assertShown(drawBulldozer(),{22,33,11})
          end
          changeTool({name='Manager'})
          assert(next(windows)==nil)
          changeTool(nil)
          assert(next(windows)==nil)
        ''')

    def test_stale_close_button_does_not_exit_another_construction_tool(self):
        self.lua.execute('''
          local window=render('XinBulldozerLineWindow',windowParams)
          activeVariant='road'
          window.params.onClose()
          assert(next(windows)==nil and #firedEvents==0)
          assert(activeTool.name=='Construction' and activeVariant=='road')
        ''')

    def test_filters_are_independent_and_combine_with_visible_area(self):
        self.lua.execute('''
          local window=render('XinBulldozerLineWindow',windowParams)
          local toggles=find(window,'ToggleButton')
          assert(#toggles==6)
          toggles[1].onValueChange(1)
          toggles[3].onValueChange(1)
          assert(windowParams.filters:old().carriers.ROAD and windowParams.filters:old().carriers.RAIL)
          assertShown(drawBulldozer(),{22,11})
          toggles[6].onValueChange(1)
          assertShown(drawBulldozer(),{11})
          visible[11]=false;visible[22]=true
          timers.XinBulldozerLinesEntry()
          render('XinBulldozerLinesEntry');flushEvents()
          assert(dirty.TestNativeAction, 'Camera changes must invalidate the active viewer')
          assertShown(drawBulldozer(),{22})
          window=render('XinBulldozerLineWindow',windowParams)
          assert(#checks(window)==1 and checks(window)[1].meta.localKey=='line-check-22')
          toggles[6].onValueChange(0)
          toggles[1].onValueChange(0)
          assert(windowParams.filters:old().carriers.RAIL)
          assertShown(drawBulldozer(),{22})
          toggles[3].onValueChange(0)
          assertShown(drawBulldozer(),{22,33,11})
        ''')

    def test_filtered_out_selection_does_not_show_unchecked_lines(self):
        self.lua.execute('''
          windowParams.selected:set({[11]=true})
          windowParams.filters:set({carriers={RAIL=true},onlyVisible=false})
          assert(drawBulldozer()==nil)
          local window=render('XinBulldozerLineWindow',windowParams)
          assert(#checks(window)==1 and checks(window)[1].value==0)
          headerCheck(window).onValueChange(1)
          assertShown(drawBulldozer(),{22})
          window=render('XinBulldozerLineWindow',windowParams)
          headerCheck(window).onValueChange(0)
          assert(next(windowParams.selected:old())==nil)
          assert(windowParams.filters:old().carriers.RAIL)
          assertShown(drawBulldozer(),{22})
        ''')

    def test_transport_compatibility_change_invalidates_the_line_snapshot(self):
        self.lua.execute('''
          windowParams.filters:set({carriers={RAIL=true},onlyVisible=false})
          timers.XinBulldozerLinesEntry()
          local original=windowParams.lines:old()
          timers.XinBulldozerLinesEntry()
          assert(windowParams.lines:old()==original, 'Unchanged data should not repaint')
          carrierSets[33]={[3]=true}
          timers.XinBulldozerLinesEntry()
          assert(windowParams.lines:old()~=original, 'Carrier changes must trigger a repaint')
          local window=render('XinBulldozerLineWindow',windowParams)
          assert(#checks(window)==2)
          assertShown(drawBulldozer(),{22,33})
        ''')

    def test_header_selection_tracks_search_and_partial_selection(self):
        self.lua.execute('''
          assertShown(drawBulldozer(),{22,33,11})
          local window=render('XinBulldozerLineWindow',windowParams)
          assert(headerCheck(window).value==0)
          checks(window)[1].onValueChange(1)
          window=render('XinBulldozerLineWindow',windowParams)
          assert(headerCheck(window).value==-1)
          find(window,'TextInputField')[1].onTyping('Sedona')
          window=render('XinBulldozerLineWindow',windowParams)
          headerCheck(window).onValueChange(1)
          assert(windowParams.selected:old()[11] and windowParams.selected:old()[33])
          assert(not windowParams.selected:old()[22])
          assertShown(drawBulldozer(),{33,11})
          window=render('XinBulldozerLineWindow',windowParams)
          assert(headerCheck(window).value==1)
          headerCheck(window).onValueChange(0)
          assert(next(windowParams.selected:old())==nil)
          assertShown(drawBulldozer(),{22,33,11})
        ''')


@unittest.skipUnless(GAME, 'Set TF3_GAME_DIR to check shipped GUI contracts')
class NativeContractTests(unittest.TestCase):
    def test_filter_icons_and_locate_match_native_resources(self):
        gui = GuiTests()
        gui.setUp()
        api_source = (GAME / 'api/tealdef/api/gui.d.tl').read_text(encoding='utf-8')
        for name in ('resetMovedWindowPosition', 'isLineEmptyOrVisible', 'followEntity'):
            self.assertRegex(api_source, rf'\b{name}\s*:\s*function')
        with ZipFile(GAME / 'base/content/gui.zip') as archive:
            icons = [category['icon'] for category in gui.lua.globals().lines.categories.values()]
            icons += ['::/gui/statistics/icons/symbol_eye_18.tga',
                      '::/gui/line_vehicle_mgmt/icons/symbol_locate_20.tga']
            for icon in icons:
                relative = icon.removeprefix('::/')
                self.assertTrue(relative in archive.namelist()
                                or relative.replace('.tga', '@2x.tga') in archive.namelist(), icon)
            native_filter = archive.read('gui/line_vehicle_mgmt/line_util.d.tl').decode('utf-8')
            self.assertIn('filterLine : function(allowedCarriers', native_filter)
            locate = archive.read('gui/line_vehicle_mgmt/line_react_util.tl').decode('utf-8')
            self.assertIn('api.gui.camera.followEntity(param.entity, true)', locate)

    def test_stylesheet_parses_with_native_selector_parser(self):
        gui = GuiTests()
        gui.setUp()
        gui.lua.execute(r'''
          function string.strip(s) return s:match("^%s*(.-)%s*$") end
          function string.ends(s,suffix) return s:sub(-#suffix)==suffix end
          function string.split(s,separator)
            local result,start={},1
            while true do
              local at=s:find(separator,start,true)
              if not at then result[#result+1]=s:sub(start);return result end
              result[#result+1]=s:sub(start,at-1);start=at+#separator
            end
          end
          local function copy(value)
            if type(value)~='table' then return value end
            local result={};for k,v in pairs(value) do result[k]=copy(v) end;return result
          end
          function require(path)
            assert(path=='/scripts/table_util.tl')
            return {copy=copy}
          end
        ''')
        with ZipFile(GAME / 'base/content/gui.zip') as archive:
            gui.lua.globals().ssu = gui.lua.execute(archive.read('gui/main/stylesheetutil.lua').decode('utf-8'))
        gui.lua.execute('''
          function require(path)
            if path=='::/gui/main/stylesheetutil.lua' then return ssu end
            assert(path=='::/gui/main/color_util.tl');return colorUtil
          end
        ''')
        gui.lua.execute((CONTENT / 'panel.css.lua').read_text(encoding='utf-8'))
        rules = gui.lua.globals().data()
        self.assertGreater(len(rules), 0)
        for rule in rules.values():
            levels = list(rule['levels'].values())
            self.assertEqual(levels[0]['id'], 'xin.bulldozer.lines')
            last = levels[-1]
            classes = set(last['classList'].values())
            if classes == {'bl-list', 'empty'}:
                self.assertEqual(rule['styleSheet']['visibility'], 'none')
            if 'bl-card' in classes:
                self.assertFalse(last['element'], 'Class selector must match recipe-backed components too')

    def test_dependent_states_and_snapshot_refresh_follow_native_contracts(self):
        declarations = (GAME / 'base/tealdef/scripts/react.d.tl').read_text(encoding='utf-8')
        self.assertIn('transform : function(curDependent : D, source : S) : D', declarations)
        with ZipFile(GAME / 'base/content/gui.zip') as archive:
            engine = archive.read('gui/main/engine_react_util.tl').decode('utf-8')
        self.assertIn('getFromEngine(stateData:old())', engine)
        self.assertIn('stateEqualsFn(newState, stateData:old())', engine)

    def test_rendered_button_fields_match_native_userdata(self):
        source = (GAME / 'base/tealdef/scripts/builtin.d.tl').read_text(encoding='utf-8')
        viewer = re.search(r'record LineViewerParam\b(.*?)\n\s*end', source, re.S).group(1)
        for field in ('selectable', 'hiddenLinesTransparent', 'showTerminals'):
            self.assertRegex(viewer, rf'\b{field}\s*:\s*boolean')
        record = re.search(r'record ButtonParam\b(.*?)\n\s*end', source, re.S).group(1)
        fields = set(re.findall(r'^\s*(\w+)\s*:', record, re.M))
        gui = GuiTests()
        gui.setUp()
        buttons = gui.lua.execute('''
          drawBulldozer()
          return find(render('XinBulldozerLineWindow',windowParams),'Button')
        ''')
        for button in buttons.values():
            self.assertLessEqual(set(button.keys()) - {'meta'}, fields)
            self.assertIsNotNone(button['content'])

    def test_native_bulldozer_has_the_expected_action_and_descriptor(self):
        with ZipFile(GAME / 'base/content/gui.zip') as archive:
            construction = archive.read('gui/construction/construction.tl').decode('utf-8')
            builtin = archive.read('gui/main/builtin.lua').decode('utf-8')
            globals_code = archive.read('gui/main/game_react_globals.tl').decode('utf-8')
        self.assertIn('addSingleCategory(_("Bulldozer"), "bulldozer"', construction)
        self.assertIn('builtin.ConstructionAction(actionParams.constructionActionParams)', construction)
        self.assertIn('("construction-menu-" .. categories[activeIndex].id)', construction)
        self.assertIn('DeclareBuiltinWithUserdata("ActionDescriptor", function (params) return params.children end)', builtin)
        self.assertIn('function game_react_globals.getDefaultWindowApi()', globals_code)

if __name__ == '__main__':
    unittest.main()
