local selection = ug_require "xin_auto_alternatives_1::/auto_alternatives/selection.lua"
local assignment = {}

local function component(entity, kind)
  if not api.engine.entityExists(entity) then return nil end
  return api.engine.getComponent(entity, api.type.ComponentType[kind])
end

function assignment.complete(stops, transportModes, groups, stopChoices)
  local enum = api.type.enum.TransportMode
  local lineModes = selection.vehicleModes(transportModes, enum)
  if lineModes[enum.TRAIN] or lineModes[enum.ELECTRIC_TRAIN] then return stops, false end
  local result, changes, groupCache = {}, {}, {}
  for index, stop in ipairs(stops) do
    result[index] = stop
    if groups == nil or groups[stop.stationGroup] then
      local cached = groupCache[stop.stationGroup]
      if cached == nil then
        local group = component(stop.stationGroup, "STATION_GROUP")
        local stations = {}
        if group then
          for _, entity in ipairs(group.stations) do
            if not component(entity, "EDGE_OBJECT") then
              stations[entity] = component(entity, "STATION")
            end
          end
        end
        cached = group and { group = group, stations = stations } or false
        groupCache[stop.stationGroup] = cached
      end
      if cached then
        local group, stations = cached.group, cached.stations
        local modes = lineModes
        if next(modes) == nil then
          local station = stations[group.stations[stop.station + 1]]
          local primary = station and station.terminals[stop.terminal + 1]
          modes = primary and selection.vehicleModes(primary.transportModes, enum) or {}
        end
        local allowed = groups and groups[stop.stationGroup]
        if stopChoices then allowed = stopChoices[index] end
        local additions, primarySelected = {}, false
        if not modes[enum.TRAIN] and not modes[enum.ELECTRIC_TRAIN] then
          additions, primarySelected = selection.additions(stop, group, stations, modes, allowed)
        end
        if #additions > 0 or primarySelected then
          local alternatives = {}
          for _, terminal in ipairs(stop.alternativeTerminals) do
            if terminal.station ~= stop.station or terminal.terminal ~= stop.terminal then
              alternatives[#alternatives + 1] = api.type.StationTerminal.new(terminal.station, terminal.terminal)
            end
          end
          for _, terminal in ipairs(additions) do
            alternatives[#alternatives + 1] = api.type.StationTerminal.new(terminal.station, terminal.terminal)
          end
          changes[#changes + 1] = { stop = stop, alternatives = alternatives }
        end
      end
    end
  end
  -- Keep the native assignment intact if any later lookup or conversion fails;
  -- the GUI hook can then return its original result without partial changes.
  for _, change in ipairs(changes) do
    change.stop.alternativeTerminals = change.alternatives
  end
  return result, #changes > 0
end

return assignment
