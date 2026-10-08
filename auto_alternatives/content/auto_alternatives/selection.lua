local selection = {}

function selection.vehicleModes(modes, enum)
  local result = {}
  for mode, enabled in pairs(modes) do
    if enabled and mode ~= enum.PERSON and mode ~= enum.CARGO then result[mode] = true end
  end
  return result
end

local function compatible(primary, candidate, lineModes)
  local modeMatches = false
  for mode, enabled in pairs(primary.transportModes) do
    if enabled and candidate.transportModes[mode] and lineModes[mode] then
      modeMatches = true
      break
    end
  end
  if not modeMatches then return false end

  return (primary.passengersLoad and candidate.passengersLoad)
    or (primary.passengersUnload and candidate.passengersUnload)
    or (primary.cargoLoad and candidate.cargoLoad)
    or (primary.cargoUnload and candidate.cargoUnload)
end

-- Find missing alternatives and any overlap with the primary terminal.
function selection.additions(stop, group, stations, lineModes, allowed)
  local stationEntity = group.stations[stop.station + 1]
  local primaryStation = stationEntity and stations[stationEntity]
  local primary = primaryStation and primaryStation.terminals[stop.terminal + 1]
  if not primary then return {}, false end

  local selected, primarySelected = {}, false
  for _, terminal in ipairs(stop.alternativeTerminals) do
    if terminal.station == stop.station and terminal.terminal == stop.terminal then
      primarySelected = true
    else
      selected[terminal.station] = selected[terminal.station] or {}
      selected[terminal.station][terminal.terminal] = true
    end
  end

  local additions = {}
  for stationIndex, entity in ipairs(group.stations) do
    local station = stations[entity]
    if station then
      for terminalIndex, terminal in ipairs(station.terminals) do
        local s, t = stationIndex - 1, terminalIndex - 1
        if (s ~= stop.station or t ~= stop.terminal)
          and not (selected[s] and selected[s][t])
          and (allowed == nil or (allowed[entity] and allowed[entity][terminal.tag]))
          and compatible(primary, terminal, lineModes) then
          additions[#additions + 1] = { station = s, terminal = t }
        end
      end
    end
  end
  return additions, primarySelected
end

return selection
