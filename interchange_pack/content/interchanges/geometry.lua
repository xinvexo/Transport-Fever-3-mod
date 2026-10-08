-- Local +x is east, +y is north. One-way splines follow traffic.
-- Tags identify actual junctions; different levels never share a tag.
local M = {}
local roads = require "xin_interchange_pack_1::/interchanges/roads.lua"
local candidates = require "xin_interchange_pack_1::/interchanges/design_candidates.lua"
local settings = require "xin_interchange_pack_1::/interchanges/settings.lua"
local arms = { "W", "S", "E", "N" }
local function arm(r) return arms[r % 4 + 1] end
local function tag(r, part) return arm(r) .. ":" .. part end
local function armOffset(net,r)
  return net.branchD and r%2==1 and net.branchD or net.d
end
local function rot(p, r)
  r = r % 4
  if r == 1 then return { -p[2], p[1], p[3] } end
  if r == 2 then return { -p[1], -p[2], p[3] } end
  if r == 3 then return { p[2], -p[1], p[3] } end
  return { p[1], p[2], p[3] }
end
local function vec(x, y, z) return { x, y, z or 0 } end
local function length(p) return math.sqrt(p[1]^2 + p[2]^2) end
local function mul(v, s) return { v[1]*s, v[2]*s, v[3]*s } end
local function turn(t,degrees)
  local angle = math.rad(degrees)
  return vec(math.cos(angle)*t[1]-math.sin(angle)*t[2],
    math.sin(angle)*t[1]+math.cos(angle)*t[2],t[3])
end
local function enabled(params, prefix, index)
  local current = params[prefix .. "Enabled" .. index]
  if current ~= nil then return current == 2 end
  return params[prefix .. index] ~= 2 -- Older saved parameter values.
end

function M.sample(s, u)
  local a, b, c, d = 2*u^3-3*u^2+1, u^3-2*u^2+u, -2*u^3+3*u^2, u^3-u^2
  local p = {}
  for k = 1, 3 do p[k] = a*s.p0[k]+b*s.t0[k]+c*s.p1[k]+d*s.t1[k] end
  return p
end

local function road(net, id, from, to, role)
  local value = { id = id, from = from, to = to, role = role, segments = {} }
  net.roads[#net.roads + 1] = value
  return value
end

local function edge(path, p0, p1, t0, t1, tag0, tag1, bridge)
  path.segments[#path.segments + 1] = {
    p0 = p0, p1 = p1, t0 = t0, t1 = t1,
    tag0 = tag0, tag1 = tag1, bridge = bridge or false,
  }
end

local function straight(path, p0, p1, tag0, tag1, bridge)
  local t = vec(p1[1]-p0[1], p1[2]-p0[2])
  edge(path, p0, p1, t, t, tag0, tag1, bridge)
end

local function curve(path, p0, p1, dir0, dir1, tag0, tag1, bridge)
  local dist = length(vec(p1[1]-p0[1], p1[2]-p0[2]))
  local dot = math.max(-1, math.min(1, dir0[1]*dir1[1]+dir0[2]*dir1[2]))
  -- Circular 90-degree Hermite approximation; parallel ends use chord length.
  local scale = dot > 0.999 and dist or dist * 1.17157287525381
  edge(path, p0, p1, mul(dir0, scale), mul(dir1, scale), tag0, tag1, bridge)
end

local function rotateRoad(path, r)
  for _, s in ipairs(path.segments) do
    s.p0, s.p1, s.t0, s.t1 = rot(s.p0, r), rot(s.p1, r), rot(s.t0, r), rot(s.t1, r)
  end
end

local function mainline(net, r, h)
  local a, b, l, d = net.a, net.b, net.l, net.d
  local path = road(net, "main-" .. arm(r), arm(r), arm(r+2), "main")
  local xs = { -l, -a, -b, b, a, l }
  local zs = { 0, 0, h, h, 0, 0 }
  local tags = { tag(r,"external-in"), tag(r,"in"), tag(r,"before"),
    tag(r,"after"), tag(r,"out"), tag(r,"external-out") }
  if net.stagger and net.stagger>0 then
    xs = {-l,-a-net.stagger,-a,-b,b,a,a+net.stagger,l}
    zs = {0,0,0,h,h,0,0,0}
    tags = {tag(r,"external-in"),tag(r,"in"),tag(r,"left-in"),tag(r,"before"),
      tag(r,"after"),tag(r,"left-out"),tag(r,"out"),tag(r,"external-out")}
  end
  for i = 1,#xs-1 do
    straight(path, vec(xs[i],-d,zs[i]), vec(xs[i+1],-d,zs[i+1]), tags[i], tags[i+1], xs[i]==-b and xs[i+1]==b and h > 0)
  end
  rotateRoad(path, r)
end

local function branch(net)
  local d, a, l = net.branchD or net.d, net.a, net.l
  local incoming = road(net, "branch-in", "S", nil, "main")
  incoming.profile = "branch"
  straight(incoming, vec(d,-l), vec(d,-a), tag(1,"external-in"), tag(1,"in"))
  local outgoing = road(net, "branch-out", nil, "S", "main")
  outgoing.profile = "branch"
  straight(outgoing, vec(-d,-a), vec(-d,-l), tag(3,"out"), tag(3,"external-out"))
end

local function rightTurn(net, r)
  local a = net.a+(net.stagger or 0)
  local path = road(net, "right-" .. arm(r), arm(r), arm(r+1), "right")
  curve(path, vec(-a,-armOffset(net,r)), vec(-armOffset(net,r-1),-a), vec(1,0), vec(0,-1), tag(r,"in"), tag(r-1,"out"))
  rotateRoad(path, r)
end

local function loop(net, r, startHeight, endHeight, startTag, endTag)
  local b, d = net.b, net.d
  local radius = b-d
  local path = road(net, "loop-" .. arm(r), arm(r), arm(r-1), "loop")
  local z0, z1 = startHeight, endHeight
  -- Three quarter circles, clockwise: eastbound -> northbound after 270 degrees.
  for i = 0, 5 do
    local u0, u1 = i/6, (i+1)/6
    local theta0, theta1 = math.pi/2-u0*1.5*math.pi, math.pi/2-u1*1.5*math.pi
    local function point(theta, u)
      return vec(b+radius*math.cos(theta), -b+radius*math.sin(theta), z0+(z1-z0)*(3*u*u-2*u*u*u))
    end
    local k = 4*math.tan(math.pi/16)*radius
    local function tangent(theta, u)
      return vec(k*math.sin(theta), -k*math.cos(theta), (z1-z0)*6*u*(1-u)/6)
    end
    local p0, p1 = point(theta0,u0), point(theta1,u1)
    edge(path, p0, p1, tangent(theta0,u0), tangent(theta1,u1),
      i == 0 and startTag or nil, i == 5 and endTag or nil,
      math.min(p0[3],p1[3]) >= math.max(0,(z0+z1)/2) and math.min(p0[3],p1[3]) > 0)
  end
  -- Avoid round-off separating shared junctions.
  path.segments[1].p0 = vec(b,-d,z0)
  path.segments[6].p1 = vec(d,-b,z1)
  rotateRoad(path, r)
  return path
end

local function sharedLeaf(net, r)
  local design = net.design
  local h0, h1 = r % 2 == 0 and 0 or net.h, r % 2 == 0 and net.h or 0
  local full = loop(net, r, h0, h1, tag(r,"after"), tag(r+1,"before"))
  table.remove(net.roads) -- Reuse exact circle pieces; do not overlay a second road.
  -- Keep the adjacent opposing decks level. Rise/fall on the quarter-circle
  -- approaches, with horizontal tangents where they meet the shared deck.
  local deck = net.h/2
  for i,s in ipairs(full.segments) do
    local startHeight,endHeight,u0,u1
    if i <= 2 then
      startHeight,endHeight,u0,u1 = h0,deck,(i-1)/2,i/2
      s.bridge = h0 > deck
    elseif i >= 5 then
      startHeight,endHeight,u0,u1 = deck,h1,(i-5)/2,(i-4)/2
      s.bridge = h1 > deck
    else
      startHeight,endHeight,u0,u1 = deck,deck,0,1
      s.bridge = true
    end
    local delta = endHeight-startHeight
    s.p0[3] = startHeight+delta*(3*u0*u0-2*u0*u0*u0)
    s.p1[3] = startHeight+delta*(3*u1*u1-2*u1*u1*u1)
    s.t0[3],s.t1[3] = delta*3*u0*(1-u0),delta*3*u1*(1-u1)
    if (design.sharedGround and i>=3 and i<=4) or design.approachGround then s.bridge=false end
  end
  local a, b = "shared-" .. arm(r) .. ":start", "shared-" .. arm(r) .. ":end"
  local function lanePort(p,t,side)
    local offset = side*(design.portOffset or 2.5)/length(t)
    return vec(p[1]+offset*t[2],p[2]-offset*t[1],p[3])
  end
  -- One native two-way street: the loop uses its forward lane and the right
  -- turn its backward lane. Only the four approaches are one-way streets.
  local shared = road(net, "shared-" .. arm(r), nil, nil, "shared")
  shared.segments = { full.segments[3],full.segments[4] }
  shared.segments[1].tag0, shared.segments[2].tag1 = a, b
  local first,last = shared.segments[1],shared.segments[2]
  local angle = design.fork or 0
  full.segments[2].p1,full.segments[2].t1,full.segments[2].tag1 = lanePort(first.p0,first.t0,1),turn(first.t0,angle),a
  full.segments[5].p0,full.segments[5].t0,full.segments[5].tag0 = lanePort(last.p1,last.t1,1),turn(last.t1,-angle),b
  local entry = road(net, full.id, full.from, full.to, "loop")
  entry.segments = { full.segments[1], full.segments[2] }
  local exit = road(net, "loop-tail-" .. arm(r), nil, full.to, "loop_tail")
  exit.segments = { full.segments[5], full.segments[6] }
  local enter = road(net, "right-in-" .. arm(r+1), arm(r+1), nil, "right")
  local leave = road(net, "right-out-" .. arm(r+1), nil, arm(r+2), "right")
  local enterDirection,leaveDirection = mul(last.t1,-1/length(last.t1)),mul(first.t0,-1/length(first.t0))
  enterDirection,leaveDirection = turn(enterDirection,angle),turn(leaveDirection,-angle)
  curve(enter, rot(vec(net.d,-net.a),r), lanePort(last.p1,last.t1,-1), rot(vec(0,1),r), enterDirection, tag(r+1,"in"), b)
  curve(leave, lanePort(first.p0,first.t0,-1), rot(vec(net.a,-net.d),r), leaveDirection, rot(vec(1,0),r), a, tag(r,"out"))
end

local function archBridge(path, height, drop)
  local lengths,total = {},0
  for i = 2,#path.segments-1 do
    local previous,distance = M.sample(path.segments[i],0),0
    for j = 1,64 do
      local p = M.sample(path.segments[i],j/64)
      distance = distance+length(vec(p[1]-previous[1],p[2]-previous[2]))
      previous = p
    end
    lengths[i],total = distance,total+distance
  end
  local distance = 0
  local function altitude(s,suffix,u)
    s["p"..suffix][3] = height-drop*(2*u-1)^2
    s["t"..suffix][3] = 4*drop*(1-2*u)/total*length(s["t"..suffix])
  end
  for i = 2,#path.segments-1 do
    altitude(path.segments[i],"0",distance/total)
    distance = distance+lengths[i]
    altitude(path.segments[i],"1",distance/total)
  end
  altitude(path.segments[1],"1",0)
  altitude(path.segments[#path.segments],"0",1)
end

local function flyover(net, r, height, turbine, archDrop)
  local a, c, d = net.a, net.c, net.d
  local path = road(net, "left-" .. arm(r), arm(r), arm(r-1), "left")
  local offset = net.rampOffset
  local p0, p1 = vec(-a,-armOffset(net,r)), vec(-c,-offset,height)
  local p2, p3 = vec(offset,c,height), vec(armOffset(net,r+1),a)
  local staggered = net.stagger and net.stagger>0
  curve(path, p0, p1, vec(1,0), vec(1,0), tag(r,staggered and "left-in" or "in"), nil)
  if turbine then
    -- Offset sweep around the outside of the core, separate from the other turns.
    local q1, q2 = vec(-0.45*c,-0.1*c,height), vec(0.1*c,0.45*c,height)
    curve(path, p1, q1, vec(1,0), vec(1,0), nil, nil, true)
    curve(path, q1, q2, vec(1,0), vec(0,1), nil, nil, true)
    curve(path, q2, p2, vec(0,1), vec(0,1), nil, nil, true)
  else
    curve(path, p1, p2, vec(1,0), vec(0,1), nil, nil, true)
  end
  curve(path, p2, p3, vec(0,1), vec(0,1), nil, tag(r+1,staggered and "left-out" or "out"))
  if archDrop then archBridge(path,height,archDrop) end
  rotateRoad(path, r)
end

local function diamond(net, params)
  local j, h, a, d = 45*net.scale, net.h, net.a, net.d
  local nativeHighway = params.roadType ~= 2
  if nativeHighway then
    local profile = roads.select(params)
    local offset = (profile.connectorWidth-profile.mainWidth)/2
    for _,r in ipairs({0,2}) do
      local inlet = road(net,"main-in-"..arm(r),arm(r),nil,"main")
      inlet.profile = "connector"
      straight(inlet,vec(-net.l,-d),vec(-a,-d),tag(r,"external-in"),tag(r,"in"))
      local center = road(net,"main-"..arm(r),arm(r),arm(r+2),"main")
      straight(center,vec(-a,-d+offset),vec(a,-d+offset),tag(r,"in"),tag(r,"out"))
      local outlet = road(net,"main-out-"..arm(r),nil,arm(r+2),"main")
      outlet.profile = "connector"
      straight(outlet,vec(a,-d),vec(net.l,-d),tag(r,"out"),tag(r,"external-out"))
      rotateRoad(inlet,r); rotateRoad(center,r); rotateRoad(outlet,r)
    end
    -- Match the lane-aligned ports used by the native highway diamond.
    d = d+4
  else
    mainline(net,0,0)
    mainline(net,2,0)
  end
  local elevated = params.crossApproach ~= 2
  local l = elevated and 80*net.scale or j+8*h
  local endHeight = elevated and h or 0
  net.crossL = l
  local cross = road(net, "cross", "S", "N", "cross")
  straight(cross, vec(0,-l,endHeight), vec(0,-j,h), "cross:external-S", "cross:S", elevated)
  straight(cross, vec(0,-j,h), vec(0,j,h), "cross:S", "cross:N", true)
  straight(cross, vec(0,j,h), vec(0,l,endHeight), "cross:N", "cross:external-N", elevated)
  local specs = {
    { "ramp4", vec(-a,-d), vec(0,-j,h), vec(1,0), "W:in", "cross:S", "W", "cross:S" },
    { "ramp3", vec(0,-j,h), vec(a,-d), vec(1,0), "cross:S", "W:out", "cross:S", "E" },
    { "ramp2", vec(a,d), vec(0,j,h), vec(-1,0), "E:in", "cross:N", "E", "cross:N" },
    { "ramp1", vec(0,j,h), vec(-a,d), vec(-1,0), "cross:N", "E:out", "cross:N", "W" },
  }
  for _, s in ipairs(specs) do
    if enabled(params,"ramp",s[1]:sub(-1)) then
      local path = road(net, s[1], s[7], s[8], "diamond")
      curve(path, s[2], s[3], s[4], s[4], s[5], s[6])
      if nativeHighway then
        local ramp = path.segments[1]
        local dx,dy,dz = s[3][1]-s[2][1],s[3][2]-s[2][2],s[3][3]-s[2][3]
        local chord = math.sqrt(dx*dx+dy*dy+dz*dz)
        ramp.t0,ramp.t1 = mul(s[4],chord),mul(s[4],chord)
      end
    end
  end
end

local function reflectTraffic(net)
  -- Reflection alone changes driving side. Reverse the entire directed graph too.
  local reflected = { W = "E", E = "W", S = "S", N = "N" }
  for _, path in ipairs(net.roads) do
    path.from, path.to = reflected[path.to], reflected[path.from]
    local reversed = {}
    for i = #path.segments, 1, -1 do
      local s = path.segments[i]
      local function point(p) return vec(-p[1],p[2],p[3]) end
      local function tangent(t) return vec(t[1],-t[2],-t[3]) end
      reversed[#reversed+1] = { p0=point(s.p1), p1=point(s.p0),
        t0=tangent(s.t1), t1=tangent(s.t0), tag0=s.tag1, tag1=s.tag0, bridge=s.bridge }
    end
    path.segments = reversed
  end
end

local function joinCurvePieces(path)
  local merged = {segments={}}
  local i = 1
  while i <= #path.segments do
    local last = i
    while path.segments[last+1] and path.segments[last+1].bridge == path.segments[i].bridge do
      last = last+1
    end
    -- Keep long approaches at both junctions. An odd final run must be
    -- paired from its exit, while preserving the normal/bridge boundary.
    if last == #path.segments and (last-i+1)%2 == 1 then
      merged.segments[#merged.segments+1] = path.segments[i]
      i = i+1
    end
    while i <= last do
      local a,b = path.segments[i],i < last and path.segments[i+1] or nil
      if b then
        curve(merged,a.p0,b.p1,mul(a.t0,1/length(a.t0)),mul(b.t1,1/length(b.t1)),a.tag0,b.tag1,a.bridge)
        i = i+2
      else
        merged.segments[#merged.segments+1] = a
        i = i+1
      end
    end
  end
  path.segments = merged.segments
end

local function offsetMergePorts(net, params, kind)
  local mainTags,branchTags = {},{}
  for _,path in ipairs(net.roads) do
    if path.role == "main" then
      for _,s in ipairs(path.segments) do
        if s.tag0 then mainTags[s.tag0],branchTags[s.tag0] = s.t0,path.profile=="branch" end
        if s.tag1 then mainTags[s.tag1],branchTags[s.tag1] = s.t1,path.profile=="branch" end
      end
    end
  end
  for _,path in ipairs(net.roads) do
    if path.role ~= "main" then
      local amount = params.lanes == 2 and 6 or 4
      local side = path.role == "left" and -1 or 1
      local degrees = 0
      if path.role=="right" and net.design.rightAngle then degrees=net.design.rightAngle end
      if path.role == "left" then degrees = (kind=="stack" or kind=="turbine") and 15 or 30 end
      if path.role == "left" and net.design.mergeAngle then degrees=net.design.mergeAngle/net.scale end
      if path.role == "loop" or path.role == "loop_tail" then degrees = kind=="trumpet" and (params.lanes==2 and 15 or 10) or 15 end
      if kind=="trumpet" and path.role=="loop" and net.design.loopAngle then degrees=net.design.loopAngle end
      if kind=="trumpet" and params.lanes==2 and path.id=="trumpet-stem" then degrees=0 end
      for _,s in ipairs(path.segments) do
        local oldLength = length(vec(s.p1[1]-s.p0[1],s.p1[2]-s.p0[2]))
        local changed = false
        for _,suffix in ipairs({ "0", "1" }) do
          if s["tag"..suffix] and mainTags[s["tag"..suffix]] then
            local p,t = s["p"..suffix],s["t"..suffix]
            local main = mainTags[s["tag"..suffix]]
            local factor = side*(branchTags[s["tag"..suffix]] and 4 or amount)/length(main)
            -- Native construction tags join lane-aligned ports, not coincident
            -- centre lines. Separate the left/right forks before engine shaping.
            s["p"..suffix] = vec(p[1]+factor*main[2],p[2]-factor*main[1],p[3])
            local angle = math.rad(degrees*side*(suffix=="0" and -1 or 1))
            s["t"..suffix] = vec(math.cos(angle)*t[1]-math.sin(angle)*t[2],
              math.sin(angle)*t[1]+math.cos(angle)*t[2],t[3])
            changed = true
          end
        end
        if changed then
          local ratio = length(vec(s.p1[1]-s.p0[1],s.p1[2]-s.p0[2]))/oldLength
          s.t0,s.t1 = mul(s.t0,ratio),mul(s.t1,ratio)
        end
      end
    end
  end
end

function M.generate(kind, params)
  params = settings.normalize(params)
  local acceptance=math.max(0,math.min(3,math.floor(tonumber(params._ipAcceptVariant) or 0)))
  local design = candidates.get(kind,params._ipProbe)
  if params._ipProbe==nil then
    if kind=="cloverleaf" then design={fork=30}
    elseif kind=="trumpet" then design={approach=params.lanes==2 and 11 or 10.5,
      loopAngle=params.lanes==2 and (acceptance>=2 and 20 or 15) or 10}
    elseif kind=="directional" then design={approach=10}
    elseif kind=="stack" or kind=="turbine" then design={wideMedian=true,mergeAngle=30,rightAngle=35,
      stagger=({24,32,40,48})[acceptance+1]} end
  end
  local sizes = { 1, 1.2, 1.4 }
  local scale, h = sizes[params.size or 1] or 1, design.height or 8
  local profile = roads.select(params)
  local net = { roads = {}, scale = scale, h = h, design=design, stagger=(design.stagger or 0)*scale,
    d = profile.mainWidth/2+3, b = 48*scale, a = 270*scale,
    c = 35*scale, rampOffset = (profile.rampWidth+3)/2, sharedWidth = profile.sharedWidth }
  if kind=="directional" or kind=="trumpet" then
    net.d = profile.mainWidth/2+profile.rampWidth+2.5
    net.branchD = profile.branchWidth/2+profile.rampWidth+2.5
  elseif kind=="stack" or kind=="turbine" then
    net.d = profile.mainWidth/2+profile.rampWidth*(design.wideMedian and 2 or 1)+(design.wideMedian and 3 or 2.5)
  end
  local shared = kind == "cloverleaf" and params.cloverLayout ~= 2
  if shared and params.lanes==2 then net.b=56*scale end
  if kind=="trumpet" and params.lanes==2 then net.b=({64,68,72,76})[acceptance+1]*scale end
  if shared then net.a = net.b+(net.b-net.d)+math.max(40*scale,5.5*h) end
  if kind == "diamond" then net.a, net.b = math.max(70*scale,8.75*h), 32*scale end
  if kind == "directional" or kind == "trumpet" then net.a = math.max(110*scale, net.c+(design.approach or 12)*h) end
  if kind == "stack" or kind == "turbine" then
    net.c = kind == "stack" and 45*scale or math.max(60*scale,profile.rampWidth/0.17+5)
    net.c = math.max(net.c,net.d+profile.mainWidth/2+8)
    net.a = net.c+(design.approach or (kind=="stack" and 15.5 or 14))*h*scale
  end
  local terminal = kind=="cloverleaf" and params.lanes~=2 and 12 or (params.lanes==2 and 25 or 20)
  net.l = net.a+net.stagger+terminal*scale
  if kind=="diamond" and params.roadType~=2 then
    local size = params.size or 1
    net.d = 13.5
    net.a = (params.lanes==2 and 75 or 70)+10*(size-1)
    net.l = net.a+(params.lanes==2 and 25 or 20)
  end
  if kind == "diamond" then
    diamond(net, params)
  elseif kind == "cloverleaf" then
    local leaves = { 3, 2, 1, 4 }
    for r = 0, 3 do
      mainline(net, r, r % 2 == 0 and 0 or h)
      if shared then
        if enabled(params,"leaf",leaves[r+1]) then
          sharedLeaf(net, r)
        else
          rightTurn(net, r+1)
        end
      else
        rightTurn(net, r)
      end
      if not shared and enabled(params,"leaf",leaves[r+1]) then
        loop(net, r, r % 2 == 0 and 0 or h, r % 2 == 0 and h or 0, tag(r,"after"), tag(r+1,"before"))
      end
    end
  elseif kind == "stack" or kind == "turbine" then
    for r = 0, 3 do
      mainline(net, r, r % 2 == 0 and -h/2 or h/2)
      rightTurn(net, r)
      local upper = r%2 == 1
      local height = (r%2+1.5)*h+(kind=="stack" and upper and 1 or 0)
      local drop = upper and (kind=="stack" and 3 or 4) or 0.5
      if design.arch==false then height,drop=(r%2+1.5)*h,nil end
      flyover(net,r,height,kind=="turbine",drop)
    end
  elseif kind == "directional" or kind == "trumpet" then
    mainline(net, 0, -h/2)
    mainline(net, 2, -h/2)
    branch(net)
    rightTurn(net, 0)
    rightTurn(net, 1)
    flyover(net, 1, 1.5*h, false,design.teeArch and 0.5 or nil)
    if kind == "directional" then
      flyover(net, 2, h/2, false,design.teeArch and 0.5 or nil)
    else
      local trumpetLoop = loop(net, 2, -h/2, h/2, tag(2,"after"), "trumpet:top")
      for _,s in ipairs(trumpetLoop.segments) do s.bridge = false end
      local stem = road(net, "trumpet-stem", nil, nil, "left")
      curve(stem,vec(-net.d,net.b,h/2),vec(-net.branchD,-net.b,h/2),vec(0,-1),vec(0,-1),"trumpet:top","trumpet:bottom",true)
      straight(stem,vec(-net.branchD,-net.b,h/2),vec(-net.branchD,-net.a),"trumpet:bottom",tag(3,"out"))
      if params.loopSide == 2 then reflectTraffic(net) end
    end
  else
    error("Unknown interchange: " .. tostring(kind))
  end
  -- Diamond ports are generated from the native fork layout above.
  if kind ~= "diamond" then
    for _,path in ipairs(net.roads) do
      if path.role=="loop" or path.role=="loop_tail" then joinCurvePieces(path) end
    end
    offsetMergePorts(net,params,kind)
  end
  return net
end

return M
