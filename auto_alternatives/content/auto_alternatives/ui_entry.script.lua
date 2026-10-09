local react = ug_require "::/gui/main/react.lua"
local entryPoint = ug_require "::/gui/main/mod_entry_point.tl"
local lineUtil = ug_require "::/gui/line_vehicle_mgmt/line_util.tl"
local assignment = ug_require "xin_auto_alternatives_1::/auto_alternatives/assignment.lua"

local function complete(stops, entity, initialize)
  local lineModes, previous = {}, {}
  if entity and entity >= 0 and api.engine.entityExists(entity) then
    local line = api.engine.getComponent(entity, api.type.ComponentType.LINE)
    if line then
      lineModes = line.vehicleInfo.transportModes
      for _, stop in ipairs(line.stops) do
        previous[stop.stationGroup] = previous[stop.stationGroup] or {}
        table.insert(previous[stop.stationGroup], stop)
      end
    end
  end
  local choices, visits = {}, {}
  for index, stop in ipairs(stops) do
    local groupId = stop.stationGroup
    visits[groupId] = (visits[groupId] or 0) + 1
    if not initialize[index] then
      choices[index] = {}
      local old = previous[groupId] and previous[groupId][visits[groupId]]
      if old and (old.station ~= stop.station or old.terminal ~= stop.terminal)
        and api.engine.entityExists(groupId) then
        local group = api.engine.getComponent(groupId, api.type.ComponentType.STATION_GROUP)
        local stationId = group and group.stations[old.station + 1]
        local station = stationId and api.engine.entityExists(stationId)
          and api.engine.getComponent(stationId, api.type.ComponentType.STATION)
        local terminal = station and station.terminals[old.terminal + 1]
        if terminal and terminal.tag ~= nil then
          choices[index][stationId] = { [terminal.tag] = true }
        end
      end
    end
  end
  return assignment.complete(stops, lineModes, nil, choices)
end

local original = lineUtil.autoAssignTerminals
lineUtil.autoAssignTerminals = function(entity, path)
  local initialize, index = {}, 0
  for _, via in ipairs(path) do
    if via.stop then
      index = index + 1
      initialize[index] = via.stop.alternativeTerminals == nil
    end
  end
  local stops = original(entity, path)
  local ok, completed = pcall(complete, stops, entity, initialize)
  if ok then return completed end
  log.warning("[Auto Alternatives] Could not complete line terminals: " .. tostring(completed))
  return stops
end

local entry = react.RegisterPluginRecipe(
  entryPoint.ModEntryPointExtension, "XinAutoAlternativesEntry", function() return nil end
)

function data()
  return { entry = entry }
end
