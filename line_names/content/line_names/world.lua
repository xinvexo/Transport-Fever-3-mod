-- Read-only adapter for native entities. IDs in cargo vectors are zero-based;
-- vectors and station/terminal arrays use Lua's one-based indexing.
local M = {}

local function component(entity, kind)
  if entity and entity >= 0 and api.engine.entityExists(entity) then
    return api.engine.getComponent(entity, api.type.ComponentType[kind])
  end
end

local function sole(values)
  local result
  for key in pairs(values) do
    if result ~= nil then return nil end
    result = key
  end
  return result
end

local function union(target, source)
  for key in pairs(source) do target[key] = true end
end

function M.new()
  local ctx = { stations = {}, stocks = {}, towns = {}, industries = {} }
  local system, util = api.engine.system, api.engine.util
  local passenger = api.res.cargoTypeRep.getPassengerCargoTypeId()
  local passengerBuildings
  local stockOwners, townStockOwners

  function ctx.town(id)
    if ctx.towns[id] then return ctx.towns[id] end
    if not component(id, "TOWN") then return nil end
    ctx.towns[id] = { id = id, name = util.getEntityName(id) }
    return ctx.towns[id]
  end

  local function ownerOf(stock)
    local function remember(result, entity, kind)
      local comp = component(entity, kind)
      if comp and comp.stockList and comp.stockList >= 0 then
        result[comp.stockList] = { id = entity, kind = kind, town = comp.town }
      end
    end
    if not stockOwners then
      local result = {}
      for _, kind in ipairs({ "INDUSTRY", "WAREHOUSE" }) do
        for _, entity in ipairs(api.engine.getEntitiesWithComponent(api.type.ComponentType[kind])) do
          remember(result, entity, kind)
        end
      end
      stockOwners = result
    end
    if stockOwners[stock] then return stockOwners[stock] end
    if townStockOwners then return townStockOwners[stock] end
    -- Factory-to-factory freight never needs the whole town-building index.
    -- Build it once in this synchronous plan only when a catchable stock was
    -- not resolved as an industry or warehouse.
    -- Match the native town UI's building lookup instead of assuming every
    -- component type supports a global entity enumeration.
    local result = {}
    for _, buildings in pairs(system.townBuildingSystem.getTown2BuildingMap()) do
      for _, entity in ipairs(buildings) do remember(result, entity, "TOWN_BUILDING") end
    end
    townStockOwners = result
    return townStockOwners[stock]
  end

  local function stockInfo(id)
    if ctx.stocks[id] then return ctx.stocks[id] end
    local info = { input = {}, output = {} }
    local stock = component(id, "STOCK_LIST")
    if stock then
      for index, entry in ipairs(stock.stocks) do
        for _, cargo in ipairs(util.stock.getStockCargoTypes(id, index - 1)) do
          if entry.type ~= api.type.enum.StockListType.OutputStock then info.input[cargo] = true end
          if entry.type ~= api.type.enum.StockListType.InputStock then info.output[cargo] = true end
        end
      end
    end
    ctx.stocks[id] = info
    return info
  end

  local function industry(id)
    if ctx.industries[id] then return ctx.industries[id] end
    local comp = component(id, "INDUSTRY")
    if not comp then return nil end
    local town
    if component(comp.construction, "CONSTRUCTION") then
      town = ctx.town(system.streetConnectorSystem.getConstructionClosestTown(comp.construction))
    end
    local result = { id = id, name = util.getEntityName(id), town = town }
    ctx.industries[id] = result
    return result
  end

  local function stationInfo(id, freight)
    local key = tostring(id) .. (freight and ":cargo" or ":passenger")
    if ctx.stations[key] then return ctx.stations[key] end
    local result = { industries = {}, towns = {}, unknown = false }
    for _, entity in ipairs(system.catchmentAreaSystem.getStationCatchables(id, freight) or {}) do
      if freight then
        local owner = ownerOf(entity)
        if owner and owner.kind == "INDUSTRY" then
          result.industries[owner.id] = { place = industry(owner.id), stock = stockInfo(entity) }
        elseif owner and owner.kind == "TOWN_BUILDING" then
          local town = ctx.town(owner.town)
          if town then
            result.towns[town.id] = result.towns[town.id] or { place = town, input = {}, output = {} }
            local info = stockInfo(entity)
            union(result.towns[town.id].input, info.input)
            union(result.towns[town.id].output, info.output)
          else result.unknown = true end
        else result.unknown = true end
      else
        local place = industry(entity)
        local capacity = component(entity, "PERSON_CAPACITY")
        if place and capacity and capacity.capacity > 0 then
          result.industries[place.id] = { place = place }
        elseif capacity and capacity.capacity > 0 then
          -- The native reverse map is needed only for town passenger stops;
          -- freight and industry-only previews should not copy the whole map.
          passengerBuildings = passengerBuildings or system.townBuildingSystem.getPersonCapacity2townBuildingMap()
          local building = component(passengerBuildings[entity], "TOWN_BUILDING")
          local town = building and ctx.town(building.town)
          if town then result.towns[town.id] = { place = town }
          else result.unknown = true end
        end
      end
    end
    ctx.stations[key] = result
    return result
  end

  local function endpoint(stop, kind, cargo)
    local group = component(stop.stationGroup, "STATION_GROUP")
    local fallback = { kind = "station", id = stop.stationGroup,
      name = util.getEntityName(stop.stationGroup), towns = {} }
    if not group then return fallback end
    local indices = {}
    if stop.station and stop.station >= 0 then indices[stop.station + 1] = true end
    for _, alternative in ipairs(stop.alternativeTerminals or {}) do
      if alternative.station and alternative.station >= 0 then indices[alternative.station + 1] = true end
    end
    local industries, towns, stationTowns, unknown = {}, {}, {}, false
    local freight = kind == "freight"
    for index in pairs(indices) do
      local station = group.stations[index]
      if component(station, "STATION") then
        local town = ctx.town(system.stationSystem.getTown(station))
        if town then stationTowns[town.id] = town end
        if kind == "passenger" or freight then
          local info = stationInfo(station, freight)
          unknown = unknown or info.unknown
          for id, candidate in pairs(info.industries) do
            if not cargo or candidate.stock.input[cargo] or candidate.stock.output[cargo] then
              industries[id] = candidate.place
            end
          end
          for id, candidate in pairs(info.towns) do
            if not cargo or candidate.input[cargo] or candidate.output[cargo] then
              towns[id] = candidate.place
            end
          end
        end
      else unknown = true end
    end
    for id, town in pairs(stationTowns) do fallback.towns[id] = town end
    for id, town in pairs(towns) do fallback.towns[id] = town end
    for _, place in pairs(industries) do
      if place.town then fallback.towns[place.town.id] = place.town end
    end
    local industryId, townId = sole(industries), sole(towns)
    if industryId and not next(towns) and not unknown then
      local place = industries[industryId]
      return { kind = "industry", id = place.id, name = place.name, town = place.town,
        towns = place.town and { [place.town.id] = place.town } or {} }
    end
    if townId and not next(industries) and not unknown then
      local place = towns[townId]
      return { kind = "town", id = place.id, name = place.name, town = place,
        towns = { [place.id] = place } }
    end
    -- Stations without catchables (e.g. interchange hubs) may still have a
    -- town assignment. Do not let it hide an ambiguous industry or warehouse.
    if not next(industries) and not next(towns) and not unknown and sole(stationTowns)
      and (kind == "passenger" or freight) then
      local place = stationTowns[sole(stationTowns)]
      return { kind = "town", id = place.id, name = place.name, town = place,
        towns = { [place.id] = place } }
    end
    fallback.town = sole(fallback.towns) and fallback.towns[sole(fallback.towns)] or nil
    return fallback
  end

  function ctx.line(id)
    local line = component(id, "LINE")
    if not line then return nil end
    local record = { id = id, name = util.getEntityName(id), stops = {} }
    local configured = {}
    for _, stop in ipairs(line.stops) do
      local config = stop.stopConfig
      for index, enabled in ipairs(config and config.load or {}) do
        if enabled and (not config.maxLoad or not config.maxLoad[index] or config.maxLoad[index] > 0) then
          configured[index - 1] = true
        end
      end
    end
    local supported, loaded = {}, nil
    for index, usage in pairs(util.line.getLineCapacityUsages(id, true)) do
      if usage.capacity > 0 then supported[index - 1] = true end
    end
    local function currentLoad()
      if not loaded then
        loaded = {}
        for index, usage in pairs(util.line.getLineCapacityUsages(id, false)) do
          if usage.used > 0 then loaded[index - 1] = true end
        end
      end
      return loaded
    end
    local candidates = {}
    if next(supported) then
      for cargo in pairs(supported) do
        if not next(configured) or configured[cargo] or currentLoad()[cargo] then candidates[cargo] = true end
      end
    else union(candidates, configured) end
    local freightTypes, loadedFreight = {}, {}
    for cargo in pairs(candidates) do
      if cargo ~= passenger then freightTypes[cargo] = true end
    end
    if candidates[passenger] and next(freightTypes) then record.kind = "mixed"
    elseif candidates[passenger] then record.kind = "passenger"
    elseif next(freightTypes) then record.kind = "freight"
    else record.kind = "unknown" end
    local cargo = sole(freightTypes)
    if record.kind == "freight" and not cargo then
      for candidate in pairs(currentLoad()) do
        if freightTypes[candidate] then loadedFreight[candidate] = true end
      end
      cargo = sole(loadedFreight)
    end
    if record.kind == "freight" and cargo then
      record.cargo = api.res.cargoTypeRep.get(cargo).name
    else cargo = nil end

    local carriers = {}
    for _, vehicle in ipairs(system.transportVehicleSystem.getLineVehicles(id)) do
      local tv = component(vehicle, "TRANSPORT_VEHICLE")
      if tv then carriers[tv.carrier] = true end
    end
    if not next(carriers) then
      local common
      for _, stop in ipairs(line.stops) do
        local result = component(stop.stationGroup, "STATION_GROUP")
          and system.stationGroupSystem.getCarriers(stop.stationGroup, stop.station, stop.terminal)
        local choices = {}
        for _, carrier in ipairs(result and result[1] or {}) do choices[carrier] = true end
        if not common then common = choices
        else
          for carrier in pairs(common) do if not choices[carrier] then common[carrier] = nil end end
        end
      end
      carriers = common or {}
    end
    local carrier = sole(carriers)
    for _, name in ipairs({ "ROAD", "RAIL", "TRAM", "WATER", "AIR" }) do
      if carrier == api.type.enum.Carrier[name] then record.carrier = name end
    end
    for _, stop in ipairs(line.stops) do
      if component(stop.stationGroup, "STATION_GROUP") then
        record.stops[#record.stops + 1] = { group = stop.stationGroup,
          point = endpoint(stop, record.kind, cargo) }
      else record.invalid = true end
    end
    return record
  end
  return ctx
end

return M
