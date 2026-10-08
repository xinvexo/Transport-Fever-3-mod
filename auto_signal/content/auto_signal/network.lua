local spacing = ug_require "xin_auto_signal_1::/auto_signal/spacing.lua"
local network = {}
local MAX_EDGES = 5000
local MAX_SIGNALS = 1000
local JOINT_CLEARANCE = 0.5
local BOUNDARY_CLEARANCE = 10

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
        local list = component(signal, "SIGNAL_LIST")
        local data = list and list.signals[found.index + 1]
        local oneWay = data and data.type == api.type.Signal.Type.ONE_WAY_SIGNAL or false
        return reversed, oneWay, data and data.type
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

local function tangentKey(segment, reverse)
  local forward = segment.forward ~= reverse
  local first = forward and segment.base.tangent0 or segment.base.tangent1
  local last = forward and segment.base.tangent1 or segment.base.tangent0
  local sign = forward and 1 or -1
  return { sign * first.x, sign * first.y, sign * first.z,
    sign * last.x, sign * last.y, sign * last.z }
end

local function keyLess(first, second)
  for index = 1, #first do
    if first[index] ~= second[index] then return first[index] < second[index] end
  end
  return false
end

-- A stable node, rather than the clicked position or mutable edge ids, anchors
-- the section. Rebuilding its signals therefore produces the same layout.
local function canonicalize(segments, closed)
  if not closed then
    if startNode(segments[1]) > endNode(segments[#segments]) then
      return reverseSegments(segments)
    end
    return segments
  end
  local first = 1
  for index = 2, #segments do
    if startNode(segments[index]) < startNode(segments[first]) then first = index end
  end
  local rotated = {}
  for index = 1, #segments do
    rotated[index] = segments[(first + index - 2) % #segments + 1]
  end
  local nextNode, previousNode = endNode(rotated[1]), startNode(rotated[#rotated])
  -- A two-arc loop shares both end nodes. Its tangents distinguish the two
  -- directions without depending on edge ids that change during rebuilding.
  if nextNode > previousNode or (nextNode == previousNode
    and keyLess(tangentKey(rotated[#rotated], true), tangentKey(rotated[1], false))) then
    return reverseSegments(rotated)
  end
  return rotated
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

function network.plan(signal, minimum, layout)
  local seedObject = component(signal, "EDGE_OBJECT")
  if not seedObject then return nil, "signal no longer exists" end
  local host = api.engine.system.streetSystem.getEdgeForEdgeObject(signal)
  if not host or host < 0 then return nil, "signal has no track" end
  local cache = { transport = {}, signals = {} }
  local seedDirection, oneWay, signalType = network.signalDirection(host, signal, cache)
  if seedDirection == nil then return nil, "signal direction unavailable" end
  if signalType == api.type.Signal.Type.WAYPOINT then return nil, "not a signal" end
  local segments, closed = network.corridor(host)
  if not segments then return nil, closed end

  local direction, total = seedDirection, 0
  for _, segment in ipairs(segments) do
    if segment.entity == host and not segment.forward then direction = not seedDirection end
    segment.offset, segment.length = total, edgeLength(segment.entity, cache)
    if segment.length <= 0 then return nil, "track length unavailable" end
    total = total + segment.length
  end

  local resourceId = api.res.constructionRep.find(seedObject.edgeObjectConstruction)
  local construction = resourceId >= 0 and api.res.constructionRep.get(resourceId) or nil
  local clearance = construction and construction.edgeObject and construction.edgeObject.minDistToCrossing or 0
  local excluded, visitedNodes = {}, {}
  local function checkCrossing(node, distance)
    if clearance <= 0 then return end
    if visitedNodes[node] then return end
    visitedNodes[node] = true
    local streets = api.engine.system.streetSystem.getNodeStreetSegments(node) or {}
    local tracks = api.engine.system.streetSystem.getNodeTrackSegments(node) or {}
    if #streets == 0 and #tracks <= 2 then return end
    excluded[#excluded + 1] = { distance - clearance, distance + clearance }
    if closed then
      excluded[#excluded + 1] = { distance - clearance - total, distance + clearance - total }
      excluded[#excluded + 1] = { distance - clearance + total, distance + clearance + total }
    end
  end
  for _, segment in ipairs(segments) do checkCrossing(startNode(segment), segment.offset) end
  checkCrossing(endNode(segments[#segments]), total)

  local margin = math.min(BOUNDARY_CLEARANCE, total * 0.1)
  local maximumCount = math.min(MAX_SIGNALS, layout and layout.maximumCount or MAX_SIGNALS)
  if closed then
    maximumCount = math.max(1, math.min(maximumCount, math.floor(total / minimum)))
    margin = maximumCount > 1 and total / maximumCount / 2 or 0
  end
  local intervals = {}
  for _, segment in ipairs(segments) do
    local first = math.max(margin, segment.offset + JOINT_CLEARANCE)
    local last = math.min(total - margin, segment.offset + segment.length - JOINT_CLEARANCE)
    if first <= last then intervals[#intervals + 1] = { first, last } end
  end
  intervals = spacing.exclude(intervals, excluded)
  local positions = spacing.plan(intervals, minimum, maximumCount, layout)
  if #positions == 0 then return nil, "no room for signals" end

  local steps, positionIndex = {}, 1
  for _, segment in ipairs(segments) do
    local reversed = direction
    if not segment.forward then reversed = not reversed end
    local step = { edge = segment.entity, positions = {}, remove = {}, left = not reversed }
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
      step.positions[#step.positions + 1] = segment.forward and fraction or 1 - fraction
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
