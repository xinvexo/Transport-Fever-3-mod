-- Offline integration harness: executes the actual resource, proposal and UI.
local function copy(x)
  if type(x)~="table" then return x end
  local y={};for k,v in pairs(x) do y[k]=copy(v) end;return y
end
local function v3(x,y,z) return {x=x,y=y,z=z} end
local function edge(x)
  return {position0=v3(x,0,0),position1=v3(x,1000,0),tangent0=v3(0,1000,0),tangent1=v3(0,1000,0),
    node0=x*2+100,node1=x*2+101,objects={},type="BRIDGE",typeIndex=9,roadType="TRACK",
    roadTemplate="third_party::/custom_track.street_template",roadStyle="custom_style",laneConfigs={{catenary=true}},
    edgeDecorations={{42,true}},clone=function(self) return copy(self) end}
end
local entities={[10]=edge(0),[20]=edge(5)}
local revision=1
local enum={RoadType={TRACK="TRACK"},BaseEdgeType={NORMAL="NORMAL",BRIDGE="BRIDGE",TUNNEL="TUNNEL"},
  ScriptParamType={Slider="Slider",ComboBox="ComboBox",Button="Button"},
  ScriptParamLocation={Default=1},ScriptParamDisplayMode={Horizontal=1}}
local components={BASE_EDGE="BASE_EDGE",PLAYER_OWNED="PLAYER_OWNED",TRANSPORT_NETWORK="TRANSPORT_NETWORK"}
local built,previewCallbacks=nil,{}
api={type={enum=enum,ComponentType=components,
    Vec3f={new=v3},Vec4f={new=function(...) return {...} end},
    SimpleProposal={new=function() return {streetProposal={}} end},
    NodeAndEntity={new=function() return {comp={}} end},SegmentAndEntity={new=function() return {comp={}} end},
    Context={new=function() return {} end}},
  engine={entityExists=function(id) return entities[id]~=nil end,
    getRevision=function() return {num={revision,0,0}} end,
    getComponent=function(id,kind) if kind=="BASE_EDGE" then return entities[id] end;if kind=="PLAYER_OWNED" then return {player=1} end end,
    util={getPlayer=function() return 1 end,finance={getPlayersBalance=function() return 1e9 end}}},
  res={bridgeTypeRep={find=function() return 7 end},tunnelTypeRep={find=function() return 8 end}},
  gui={SelectionDetails={Type={TransportNetworkEdge=1}},camera={world2Screen=function(p) return p end},
    construction={getRefundableEntities=function() return nil end,updateRefundableEntities=function() end}},
  util={formatMoney=tostring},cmd={
    makeWorldBuildProposalCmd=function(p,c,a,b) return {p=p} end,
    sendCommand=function(cmd,callback) built=cmd.p;callback({resultEntities={},proposal={proposal=cmd.p}},true) end}}

local geometry=assert(loadfile(MOD.."/dynamic_geometry.lua"))()
local modules={["xin_smooth_rail_loop_1::/rail_loop/dynamic_geometry.lua"]=geometry}
require=function(name) return assert(modules[name],name) end
local proposal=assert(loadfile(MOD.."/dynamic_proposal.lua"))()
modules["xin_smooth_rail_loop_1::/rail_loop/dynamic_proposal.lua"]=proposal
local a=proposal.pick(10,nil,{x=0,y=350})
local b=proposal.pick(20,nil,{x=5,y=350})
assert(math.abs(a.p[2]-350)<.001)
local out,info=proposal.make(a,b,{extension=50,elevation=0,direction=1})
local p=out.streetProposal
assert(#p.edgesToRemove==2 and p.edgesToRemove[1]==10 and p.edgesToRemove[2]==20)
local ids={}
for _,n in ipairs(p.nodesToAdd) do assert(n.entity<0 and not ids[n.entity]);ids[n.entity]=true end
for _,e in ipairs(p.edgesToAdd) do
  assert(e.entity<0 and not ids[e.entity]);ids[e.entity]=true
  assert(e.comp.roadTemplate==entities[10].roadTemplate)
  assert(e.comp.roadStyle=="custom_style" and e.comp.laneConfigs[1].catenary)
end
for i=1,4 do
  assert(p.edgesToAdd[i].comp.type=="BRIDGE" and p.edgesToAdd[i].comp.typeIndex==9)
  assert(p.edgesToAdd[i].comp.edgeDecorations[1][1]==42)
end
for _,e in ipairs(p.edgesToAdd) do
  assert(e.comp.node0>=0 or ids[e.comp.node0]);assert(e.comp.node1>=0 or ids[e.comp.node1])
end
assert(p.edgesToAdd[5].comp.node0==p.edgesToAdd[1].comp.node1)
assert(p.edgesToAdd[#p.edgesToAdd].comp.node1==p.edgesToAdd[3].comp.node1)
-- Splitting retains the exact source cubic, not a straight approximation.
for k=1,4 do
  local s=p.edgesToAdd[k].comp
  local lo=(k%2==1) and 0 or .35
  local hi=(k%2==1) and .35 or 1
  for i=0,10 do
    local pos=geometry.hermite({s.position0.x,s.position0.y,s.position0.z},{s.position1.x,s.position1.y,s.position1.z},
      {s.tangent0.x,s.tangent0.y,s.tangent0.z},{s.tangent1.x,s.tangent1.y,s.tangent1.z},i/10)
    assert(math.abs(pos[2]-(lo+(hi-lo)*i/10)*1000)<.001)
  end
end
entities[10].objects={{999,2}}
assert(not pcall(proposal.make,a,b,{extension=0,elevation=0,direction=1}))
assert(entities[10].objects[1][1]==999)
entities[10].objects={}
revision=2;assert(not pcall(proposal.make,a,b,{extension=0,elevation=0,direction=1}));revision=1
assert(not pcall(proposal.make,a,a,{extension=0,elevation=0,direction=1}))


local instances,recipes,logs={},{},{}
local scope,current,cursor="outside",nil,0
local states={Disabled="Disabled",Inactive="Inactive",Enabled="Enabled"}
local function unmount(name)
  if instances[name] then instances[name].alive=false end
end
local function renderInstance(name,context,fn)
  local instance=instances[name]
  if not instance or not instance.alive then instance={hooks={},alive=true};instances[name]=instance end
  instance.steps={};instance.actions={}
  current,cursor,scope=instance,0,context
  local result=fn()
  current,scope=nil,"outside"
  return result
end
local function stepAll()
  for _,name in ipairs({"registration","secondRegistration","tool"}) do
    local instance=instances[name]
    if instance and instance.alive then
      for _,fn in ipairs(instance.steps) do if instance.alive then fn() end end
    end
  end
end
local function ref(value)
  cursor=cursor+1
  if not current.hooks[cursor] then
    local owner=current
    current.hooks[cursor]={value=value,
      get=function(self) assert(owner.alive,"reading an expired ref");return self.value end,
      old=function(self) assert(owner.alive,"reading expired state");return self.value end,
      set=function(self,v) assert(owner.alive,"writing an expired ref");self.value=v end,
      hasExpired=function() return not owner.alive end}
  end
  return current.hooks[cursor]
end
local react={
  RegisterRecipe=function(name,fn)
    recipes[name]=fn
    return function(p) return {recipeName=name,params=p} end
  end,
  RegisterPluginRecipe=function(ep,name,fn) return function() return {recipeName=name} end end,
  useRef=ref,useState=ref,
  iaHandler=function(fn,enabled)
    return {fn=fn,state=function()
      local value=enabled and enabled()
      if type(value)=="boolean" then return value and states.Enabled or states.Inactive end
      return value or states.Enabled
    end}
  end,
  useInputAction=function(key,handler) current.actions[key]=handler end,
  onStep=function(fn) current.steps[#current.steps+1]=fn end,
}
local builtin={type={Orientation={Vertical=1,Horizontal=2},EdgeRenderable={Edge={new=function(shape)
  assert(shape.type=="CUBIC_SPLINE" and #shape.cubicSpline.pos==2 and #shape.cubicSpline.tangent==2)
  assert(shape.height and shape.tangent and shape.length>0 and shape.width>0)
  return {geometry=shape}
end}}}}
for _,name in ipairs({"Selector","ProposalViewer","ActionDescriptor","ActionTooltip","LayerConfig","EdgeRenderable"}) do
  builtin[name]=function(p)
    if name=="ActionDescriptor" then assert(scope=="ActionFn","Native descriptor must be a direct ActionFn child") end
    if name=="EdgeRenderable" then
      assert(#p.edges>0 and p.ignoreDepth)
      for _,e in ipairs(p.edges) do assert(#e.colors==2 and e.width>0 and e.stepSize>0) end
    end
    p.recipeName=name;return p
  end
end
local nativeDefinition={resName="selected_track",action="ACTION_TRACK_BUILDER_UPGRADER",params={
  {key="mode",values={"build","replace"},tooltips={"Build","Replace"},defaultIndex=1},
  {key="height",checkEnabledFn=function(p) return p.mode==1 and p.terrainMode==1 and "Enabled" or "Hidden" end,
    stepValueFn=function(value,direction) return value+direction end},
  {key="bend",checkEnabledFn=function(p) return p.mode==1 and "Enabled" or "Disabled" end},
  {key="terrainMode",checkEnabledFn=function() return "Enabled" end},
  {key="trackAlignToTerrain",checkEnabledFn=function() return "Enabled" end},
  {key="bridgeType"},{key="tunnelType"},{key="undergroundMode"},{key="disableSnapping"}}}
local cu={getTrackDefinitions=function() return {copy(nativeDefinition)} end,SimpleTooltipRecipe=function() end}
modules["::/gui/main/react.lua"]=react;modules["::/gui/main/builtin.lua"]=builtin
modules["::/gui/construction/construction_react_util.tl"]=cu
modules["::/gui/main/mod_entry_point.tl"]={ModEntryPointExtension={}}
ug_require=require;resolve=function(x) return x end;log={message=function(message) logs[#logs+1]=message end}
api.type.LayerConfig={new=function() return {} end}
api.type.Vec2f={new=function(x,y) return {x=x,y=y} end}
api.type.EdgeGeometry={Type={CUBIC_SPLINE="CUBIC_SPLINE"},new=function() return {cubicSpline={}} end}
api.gui.inputAction={InputActionState=states,modifierOnlyActionIsActive=function() return false end}
local terrainPosition
api.gui.mouse={Event={Type={Clicked="Clicked"}},hasTerrainPosition=function() return terrainPosition~=nil end,
  getTerrainPosition=function() return terrainPosition end}
api.res.streetTemplateRep={find=function() return 1 end,get=function() return {streetStyle="selected_style",laneConfigs={{catenary=false}}} end}
modules["xin_smooth_rail_loop_1::/rail_loop/dynamic_preview.lua"]=assert(loadfile(MOD.."/dynamic_preview.lua"))()
assert(loadfile(MOD.."/dynamic_tool.script.lua"))()
local def=cu.getTrackDefinitions()[1]
assert(def.action=="ACTION_TRACK_BUILDER_UPGRADER" and #def.params==#nativeDefinition.params)
assert(#def.params[1].values==3 and def.params[1].stepValueFn(3,1)==1)
assert(def.params[2].checkEnabledFn({mode=3,terrainMode=2})=="Enabled")
assert(def.params[4].checkEnabledFn({mode=3})=="Disabled")
assert(def.params[2].checkEnabledFn({mode=2,terrainMode=1})=="Hidden")
local options={mode=3,height=0,bend=0,terrainMode=1,bridgeType=7,tunnelType=8,undergroundMode=2}
local bound,secondBound,abortCalls
abortCalls=0
-- Toolbar and Default stores differ. Mouse abort does not change mode/isActive.
local toolbar={getCurrentParams=function() return options end}
function toolbar.getParamByKey(key)
  for i,param in ipairs(def.params) do
    if param.key==key then return {index=i,param=param,value=options[key]} end
  end
end
function toolbar.changeParam(index,value)
  local param=def.params[index]
  local old=options[param.key];options[param.key]=value
  -- Native updateActionWithNewParams precedes onChangeFn.
  stepAll()
  if param.onChangeFn then param.onChangeFn(value,toolbar,old) end
end
def.params[1].onChangeFn(3,toolbar,1)
local ctx={definition=def,isActive=true,getCurrentParams=function() return {} end,
  abort=function() abortCalls=abortCalls+1 end,
  setActionFn=function(fn) bound=fn;if not fn then unmount("tool") end end}
renderInstance("registration","recipe",function() recipes.XinNativeRailLoopMode(ctx) end)
assert(bound)
local secondDef=cu.getTrackDefinitions()[1];secondDef.resName="second_track"
renderInstance("secondRegistration","recipe",function()
  recipes.XinNativeRailLoopMode({definition=secondDef,isActive=true,getCurrentParams=function() return {} end,
    setActionFn=function(fn) secondBound=fn end})
end)
assert(secondBound,"Loop mode must follow the toolbar when switching track types")
local function render()
  assert(bound)
  return renderInstance("tool","ActionFn",bound)
end
local function find(action,name)
  for _,c in ipairs(action.children) do if c.recipeName==name then return c end end
end
local function input(key) return instances.tool.actions[key] end
local function enabled(key) return input(key).state()==states.Enabled end
local function twoPoints()
  local action=render();local selector=find(action,"Selector")
  selector.onProcessMouseEvent({x=0,y=350});selector.onSelect(10)
  action=render();selector=find(action,"Selector")
  selector.onProcessMouseEvent({x=5,y=350});selector.onSelect(20)
  return render()
end
local function checked(preview,critical,messages,cost)
  preview.onCreateProposalData({costs=cost or 123,errorState={critical=critical,messages=messages or {},
    warnings={"test warning"},infos={}},collisionInfo={collisionEntities={{entity=10}}}},
    {proposal={addedSegments=preview.simpleProposal.streetProposal.edgesToAdd}})
end

-- With no picks, Escape explicitly leaves mode 3; false would consume the key.
local action=render();assert(enabled("IA_CLOSE_TOPMOST_WINDOW"))
local oldBack=input("IA_CLOSE_TOPMOST_WINDOW")
oldBack.fn();assert(options.mode==1 and bound==nil and secondBound==nil and abortCalls==0)
assert(oldBack.state()==states.Disabled)
for _=1,3 do stepAll();assert(bound==nil) end
toolbar.changeParam(1,3);stepAll();assert(bound)
-- One pick: cancel stays in loop mode and starts over.
action=render();local selector=find(action,"Selector")
selector.onProcessMouseEvent({x=0,y=350});selector.onSelect(10)
action=render();input("IA_ABORT").fn()
action=render();assert(options.mode==3 and #action.highlightedEntities==0)

-- Before any native callback, an independent rail outline is already visible.
action=twoPoints();local preview=find(action,"ProposalViewer")
assert(preview and not enabled("IA_APPLY"))
local outline=find(action,"EdgeRenderable");assert(outline and #outline.edges>2)
assert(outline.edges[1].colors[1][3]==1)
local left,right=outline.edges[1].geometry,outline.edges[2].geometry
assert(math.abs(left.cubicSpline.pos[1].x-right.cubicSpline.pos[1].x-1.5)<1e-6)
assert(math.abs(left.cubicSpline.pos[1].y-350)<.001 and left.height.x==0)
for i=1,#outline.edges-2 do
  local ending=outline.edges[i].geometry.cubicSpline.pos[2]
  local starting=outline.edges[i+2].geometry.cubicSpline.pos[1]
  assert((ending.x-starting.x)^2+(ending.y-starting.y)^2<1e-10,"Rail outlines must remain continuous")
end
assert(preview.simpleProposal.streetProposal.edgesToAdd[5].comp.roadTemplate=="selected_track")
checked(preview,true,{"无法建造"},0)
action=render();assert(not enabled("IA_APPLY"))
assert(find(action,"ActionTooltip").param.cost==nil)
assert(find(action,"ActionTooltip").param.message.message:find("回环穿过保留的主线",1,true))
assert(find(action,"EdgeRenderable").edges[1].colors[1][1]==1)
assert(table.concat(logs,"\n"):find("Engine preview rejected:",1,true))
checked(preview,true,{},0)
action=render();assert(find(action,"EdgeRenderable") and not enabled("IA_APPLY"))
assert(find(action,"ActionTooltip").param.message.message:find("游戏拒绝",1,true))
checked(preview,false)
action=render();assert(enabled("IA_APPLY") and find(action,"ActionTooltip").param.cost==123)

-- Movement makes the old check pending, never an unexplained red/$0 failure.
terrainPosition={x=0,y=750}
find(action,"Selector").onProcessMouseEvent({x=0,y=350,type="Moved"})
action=render();assert(not enabled("IA_APPLY"))
assert(find(action,"ActionTooltip").param.cost==nil)
assert(find(action,"ActionTooltip").param.message.message:find("正在更新",1,true))
terrainPosition={x=0,y=350}
find(action,"Selector").onProcessMouseEvent({x=0,y=350,type="Moved"})
action=render();assert(enabled("IA_APPLY"),"Returning before the queued shape update must restore readiness")
terrainPosition=nil

-- A changed height invalidates old callbacks and updates rail heights/bridges.
local old=preview
options.height=8;stepAll();action=render();assert(not enabled("IA_APPLY"))
checked(old,false,{},1)
action=render();assert(not enabled("IA_APPLY"))
preview=find(action,"ProposalViewer");assert(preview)
local foundBridge,raisedOutline=false,false
for _,e in ipairs(preview.simpleProposal.streetProposal.edgesToAdd) do
  if e.comp.type=="BRIDGE" and e.comp.roadTemplate=="selected_track" then foundBridge=true;assert(e.comp.typeIndex==7) end
end
for _,e in ipairs(find(action,"EdgeRenderable").edges) do
  if e.geometry.height.x>7 then raisedOutline=true end
end
assert(foundBridge and raisedOutline)
checked(preview,true,{"collision"},500)
action=render();assert(not enabled("IA_APPLY"))
assert(not find(action,"ActionTooltip").param.message.message:find("高差不足",1,true))
checked(preview,false,{},500)
action=render();assert(enabled("IA_APPLY"));input("IA_APPLY").fn();assert(built)
action=render();assert(not find(action,"ProposalViewer") and not find(action,"EdgeRenderable"))
assert(find(action,"ActionTooltip").param.message.message:find("已建造",1,true))

-- Proposal assembly failure still leaves the independently generated rails.
options.height=0;entities[10].objects={{999,2}}
action=twoPoints();assert(not find(action,"ProposalViewer"))
assert(find(action,"EdgeRenderable") and find(action,"EdgeRenderable").edges[1].colors[1][1]==1)
terrainPosition={x=0,y=750};find(action,"Selector").onProcessMouseEvent({x=0,y=350,type="Moved"})
terrainPosition={x=0,y=350};find(action,"Selector").onProcessMouseEvent({x=0,y=350,type="Moved"})
terrainPosition=nil;action=render()
assert(find(action,"ActionTooltip").param.message.message:find("信号或路标",1,true))
action.onBack();entities[10].objects={}
action=render();assert(not find(action,"EdgeRenderable"))

-- Two-point Escape resets; a second Escape exits and late callbacks stay dead.
action=twoPoints();old=find(action,"ProposalViewer")
input("IA_CLOSE_TOPMOST_WINDOW").fn()
action=render();assert(options.mode==3 and not find(action,"ProposalViewer") and not find(action,"EdgeRenderable"))
checked(old,false);action=render();assert(not find(action,"EdgeRenderable"))
local oldSelector=find(action,"Selector")
input("IA_CLOSE_TOPMOST_WINDOW").fn()
assert(options.mode==1 and bound==nil)
checked(old,false);assert(not oldSelector.onProcessMouseEvent({type="Clicked",button=0}))
for _=1,3 do stepAll();assert(bound==nil) end

-- A running command is not cancelled midway; callbacks tolerate tool unmount.
toolbar.changeParam(1,3);stepAll()
action=twoPoints();checked(find(action,"ProposalViewer"),false)
action=render();local complete
api.cmd.sendCommand=function(cmd,callback) built=cmd.p;complete=callback end
input("IA_APPLY").fn();action=render()
assert(input("IA_CLOSE_TOPMOST_WINDOW").state()==states.Inactive)
action.onBack();assert(bound and options.mode==3)
toolbar.changeParam(1,1);assert(bound==nil)
complete({resultEntities={},proposal={proposal=built}},true)
print("PASS: native menu, independent failed-plan rail outlines, delayed previews, Escape/reset/exit, expired callbacks and construction lifecycle")
