world, sent, logs = {}, {}, {}
failures, editor, saves = 0, false, 0
unsupportedKinds, fullScans, enumerationCalls = {street = true}, 0, {}
deferred, queued = false, {}
unsafeNameCommands = 0
closestTownQueries, descriptorQueries = 0, 0
local vecMeta = {}
local function vec(x, y, z, owner)
  return setmetatable({x = x or 0, y = y or 0, z = z or 0, owner = owner}, vecMeta)
end
vecMeta.__add = function(a, b) return vec(a.x + b.x, a.y + b.y, a.z + b.z) end
vecMeta.__mul = function(a, b) return vec(a.x * b, a.y * b, a.z * b) end
-- Mirror the table branch of base/init.lua's unpack override in every test.
local luaUnpack = table.unpack
table.unpack = function(values) return luaUnpack(values) end
local function copy(value)
  if type(value) ~= "table" then return value end
  local result = {}
  for k, v in pairs(value) do result[k] = copy(v) end
  return result
end
state = {
  value = {},
  get = function(self) return copy(self.value) end,
  set = function(self, value) self.value = copy(value); saves = saves + 1 end,
}
local types = {
  NAME = "name", TOWN = "town", BASE_EDGE_STREET = "street", SIM_PERSON = "person",
  INDUSTRY = "industry", STATION = "station", STATION_GROUP = "group", CONSTRUCTION = "construction",
  VEHICLE_DEPOT = "depot", WAREHOUSE = "warehouse", LINE = "line", TRANSPORT_VEHICLE = "vehicle", PLAYER = "player",
  BOUNDING_VOLUME = "bounds",
}
local function component(entity, kind)
  local item = world[entity]
  if item and kind == "bounds" and item.town then
    local p = item.position or {0, 0, 0}
    return {bbox = {min = vec(p[1], p[2], p[3]), max = vec(p[1], p[2], p[3])}}
  end
  if not item or not item[kind] then return nil end
  if kind == "name" then return {name = item.name} end
  if kind == "construction" then
    local p = item.position or {0, 0, 0}
    return {fileName = item.construction, industries = item.industries or {}, stations = item.stations or {},
      subconstructions = item.subconstructions or item.industries or {},
      transf = {getTransl = function() return vec(p[1], p[2], p[3], entity) end}}
  end
  if kind == "station" then return {terminals = item.terminals or {}} end
  if kind == "industry" then return {construction = item.industryConstruction or item.parent or item.subParent or -1} end
  if kind == "group" then return {stations = item.stations or {}} end
  if kind == "warehouse" then return {construction = item.parent or -1} end
  if kind == "depot" then return {maintenancePool = item.maintenancePool or 0} end
  return {}
end
local function displayed(entity)
  local item = world[entity]
  if not item then return nil end
  if item.name and item.name ~= "" then return item.name end
  if item.industry and item.stem then return displayed(item.stem) end
  if item.station and item.parent and world[item.parent] and world[item.parent].construction and not item.suffix then
    local descriptor = resources[world[item.parent].construction] or {}
    local template = descriptor.subConstructionNamePrefix
    if not template or template == "" then template = "{constructionName} {subConstructionType}" end
    return (template:gsub("{constructionName}", function() return displayed(item.parent) end)
      :gsub("{subConstructionType}", function() return _("Station") end))
  end
  if item.stem and item.stem ~= entity then return displayed(item.stem) .. (item.suffix or "") end
  return item.display
end
resources = {
  coal = {description = {name = "煤矿"}, isIndustry = true, namePrefix = "", subConstructionNamePrefix = ""},
  roadDepot = {description = {name = "道路车库"}, isIndustry = false, namePrefix = "{townName}道路车库", subConstructionNamePrefix = "{constructionName}"},
  maintenance = {description = {name = "维护设施"}, isIndustry = false, namePrefix = "{townName}维护设施", subConstructionNamePrefix = "{constructionName}"},
  warehouse = {description = {name = "仓库"}, isIndustry = false, namePrefix = "{townName}仓库", subConstructionNamePrefix = ""},
  hq = {description = {name = "总部"}, isIndustry = false, namePrefix = "{townName}总部", subConstructionNamePrefix = ""},
  landmark = {description = {name = "新天鹅堡"}, isIndustry = false, namePrefix = "", subConstructionNamePrefix = ""},
  signal = {description = {name = "信号灯"}, isIndustry = false, namePrefix = "", subConstructionNamePrefix = ""},
  forest = {description = {name = "伐木营地"}, isIndustry = true, namePrefix = "", subConstructionNamePrefix = ""},
  farm = {description = {name = "作物农场"}, isIndustry = true, namePrefix = "", subConstructionNamePrefix = ""},
  livestock_farm = {description = {name = "牲畜养殖场"}, isIndustry = true, namePrefix = "", subConstructionNamePrefix = ""},
  oil_well = {description = {name = "油井"}, isIndustry = true, namePrefix = "", subConstructionNamePrefix = ""},
  oil_platform = {description = {name = "采油平台"}, isIndustry = true, namePrefix = "", subConstructionNamePrefix = ""},
}
local resourceNames, resourceIds = {}, {}
api = {
  type = {ComponentType = types},
  engine = {
    entityExists = function(entity) return world[entity] ~= nil end,
    getComponent = component,
    getEntitiesWithComponent = function(kind)
      enumerationCalls[kind] = (enumerationCalls[kind] or 0) + 1
      if unsupportedKinds[kind] then error("Cannot loop over this component type") end
      local result = {}
      for entity, item in pairs(world) do if item[kind] then result[#result + 1] = entity end end
      return result
    end,
    forEachEntity = function(callback)
      fullScans = fullScans + 1
      for entity in pairs(world) do callback(entity) end
    end,
    config = {getModParams = function() return {[""] = {isMapEditor = editor}} end},
    util = {
      getEntityName = displayed,
      town = {getClosestTown = function(position)
        closestTownQueries = closestTownQueries + 1
        if position.owner and world[position.owner].nearestTown ~= nil then return world[position.owner].nearestTown end
        local best, distance = -1, math.huge
        for entity, value in pairs(world) do
          if value.town then
            local p = value.position or {0, 0, 0}
            local d = (position.x-p[1])^2 + (position.y-p[2])^2 + (position.z-p[3])^2
            if d < distance then best, distance = entity, d end
          end
        end
        return best
      end},
      getEntityNameStem = function(entity)
        local source = world[entity].stem or entity
        return {displayed(source), source}
      end,
    },
    system = {streetConnectorSystem = {
      getConstructionEntityForSubconstruction = function(entity)
        assert(world[entity].industry, "Only industries use the native subconstruction lookup here")
        return world[entity].subParent or world[entity].parent or -1
      end,
      getConstructionEntityForStation = function(entity) return world[entity].parent or -1 end,
      getConstructionEntityForIndustry = function(entity) return world[entity].parent or -1 end,
      getConstructionEntityForDepot = function(entity) return world[entity].parent or -1 end,
      getConstructionClosestTown = function(entity) return world[entity].nearestTown or -1 end,
    }},
  },
  res = {constructionRep = {
    find = function(name)
      if not resources[name] then return -1 end
      if not resourceIds[name] then resourceNames[#resourceNames + 1] = name; resourceIds[name] = #resourceNames end
      return resourceIds[name]
    end,
    getAsTable = function(id) descriptorQueries = descriptorQueries + 1; return copy(resources[resourceNames[id]]) end,
    get = function() error("The final native prefixes must be read through getAsTable") end,
  }},
  cmd = {
    makeEntitySetNameCmd = function(entity, name, force)
      if not component(entity, "name") then
        unsafeNameCommands = unsafeNameCommands + 1
        error("Native fatal: forced rename requires an existing NAME component")
      end
      return {entity = entity, name = name, force = force}
    end,
    sendCommand = function(command, callback)
      assert(callback == nil, "Callbacks are currently disallowed")
      sent[#sent + 1] = command
      if failures > 0 then
        failures = failures - 1
      elseif deferred then
        queued[#queued + 1] = command
      else
        world[command.entity].name = command.name
      end
    end,
  },
}
function flushCommands()
  for _, command in ipairs(queued) do
    if world[command.entity] then world[command.entity].name = command.name end
  end
  queued = {}
end
log = {
  message = function(message) logs[#logs + 1] = message end,
  warning = function(message) logs[#logs + 1] = message end,
}
function _(value)
  return ({["Station"] = "站点", ["Line {lineNumber}"] = "线路{lineNumber}", ["Train {number}"] = "火车{number}",
    ["Tram {number}"] = "有轨电车{number}", ["Road Vehicle {number}"] = "道路载具{number}",
    ["Ship {number}"] = "船{number}", ["Aircraft {number}"] = "飞机{number}",
    ["{townName} Station"] = "{townName} 车站", ["{townName} Road Depot"] = "{townName}道路车库",
    ["{townName} Maintenance Building"] = "{townName}维护设施", ["{townName} Warehouse"] = "{townName}仓库",
    ["{townName} Headquarters"] = "{townName}总部", ["{townName} Signal #{number}"] = "{townName}信号灯#{number}",
    ["{stationName} Central"] = "{stationName}中心", ["{stationName} West"] = "{stationName}西",
    ["{stationName} North"] = "{stationName}北", ["{stationName} East"] = "{stationName}东",
    ["{stationName} South"] = "{stationName}南", ["{stationName} #{number}"] = "{stationName} #{number}"})[value] or value
end
