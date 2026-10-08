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
local baseNodes,constructionOwners,constructions={},{},{}
for _,value in pairs(entities) do
  baseNodes[value.node0]={position=value.position0}
  baseNodes[value.node1]={position=value.position1}
end
local revision=1
local revisions,networks={},{}
local enum={RoadType={TRACK="TRACK"},BaseEdgeType={NORMAL="NORMAL",BRIDGE="BRIDGE",TUNNEL="TUNNEL"},
  ScriptParamType={Slider="Slider",ComboBox="ComboBox",Button="Button"},
  ScriptParamLocation={Default=1},ScriptParamDisplayMode={Horizontal=1}}
local components={BASE_EDGE="BASE_EDGE",BASE_NODE="BASE_NODE",CONSTRUCTION="CONSTRUCTION",PLAYER_OWNED="PLAYER_OWNED",TRANSPORT_NETWORK="TRANSPORT_NETWORK"}
local built,previewCallbacks=nil,{}
api={type={enum=enum,ComponentType=components,
    Vec3f={new=v3},Vec4f={new=function(...) return {...} end},EdgePos={new=copy},
    SimpleProposal={new=function() return {streetProposal={}} end},
    NodeAndEntity={new=function() return {comp={}} end},SegmentAndEntity={new=function() return {comp={}} end},
    Context={new=function() return {} end}},
  engine={entityExists=function(id) return entities[id]~=nil or baseNodes[id]~=nil or constructions[id]~=nil end,
    getRevision=function(id) return {num={revisions[id] or revision,0,0}} end,
    getComponent=function(id,kind)
      if kind=="BASE_EDGE" then return entities[id] end
      if kind=="PLAYER_OWNED" then return {player=1} end
      if kind=="TRANSPORT_NETWORK" then return networks[id] end
      if kind=="BASE_NODE" then return baseNodes[id] end
      if kind=="CONSTRUCTION" then return constructions[id] end
    end,
    system={streetConnectorSystem={getConstructionEntityForEdge=function(id) return constructionOwners[id] or -1 end}},
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
local description=proposal.describe(out,{proposal={addedNodes=p.nodesToAdd,addedSegments=p.edgesToAdd}},a,b)
assert(description:find("duplicateIds=0 missingNodes=0 endpointGaps=0 zeroTangents=0",1,true))
local badGraph=copy(out)
badGraph.streetProposal.edgesToAdd[1].comp.position0.x=badGraph.streetProposal.edgesToAdd[1].comp.position0.x+3
assert(proposal.describe(badGraph,nil,a,b):find("endpointGaps=1",1,true))
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
constructions[700]={};constructionOwners[10]=700
assert(proposal.pickProblem(a):find("车站或建筑",1,true))
assert(not pcall(proposal.make,a,b,{extension=0,elevation=0,direction=1}))
local stationEnd=proposal.pick(10,nil,{x=0,y=0})
assert(proposal.pickProblem(stationEnd)==nil,"Existing station endpoints must remain usable")
constructionOwners[10]=nil;constructions[700]=nil
revision=2;assert(not pcall(proposal.make,a,b,{extension=0,elevation=0,direction=1}));revision=1
assert(not pcall(proposal.make,a,a,{extension=0,elevation=0,direction=1}))

-- Centreline picks stay under the cursor; only near-exact node hits snap.
local nearStart=proposal.pick(10,nil,{x=0,y=.1},true)
assert(nearStart.u==0 and nearStart.snapped)
local unsnapped=proposal.resnap(nearStart,false)
assert(math.abs(unsnapped.p[2]-.1)<.001 and not unsnapped.snapped)
assert(proposal.pick(10,nil,{x=0,y=999.9},true).u==1)
assert(math.abs(proposal.pick(10,nil,{x=0,y=7},true).p[2]-7)<.001)
assert(math.abs(proposal.pick(10,nil,{x=0,y=993},true).p[2]-993)<.001)
local middle=proposal.pick(10,nil,{x=.9,y=500},true)
assert(middle.p[1]==0 and math.abs(middle.p[2]-500)<.001)
assert(proposal.pick(10,nil,{x=0,y=20},true).u>0)
assert(proposal.pick(10,nil,{x=0,y=0},false).u==0)
assert(proposal.pick(10,nil,{x=0,y=1000},false).u==1)
entities[10].objects={{999,2}}
assert(proposal.pickProblem(nearStart)==nil and proposal.pickProblem(unsnapped))
entities[10].objects={}

-- A transport-network subedge parameter is not the BASE_EDGE parameter.
networks[20]={edges={{geometry={calcPos=function(self,u) return {v3(5,200+400*u,0)} end}}}}
local nativeDetails={data={kind=1,snap={edgeId={entity=20,index=0},param=.375}}}
local nativePoint=proposal.pick(20,nativeDetails,{x=500,y=900},false)
assert(nativePoint.nativeSnap and math.abs(nativePoint.u-.35)<1e-6)


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
-- GUI parameter constructors do not promise readable or prefilled fields.
-- Only the native consumer can inspect these write-only parameter objects.
local nativeParams=setmetatable({}, {__mode="k"})
local function newNativeParams(...)
  local result={};nativeParams[result]={}
  return setmetatable(result,{__index=function() return nil end,
    __newindex=function(self,key,value) nativeParams[self][key]=value end})
end
local builtin={type={Orientation={Vertical=1,Horizontal=2},EdgeRenderable={Edge={new=newNativeParams}}}}
builtin.type.ControlPointInfo={State={Invalid="Invalid",Hover="Hover",Idle="Idle",IdleOverEdge="IdleOverEdge"},
  new=newNativeParams}
for _,name in ipairs({"Selector","ProposalViewer","ActionDescriptor","ActionTooltip","LayerConfig","EdgeRenderable"}) do
  builtin[name]=function(p)
    if name=="ActionDescriptor" then
      assert(scope=="ActionFn","Native descriptor must be a direct ActionFn child")
      assert(#p.highlightedEntities==0,"Point selection must not highlight entire rail segments")
      local counts={}
      local function collect(node)
        if node.recipeName=="ProposalViewer" or node.recipeName=="EdgeRenderable" then
          counts[node.recipeName]=(counts[node.recipeName] or 0)+1
          assert(counts[node.recipeName]<=1,"Must not specify more than 1 "..node.recipeName)
        end
        for _,child in ipairs(node.children or {}) do collect(child) end
      end
      collect(p)
    end
    if name=="Selector" then
      assert(p.selectionColor[4]==0 and p.selectionOutlineColor[4]==0 and p.selectionOutlineColor1[4]==0,
        "Hovering a pick point must not highlight the rail entity")
    end
    if name=="EdgeRenderable" then
      assert(#p.edges>0 and p.ignoreDepth)
      local converted={}
      for _,opaque in ipairs(p.edges) do
        local e=assert(nativeParams[opaque],"Expected a native edge parameter object")
        assert(e.geometry and e.geometry.type=="CUBIC_SPLINE","Missing explicit preview geometry")
        assert(#e.colors==2 and e.width>0 and e.stepSize>0)
        converted[#converted+1]=e
      end
      p.edges=converted
    elseif name=="ProposalViewer" and p.controlPointInfo then
      local cp=assert(nativeParams[p.controlPointInfo])
      assert(cp.position and cp.offsetZ==0.25 and cp.radius==2.5,"Missing explicit control-point fields")
      assert(cp.state=="IdleOverEdge" or cp.state=="Idle" or cp.state=="Invalid")
      p.controlPointInfo=cp
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
-- A native nested-value getter may return a copy. Ordinary Lua tables hid
-- lost spline writes in the original preview tests.
api.type.EdgeGeometry={Type={CUBIC_SPLINE="CUBIC_SPLINE"},CubicSpline={new=function() return {} end},new=function()
  local values={cubicSpline={pos={v3(0,0,0),v3(0,0,0)},tangent={v3(0,0,0),v3(0,0,0)}}}
  local function calcPos(self,u)
    local c=values.cubicSpline
    local p,t,dd=geometry.hermite(
      {c.pos[1].x,c.pos[1].y,values.height.x},{c.pos[2].x,c.pos[2].y,values.height.y},
      {c.tangent[1].x,c.tangent[1].y,values.tangent.x},{c.tangent[2].x,c.tangent[2].y,values.tangent.y},u)
    return {v3(table.unpack(p)),v3(table.unpack(t)),v3(table.unpack(dd))}
  end
  return setmetatable({}, {
    __index=function(_,key) if key=="calcPos" then return calcPos end;return copy(values[key]) end,
    __newindex=function(_,key,value) values[key]=copy(value) end,
  })
end}
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
  for _,c in ipairs(action.children) do
    if c.recipeName==name and (name~="ProposalViewer" or c.onCreateProposalData) then return c end
  end
end
local function markers(action)
  local result={}
  local batch=find(action,"EdgeRenderable")
  local ring={}
  for _,edge in ipairs(batch and batch.edges or {}) do
    if edge.width==0.65 then
      ring[#ring+1]=edge.geometry
      if #ring==4 then
        local x,y,z=0,0,0
        for _,shape in ipairs(ring) do
          local p=shape.cubicSpline.pos[1]
          x=x+p.x;y=y+p.y;z=z+shape.height.x
        end
        result[#result+1]={position=v3(x/4,y/4,z/4),state="Idle"}
        ring={}
      end
    end
  end
  assert(#ring==0,"Fixed point marks must be complete rings")
  for _,c in ipairs(action.children) do if c.controlPointInfo then result[#result+1]=c.controlPointInfo end end
  return result
end
local function lockedCount(action)
  local count=0
  for _,point in ipairs(markers(action)) do if point.state=="Idle" then count=count+1 end end
  return count
end
local function railEdges(action)
  local result={}
  local batch=find(action,"EdgeRenderable")
  for _,edge in ipairs(batch and batch.edges or {}) do if edge.width==1 then result[#result+1]=edge end end
  return result
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
    {proposal={addedNodes=preview.simpleProposal.streetProposal.nodesToAdd,addedSegments=preview.simpleProposal.streetProposal.edgesToAdd}})
end

-- With no picks, Escape explicitly leaves mode 3; false would consume the key.
local action=render();assert(enabled("IA_CLOSE_TOPMOST_WINDOW"))
local oldBack=input("IA_CLOSE_TOPMOST_WINDOW")
oldBack.fn();assert(options.mode==1 and bound==nil and secondBound==nil and abortCalls==0)
assert(oldBack.state()==states.Disabled)
for _=1,3 do stepAll();assert(bound==nil) end
toolbar.changeParam(1,3);stepAll();assert(bound)
-- Hover markers, endpoint snapping, and toggling snapping without moving.
action=render();local selector=find(action,"Selector")
selector.onProcessMouseEvent({x=0,y=.1,type="Moved"});selector.onHover(10)
action=render();assert(#markers(action)==1 and markers(action)[1].position.y==0)
assert(markers(action)[1].state=="IdleOverEdge" and enabled("IA_APPLY"))
options.disableSnapping=2;stepAll();action=render()
assert(math.abs(markers(action)[1].position.y-.1)<.001)
input("IA_APPLY").fn();action=render()
assert(#markers(action)==1 and markers(action)[1].state=="Idle")
local firstY=markers(action)[1].position.y
-- Native hover fires again immediately after fixing the first point. This
-- must remain a single ProposalViewer, including an invalid same-rail hover.
find(action,"Selector").onHover(10);action=render()
assert(#markers(action)==2 and lockedCount(action)==1)
local repeatSize=#find(action,"EdgeRenderable").edges
for _=1,5 do action=render();assert(#find(action,"EdgeRenderable").edges==repeatSize) end
find(action,"Selector").onHover(nil);action=render()
options.disableSnapping=1;stepAll();action=render()
assert(markers(action)[1].position.y==firstY,"Locked points must not move with snapping settings")
action=render();input("IA_ABORT").fn()
action=render();assert(options.mode==3 and lockedCount(action)==0 and #markers(action)==0)

-- The second native hit previews the loop before clicking, even when its
-- transport-network parameter differs from the BASE_EDGE parameter.
selector=find(action,"Selector");selector.onProcessMouseEvent({x=0,y=350});selector.onHover(10)
action=render();assert(math.abs(markers(action)[1].position.y-350)<.001)
find(action,"Selector").onSelect(10);action=render()
selector=find(action,"Selector");selector.onProcessMouseEvent({x=500,y=900});selector.onHover(20,nil,nativeDetails)
action=render();local hovering=find(action,"ProposalViewer")
assert(hovering and find(action,"EdgeRenderable") and #markers(action)==2)
assert(math.abs(markers(action)[2].position.y-350)<.001)
checked(hovering,false);action=render();assert(enabled("IA_APPLY") and built==nil)
input("IA_APPLY").fn();action=render()
assert(lockedCount(action)==2 and built==nil and not enabled("IA_APPLY"),"Fixing the second point must not build")
checked(hovering,false,{},1);action=render();assert(not enabled("IA_APPLY"))
input("IA_ABORT").fn();action=render();assert(#markers(action)==1)
input("IA_ABORT").fn();action=render();assert(#markers(action)==0)

-- Before any native callback, an independent rail outline is already visible.
action=twoPoints();local preview=find(action,"ProposalViewer")
assert(preview and not enabled("IA_APPLY"))
local outline=find(action,"EdgeRenderable");assert(outline and #outline.edges>2)
assert(outline.edges[1].colors[1][3]==1)
assert(table.concat(logs,"\n"):find("Rail outline geometry checked:",1,true))
local left,right=outline.edges[1].geometry,outline.edges[2].geometry
assert(math.abs(left.cubicSpline.pos[1].x-right.cubicSpline.pos[1].x-1.5)<1e-6)
assert(math.abs(left.cubicSpline.pos[1].y-350)<.001 and left.height.x==0)
local rails=railEdges(action)
for i=1,#rails-2 do
  local ending=rails[i].geometry.cubicSpline.pos[2]
  local starting=rails[i+2].geometry.cubicSpline.pos[1]
  assert((ending.x-starting.x)^2+(ending.y-starting.y)^2<1e-10,"Rail outlines must remain continuous")
end
local batchSize=#outline.edges
for _=1,5 do action=render();assert(#find(action,"EdgeRenderable").edges==batchSize) end
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
find(action,"Selector").onProcessMouseEvent({x=0,y=350,type="Moved",handled=true})
action=render();assert(enabled("IA_APPLY"),"Toolbar mouse movement must not stretch the loop")
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
options.height=8;assert(not enabled("IA_APPLY"));input("IA_APPLY").fn();assert(built==nil)
stepAll();action=render();assert(not enabled("IA_APPLY"))
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

-- Moving a candidate, leaving the track, and track edits invalidate stale
-- checks but keep the first locked point.
built=nil;options.height=0
selector=find(action,"Selector");selector.onProcessMouseEvent({x=0,y=350});selector.onSelect(10)
action=render();selector=find(action,"Selector")
selector.onProcessMouseEvent({x=5,y=350});selector.onHover(20)
action=render();local candidateA=find(action,"ProposalViewer");checked(candidateA,false)
selector=find(action,"Selector");selector.onProcessMouseEvent({x=5,y=450});selector.onHover(20)
checked(candidateA,false,{},1)
for _=1,4 do stepAll() end
action=render();local candidateB=find(action,"ProposalViewer")
assert(candidateB and candidateA.proposalId~=candidateB.proposalId)
checked(candidateB,false,{},222);checked(candidateA,true,{"stale failure"},0)
action=render();assert(find(action,"ActionTooltip").param.cost==222)
assert(math.abs(markers(action)[2].position.y-450)<.001 and built==nil)
find(action,"Selector").onProcessMouseEvent({x=200,y=350,type="Moved"})
action=render();assert(#markers(action)==1 and not find(action,"EdgeRenderable"))
find(action,"Selector").onHover(nil);checked(candidateB,false)
action=render();assert(#markers(action)==1 and not find(action,"EdgeRenderable"))
assert(not enabled("IA_APPLY") and find(action,"ActionTooltip").param.cost==nil)
selector=find(action,"Selector");selector.onProcessMouseEvent({x=5,y=350});selector.onHover(20)
action=render();old=find(action,"ProposalViewer")
revisions[20]=2;stepAll();checked(old,false)
action=render();assert(#markers(action)==1 and lockedCount(action)==1 and not find(action,"ProposalViewer"))
revisions[20]=nil

-- Invalid second points still have a visible marker and red outline, but
-- cannot be locked or sent to construction.
selector=find(action,"Selector");selector.onProcessMouseEvent({x=0,y=400});selector.onHover(10)
action=render();assert(markers(action)[2].state=="Invalid" and not enabled("IA_APPLY"))
assert(not find(action,"ProposalViewer"))
entities[20].objects={{999,2}}
selector=find(action,"Selector");selector.onProcessMouseEvent({x=5,y=350});selector.onHover(20)
action=render();assert(not find(action,"ProposalViewer"))
assert(markers(action)[2].state=="Invalid" and not enabled("IA_APPLY"))
assert(find(action,"EdgeRenderable") and find(action,"EdgeRenderable").edges[1].colors[1][1]==1)
find(action,"Selector").onSelect(20);action=render();assert(lockedCount(action)==1)
assert(find(action,"ActionTooltip").param.message.message:find("信号或路标",1,true))
action.onBack();entities[20].objects={}
action=render();assert(not find(action,"EdgeRenderable"))

-- Every cancel route walks back 2 -> 1 -> 0. Pending length changes and old
-- callbacks cannot reintroduce the discarded second point.
local cancelCases={
  function(a) input("IA_ABORT").fn() end,
  function(a) input("IA_CLOSE_TOPMOST_WINDOW").fn() end,
  function(a) find(a,"Selector").onProcessMouseEvent({type="Clicked",button=2}) end,
  function(a) find(a,"Selector").onSelectSecondary() end,
  function(a) a.onBack() end,
}
for _,cancel in ipairs(cancelCases) do
  action=twoPoints();old=find(action,"ProposalViewer");checked(old,false)
  terrainPosition={x=0,y=750};find(action,"Selector").onProcessMouseEvent({x=0,y=350,type="Moved"})
  cancel(action);terrainPosition=nil;checked(old,false)
  for _=1,4 do stepAll() end
  action=render();assert(#markers(action)==1 and lockedCount(action)==1 and not find(action,"EdgeRenderable"))
  assert(math.abs(markers(action)[1].position.y-350)<.001)
  cancel(action);action=render();assert(#markers(action)==0 and lockedCount(action)==0 and options.mode==3)
end

action=twoPoints();revisions[20]=2;stepAll();action=render()
assert(#markers(action)==1 and lockedCount(action)==1 and not find(action,"ProposalViewer"))
revisions[20]=nil;action.onBack();action=render();assert(#markers(action)==0)

-- Three Escapes from two points exit; late callbacks remain dead.
action=twoPoints();old=find(action,"ProposalViewer")
input("IA_CLOSE_TOPMOST_WINDOW").fn()
action=render();assert(options.mode==3 and #markers(action)==1 and not find(action,"ProposalViewer"))
checked(old,false);action=render();assert(not find(action,"EdgeRenderable"))
input("IA_CLOSE_TOPMOST_WINDOW").fn();action=render();assert(#markers(action)==0)
local oldSelector=find(action,"Selector")
input("IA_CLOSE_TOPMOST_WINDOW").fn()
assert(options.mode==1 and bound==nil)
checked(old,false);assert(not oldSelector.onProcessMouseEvent({type="Clicked",button=0}))
for _=1,3 do stepAll();assert(bound==nil) end

-- A running command is not cancelled midway; callbacks tolerate tool unmount.
toolbar.changeParam(1,3);stepAll()
action=render();selector=find(action,"Selector")
selector.onProcessMouseEvent({x=0,y=350});selector.onSelect(10)
revisions[10]=2;stepAll();action=render();assert(#markers(action)==0 and lockedCount(action)==0)
revisions[10]=nil
action=twoPoints();checked(find(action,"ProposalViewer"),false)
action=render();local complete
api.cmd.sendCommand=function(cmd,callback) built=cmd.p;complete=callback end
input("IA_APPLY").fn();action=render()
assert(input("IA_CLOSE_TOPMOST_WINDOW").state()==states.Inactive)
action.onBack();assert(bound and options.mode==3)
toolbar.changeParam(1,1);assert(bound==nil)
complete({resultEntities={},proposal={proposal=built}},true)
print("PASS: hover/snap markers, live second-point previews, progressive cancellation, stale callbacks, native parameters and guarded construction")
