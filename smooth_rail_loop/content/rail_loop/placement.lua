local M = {}

function M.makeProposal(api, fileName, params, matrix, plan)
  local proposal = api.type.SimpleProposal.new()
  local entity = api.type.SimpleProposal.ConstructionEntity.new()
  local saved = {}
  for key, value in pairs(params or {}) do saved[key] = value end
  saved.xinTerrainPlan = plan
  saved.xinGeometryVersion = 1
  saved.seed = saved.seed or 0
  saved.year = saved.year or api.engine.util.getYear()
  local columns = {}
  for i = 1, 16, 4 do
    columns[#columns + 1] = api.type.Vec4f.new(matrix[i], matrix[i+1], matrix[i+2], matrix[i+3])
  end
  entity.fileName = fileName
  entity.transf = api.type.Mat4f.new(table.unpack(columns))
  entity.params = saved
  entity.playerEntity = api.engine.util.getPlayer()
  proposal.constructionsToAdd = { entity }
  return proposal
end

-- Verify the native prepared world curves as well as the Lua design curves.
function M.checkPrepared(proposal)
  if not proposal or not proposal.proposal then return "无法读取施工预览" end
  local stats = { count = 0, maxGrade = 0 }
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
  if stats.maxGrade > .0851 then return "施工处理后的轨道坡度过大，请调整放置位置或高度", stats end
  return nil, stats
end

-- Reuse native transport-network geometry, never reconstruct undocumented
-- renderer splines. This line overlay can show a rejected construction too.
function M.previewEdges(api, builtin, data, proposal, allowed)
  local result = {}
  if not proposal or not proposal.proposal or not data.entity2tn then return result end
  local color = allowed and api.type.Vec4f.new(.20, .65, 1, 1) or api.type.Vec4f.new(1, .25, .18, 1)
  for _, segment in ipairs(proposal.proposal.addedSegments) do
    local network = segment.type == 1 and data.entity2tn[segment.entity]
    if network then
      for _, edge in ipairs(network.edges or {}) do
        local geometry = edge.geometry
        if geometry and geometry.length >= 2 and geometry.length < math.huge then
          local render = builtin.type.EdgeRenderable.Edge.new(geometry)
          render.colors = { color, color }
          render.width, render.offsetZ, render.stepSize = 1.5, .15, 1
          result[#result + 1] = render
        end
      end
    end
  end
  return result
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
