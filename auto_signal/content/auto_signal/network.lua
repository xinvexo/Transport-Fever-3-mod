local spacing = ug_require "xin_auto_signal_1::/auto_signal/spacing.lua"
local geometry = ug_require "xin_auto_signal_1::/auto_signal/geometry.lua"
local network = {}
local MAX_EDGES = 5000
local MAX_SIGNALS = 1000
local END_CLEARANCE = 1

local function component(entity, kind)
  return api.engine.getComponent(entity, api.type.ComponentType[kind])
end

local function belongsToConstruction(edge)
  local owner = api.engine.system.streetConnectorSystem.getConstructionEntityForEdge(edge)
  return owner ~= nil and owner >= 0
end

local function edgeTransport(entity, cache)
  if not cache then return component(entity, "TRANSPORT_NETWORK") end
  if cache.transport[entity] == nil then
    cache.transport[entity] = component(entity, "TRANSPORT_NETWORK") or false
  end
  return cache.transport[entity] or nil
end

local function edgeLength(entity, cache)
  local transport = edgeTransport(entity, cache)
  local length = 0
  for _, edge in ipairs(transport and transport.edges or {}) do
    length = length + edge.geometry.length
  end
  return length
end

-- Return direction relative to BaseEdge.node0 -> node1, not the potentially
-- reversed direction of a transport-network subedge hosting the signal.
function network.signalDirection(edge, signal, cache)
  local transport = edgeTransport(edge, cache)
  local queries
  if cache then
    cache.signals[edge] = cache.signals[edge] or {}
    queries = cache.signals[edge]
  end
  for index in ipairs(transport and transport.edges or {}) do
    local id
    for _, reversed in ipairs({ false, true }) do
      local key = index * 2 + (reversed and 1 or 0)
      local found = queries and queries[key]
      if found == nil then
        id = id or api.type.EdgeId.new(edge, index - 1)
        found = api.engine.system.signalSystem.getSignal(id, reversed) or false
        if queries then queries[key] = found end
      end
      if found and found.entity == signal then
        local opposite
        if cache then
          cache.orientations[edge] = cache.orientations[edge] or {}
          opposite = cache.orientations[edge][index]
        end
        if opposite == nil then
          local base = assert(component(edge, "BASE_EDGE"), "signal track no longer exists")
          local curveData
          opposite, curveData = geometry.transportOpposite(base, transport.edges[index].geometry,
            cache and cache.geometry[edge])
          if cache then
            cache.orientations[edge][index] = opposite
            cache.geometry[edge] = curveData
          end
        end
        local list = component(signal, "SIGNAL_LIST")
        local data = list and list.signals[found.index + 1]
        local oneWay = data and data.type == api.type.Signal.Type.ONE_WAY_SIGNAL or false
        return reversed ~= opposite, oneWay, data and data.type
      end
    end
  end
  return nil
end

local function reverseSegments(segments)
  local result = {}
  for index = #segments, 1, -1 do
    local segment = segments[index]
    result[#result + 1] = {
      entity = segment.entity, base = segment.base,
      forward = not segment.forward,
    }
  end
  return result
end

local function startNode(segment)
  return segment.forward and segment.base.node0 or segment.base.node1
end

local function endNode(segment)
  return segment.forward and segment.base.node1 or segment.base.node0
end

-- A stable node, rather than the clicked position or mutable edge ids, anchors
-- the section. Rebuilding its signals therefore produces the same layout.
local function canonicalize(segments, closed)
  if not closed and startNode(segments[1]) > endNode(segments[#segments]) then
    return reverseSegments(segments)
  end
  return segments
end

function network.corridor(seedEdge)
  local seed = component(seedEdge, "BASE_EDGE")
  if not seed or belongsToConstruction(seedEdge) then return nil, "construction track" end
  local visited, count = { [seedEdge] = true }, 1
  local function walk(current, node)
    local result = {}
    while true do
      local connected = api.engine.system.streetSystem.getNodeTrackSegments(node) or {}
      if #connected ~= 2 then return result, false end
      local nextEdge
      if connected[1] == current then nextEdge = connected[2]
      elseif connected[2] == current then nextEdge = connected[1]
      else return nil, "disconnected track" end
      if nextEdge == seedEdge then return result, true end
      if visited[nextEdge] then return nil, "overlapping track traversal" end
      if belongsToConstruction(nextEdge) then return result, false end
      if count >= MAX_EDGES then return nil, "section exceeds 5000 track segments" end
      local base = component(nextEdge, "BASE_EDGE")
      if not base or (base.node0 ~= node and base.node1 ~= node) then
        return nil, "track changed during traversal"
      end
      local segment = { entity = nextEdge, base = base, forward = base.node0 == node }
      result[#result + 1] = segment
      visited[nextEdge], count = true, count + 1
      node, current = endNode(segment), nextEdge
    end
  end

  local after, closed = walk(seedEdge, seed.node1)
  if not after then return nil, closed end
  local segments = { { entity = seedEdge, base = seed, forward = true } }
  for _, segment in ipairs(after) do segments[#segments + 1] = segment end
  if not closed then
    local before, reason = walk(seedEdge, seed.node0)
    if not before then return nil, reason end
    before = reverseSegments(before)
    for _, segment in ipairs(segments) do before[#before + 1] = segment end
    segments = before
  end
  return canonicalize(segments, closed), closed
end

-- Native town_util measures a road by summing its actual lane widths. Project
-- that half-width onto the rail at the common node, then leave one metre clear.
-- Shared nodes identify level crossings; a road on a bridge is not connected.
local function roadClearance(edge, node, railTangent)
  local road = assert(component(edge, "BASE_EDGE"), "crossing road no longer exists")
  local width = 0
  if road.laneConfigs_native then
    for index = 1, road.laneConfigs_native:size() do
      width = width + road.laneConfigs_native:at(index).width
    end
  else
    for _, lane in ipairs(road.laneConfigs or {}) do width = width + lane.width end
  end
  assert(width > 0, "crossing road width unavailable")
  local tangent
  if road.node0 == node then tangent = road.tangent0
  elseif road.node1 == node then tangent = road.tangent1 end
  assert(tangent and railTangent, "crossing tangent unavailable")
  local denominator = math.sqrt((tangent.x^2+tangent.y^2)*(railTangent.x^2+railTangent.y^2))
  assert(denominator > 0, "crossing tangent has zero length")
  local sine = math.abs(tangent.x*railTangent.y-tangent.y*railTangent.x)/denominator
  assert(sine > 1e-6, "crossing angle unavailable")
  return math.ceil(width/2/sine) + END_CLEARANCE
end

function network.plan(signal, gap)
  local seedObject = component(signal, "EDGE_OBJECT")
  if not seedObject then return nil, "signal no longer exists" end
  local host = api.engine.system.streetSystem.getEdgeForEdgeObject(signal)
  if not host or host < 0 then return nil, "signal has no track" end
  local cache = { transport = {}, signals = {}, orientations = {}, geometry = {} }
  local seedDirection, oneWay, signalType = network.signalDirection(host, signal, cache)
  if seedDirection == nil then return nil, "signal direction unavailable" end
  if signalType == api.type.Signal.Type.WAYPOINT then return nil, "not a signal" end
  local segments, closed = network.corridor(host)
  if not segments then return nil, closed end
  if closed then return nil, "closed track has no forward endpoint; original signals kept" end

  local direction, total = seedDirection, 0
  for _, segment in ipairs(segments) do
    if segment.entity == host and not segment.forward then direction = not seedDirection end
    segment.offset, segment.length = total, edgeLength(segment.entity, cache)
    if segment.length <= 0 then return nil, "track length unavailable" end
    total = total + segment.length
  end
  geometry.prepare(segments, cache.geometry)

  local resourceId = api.res.constructionRep.find(seedObject.edgeObjectConstruction)
  local construction = resourceId >= 0 and api.res.constructionRep.get(resourceId) or nil
  local clearance = construction and construction.edgeObject and construction.edgeObject.minDistToCrossing or 0
  local excluded, visitedNodes = {}, {}
  local function checkCrossing(node, distance, railTangent)
    local data = visitedNodes[node]
    if not data then
      data = {
        streets = api.engine.system.streetSystem.getNodeStreetSegments(node) or {},
        tracks = api.engine.system.streetSystem.getNodeTrackSegments(node) or {},
      }
      visitedNodes[node] = data
    end
    if #data.streets == 0 and #data.tracks <= 2 then return end
    local required = clearance
    for _, road in ipairs(data.streets) do
      required = math.max(required, roadClearance(road, node, railTangent))
    end
    if required <= 0 then return end
    if data.range then
      data.range[1] = math.min(data.range[1], distance-required)
      data.range[2] = math.max(data.range[2], distance+required)
    else
      data.range = {distance-required, distance+required}
      excluded[#excluded+1] = data.range
    end
  end
  for _, segment in ipairs(segments) do
    checkCrossing(startNode(segment), segment.offset,
      segment.forward and segment.base.tangent0 or segment.base.tangent1)
    checkCrossing(endNode(segment), segment.offset+segment.length,
      segment.forward and segment.base.tangent1 or segment.base.tangent0)
  end

  -- Ordinary degree-two edge joints do not interrupt the distance grid. Only
  -- the section's actual endpoints need the small construction setback.
  local positions, reason = spacing.plan(total, gap, direction, END_CLEARANCE, MAX_SIGNALS, excluded)
  if not positions then return nil, reason end

  local steps, positionIndex = {}, 1
  for _, segment in ipairs(segments) do
    local reversed = direction
    if not segment.forward then reversed = not reversed end
    -- Native campaign signal checks use left = not forward = baseReversed.
    local step = { edge = segment.entity, positions = {}, remove = {}, left = reversed }
    for _, object in ipairs(segment.base.objects or {}) do
      if object[2] == api.type.enum.EdgeObjectType.SIGNAL then
        local existingDirection, _, existingType = network.signalDirection(segment.entity, object[1], cache)
        if existingDirection == reversed and existingType ~= api.type.Signal.Type.WAYPOINT then
          step.remove[#step.remove + 1] = object[1]
        end
      end
    end
    while positionIndex <= #positions do
      local distance = positions[positionIndex] - segment.offset
      if distance > segment.length then break end
      local fraction = distance / segment.length
      if not segment.forward then fraction = 1 - fraction end
      step.positions[#step.positions + 1] = geometry.parameterAt(segment, fraction)
      positionIndex = positionIndex + 1
    end
    if #step.positions > 0 or #step.remove > 0 then steps[#steps + 1] = step end
  end
  local sourceEdges = {}
  for _, segment in ipairs(segments) do sourceEdges[#sourceEdges + 1] = segment.entity end
  return {
    steps = steps, model = seedObject.edgeObjectConstruction,
    oneWay = oneWay, count = #positions,
    positions = positions, sourceEdges = sourceEdges,
  }
end

function network.proposal(plan)
  local proposal = api.type.SimpleProposal.new()
  local edges, removedEdges, objects, removedObjects = {}, {}, {}, {}
  local placeholder = -400000000
  local player = api.engine.util.getPlayer()
  for _, step in ipairs(plan.steps) do
    local base = component(step.edge, "BASE_EDGE")
    if not base then return nil, "track changed before construction" end
    local removeSet, retained = {}, {}
    for _, entity in ipairs(step.remove) do
      removeSet[entity] = true
      removedObjects[#removedObjects + 1] = entity
    end
    for _, object in ipairs(base.objects or {}) do
      if not removeSet[object[1]] then retained[#retained + 1] = { object[1], object[2] } end
    end
    local segment = api.type.SegmentAndEntity.new()
    segment.entity, segment.type = -(#edges + 1), 1
    segment.comp = base:clone()
    local owner = component(step.edge, "PLAYER_OWNED")
    if owner then segment.playerOwned = owner end
    for _, fraction in ipairs(step.positions) do
      retained[#retained + 1] = { placeholder, api.type.enum.EdgeObjectType.SIGNAL }
      placeholder = placeholder - 1
      local object = api.type.SimpleStreetProposal.EdgeObject.new()
      object.edgeEntity, object.param = segment.entity, fraction
      object.oneWay, object.left = plan.oneWay, step.left
      object.model, object.playerEntity = plan.model, player
      objects[#objects + 1] = object
    end
    segment.comp.objects = retained
    removedEdges[#removedEdges + 1], edges[#edges + 1] = step.edge, segment
  end
  proposal.streetProposal.edgesToRemove = removedEdges
  proposal.streetProposal.edgesToAdd = edges
  proposal.streetProposal.edgeObjectsToAdd = objects
  proposal.streetProposal.edgeObjectsToRemove = removedObjects
  return proposal
end

return network
