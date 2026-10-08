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


local hooks,steps,recipes,actions={},{},{},{}
local cursor,context=0,"module"
local react={RegisterRecipe=function(name,fn)
  recipes[name]=fn
  return function(p) return {recipeName=name,params=p} end
end,
  RegisterPluginRecipe=function(ep,name,fn) return function() return {recipeName=name} end end,
  useRef=function(value)
    cursor=cursor+1
    if not hooks[cursor] then hooks[cursor]={value=value,get=function(self) return self.value end,
      set=function(self,v) self.value=v end,hasExpired=function() return false end} end
    return hooks[cursor]
  end,
  useState=function(value)
    cursor=cursor+1
    if not hooks[cursor] then hooks[cursor]={value=value,old=function(self) return self.value end,set=function(self,v) self.value=v end} end
    return hooks[cursor]
  end,
  iaHandler=function(fn,enabled) return {fn=fn,enabled=enabled} end,
  useInputAction=function(key,handler) actions[key]=handler end,
  onStep=function(fn) steps={fn} end}
local builtin={type={Orientation={Vertical=1,Horizontal=2}}}
for _,name in ipairs({"Selector","ProposalViewer","ActionDescriptor","ActionTooltip","LayerConfig"}) do
  builtin[name]=function(p)
    if name=="ActionDescriptor" then assert(context=="ActionFn","Native descriptor must be a direct ActionFn child") end
    p.recipeName=name;return p
  end
end
local nativeDefinition={resName="selected_track",action="ACTION_TRACK_BUILDER_UPGRADER",params={
  {key="mode",values={"build","replace"},tooltips={"Build","Replace"},defaultIndex=1},
  {key="height",checkEnabledFn=function(p) return p.mode==1 and p.terrainMode==1 and "Enabled" or "Hidden" end},
  {key="bend",checkEnabledFn=function(p) return p.mode==1 and "Enabled" or "Disabled" end},
  {key="terrainMode",checkEnabledFn=function() return "Enabled" end},
  {key="trackAlignToTerrain",checkEnabledFn=function() return "Enabled" end},
  {key="bridgeType"},{key="tunnelType"},{key="undergroundMode"},{key="disableSnapping"}}}
local cu={getTrackDefinitions=function() return {copy(nativeDefinition)} end,SimpleTooltipRecipe=function() end}
modules["::/gui/main/react.lua"]=react;modules["::/gui/main/builtin.lua"]=builtin
modules["::/gui/construction/construction_react_util.tl"]=cu
modules["::/gui/main/mod_entry_point.tl"]={ModEntryPointExtension={}}
ug_require=require;resolve=function(x) return x end;log={message=function() end}
api.type.LayerConfig={new=function() return {} end}
api.gui.mouse={Event={Type={Clicked="Clicked"}},hasTerrainPosition=function() return false end}
api.res.streetTemplateRep={find=function() return 1 end,get=function() return {streetStyle="selected_style",laneConfigs={{catenary=false}}} end}
assert(loadfile(MOD.."/dynamic_tool.script.lua"))()
local def=cu.getTrackDefinitions()[1]
assert(def.action=="ACTION_TRACK_BUILDER_UPGRADER" and #def.params==#nativeDefinition.params)
assert(#def.params[1].values==3 and def.params[1].stepValueFn(3,1)==1)
assert(def.params[2].checkEnabledFn({mode=3,terrainMode=2})=="Enabled")
assert(def.params[4].checkEnabledFn({mode=3})=="Disabled")
assert(def.params[2].checkEnabledFn({mode=2,terrainMode=1})=="Hidden")
local options={mode=3,height=0,bend=0,terrainMode=1,bridgeType=7,tunnelType=8,undergroundMode=2}
local bound
-- Default and Toolbar parameter stores are distinct in the real menu.
local toolbar={getCurrentParams=function() return options end}
def.params[1].onChangeFn(3,toolbar,1)
local ctx={definition=def,isActive=true,getCurrentParams=function() return {} end,abort=function() end,
  setActionFn=function(fn) bound=fn end}
recipes.XinNativeRailLoopMode(ctx)
assert(bound)
-- Changing track tiles preserves Toolbar values without another onChangeFn.
local secondDef=cu.getTrackDefinitions()[1];secondDef.resName="second_track"
local secondBound
hooks={};cursor=0
recipes.XinNativeRailLoopMode({definition=secondDef,isActive=true,getCurrentParams=function() return {} end,
  setActionFn=function(fn) secondBound=fn end})
assert(secondBound,"Loop mode must follow the toolbar when switching track types")
hooks={}
local function render()
  cursor=0;context="ActionFn";local result=bound();context="outside"
  assert(result.recipeName=="ActionDescriptor")
  return result
end
local function find(action,name)
  for _,c in ipairs(action.children) do if c.recipeName==name then return c end end
end
local action=render();local selector=find(action,"Selector")
selector.onProcessMouseEvent({x=0,y=350});selector.onSelect(10,nil,nil)
action=render();selector=find(action,"Selector")
selector.onProcessMouseEvent({x=5,y=350});selector.onSelect(20,nil,nil)
action=render();local preview=find(action,"ProposalViewer")
assert(preview and not actions.IA_APPLY.enabled())
preview.onCreateProposalData({costs=123,errorState={critical=false,messages={}}})
action=render();assert(actions.IA_APPLY.enabled())
assert(preview.simpleProposal.streetProposal.edgesToAdd[5].comp.roadTemplate=="selected_track")
local old=preview
options.height=8;steps[1]();action=render()
assert(not actions.IA_APPLY.enabled())
old.onCreateProposalData({costs=1,errorState={critical=false,messages={}}})
action=render();assert(not actions.IA_APPLY.enabled())
preview=find(action,"ProposalViewer");assert(preview)
local foundBridge=false
for _,e in ipairs(preview.simpleProposal.streetProposal.edgesToAdd) do
  if e.comp.type=="BRIDGE" and e.comp.roadTemplate=="selected_track" then
    foundBridge=true;assert(e.comp.typeIndex==7)
  end
end
assert(foundBridge)
preview.onCreateProposalData({costs=500,errorState={critical=true,messages={"collision"}}})
action=render();assert(not actions.IA_APPLY.enabled())
preview.onCreateProposalData({costs=500,errorState={critical=false,messages={}}})
action=render();assert(actions.IA_APPLY.enabled());actions.IA_APPLY.fn();assert(built)
action=render();assert(not find(action,"ProposalViewer"))
assert(find(action,"ActionTooltip").param.message.message:find("已建造"))
-- Empty-ground left click confirms only a validated two-point proposal.
built=nil;options.height=0
selector=find(action,"Selector");selector.onProcessMouseEvent({x=0,y=350,type="Moved"});selector.onSelect(10)
action=render();selector=find(action,"Selector")
assert(not selector.onProcessMouseEvent({x=5,y=350,type="Clicked",button=0}))
selector.onSelect(20)
action=render();selector=find(action,"Selector")
assert(selector.onProcessMouseEvent({type="Clicked",button=0}) and not built)
preview=find(action,"ProposalViewer");preview.onCreateProposalData({costs=1,errorState={critical=false,messages={}}})
action=render();selector=find(action,"Selector")
assert(selector.onProcessMouseEvent({type="Clicked",button=0}) and built)
hooks={};cursor=0;options.mode=1
recipes.XinNativeRailLoopMode(ctx);assert(bound==nil)
print("PASS: native menu keeps original parameter keys, mode fallback, direct ActionFn descriptor, native height/track/bridge selection, preview/confirmation lifecycle, shared junctions and object guard")
