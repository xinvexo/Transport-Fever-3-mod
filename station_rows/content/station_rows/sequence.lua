local proposals = ug_require "xin_station_rows_1::/station_rows/proposal.lua"
local entity_util = ug_require "::/scripts/entity_util.tl"
local sequence = {}
local active

function sequence.running()
  return active ~= nil
end

function sequence.start(plan)
  if active or not plan or #plan.steps == 0 then return false end
  local job = { entity = plan.entity, index = 1, completed = 0 }
  active = job

  local function finish(reason)
    if active ~= job then return end
    active = nil
    if reason then
      log.warning("[Station Rows] Stopped after " .. job.completed .. " modules: " .. tostring(reason))
    else
      log.message("[Station Rows] Applied " .. job.completed .. " module changes.")
    end
    local notified, failure = pcall(function()
      api.cmd.sendCommand(api.cmd.makeScriptingSendEventCmd("", "xin_station_rows", "stationRowsFinished", {}))
    end)
    if not notified then log.warning("[Station Rows] Could not notify simulation: " .. tostring(failure)) end
    notified, failure = pcall(api.gui.fireReactEvent, "xinStationRowsFinished", job.entity)
    if not notified then log.warning("[Station Rows] Could not notify interface: " .. tostring(failure)) end
  end

  local advance
  advance = function()
    if active ~= job then return end
    while job.index <= #plan.steps do
      local step = plan.steps[job.index]
      local proposal, reason = proposals.makeStep(job.entity, step)
      if not proposal and reason then finish(reason); return end
      job.index = job.index + 1
      if proposal then
        local context = api.type.Context.new()
        context.player = api.engine.util.getPlayer()
        local refundable = api.gui.construction.getRefundableEntities()
        if refundable then context.refundableEntities = refundable end
        local command = api.cmd.makeWorldBuildProposalCmd(proposal, context, false, true)
        local function completed(result, success)
          if not success then
            finish("game rejected slot " .. step.slotId .. " at station " .. job.entity)
            return
          end
          local valid, replacement = {}, nil
          for _, entityRevision in ipairs(result.resultEntities) do
            local entity = entityRevision[1]
            if not entity_util.entityChanged({ entity = entity, revision = entityRevision[2] }) then
              valid[#valid + 1] = entity
              local construction = api.engine.getComponent(entity, api.type.ComponentType.CONSTRUCTION)
              if proposals.isSupported(construction) then
                if replacement then finish("ambiguous updated station"); return end
                replacement = entity
              end
            end
          end
          api.gui.construction.updateRefundableEntities(valid, result.proposal.proposal)
          if not replacement then finish("updated station unavailable"); return end
          local previous = job.entity
          job.entity = replacement
          job.completed = job.completed + 1
          api.gui.fireReactEvent("xinStationRowsTargetChanged", { sourceEntity = previous, entity = replacement })
          advance()
        end
        api.cmd.sendCommand(command, function(result, success)
          if active ~= job then return end
          local ok, reason = pcall(completed, result, success)
          if not ok then finish(reason) end
        end)
        return
      end
    end
    finish()
  end

  local ok, reason = pcall(advance)
  if not ok then finish(reason) end
  return true
end

return sequence
