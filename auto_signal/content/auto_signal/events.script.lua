local network = ug_require "xin_auto_signal_1::/auto_signal/network.lua"
local pendingBuild

local function warn(message)
  log.warning("[Auto Signal] " .. tostring(message))
end

local function component(entity, kind)
  return api.engine.getComponent(entity, api.type.ComponentType[kind])
end

local function scriptState(state)
  local current = state:get() or {}
  current.jobs = current.jobs or {}
  current.nextId = current.nextId or 0
  return current
end

local function buildFailure(command)
  local result = command and command.resultProposalData
  local errors = result and result.errorState or {}
  local collision = result and result.collisionInfo or {}
  local collided = {}
  for _, item in ipairs(collision.collisionEntities or {}) do
    collided[#collided + 1] = tostring(item.entity)
  end
  return "construction failed: " .. table.concat(errors.messages or {}, "; ")
    .. "; critical=" .. tostring(errors.critical)
    .. "; warnings=" .. table.concat(errors.warnings or {}, "; ")
    .. "; infos=" .. table.concat(errors.infos or {}, "; ")
    .. "; collisions=" .. table.concat(collided, ",")
    .. "; buildings=" .. table.concat(collision.buildingEntities or {}, ",")
    .. "; modules=" .. table.concat(collision.removableModules or {}, ",")
end

local function collectJobs(event, current)
  local old, seen = {}, {}
  for _, segment in ipairs(event.proposal.removedSegments or {}) do
    for _, object in ipairs(segment.comp and segment.comp.objects or {}) do old[object[1]] = true end
  end
  for _, segment in ipairs(event.proposal.addedSegments or {}) do
    if segment.comp then
      local candidates = api.engine.system.streetSystem.getNodeTrackSegments(segment.comp.node0) or {}
      for _, edge in ipairs(candidates) do
        local base = component(edge, "BASE_EDGE")
        if base and ((base.node0 == segment.comp.node0 and base.node1 == segment.comp.node1)
          or (base.node0 == segment.comp.node1 and base.node1 == segment.comp.node0)) then
          for _, object in ipairs(base.objects or {}) do
            local entity = object[1]
            if object[2] == api.type.enum.EdgeObjectType.SIGNAL and not old[entity] and not seen[entity] then
              seen[entity] = true
              local data = component(entity, "EDGE_OBJECT")
              local params = data and data.params or {}
              if params.asEnabled == 2 then
                local minimum = tonumber(params.asMinimumSpacing)
                if minimum and minimum >= 50 and minimum <= 2000 then
                  current.nextId = current.nextId + 1
                  current.jobs[#current.jobs + 1] = {
                    id = current.nextId, signal = entity, minimum = minimum,
                  }
                end
              end
            end
          end
        end
      end
    end
  end
  while #current.jobs > 20 do table.remove(current.jobs, 1) end
end

local function sameArray(first, second, tolerance)
  if #first ~= #second then return false end
  for index, value in ipairs(first) do
    if math.abs(value - second[index]) > tolerance then return false end
  end
  return true
end

local function recoveryLayouts(count)
  if count == 1 then
    return { { phase = 0.25 }, { phase = 0.75 }, { phase = 0 }, { phase = 1 } }
  end
  return {
    { spread = 0, phase = 0.5, maximumCount = count },
    { spread = 0.5, phase = 0.5, maximumCount = count },
    { spread = 0, phase = 0.25, maximumCount = count },
    { spread = 0, phase = 0.75, maximumCount = count },
    { spread = 0, phase = 0, maximumCount = count },
    { spread = 0, phase = 1, maximumCount = count },
    { spread = 1, phase = 0.5, maximumCount = count - 1 },
    { spread = 0, phase = 0.5, maximumCount = count - 1 },
  }
end

-- A rejected build leaves the old signals intact. Try another complete layout
-- on the next GUI update, retaining the requested minimum distance throughout.
local function startAttempt(request)
  local ok, submitted, reason = pcall(function()
    while request.nextLayout <= #request.layouts do
      local index = request.nextLayout
      request.nextLayout = index + 1
      local plan, planError = network.plan(request.job.signal, request.job.minimum, request.layouts[index])
      if not plan then return false, planError end
      if request.sourceEdges and not sameArray(request.sourceEdges, plan.sourceEdges, 0) then
        return false, "track section changed during placement"
      end
      if not request.sourceEdges then
        request.sourceEdges = plan.sourceEdges
        for _, layout in ipairs(recoveryLayouts(plan.count)) do
          request.layouts[#request.layouts + 1] = layout
        end
      end
      local repeated = false
      for _, positions in ipairs(request.tried) do
        if sameArray(positions, plan.positions, 0.000001) then repeated = true; break end
      end
      if not repeated then
        request.tried[#request.tried + 1] = plan.positions
        local proposal, proposalError = network.proposal(plan)
        if not proposal then return false, proposalError end
        local context = api.type.Context.new()
        context.player = api.engine.util.getPlayer()
        local completion = { complete = false, request = request }
        pendingBuild = completion
        api.cmd.sendCommand(api.cmd.makeWorldBuildProposalCmd(proposal, context, false, false),
          function(command, success)
            -- Game state helpers are used only during guiUpdate.
            completion.complete = true
            if not success then
              local result = command and command.resultProposalData
              completion.retryable = result and result.errorState and result.errorState.critical == true
              completion.error = buildFailure(command)
            end
          end)
        return true
      end
    end
    return false, "no accepted layout after " .. tostring(#request.tried) .. " attempts"
  end)
  if not ok then pendingBuild = nil; return false, submitted end
  return submitted, reason
end

function data()
  return {
    update = function(_, state)
      if not state:hasEventSubscriptions() then
        state:set(scriptState(state))
        state:subscribeToEvent("onPostBuildProposal")
      end
    end,

    handleEvent = function(_, state, _, eventId, eventName, eventParams)
      if eventId ~= "apply_command" or eventName ~= "onPostBuildProposal" then return end
      local event = eventParams and eventParams[1]
      local playerInitiated = eventParams and eventParams[4]
      if not event or not event.proposal or not playerInitiated then return end
      local current = scriptState(state)
      local previousId = current.nextId
      local ok, reason = pcall(collectJobs, event, current)
      if current.nextId ~= previousId then state:set(current) end
      if not ok then warn(reason) end
    end,

    guiUpdate = function(_, state, guiState)
      if pendingBuild and not pendingBuild.complete then return end
      local current = scriptState(state)
      local ui = guiState:get() or {}
      if ui.done == nil then
        guiState:set({ done = current.nextId })
        return
      end
      if pendingBuild then
        local completed = pendingBuild
        pendingBuild = nil
        if completed.error then
          if completed.retryable then
            local submitted, reason = startAttempt(completed.request)
            if submitted then return end
            warn(completed.error .. "; " .. tostring(reason))
          else
            warn(completed.error)
          end
        end
      end
      if ui.done >= current.nextId then return end
      for _, job in ipairs(current.jobs) do
        if job.id > ui.done then
          ui.done = job.id
          guiState:set(ui)
          if component(job.signal, "EDGE_OBJECT") then
            local submitted, reason = startAttempt({
              job = job, layouts = { {} }, nextLayout = 1, tried = {},
            })
            if submitted then return end
            warn(reason)
          end
        end
      end
    end,
  }
end
