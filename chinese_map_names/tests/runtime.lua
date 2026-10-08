world, sent, logs = {}, {}, {}
failures, editor, saves = 0, false, 0
unsupportedKinds, fullScans, enumerationCalls = {street = true}, 0, {}
deferred, queued = false, {}
unsafeNameCommands = 0
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
}
local function component(entity, kind)
  local item = world[entity]
  if not item or not item[kind] then return nil end
  if kind == "name" then return {name = item.name} end
  if kind == "construction" then return {fileName = item.construction} end
  if kind == "warehouse" then return {construction = item.parent or -1} end
  if kind == "depot" then return {maintenancePool = item.maintenancePool or 0} end
  return {}
end
local function displayed(entity)
  local item = world[entity]
  if not item then return nil end
  if item.name and item.name ~= "" then return item.name end
  if item.stem and item.stem ~= entity then return displayed(item.stem) .. (item.suffix or "") end
  return item.display
end
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
      getEntityNameStem = function(entity) return {displayed(entity), world[entity].stem or entity} end,
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
    find = function(name) return ({coal = 1, roadDepot = 2, maintenance = 3, warehouse = 4, hq = 5, landmark = 6, signal = 7, forest = 8})[name] or -1 end,
    get = function(id)
      return {description = {name = ({"煤矿", "道路车库", "维护设施", "仓库", "总部", "新天鹅堡", "信号灯", "伐木场"})[id]}}
    end,
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
  return ({["Line {lineNumber}"] = "线路{lineNumber}", ["Train {number}"] = "火车{number}",
    ["Tram {number}"] = "有轨电车{number}", ["Road Vehicle {number}"] = "道路载具{number}",
    ["Ship {number}"] = "船{number}", ["Aircraft {number}"] = "飞机{number}"})[value] or value
end
