local M = {}

-- Use the same node/segment API as the native mission track_builder. A single
-- tag map spans all materials and routes, including both three-way junctions.
-- ConstructionEntity conversion can split these into duplicate base nodes.
function M.makeProposal(api, segments, matrix, trackName, bridgeName)
  local proposal = api.type.SimpleProposal.new()
  local trackIndex = api.res.streetTemplateRep.find(trackName)
  assert(trackIndex >= 0, "Rail track template unavailable: " .. tostring(trackName))
  local template = api.res.streetTemplateRep.get(trackIndex)
  local nodes, edges, byTag, types = {}, {}, {}, {}
  local nextId = 0
  local function id()
    nextId = nextId - 1
    return nextId
  end
  local function transform(p, position)
    return { matrix[1]*p[1]+matrix[5]*p[2]+matrix[9]*p[3]+(position and matrix[13] or 0),
      matrix[2]*p[1]+matrix[6]*p[2]+matrix[10]*p[3]+(position and matrix[14] or 0),
      matrix[3]*p[1]+matrix[7]*p[2]+matrix[11]*p[3]+(position and matrix[15] or 0) }
  end
  local function node(tag, p)
    assert(type(tag) == "string", "Missing rail node tag")
    local existing = byTag[tag]
    if existing then
      for i = 1, 3 do assert(math.abs(existing.raw[i] - p[i]) < 1e-7, "Mismatched rail junction") end
      return existing.value
    end
    local value = api.type.NodeAndEntity.new()
    value.entity = id()
    value.comp.position = api.type.Vec3f.new(table.unpack(p))
    nodes[#nodes + 1] = value
    byTag[tag] = { value = value, raw = p }
    return value
  end
  local function structureIndex(kind)
    if kind == "NORMAL" then return 0 end
    if not types[kind] then
      local name = kind == "BRIDGE" and bridgeName or "::/infrastructure/tunnel/tunnel_a.tunnel"
      local rep = kind == "BRIDGE" and api.res.bridgeTypeRep or api.res.tunnelTypeRep
      local index = rep.find(name)
      assert(index >= 0, "Rail structure unavailable: " .. tostring(name))
      types[kind] = index
    end
    return types[kind]
  end
  for _, segment in ipairs(segments) do
    local p0, p1 = transform(segment.p0, true), transform(segment.p1, true)
    local n0, n1 = node(segment.tag0, p0), node(segment.tag1, p1)
    local t0, t1 = transform(segment.t0), transform(segment.t1)
    local edge = api.type.SegmentAndEntity.new()
    edge.entity, edge.type = id(), 1
    local comp = edge.comp
    comp.node0, comp.node1 = n0.entity, n1.entity
    comp.position0, comp.position1 = n0.comp.position, n1.comp.position
    comp.tangent0 = api.type.Vec3f.new(table.unpack(t0))
    comp.tangent1 = api.type.Vec3f.new(table.unpack(t1))
    comp.type = assert(api.type["enum"].BaseEdgeType[segment.kind], "Unknown rail structure")
    comp.typeIndex = structureIndex(segment.kind)
    comp.laneConfigs, comp.roadTemplate, comp.roadStyle = template.laneConfigs, trackName, template.streetStyle
    comp.roadType = api.type["enum"].RoadType.TRACK
    edges[#edges + 1] = edge
  end
  proposal.streetProposal.nodesToAdd, proposal.streetProposal.edgesToAdd = nodes, edges
  return proposal
end

-- Verify the native prepared world curves as well as the Lua design curves.
function M.checkPrepared(proposal)
  if not proposal or not proposal.proposal then return "无法读取施工预览" end
  local stats = { count = 0, maxGrade = 0, duplicateNodes = 0, nodes = 0 }
  local positions = {}
  for _, node in ipairs(proposal.proposal.addedNodes or {}) do
    local p = node.comp.position
    local key = string.format("%.9g,%.9g,%.9g", p.x, p.y, p.z)
    if positions[key] then stats.duplicateNodes = stats.duplicateNodes + 1 end
    positions[key] = true
    stats.nodes = stats.nodes + 1
  end
  for _, edge in ipairs(proposal.proposal.addedSegments) do
    if edge.type == 1 then
      stats.count = stats.count + 1
      local s = edge.comp
      for i = 0, 64 do
        local u = i / 64
        local velocity = {}
        for _, axis in ipairs({ "x", "y", "z" }) do
          velocity[axis] = (6*u*u-6*u)*s.position0[axis] + (3*u*u-4*u+1)*s.tangent0[axis]
            + (-6*u*u+6*u)*s.position1[axis] + (3*u*u-2*u)*s.tangent1[axis]
        end
        local horizontal = math.sqrt(velocity.x^2 + velocity.y^2)
        local grade = horizontal < 1e-6 and math.huge or math.abs(velocity.z) / horizontal
        if grade ~= grade then grade = math.huge end
        if grade > stats.maxGrade then
          stats.maxGrade = grade
          stats.worst = edge
        end
      end
    end
  end
  if stats.count == 0 then return "施工预览未生成轨道", stats end
  if stats.duplicateNodes > 0 then return "施工预览出现重复接点，请调整放置位置", stats end
  if stats.maxGrade > .0851 then return "施工处理后的轨道坡度过大，请调整放置位置或高度", stats end
  return nil, stats
end

-- Reuse native transport-network geometry, never reconstruct undocumented
-- renderer splines. This line overlay can show a rejected construction too.
function M.previewEdges(api, builtin, data, proposal, allowed)
  local result = {}
  local stats = { networks = 0, matched = 0, short = 0 }
  if data.entity2tn then for _ in pairs(data.entity2tn) do stats.networks = stats.networks + 1 end end
  if not proposal or not proposal.proposal or not data.entity2tn then return result, stats end
  local color = allowed and api.type.Vec4f.new(.20, .65, 1, 1) or api.type.Vec4f.new(1, .25, .18, 1)
  for _, segment in ipairs(proposal.proposal.addedSegments) do
    local network = segment.type == 1 and data.entity2tn[segment.entity]
    if network then
      stats.matched = stats.matched + 1
      for _, edge in ipairs(network.edges or {}) do
        local geometry = edge.geometry
        if geometry and geometry.length >= 2 and geometry.length < math.huge then
          local render = builtin.type.EdgeRenderable.Edge.new(geometry)
          render.colors = { color, color }
          render.width, render.offsetZ, render.stepSize = 1.5, .15, 1
          result[#result + 1] = render
        else
          stats.short = stats.short + 1
        end
      end
    end
  end
  return result, stats
end

-- A candidate can only be committed after validation of that exact revision.
function M.session()
  local state = { revision = 0, live = true, busy = false }
  function state:replace(key, proposal)
    self.revision = self.revision + 1
    self.key, self.proposal, self.prepared, self.allowed = key, proposal, nil, false
    return self.revision
  end
  function state:validated(revision, prepared, allowed)
    if self.live and self.revision == revision and not self.busy then
      self.prepared, self.allowed = prepared, allowed
      return true
    end
    return false
  end
  function state:take(key)
    if not self.live or self.busy or not self.allowed or key ~= self.key then return nil end
    self.busy, self.allowed = true, false
    return self.prepared
  end
  function state:close()
    self.live = false
    self:replace(nil, nil)
  end
  return state
end

return M
