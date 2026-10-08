local geometry = require "xin_smooth_rail_loop_1::/rail_loop/dynamic_geometry.lua"
local M = {}
local function vec(p) return api.type.Vec3f.new(p[1],p[2],p[3]) end
local function array(p) return {p.x,p.y,p.z} end
local function edgeData(edge)
  return array(edge.position0),array(edge.position1),array(edge.tangent0),array(edge.tangent1)
end
local function sample(edge,u)
  local p0,p1,t0,t1=edgeData(edge)
  return geometry.hermite(p0,p1,t0,t1,u)
end
local function revision(entity)
  local r=api.engine.getRevision(entity)
  return tostring(r.num[1])..":"..tostring(r.num[2])..":"..tostring(r.num[3])
end
function M.current(point)
  return point and api.engine.entityExists(point.entity) and revision(point.entity)==point.revision
end
function M.isTrack(entity)
  if not entity or not api.engine.entityExists(entity) then return false end
  local e=api.engine.getComponent(entity,api.type.ComponentType.BASE_EDGE)
  return e~=nil and e.roadType==api.type["enum"].RoadType.TRACK
end

function M.resnap(point,snapping)
  assert(M.current(point),"轨道已改变，请重新选点")
  local edge=api.engine.getComponent(point.entity,api.type.ComponentType.BASE_EDGE)
  local rawU=point.rawU or point.u
  local p=sample(edge,rawU)
  local u,best=rawU,math.huge
  if snapping~=false then
    for _,endpoint in ipairs({0,1}) do
      local q=sample(edge,endpoint)
      local distance=(p[1]-q[1])^2+(p[2]-q[2])^2+(p[3]-q[3])^2
      local close=distance<4
      if not close and distance<100 and point.mouse then
        local screen=api.gui.camera.world2Screen(vec(q))
        close=(screen.x-point.mouse.x)^2+(screen.y-point.mouse.y)^2<=64
      end
      if close and distance<best then u,best=endpoint,distance end
    end
  end
  local position,tangent=sample(edge,u)
  return {entity=point.entity,u=u,rawU=rawU,p=position,t=tangent,revision=point.revision,
    mouse=point.mouse,nativeSnap=point.nativeSnap,snapped=u==0 or u==1}
end

function M.pickProblem(point,first)
  if first and first.entity==point.entity then return "请选择另一条轨道上的连接点" end
  if point.u~=0 and point.u~=1 then
    local edge=api.engine.getComponent(point.entity,api.type.ComponentType.BASE_EDGE)
    if #edge.objects>0 then return "这段轨道带有信号或路标，请选择端点或旁边的轨道段" end
  end
end

function M.pick(entity,details,mouse,snapping)
  local target
  if details and details.data and details.data.kind==api.gui.SelectionDetails.Type.TransportNetworkEdge then
    local snap=api.type.EdgePos.new(details.data.snap)
    entity=snap.edgeId.entity
    local network=api.engine.getComponent(entity,api.type.ComponentType.TRANSPORT_NETWORK)
    local e=network and network.edges[snap.edgeId.index+1]
    if e then target=array(e.geometry:calcPos(snap.param)[1]) end
  end
  assert(M.isTrack(entity),"请点击普通铁路轨道")
  assert(target or (mouse and type(mouse.x)=="number" and type(mouse.y)=="number"),"请先把鼠标移到轨道上再点击")
  local edge=api.engine.getComponent(entity,api.type.ComponentType.BASE_EDGE)
  local function distance(u)
    local p=sample(edge,u)
    if target then return (p[1]-target[1])^2+(p[2]-target[2])^2+(p[3]-target[3])^2 end
    local s=api.gui.camera.world2Screen(vec(p))
    return (s.x-mouse.x)^2+(s.y-mouse.y)^2
  end
  local best,score=0,math.huge
  for i=0,64 do local d=distance(i/64);if d<score then best,score=i/64,d end end
  local lo,hi=math.max(0,best-1/64),math.min(1,best+1/64)
  for _=1,24 do
    local l,r=(2*lo+hi)/3,(lo+2*hi)/3
    if distance(l)<distance(r) then hi=r else lo=l end
  end
  local u=(lo+hi)/2
  -- The bounded search approaches an endpoint without landing exactly on it.
  -- Preserve an exact endpoint hit even when automatic snapping is disabled.
  if distance(0)<distance(u) then u=0 end
  if distance(1)<distance(u) then u=1 end
  local cursor=mouse and type(mouse.x)=="number" and type(mouse.y)=="number" and {x=mouse.x,y=mouse.y} or nil
  return M.resnap({entity=entity,u=u,rawU=u,revision=revision(entity),mouse=cursor,nativeSnap=target~=nil},snapping)
end

function M.make(a,b,options,segments,info)
  assert(M.current(a) and M.current(b),"选中的轨道已改变，请重新选点")
  assert(a.entity~=b.entity,"请在另一条轨道上选择第二个点")
  if not segments then segments,info=geometry.generate(a,b,options) end
  local proposal=api.type.SimpleProposal.new()
  local nodes,edges,removed={},{},{}
  local id=0
  local function nextId() id=id-1;return id end
  local function node(p)
    local n=api.type.NodeAndEntity.new();n.entity=nextId();n.comp.position=vec(p)
    nodes[#nodes+1]=n;return n.entity
  end
  local function edge(source,n0,n1,p0,p1,t0,t1,kind,typeIndex,owner)
    local e=api.type.SegmentAndEntity.new();e.entity=nextId();e.type=1
    e.comp=source:clone()
    e.comp.node0=n0;e.comp.node1=n1
    e.comp.position0=vec(p0);e.comp.position1=vec(p1)
    e.comp.tangent0=vec(t0);e.comp.tangent1=vec(t1)
    e.comp.objects={}
    e.comp.type=kind;e.comp.typeIndex=typeIndex
    local length,prev=0,p0
    for j=1,16 do
      local p=geometry.hermite(p0,p1,t0,t1,j/16)
      length=length+math.sqrt((p[1]-prev[1])^2+(p[2]-prev[2])^2+(p[3]-prev[3])^2);prev=p
    end
    e.comp.distance=length
    if owner then e.playerOwned=owner end
    edges[#edges+1]=e
    return e
  end
  local function attach(point)
    local old=api.engine.getComponent(point.entity,api.type.ComponentType.BASE_EDGE)
    if point.u==0 then return old.node0,old end
    if point.u==1 then return old.node1,old end
    -- Modern signal construction parameters cannot be faithfully reconstructed
    -- through SimpleProposal.EdgeObject. Never silently discard them.
    assert(#old.objects==0,"该轨道段上有信号或路标，请改选旁边不带信号的轨道段或已有端点")
    local n=node(point.p)
    local owner=api.engine.getComponent(point.entity,api.type.ComponentType.PLAYER_OWNED)
    local function part(lo,hi,n0,n1)
      local p0,t0=sample(old,lo);local p1,t1=sample(old,hi)
      for k=1,3 do t0[k]=t0[k]*(hi-lo);t1[k]=t1[k]*(hi-lo) end
      edge(old,n0,n1,p0,p1,t0,t1,old.type,old.typeIndex,owner)
    end
    part(0,point.u,old.node0,n);part(point.u,1,n,old.node1)
    removed[#removed+1]=point.entity
    return n,old
  end
  local start,source=attach(a)
  local finish,finishSource=attach(b)
  local function curve(component)
    local p0,p1,t0,t1=edgeData(component)
    return {p0=p0,p1=p1,t0=t0,t1=t1}
  end
  info.mainCrossings=geometry.mainTrackCrossings(segments,{curve(source),curve(finishSource)})
  -- Use the selected native track/bridge/tunnel resources, including mods.
  if options.trackTemplate then
    local index=api.res.streetTemplateRep.find(options.trackTemplate)
    assert(index>=0,"当前轨型不可用，请重新选择轨道")
    local template=api.res.streetTemplateRep.get(index)
    source=source:clone()
    source.roadTemplate=options.trackTemplate;source.roadStyle=template.streetStyle
    source.laneConfigs=template.laneConfigs
  end
  local bridge,tunnel=options.bridgeType,options.tunnelType
  local owner=api.engine.getComponent(a.entity,api.type.ComponentType.PLAYER_OWNED)
  local prev=start
  for i,s in ipairs(segments) do
    local n=i==#segments and finish or node(s.p1)
    if s.kind=="BRIDGE" then assert(bridge and bridge>=0,"请在原桥梁选项中选择桥型") end
    if s.kind=="TUNNEL" then assert(tunnel and tunnel>=0,"请在原隧道选项中选择隧道类型") end
    local typeIndex=s.kind=="BRIDGE" and bridge or (s.kind=="TUNNEL" and tunnel or 0)
    local e=edge(source,prev,n,s.p0,s.p1,s.t0,s.t1,api.type["enum"].BaseEdgeType[s.kind],typeIndex,owner)
    e.comp.edgeDecorations={}
    prev=n
  end
  proposal.streetProposal.nodesToAdd=nodes
  proposal.streetProposal.edgesToAdd=edges
  proposal.streetProposal.edgesToRemove=removed
  return proposal,info
end
return M
