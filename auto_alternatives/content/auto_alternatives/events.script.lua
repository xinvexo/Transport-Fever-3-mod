local assignment = ug_require "xin_auto_alternatives_1::/auto_alternatives/assignment.lua"
local LINES_PER_UPDATE = 8
local LISTENER_REVISION = 11

local function component(entity, kind)
  if not api.engine.entityExists(entity) then return nil end
  return api.engine.getComponent(entity, api.type.ComponentType[kind])
end

local function updateLine(entity, groups)
  local owner = component(entity, "PLAYER_OWNED")
  if not owner or owner.player ~= api.engine.util.getPlayer() then return end
  local current = component(entity, "LINE")
  if not current then return end
  local line = api.type.Line.new(current)
  local stops, changed = assignment.complete(line.stops, line.vehicleInfo.transportModes, groups)
  if not changed then return end
  line.stops = stops
  api.cmd.sendCommand(api.cmd.makeLineUpdateCmd(entity, line))
end

local function snapshot(entity)
  local construction = component(entity, "CONSTRUCTION")
  if not construction then return nil end
  local stations = {}
  for _, stationEntity in ipairs(construction.stations) do
    local station = component(stationEntity, "STATION")
    if station and not component(stationEntity, "EDGE_OBJECT") then
      local terminals = {}
      for _, terminal in ipairs(station.terminals) do
        if terminal.tag ~= nil then terminals[terminal.tag] = true end
      end
      if station.tag ~= nil and next(terminals) then
        stations[station.tag] = {
          entity = stationEntity,
          group = api.engine.system.stationGroupSystem.getStationGroup(stationEntity),
          terminals = terminals,
        }
      end
    end
  end
  return next(stations) and stations or nil
end

local function merge(groups, group, station, terminals, surviving)
  if not group or group < 0 then return end
  for tag in pairs(terminals) do
    if not surviving or surviving[tag] then
      groups[group] = groups[group] or {}
      groups[group][station] = groups[group][station] or {}
      groups[group][station][tag] = true
    end
  end
end

local function remapPending(pending, replacements)
  for lineEntity, groups in pairs(pending) do
    local updated = {}
    for group, stations in pairs(groups) do
      for entity, terminals in pairs(stations) do
        local replacement = replacements[entity]
        if replacement then
          merge(updated, replacement.group, replacement.entity, terminals, replacement.terminals)
        elseif replacement == nil then
          merge(updated, group, entity, terminals)
        end
      end
    end
    pending[lineEntity] = next(updated) and updated or nil
  end
end

local function queueLines(groups, pending)
  for group, stations in pairs(groups) do
    for _, entry in ipairs(api.engine.system.lineSystem.getLineStops(group)) do
      local entity = entry[1]
      local owner = component(entity, "PLAYER_OWNED")
      if owner and owner.player == api.engine.util.getPlayer() then
        pending[entity] = pending[entity] or {}
        for station, terminals in pairs(stations) do
          merge(pending[entity], group, station, terminals)
        end
      end
    end
  end
end

function data()
  return {
    update = function(_, state)
      local current = state:get() or {}
      if not state:hasEventSubscriptions() or current.listenerRevision ~= LISTENER_REVISION then
        state:subscribeToNoEvents()
        state:subscribeToEvent("onPreBuildProposal")
        state:subscribeToEvent("onPostBuildProposal")
        if current.listenerRevision ~= LISTENER_REVISION then
          current = { listenerRevision = LISTENER_REVISION }
          state:set(current)
        end
      end
      local pending = current.pendingLines
      if not pending then return end
      local processed = 0
      for entity, groups in pairs(pending) do
        local ok, reason = pcall(updateLine, entity, groups)
        if not ok then log.warning("[Auto Alternatives] line " .. tostring(entity) .. ": " .. tostring(reason)) end
        pending[entity] = nil
        processed = processed + 1
        if processed == LINES_PER_UPDATE then break end
      end
      current.pendingLines = next(pending) and pending or nil
      state:set(current)
    end,

    handleEvent = function(_, state, _, id, name, params)
      if id ~= "apply_command" then return end
      if name ~= "onPreBuildProposal" and name ~= "onPostBuildProposal" then return end
      local current = state:get() or {}
      local proposal = params[1]
      if name == "onPreBuildProposal" then
        current.before = {}
        for _, entity in ipairs(proposal.toRemove) do
          current.before[entity] = snapshot(entity)
        end
        state:set(current)
        return
      end

      local before, after, oldForNew, replacements = current.before or {}, {}, {}, {}
      for _, entity in ipairs(params[3]) do after[entity] = snapshot(entity) end
      for oldEntity, newIndex in pairs(proposal.old2new) do
        local newEntity = params[3][newIndex + 1]
        if newEntity then oldForNew[newEntity] = before[oldEntity] end
      end
      for _, oldEntity in ipairs(proposal.toRemove) do
        local newIndex = proposal.old2new[oldEntity]
        local newEntity = newIndex and params[3][newIndex + 1]
        local newStations = newEntity and after[newEntity] or {}
        for tag, station in pairs(before[oldEntity] or {}) do
          replacements[station.entity] = newStations[tag] or false
        end
      end

      local groups = {}
      for entity, stations in pairs(after) do
        local oldStations = oldForNew[entity] or {}
        for tag, station in pairs(stations) do
          local oldTerminals = oldStations[tag] and oldStations[tag].terminals or {}
          local added = {}
          for terminal in pairs(station.terminals) do
            if not oldTerminals[terminal] then added[terminal] = true end
          end
          merge(groups, station.group, station.entity, added)
        end
      end
      local pending = current.pendingLines or {}
      remapPending(pending, replacements)
      queueLines(groups, pending)
      current.before = nil
      current.pendingLines = next(pending) and pending or nil
      state:set(current)
    end,
  }
end
