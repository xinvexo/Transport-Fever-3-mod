local EVENT_ID = "xin_line_vehicle_colors"
local MAX_LINES = 8
local MAX_VEHICLES = 32
local MAX_COMMANDS = 16
local MAX_ATTEMPTS = 8
local EPSILON = 0.00001

local function component(entity, kind)
  if not entity or entity < 0 or not api.engine.entityExists(entity) then return nil end
  return api.engine.getComponent(entity, api.type.ComponentType[kind])
end

local function owned(entity, player)
  local owner = component(entity, "PLAYER_OWNED")
  return owner and owner.player == player
end

local function validColor(color)
  if not color then return false end
  for _, key in ipairs({ "x", "y", "z" }) do
    local value = color[key]
    if type(value) ~= "number" or not (value >= 0 and value <= 1) then return false end
  end
  return true
end

local function sameColor(left, right)
  return left and math.abs(left.x - right.x) <= EPSILON
    and math.abs(left.y - right.y) <= EPSILON
    and math.abs(left.z - right.z) <= EPSILON
end

local function needsColor(vehicle, color, paintable)
  for _, entry in ipairs(vehicle.transportVehicleConfig.vehicles) do
    local part = entry.part
    local modelId = part.modelId
    if paintable[modelId] == nil then
      local model = api.res.modelRep.get(modelId)
      local metadata = model and model.metadata and model.metadata.transportVehicle
      paintable[modelId] = metadata ~= nil and not metadata.noCblendMask
    end
    if paintable[modelId] and not sameColor(part.color, color) then return true end
  end
  return false
end

local function enqueue(current, request)
  if type(request.entity) ~= "number" or type(request.line) ~= "number"
    or request.entity < 0 or request.line < 0 then return end
  current.vehicles = current.vehicles or {}
  current.vehicles[request.entity] = { line = request.line, fromLine = request.fromLine,
    revision = request.revision, models = request.models, attempts = 0 }
end

local function sortedKeys(values)
  local result = {}
  for key in pairs(values or {}) do result[#result + 1] = key end
  table.sort(result)
  return result
end

local function syncVehicle(entity, request, player, paintable, budget)
  if not owned(entity, player) then return true end
  if request.revision and api.engine.getRevision(entity).num[1] ~= request.revision then return true end
  local vehicle = component(entity, "TRANSPORT_VEHICLE")
  if not vehicle then return true end
  if vehicle.line ~= request.line then
    -- A dispatch intent arrives before its native command. Wait only for this
    -- vehicle and target; abandon it if another dispatch has sent it elsewhere.
    return request.fromLine == nil or vehicle.line ~= request.fromLine
  end
  if not owned(request.line, player) or not component(request.line, "LINE") then return true end
  if request.models then
    local parts = vehicle.transportVehicleConfig.vehicles
    if #parts ~= #request.models then return false end
    for index, model in ipairs(request.models) do
      if parts[index].part.modelId ~= model then return false end
    end
  end
  local lineColor = component(request.line, "COLOR")
  if not lineColor or not validColor(lineColor.color) then return false end
  if not needsColor(vehicle, lineColor.color, paintable) then return true end

  local color = lineColor.color:clone()
  budget.sent = budget.sent + 1
  -- Simulation updates reject callbacks; confirm the result with a fresh read.
  api.cmd.sendCommand(api.cmd.makeEntitySetColorCmd(entity, color))
  local after = component(entity, "TRANSPORT_VEHICLE")
  return not after or not needsColor(after, color, paintable)
end

function data()
  return {
    handleEvent = function(_, state, _, id, name, params)
      if id ~= EVENT_ID then return end
      local current = state:get() or {}
      if name == "lineColorChanged" then
        if not params or type(params.line) ~= "number" or params.line < 0 then return end
        current.lines = current.lines or {}
        current.lines[params.line] = true
      elseif name == "vehiclesAssigned" or name == "vehiclesReplaced" then
        for _, request in ipairs(params and params.entries or {}) do enqueue(current, request) end
      else
        return
      end
      state:set(current)
    end,

    update = function(_, state)
      if not state:hasEventSubscriptions() then
        state:subscribeToNoEvents()
        state:subscribeToEvent("vehiclesAssigned")
        state:subscribeToEvent("vehiclesReplaced")
        state:subscribeToEvent("lineColorChanged")
      end
      local current = state:get() or {}
      if current.initialized and not current.lines and not current.vehicles then return end
      local player = api.engine.util.getPlayer()
      if not current.initialized then
        -- One initial reconciliation per save. Persist it so loading a save does
        -- not repaint vehicles that the player subsequently customized.
        current.lines = current.lines or {}
        for _, line in ipairs(api.engine.system.lineSystem.getLinesForPlayer(player)) do
          current.lines[line] = true
        end
        current.initialized = true
      end

      local loaded = 0
      for _, line in ipairs(sortedKeys(current.lines)) do
        local ok, reason = pcall(function()
          if not owned(line, player) or not component(line, "LINE") then return end
          for _, entity in ipairs(api.engine.system.transportVehicleSystem.getLineVehicles(line)) do
            if api.engine.entityExists(entity) then
              enqueue(current, { entity = entity, line = line,
                revision = api.engine.getRevision(entity).num[1] })
            end
          end
        end)
        if not ok then log.warning("[Line Vehicle Colors] Line change failed: " .. tostring(reason)) end
        current.lines[line] = nil
        loaded = loaded + 1
        if loaded == MAX_LINES then break end
      end
      if current.lines and not next(current.lines) then current.lines = nil end

      local checked, paintable, budget = 0, {}, { sent = 0 }
      for _, entity in ipairs(sortedKeys(current.vehicles)) do
        local request = current.vehicles[entity]
        request.attempts = request.attempts + 1
        local ok, done = pcall(syncVehicle, entity, request, player, paintable, budget)
        if not ok and not request.warned then
          request.warned = true
          log.warning("[Line Vehicle Colors] Vehicle " .. tostring(entity) .. ": " .. tostring(done))
        end
        if (ok and done) or request.attempts >= MAX_ATTEMPTS then
          current.vehicles[entity] = nil
        end
        checked = checked + 1
        if checked == MAX_VEHICLES or budget.sent == MAX_COMMANDS then break end
      end
      if current.vehicles and not next(current.vehicles) then current.vehicles = nil end
      state:set(current)
    end,
  }
end
