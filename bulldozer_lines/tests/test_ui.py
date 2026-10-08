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
api = {engine = {entityExists=function(id) return names[id] ~= nil end,
  util={getPlayer=function() return 7 end, getEntityName=function(id) return names[id] end},
  system={lineSystem={getLinesForPlayer=function(player) assert(player==7);return entities end}}}}
api.type = {['enum']={Carrier={ROAD=1,TRAM=2,RAIL=3,WATER=4,AIR=5}},
  Vec2f={new=function(x,y) return {x=x,y=y} end},
  Vec4f={new=function(x,y,z,w) return {x=x,y=y,z=z,w=w} end}}
local function strict(fields)
  return function() return setmetatable({}, {__newindex=function(t,k,v)
    assert(fields[k],'Unsupported native style field: '..k)
    if k=='backgroundColor' or k=='backgroundColor1' or k=='borderColor' or k=='padding' then
      assert(type(v)=='table' and v.x~=nil and v.w~=nil,'Expected Vec4f for '..k)
    end
    rawset(t,k,v)
  end}) end
end
firedEvents={}
api.gui = {fireReactEvent=function(name)
    firedEvents[#firedEvents+1]=name
    if name=='closeConstructionWindow' then activeTool=nil;activeVariant=nil end
  end,
  byEntity={isLineEmptyOrVisible=function(id) return visible[id] or false end},
  byId={resetMovedWindowPosition=function(id)
    assert(id=='xin.bulldozer.lines');resetCount=(resetCount or 0)+1
  end},
  StyleSheet={new=strict({size=true,padding=true,backgroundImage1=true,borderImage=true,
    backgroundColor1=true,borderColor=true,backgroundColor=true})},
  NinePatch={new=strict({fileName=true,horizontal=true,vertical=true})},
  genericRep={find=function(path) return path end,get=function(path)
    if path=='::/gui/main/default_colors.gres' then
      return {data={BaseMedium={0.1,0.15,0.2,1},BaseVeryLight={0.3,0.4,0.5,1},
        NeutralLight={0.8,0.8,0.8,1},Invisible={0,0,0,0}}}
    end
    assert(path=='::/gui/main/transparency.gres')
    return {data={VeryHigh=0.1,High=0.3,Medium=0.5}}
  end}}
colorUtil={toVec4=function(c) return api.type.Vec4f.new(table.unpack(c)) end,
  withTransparency=function(c,a) return api.type.Vec4f.new(c[1],c[2],c[3],a) end,
  withTransparencyRaw=function(c,a) return {c[1],c[2],c[3],a} end}
nativeLines={filterLine=function(allowed,id)
  for _,carrier in ipairs(allowed) do if carrierSets[id][carrier] then return true end end
  return false
end}
recipes, memories, mountFns, unmountFns, timers, steps, subscriptions = {}, {}, {}, {}, {}, {}, {}
local current, cursor, mounted, generation = nil, 0, {}, 0
local function slot(value)
  cursor = cursor + 1
  local memory = memories[current]
  if not memory[cursor] then
    local state = {value=value, expired=false}
    function state:old() assert(not self.expired);return self.value end
    function state:get() assert(not self.expired);return self.value end
    function state:set(v) assert(not self.expired);self.value=v end
    function state:transform(fn) self:set(fn(self:old())) end
    function state:hasExpired() return self.expired end
    memory[cursor] = state
  end
  return memory[cursor]
end
local function register(name,fn)
  recipes[name] = fn
  return function(params) return {recipe=name,params=params or {}} end
end
react = {RegisterRecipe=register,
  RegisterWrapperRecipe=function(name,_,fn) return register(name,fn) end,
  RegisterPluginRecipe=function(_,name,fn) return register(name,fn) end,
  useState=slot, useRef=slot,
  useMirrorState=function(state)
    assert(current and not state:hasExpired())
    subscriptions[current]=subscriptions[current] or {}
    subscriptions[current][state]=true
    return state
  end,
  onStep=function(fn) steps[current]=fn end,
  onMount=function(fn) mountFns[current]=fn end,
  onUnmount=function(fn) unmountFns[current]=fn end}
function render(name,params,key)
  current=key or name;generation=generation+1;cursor=0;memories[current]=memories[current] or {}
  local result=recipes[name](params or {})
  if not mounted[current] then
    mounted[current]=true
    if mountFns[current] then mountFns[current]() end
  end
  current=nil
  return result
end
function unmount(key)
  if unmountFns[key] then unmountFns[key]() end
  for _,state in ipairs(memories[key] or {}) do state.expired=true end
  memories[key]=nil;mounted[key]=nil
end
windows, added, removed = {}, 0, 0
windowApi = {
  addSingletonWindow=function(recipe,params)
    added=added+1;windows[recipe]=params;windowRecipe=recipe;windowParams=params
  end,
  removeAllWindows=function(recipe) removed=removed+1;windows[recipe]=nil end}
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
engine = {useStepStateTimer=function(fn,interval)
  assert(interval==0.5)
  local state=slot(fn());timers[current]=function()
    local nextValue=fn()
    if not equal(nextValue,state:old()) then state:set(nextValue) end
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
  TextView={text=true}, Button={content=true,onClick=true},
  ToggleButton={content=true,value=true,onValueChange=true},
  ImageView={path=true,scaling=true},
  List={children=true,orientation=true,behavior=true,selectionIndex=true,deselectAllowed=true,cycle=true,
    horizontalScrollBarPolicy=true,verticalScrollBarPolicy=true},
  LineViewer={selectable=true,showLines=true,hiddenLinesTransparent=true,showTerminals=true,
    fadingMinHeight=true,fadingDeltaHeight=true},
}
builtin = {type={Orientation={Horizontal=1,Vertical=2},ListBehavior={Default=0},
  ImageViewScaling={AutoFit=1},
  ScrollBarPolicy={AsNeeded=1},LineVisualization={new=function() return {} end}}}
for name,fields in pairs(allowed) do
  builtin[name]=function(params)
    for field in pairs(params) do assert(field=='meta' or fields[field],name..': '..field) end
    if name=='List' then
      for _,child in pairs(params.children or {}) do
        assert(child.kind=='Component' or child.kind=='TextView' or child.kind=='Button',
          'List children must be Components, not Layouts')
      end
    end
    return {kind=name,params=params,owner=current,generation=generation}
  end
end
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
styleutil={makeStyle=function(style) return style end}
log={message=function() end}
_=function(text) return text end
function ug_require(path)
  local modules={
    ['::/gui/main/builtin.lua']=builtin, ['::/gui/main/react.lua']=react,
    ['::/gui/main/mod_entry_point.tl']={ModEntryPointExtension={}},
    ['::/gui/main/game_react_globals.tl']=globals, ['::/gui/main/engine_react_util.tl']=engine,
    ['::/gui/main/styleutil.tl']=styleutil, ['::/gui/line_vehicle_mgmt/line_react_util.tl']=lineUI,
    ['::/gui/main/color_util.tl']=colorUtil,
    ['::/gui/line_vehicle_mgmt/line_util.tl']=nativeLines,
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
register('TestNativeAction',function(params)
  sourceChild={kind='ConstructionAction',owner=current,generation=generation,params={native=true}}
  sourceParams={tool=params.tool or 'construction-menu-bulldozer',
    children={sourceChild},onBack=function() end}
  if params.ref then return builtin.ActionDescriptor(params.ref,sourceParams) end
  return builtin.ActionDescriptor(sourceParams)
end)
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
        self.lua.execute("render('XinBulldozerLinesEntry'); steps.XinBulldozerLinesEntry()")

    def test_only_bulldozer_is_augmented_and_native_action_is_preserved(self):
        self.lua.execute('''
          local ref={ref=true}
          local result=render('TestNativeAction',{ref=ref})
          assert(result.args.n==2 and result.args[1]==ref)
          assert(result.params.onBack==sourceParams.onBack)
          assert(result.params.children[1]==sourceChild and #result.params.children==2)
          assert(result.params.children[2].kind=='LineViewer')
          assert(#sourceParams.children==1)
          assert(subscriptions.TestNativeAction[windowParams.selected])
          assert(subscriptions.TestNativeAction[windowParams.lines])
          for _,tool in ipairs({'management','construction-menu-road','construction-menu-module-bulldozer'}) do
            local other=render('TestNativeAction',{tool=tool})
            assert(other.params==sourceParams and #other.params.children==1)
          end
        ''')

    def test_checking_lines_hides_every_other_line_and_clear_restores_all(self):
        self.lua.execute('''
          assertShown(drawBulldozer(),{22,33,11})
          local window=render('XinBulldozerLineWindow',windowParams)
          assert(added==1 and #checks(window)==3)
          checks(window)[3].onValueChange(1)
          assertShown(drawBulldozer(),{11})
          window=render('XinBulldozerLineWindow',windowParams)
          assert(checks(window)[3].value==1)
          checks(window)[2].onValueChange(1)
          assertShown(drawBulldozer(),{33,11})
          checks(window)[3].onValueChange(0)
          assertShown(drawBulldozer(),{33})
          headerCheck(window).onValueChange(1)
          window=render('XinBulldozerLineWindow',windowParams)
          assert(headerCheck(window).value==1)
          headerCheck(window).onValueChange(0)
          assert(next(windowParams.selected:old())==nil)
          assertShown(drawBulldozer(),{22,33,11})
          assert(added==1)
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
          assert(#find(window,'List')==1 and #find(window,'ColorWidget')==1)
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

    def test_close_button_exits_bulldozer_and_cleans_up_without_reopening(self):
        self.lua.execute('''
          drawBulldozer()
          local window=render('XinBulldozerLineWindow',windowParams)
          assert(window.params.autoFocusOnBecomingVisible==false)
          assert(window.params.autoVisibilityOnFocusChange==false)
          assert(window.params.tool==nil)
          window.params.onClose()
          assert(next(windows)==nil)
          assert(#firedEvents==1 and firedEvents[1]=='closeConstructionWindow')
          assert(activeTool==nil)
          steps.XinBulldozerLinesEntry()
          assert(added==1)
          local oldParams=windowParams
          unmount('XinBulldozerLineWindow')
          unmount('XinBulldozerLinesEntry')
          assert(next(windows)==nil and oldParams.selected:hasExpired())
          activeTool={name='Construction'};activeVariant='bulldozer'
          render('XinBulldozerLinesEntry'); steps.XinBulldozerLinesEntry()
          assert(added==2 and next(windows)~=nil)
        ''')

    def test_switching_tools_closes_panel_and_reentering_resets_selection(self):
        self.lua.execute('''
          windowParams.selected:set({[11]=true})
          assertShown(drawBulldozer(),{11})
          for _,variant in ipairs({'road','module-bulldozer'}) do
            activeVariant=variant;steps.XinBulldozerLinesEntry()
            assert(next(windows)==nil)
            activeVariant='bulldozer';steps.XinBulldozerLinesEntry()
            assert(next(windows)~=nil)
            assertShown(drawBulldozer(),{22,33,11})
          end
          activeTool={name='Manager'};steps.XinBulldozerLinesEntry()
          assert(next(windows)==nil)
          activeTool=nil;steps.XinBulldozerLinesEntry()
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

    def test_action_collector_rejects_deferred_or_stale_node_ids(self):
        self.lua.execute('''
          recipes.TestBadAction=function()
            return builtin.ActionDescriptor{
              tool='management',children={{recipe='DeferredRecipe'}}
            }
          end
          local ok=pcall(render,'TestBadAction')
          assert(not ok)
          local previous=render('TestNativeAction').params.children[2]
          recipes.TestStaleAction=function()
            return builtin.ActionDescriptor{tool='management',children={previous}}
          end
          assert(not pcall(render,'TestStaleAction'))
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

    def test_left_panel_has_framed_list_locators_and_no_instruction_footer(self):
        self.lua.execute('''
          local window=render('XinBulldozerLineWindow',windowParams)
          assert(window.params.initialX > 0 and window.params.initialX < 0.05)
          assert(window.params.initialY > 0 and window.params.initialY < 0.3)
          assert(resetCount==1)
          render('XinBulldozerLineWindow',windowParams)
          assert(resetCount==1)
          local locators=find(window,'LocateButton')
          assert(#locators==3)
          assert(locators[1].entity==22 and locators[2].entity==33 and locators[3].entity==11)
          assert(locators[1].iconPathOverride=='::/gui/line_vehicle_mgmt/icons/symbol_locate_20.tga')
          local framed=false
          for _,component in ipairs(find(window,'Component')) do
            if component.meta and component.meta.class=='bl-card' then framed=true end
          end
          assert(framed)
          assert(headerCheck(window) and headerCheck(window).triStateSupport==false)
          for _,row in ipairs(find(window,'List')[1].children) do
            local cells=row.params.content.params.children
            assert(cells[1].kind=='CheckBox' and cells[2].kind=='ColorWidget')
            assert(cells[3].kind=='Button' and cells[4].kind=='LocateButton')
          end
          for _,text in ipairs(find(window,'TextView')) do
            assert(text.text~='Check lines to show only those routes.')
            assert(text.text~='Show all lines')
          end
        ''')

    def test_header_selection_tracks_search_and_partial_selection(self):
        self.lua.execute('''
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

    def test_stylesheet_parses_with_native_selector_parser_and_uses_native_sizing(self):
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
        found_row = found_filters = found_card = False
        for rule in rules.values():
            levels = list(rule['levels'].values())
            self.assertEqual(levels[0]['id'], 'xin.bulldozer.lines')
            last = levels[-1]
            classes = set(last['classList'].values())
            style = rule['styleSheet']
            if 'bl-row' in classes and style['size'] is not None:
                self.assertEqual(tuple(style['size'].values()), (490, -1))
                found_row = True
            if 'bl-card' in classes:
                self.assertEqual(tuple(style['size'].values()), (-1, 240))
                self.assertIsNotNone(style['borderImage'])
                found_card = True
            if last['element'] == 'ToggleButton':
                self.assertIsNone(style['size'], 'Native filter buttons use their icon size')
                self.assertEqual(tuple(style['padding'].values()), (6, 6, 6, 6))
                found_filters = True
        self.assertTrue(found_row and found_filters and found_card)

    def test_rendered_button_fields_match_native_userdata(self):
        source = (GAME / 'base/tealdef/scripts/builtin.d.tl').read_text(encoding='utf-8')
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

    def test_viewer_can_hide_unselected_lines_without_intercepting_selection(self):
        source = (GAME / 'base/tealdef/scripts/builtin.d.tl').read_text(encoding='utf-8')
        viewer = re.search(r'record LineViewerParam\b(.*?)\n\s*end', source, re.S).group(1)
        for field in ('selectable', 'hiddenLinesTransparent', 'showTerminals'):
            self.assertRegex(viewer, rf'\b{field}\s*:\s*boolean')
        self.assertIn('AsNeeded : ScrollBarPolicy', source)
        with ZipFile(GAME / 'base/content/gui.zip') as archive:
            line = archive.read('gui/entity_window/line/line.tl').decode('utf-8')
            self.assertRegex(line, r'builtin.LineViewer\s*{\s*selectable = false')
            self.assertIn('hiddenLinesTransparent = false', line)


if __name__ == '__main__':
    unittest.main()
