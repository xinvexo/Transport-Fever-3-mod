local proposals = ug_require "xin_station_rows_1::/station_rows/proposal.lua"
local sequence = ug_require "xin_station_rows_1::/station_rows/sequence.lua"

local function construction(entity)
  if not api.engine.entityExists(entity) then return nil end
  return api.engine.getComponent(entity, api.type.ComponentType.CONSTRUCTION)
end

local function snapshot(entity, moduleName)
  local current = construction(entity)
  if not proposals.isSupported(current) then return nil end
  local modules = {}
  for slot, module in pairs(current.params.modules or {}) do
    modules[slot] = { name = module.name }
  end
  return { entity = entity, module = moduleName, modules = modules }
end

local function completedEdit(current, params)
  local target = current.target
  if not params[4] then return end
  local matched = false
  for _, entity in ipairs(params[1].toRemove) do
    if entity == target.entity then matched = true; break end
  end
  if not matched then return end

  local replacement
  for _, entity in ipairs(params[3]) do
    local candidate = snapshot(entity, target.module)
    if candidate then
      if replacement then return end
      replacement = candidate
    end
  end
  if not replacement then current.target = nil; return true end

  local plan = proposals.remaining(target.modules, replacement.modules, target.module) or { steps = {} }
  current.target = replacement
  current.nextId = (current.nextId or 0) + 1
  plan.id, plan.entity, plan.sourceEntity = current.nextId, replacement.entity, target.entity
  current.job = plan
  if #plan.steps > 0 then
    current.busy, current.target = true, nil
  end
  return true
end

function data()
  return {
    update = function(_, state)
      local current = state:get() or {}
      if current.listenerRevision == 15 then return end
      state:subscribeToNoEvents()
      state:subscribeToEvent("stationRowsTarget")
      state:subscribeToEvent("stationRowsFinished")
      state:subscribeToEvent("onPostBuildProposal")
      state:set({ listenerRevision = 15, nextId = 0 })
    end,

    handleEvent = function(_, state, _, id, name, params)
      if id == "xin_station_rows" then
        local current = state:get() or {}
        if name == "stationRowsTarget" and not current.busy then
          current.target = params.entity and snapshot(params.entity, params.module) or nil
          state:set(current)
        elseif name == "stationRowsFinished" then
          current.target, current.job, current.busy = nil, nil, nil
          state:set(current)
        end
        return
      end
      if id ~= "apply_command" or name ~= "onPostBuildProposal" then return end
      local current = state:get() or {}
      if not current.target or current.busy then return end
      local ok, changed = pcall(completedEdit, current, params)
      if not ok then
        log.warning("[Station Rows] Could not follow native edit: " .. tostring(changed))
      elseif changed then
        state:set(current)
      end
    end,

    guiUpdate = function(_, state, guiState)
      if sequence.running() then return end
      local current = state:get() or {}
      local ui = guiState:get() or {}
      if ui.done == nil then
        guiState:set({ done = current.nextId or 0 })
        return
      end
      if not current.job or current.job.id <= ui.done then return end
      ui.done = current.job.id
      guiState:set(ui)
      api.gui.fireReactEvent("xinStationRowsTargetChanged", {
        sourceEntity = current.job.sourceEntity, entity = current.job.entity,
      })
      if #current.job.steps == 0 then return end
      api.gui.fireReactEvent("xinStationRowsStarted", current.job.entity)
      if not sequence.start(current.job) then
        api.cmd.sendCommand(api.cmd.makeScriptingSendEventCmd("", "xin_station_rows", "stationRowsFinished", {}))
        api.gui.fireReactEvent("xinStationRowsFinished", current.job.entity)
      end
    end,
  }
end
