local M = {}
local EVENT_ID = "xin_line_vehicle_colors"
local tracked = setmetatable({}, { __mode = "k" })
local reported = false

local function report(reason)
  if reported then return end
  reported = true
  log.warning("[Line Vehicle Colors] GUI notification failed: " .. tostring(reason))
end

local function completed(change, success)
  if not success or not api.engine.entityExists(change.entity) then return end
  local types = api.type.ComponentType
  if change.revision and api.engine.getRevision(change.entity).num[1] ~= change.revision then return end
  if change.kind == "color" then
    -- Vehicle paint commands deliberately do not trigger another repaint.
    if api.engine.getComponent(change.entity, types.LINE) then
      api.cmd.sendCommand(api.cmd.makeScriptingSendEventCmd("", EVENT_ID,
        "lineColorChanged", { line = change.entity }))
    end
  else
    local vehicle = api.engine.getComponent(change.entity, types.TRANSPORT_VEHICLE)
    if not vehicle or vehicle.line < 0 then return end
    if change.line and vehicle.line ~= change.line then return end
    api.cmd.sendCommand(api.cmd.makeScriptingSendEventCmd("", EVENT_ID,
      change.kind == "assign" and "vehiclesAssigned" or "vehiclesReplaced", {
        entries = { { entity = change.entity, line = vehicle.line,
          revision = api.engine.getRevision(change.entity).num[1] } },
      }))
  end
end

function M.installGui()
  -- This module is installed by the GUI entry recipe only. Engine-side command
  -- functions remain native, so simulation updates never acquire callbacks.
  local engine = ug_require "::/gui/main/engine_react_util.tl"
  if engine.__xinLineVehicleColorCommands then return end
  local commandApi = api.cmd
  local send = commandApi.sendCommand
  local setLine = commandApi.makeVehicleSetLineCmd
  local setColor = commandApi.makeEntitySetColorCmd
  local replace = commandApi.makeVehicleReplaceCmd

  local function remember(command, kind, entity, line)
    local ok, reason = pcall(function()
      tracked[command] = { kind = kind, entity = entity, line = line,
        revision = api.engine.entityExists(entity) and api.engine.getRevision(entity).num[1] or nil }
    end)
    if not ok then report(reason) end
    return command
  end

  commandApi.makeVehicleSetLineCmd = function(entity, line, ...)
    return remember(setLine(entity, line, ...), "assign", entity, line)
  end
  commandApi.makeEntitySetColorCmd = function(entity, ...)
    return remember(setColor(entity, ...), "color", entity)
  end
  commandApi.makeVehicleReplaceCmd = function(entity, ...)
    return remember(replace(entity, ...), "replace", entity)
  end
  commandApi.sendCommand = function(command, callback, progress)
    local change = tracked[command]
    if not change then return send(command, callback, progress) end
    return send(command, function(result, success, entities)
      -- Notify independently of the original UI callback: that callback may
      -- legitimately return early because its window has already closed.
      local ok, reason = pcall(completed, change, success)
      if not ok then report(reason) end
      if callback then callback(result, success, entities) end
    end, progress)
  end
  engine.__xinLineVehicleColorCommands = true
  log.message("[Line Vehicle Colors] GUI command completion hooks ready (revision 4).")
end

return M
