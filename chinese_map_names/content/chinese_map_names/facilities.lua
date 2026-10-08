local names = ug_require "xin_chinese_map_names_1::/chinese_map_names/entity_names.lua"
local M = {}

function M.parent(entity)
  local types = api.type.ComponentType
  local connector = api.engine.system.streetConnectorSystem
  local function construction(candidate)
    return candidate and candidate >= 0 and api.engine.entityExists(candidate)
      and api.engine.getComponent(candidate, types.CONSTRUCTION) and candidate or nil
  end
  if api.engine.getComponent(entity, types.INDUSTRY) then
    -- Match the native industry window; retain the documented industry API
    -- as a fallback for objects not represented by a subconstruction.
    return construction(connector.getConstructionEntityForSubconstruction(entity))
      or construction(connector.getConstructionEntityForIndustry(entity))
  elseif api.engine.getComponent(entity, types.STATION) then
    return construction(connector.getConstructionEntityForStation(entity))
  elseif api.engine.getComponent(entity, types.VEHICLE_DEPOT) then
    return construction(connector.getConstructionEntityForDepot(entity))
  end
  local warehouse = api.engine.getComponent(entity, types.WAREHOUSE)
  return warehouse and construction(warehouse.construction) or nil
end

function M.collect(industryOnly)
  local types = api.type.ComponentType
  local facilities, parents = {}, {}
  local function remember(entity, label)
    if entity and entity >= 0 and api.engine.entityExists(entity) then
      if not api.engine.getComponent(entity, types.TOWN)
        and not api.engine.getComponent(entity, types.BASE_EDGE_STREET)
        and not api.engine.getComponent(entity, types.SIM_PERSON) then
        facilities[entity] = facilities[entity] or label
      end
    end
  end
  local specs = { {types.INDUSTRY, "产业"} }
  if not industryOnly then
    specs = { {types.INDUSTRY, "产业"}, {types.STATION, "车站"}, {types.STATION_GROUP, "车站"},
      {types.VEHICLE_DEPOT, "车库"}, {types.WAREHOUSE, "仓库"} }
  end
  for _, spec in ipairs(specs) do
    for _, entity in ipairs(names.entities(spec[1])) do
      local label = spec[2]
      if spec[1] == types.VEHICLE_DEPOT then
        local depot = api.engine.getComponent(entity, types.VEHICLE_DEPOT)
        if depot.maintenancePool and depot.maintenancePool > 0 then label = "维护设施" end
      end
      remember(entity, label)
      local stem = api.engine.util.getEntityNameStem(entity)
      if stem then remember(stem[2], label) end
      local parent = M.parent(entity)
      if parent and parent >= 0 then parents[entity] = parent; remember(parent, label) end
    end
  end
  -- Headquarters, landmarks, signals and independent facilities need not have
  -- an industry/station child, but are still construction entities.
  if not industryOnly then
    for _, entity in ipairs(names.entities(types.CONSTRUCTION)) do remember(entity, "设施") end
  end
  local entities = {}
  for entity in pairs(facilities) do entities[#entities + 1] = entity end
  table.sort(entities)
  local ordered, visited = {}, {}
  local function visit(entity)
    if visited[entity] or not facilities[entity] then return end
    visited[entity] = true
    local stem = api.engine.util.getEntityNameStem(entity)
    if stem and stem[2] and stem[2] ~= entity then visit(stem[2]) end
    if parents[entity] then visit(parents[entity]) end
    ordered[#ordered + 1] = entity
  end
  -- Entity IDs do not encode ownership: a replaced building may have a newer
  -- ID than its children. Rename name sources before all inheriting objects.
  for _, entity in ipairs(entities) do visit(entity) end
  return ordered, facilities, parents
end

local directions = {
  Central = "中心", North = "北", South = "南", East = "东", West = "西",
  Upper = "上层", Lower = "下层", Annex = "附属", Branch = "支线", Transfer = "换乘",
  Exchange = "枢纽", Sidings = "侧线", Halt = "停靠点",
}
local kinds = {
  {"Road Depot", "道路车库"}, {"Train Depot", "列车车库"}, {"Tram Depot", "有轨电车车库"},
  {"Ship Depot", "船库"}, {"Maintenance Building", "维护设施"}, {"Underground Stop", "地下停靠站"},
  {"Headquarters", "总部"}, {"Warehouse", "仓库"}, {"Heliport", "直升机场"},
  {"Airport", "机场"}, {"Port", "港口"}, {"Station", "车站"}, {"Signal", "信号灯"}, {"Waypoint", "航点"},
}

function M.plan(aliases, townNames, add, industryOnly)
  local types = api.type.ComponentType
  local entities, labels, parents = M.collect(industryOnly)
  local aliasKeys, used = {}, {}
  for old in pairs(aliases) do aliasKeys[#aliasKeys + 1] = old end
  table.sort(aliasKeys, function(a, b) return #a == #b and a < b or #a > #b end)
  for _, entity in ipairs(entities) do
    local name = api.engine.util.getEntityName(entity)
    if name then used[name] = true end
  end
  for __, entity in ipairs(entities) do
    local old = api.engine.util.getEntityName(entity)
    if names.needsChineseName(old) and names.hasName(entity) then
      local base, replaced, remainder
      local function matchBase(candidate, direction)
        for _, key in ipairs(aliasKeys) do
          if candidate == key or candidate:sub(1, #key + 1) == key .. " " then
            base, remainder = aliases[key], candidate:sub(#key + 1)
            if direction then remainder = " " .. direction .. remainder end
            replaced = base .. remainder
            return true
          end
        end
      end
      -- "North Bend" is a complete town name, not the north side of "Bend".
      if not matchBase(old) then
        local prefix, rest = old:match("^(%a+) (.+)$")
        if directions[prefix] then matchBase(rest, prefix) end
      end
      if not replaced or names.needsChineseName(replaced) then
        local label = labels[entity]
        for _, kind in ipairs(kinds) do
          if (remainder or old):find("%f[%a]" .. kind[1] .. "%f[%A]") then label = kind[2]; break end
        end
        local constructionEntity = parents[entity] or entity
        local construction = api.engine.getComponent(constructionEntity, types.CONSTRUCTION)
        if construction then
          base = townNames[api.engine.system.streetConnectorSystem.getConstructionClosestTown(constructionEntity)] or base
          local id = api.res.constructionRep.find(construction.fileName)
          if id and id >= 0 then
            local resource = api.res.constructionRep.get(id)
            local description = resource and resource.description
            local translated = description and description.name and _(description.name)
            if translated and not names.needsChineseName(translated) then label = translated end
          end
        end
        replaced = (base and (base .. " ") or "") .. label
        for word in (remainder or old):gmatch("%a+") do
          if directions[word] then replaced = replaced .. directions[word] end
        end
        local number = old:match("%s(#?%d+)$")
        if number then replaced = replaced .. " " .. number end
      end
      local candidate, suffix = replaced, 1
      while used[candidate] do suffix = suffix + 1; candidate = replaced .. " " .. suffix end
      used[candidate] = true
      -- Only NAME-bearing targets are queued. Nameless child facilities keep
      -- inheriting their parent's name rather than gaining a forced override.
      add(entity, candidate, true)
    end
  end
end

return M
