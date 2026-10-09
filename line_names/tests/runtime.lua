components, stationTowns, catchables, pcBuildings = {}, {}, {}, {}
capacities, vehicles, stockCargo, scans, warnings = {}, {}, {}, {}, {}
currentPlayer, session, failCatchment, worldEntity = 7, {}, false, 999
components[999] = { GAME_TIME = { tickCount = 1, updateCount = 0 } }

local function entities(kind)
  -- Native world singletons are readable but cannot be globally enumerated.
  assert(kind ~= 'GAME_TIME', 'Cannot loop over this component type')
  assert(kind ~= 'TOWN_BUILDING', 'Use the native town-to-building map')
  scans[kind] = (scans[kind] or 0) + 1
  local result = {}
  for id, comp in pairs(components) do
    if comp[kind] then result[#result + 1] = id end
  end
  table.sort(result)
  return result
end

local types = {}
for _, kind in ipairs({ 'TOWN', 'TOWN_BUILDING', 'STATION', 'STATION_GROUP',
  'INDUSTRY', 'CONSTRUCTION', 'STOCK_LIST', 'WAREHOUSE', 'PERSON_CAPACITY',
  'LINE', 'TRANSPORT_VEHICLE', 'GAME_TIME' }) do types[kind] = kind end

api = {
  type = { ComponentType = types, enum = {
    Carrier = { ROAD = 0, RAIL = 1, TRAM = 2, WATER = 3, AIR = 4 },
    StockListType = { InputStock = 0, OutputStock = 1, StorageStock = 2 },
  } },
  res = { cargoTypeRep = {
    getPassengerCargoTypeId = function() return 7 end,
    get = function(id)
      return { name = ({ [0] = '煤炭', [1] = '食品', [2] = '铁矿石', [7] = '旅客' })[id] }
    end,
  } },
  engine = {
    entityExists = function(id) return components[id] ~= nil end,
    getEntitiesWithComponent = entities,
    getComponent = function(id, kind)
      assert(kind, 'Unknown native component type')
      return components[id] and components[id][kind]
    end,
    util = {
      getPlayer = function() return currentPlayer end,
      getWorld = function() return worldEntity end,
      getEntityName = function(id) return components[id] and components[id].name end,
      line = { getLineCapacityUsages = function(id, all)
        return capacities[id] and capacities[id][all and 'all' or 'current'] or {}
      end },
      stock = { getStockCargoTypes = function(id, index0)
        return stockCargo[id][index0 + 1]
      end },
    },
    system = {
      lineSystem = { getLinesForPlayer = function(player)
        local result = {}
        for _, id in ipairs(entities('LINE')) do
          if components[id].owner == player then result[#result + 1] = id end
        end
        return result
      end },
      townBuildingSystem = {
        getPersonCapacity2townBuildingMap = function() return pcBuildings end,
        getTown2BuildingMap = function()
          local result = {}
          for id, comp in pairs(components) do
            local building = comp.TOWN_BUILDING
            if building then
              result[building.town] = result[building.town] or {}
              table.insert(result[building.town], id)
            end
          end
          return result
        end,
      },
      streetConnectorSystem = { getConstructionClosestTown = function(id) return components[id].town end },
      stationSystem = { getTown = function(id) return stationTowns[id] or -1 end },
      stationGroupSystem = { getCarriers = function(id, station0, terminal0)
        assert(station0 >= -1 and terminal0 >= -1)
        return { components[id].carriers or { 0 }, {} }
      end },
      catchmentAreaSystem = { getStationCatchables = function(id, cargo)
        if failCatchment then error('stale catchment') end
        return catchables[id] and catchables[id][cargo and 'cargo' or 'passenger'] or {}
      end },
      transportVehicleSystem = { getLineVehicles = function(id) return vehicles[id] or {} end },
    },
  },
  cmd = setmetatable({}, { __index = function() error('Preview must never send commands') end }),
}
log = { warning = function(message) warnings[#warnings + 1] = message end }

function advance() components[999].GAME_TIME.tickCount = components[999].GAME_TIME.tickCount + 1 end
