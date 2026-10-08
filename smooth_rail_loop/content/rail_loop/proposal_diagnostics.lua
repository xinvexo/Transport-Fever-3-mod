-- Bounded, read-only checks after an early native rejection. Never build or
-- substitute a probe for the user's full candidate. Run at most one per step.
local M = {}

function M.queue(placement, segments, matrix, trackName, bridgeName)
  local function select(route, flat)
    local selected = {}
    for _, source in ipairs(segments) do
      if not route or source.route == route then
        local edge = {}
        for key, value in pairs(source) do edge[key] = value end
        if flat then
          edge.kind = "NORMAL"
          for _, key in ipairs({ "p0", "p1", "t0", "t1" }) do
            edge[key] = { source[key][1], source[key][2], 0 }
          end
        end
        selected[#selected+1] = edge
      end
    end
    return selected
  end
  local straight = { { p0={-2.5,0,0}, p1={-2.5,25,0}, t0={0,25,0}, t1={0,25,0},
    tag0="probe:0", tag1="probe:1", kind="NORMAL" } }
  local cases = {
    { name="straight-index0", edges=straight, index=0 },
    { name="straight-index1", edges=straight, index=1 },
    { name="main-only", edges=select("main") },
    { name="loop-only", edges=select("loop") },
    { name="full-flat-normal", edges=select(nil, true) },
    { name="full-original", edges=segments },
  }
  local cursor = 0
  return function(api)
    cursor = cursor + 1
    local case = cases[cursor]
    if not case then return false end
    local ok, data = pcall(function()
      local proposal = placement.makeProposal(api, case.edges, matrix, trackName, bridgeName)
      if case.index then for _, edge in ipairs(proposal.streetProposal.edgesToAdd) do edge.comp.typeIndex = case.index end end
      local context = api.type.Context.new()
      context.player = api.engine.util.getPlayer()
      local first, second = api.engine.util.proposal.makeProposalData(proposal, context)
      local function field(value, key)
        if value == nil then return nil end
        local readable, result = pcall(function() return value[key] end)
        if readable then return result end
      end
      local candidates = { [1]=first, [2]=second, [3]=field(first,1), [4]=field(first,2) }
      for i = 1, 4 do if field(candidates[i], "errorState") then return candidates[i] end end
      error("Native check returned no ProposalData")
    end)
    local description
    if ok then
      local count, messages = 0, {}
      for _ in pairs(data.entity2tn or {}) do count = count+1 end
      for _, field in ipairs({ "messages", "warnings", "infos" }) do
        for _, message in ipairs(data.errorState[field] or {}) do messages[#messages+1] = tostring(message) end
      end
      description = string.format("critical=%s; networks=%d; messages=%s", tostring(data.errorState.critical), count, table.concat(messages, " | "))
    else
      description = "error=" .. tostring(data)
    end
    return cursor < #cases, string.format("[Rail Loop] probe %s; position=%.2f,%.2f,%.2f; %s",
      case.name, matrix[13], matrix[14], matrix[15], description)
  end
end

return M
