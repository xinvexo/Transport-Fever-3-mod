local proposals = ug_require "xin_station_rows_1::/station_rows/proposal.lua"
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
    active = nil
    if reason then
      log.warning("[Station Rows] Stopped after " .. job.completed .. " modules: " .. tostring(reason))
    else
      log.message("[Station Rows] Applied " .. job.completed .. " module changes.")
    end
    api.cmd.sendCommand(api.cmd.makeScriptingSendEventCmd("", "xin_station_rows", "stationRowsFinished", {}))
    api.gui.fireReactEvent("xinStationRowsFinished", job.entity)
  end

  local advance
  advance = function()
    while job.index <= #plan.steps do
      local step = plan.steps[job.index]
      local ok, proposal, reason = pcall(proposals.makeStep, job.entity, step)
      if not ok then finish(proposal); return end
      if not proposal and reason then finish(reason); return end
      job.index = job.index + 1
      if proposal then
        local context = api.type.Context.new()
        context.player = api.engine.util.getPlayer()
        local refundable = api.gui.construction.getRefundableEntities()
        if refundable then context.refundableEntities = refundable end
        local command = api.cmd.makeWorldBuildProposalCmd(proposal, context, false, true)
        api.cmd.sendCommand(command, function(result, success)
          if not success then
            finish("game rejected slot " .. step.slotId .. " at station " .. job.entity)
            return
          end
          local valid, replacement = {}, nil
          for _, entity in ipairs(result.resultEntities) do
            if api.engine.entityExists(entity) then
              valid[#valid + 1] = entity
              local construction = api.engine.getComponent(entity, api.type.ComponentType.CONSTRUCTION)
              if proposals.isSupported(construction) then replacement = entity end
            end
          end
          api.gui.construction.updateRefundableEntities(valid, result.proposal.proposal)
          if not replacement then finish("updated station unavailable"); return end
          local previous = job.entity
          job.entity = replacement
          job.completed = job.completed + 1
          api.gui.fireReactEvent("xinStationRowsTargetChanged", { sourceEntity = previous, entity = replacement })
          advance()
        end)
        return
      end
    end
    finish()
  end

  advance()
  return true
end

return sequence
