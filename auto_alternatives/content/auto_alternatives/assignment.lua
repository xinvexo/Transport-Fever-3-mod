local selection = ug_require "xin_auto_alternatives_1::/auto_alternatives/selection.lua"
local assignment = {}

local function component(entity, kind)
  if not api.engine.entityExists(entity) then return nil end
  return api.engine.getComponent(entity, api.type.ComponentType[kind])
end

function assignment.complete(stops, transportModes, groups, stopChoices)
  local enum = api.type.enum.TransportMode
  local lineModes = selection.vehicleModes(transportModes, enum)
  local result, changed = {}, false
  for index, stop in ipairs(stops) do
    result[index] = stop
    if groups == nil or groups[stop.stationGroup] then
      local group = component(stop.stationGroup, "STATION_GROUP")
      if group then
        local stations = {}
        for _, entity in ipairs(group.stations) do
          if not component(entity, "EDGE_OBJECT") then
            stations[entity] = component(entity, "STATION")
          end
        end
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
          stop.alternativeTerminals = alternatives
          changed = true
        end
      end
    end
  end
  return result, changed
end

return assignment
