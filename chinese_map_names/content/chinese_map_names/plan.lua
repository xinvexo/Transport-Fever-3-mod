local person = ug_require "xin_chinese_map_names_1::/chinese_map_names/person.lua"
local names = ug_require "xin_chinese_map_names_1::/chinese_map_names/entity_names.lua"
local facilities = ug_require "xin_chinese_map_names_1::/chinese_map_names/facilities.lua"
local M = {}
M.hasChinese, M.needsChineseName, M.audit = names.hasChinese, names.needsChineseName, names.audit

-- Local randomness keeps the migration independent of simulation RNG state.
local function randomFor(seed)
  return function(limit)
    seed = (seed * 48271) % 2147483647
    return seed % limit + 1
  end
end

local function allocator(source, reserved, random)
  local pool, seen = {}, {}
  for _, name in ipairs(source) do
    if not seen[name] then pool[#pool + 1], seen[name] = name, true end
  end
  assert(#pool > 0, "Native Chinese name list is empty")
  for i = #pool, 2, -1 do
    local j = random(i)
    pool[i], pool[j] = pool[j], pool[i]
  end
  local index = 0
  return function()
    local name
    repeat
      index = index + 1
      local round = math.floor((index - 1) / #pool)
      name = pool[(index - 1) % #pool + 1] .. (round > 0 and (" " .. (round + 1)) or "")
    until not reserved[name]
    reserved[name] = true
    return name
  end
end

local function build(towns, streets)
  local types = api.type.ComponentType
  local entries, planned, aliases, townNames = {}, {}, {}, {}
  local entities, ownName = names.entities, names.ownName
  local function add(entity, name, includeDisplayed, nativeTown, nativeTownName, nativeOwner)
    if not names.hasName(entity) then return end
    local before = ownName(entity)
    local readDisplay = not before and includeDisplayed or false
    if readDisplay then before = api.engine.util.getEntityName(entity) end
    if before and name and before ~= name and not planned[entity] then
      entries[#entries + 1] = {
        entity = entity, before = before, after = name, attempts = 0, readDisplay = readDisplay,
        nativeTown = nativeTown, nativeTownName = nativeTownName,
        nativeOwner = nativeOwner,
      }
      planned[entity] = name
    end
  end

  local townEntities = entities(types.TOWN)
  local reserved = {}
  for _, entity in ipairs(townEntities) do
    local name = api.engine.util.getEntityName(entity)
    if name then reserved[name] = true end
  end
  local random = randomFor((townEntities[1] or 1) % 2147483646 + 1)
  local nextTown = allocator(towns, reserved, random)
  for _, entity in ipairs(townEntities) do
    local old = api.engine.util.getEntityName(entity)
    local name = old
    if names.needsChineseName(old) and names.hasName(entity) then
      name = nextTown()
      add(entity, name, true)
    end
    if old then aliases[old] = name end
    townNames[entity] = name or api.engine.util.getEntityName(entity)
  end

  local streetEntities = entities(types.BASE_EDGE_STREET)
  local streetReserved, byStreetName = {}, {}
  for _, entity in ipairs(streetEntities) do
    local name = api.engine.util.getEntityName(entity)
    if name then streetReserved[name] = true end
  end
  local nextStreet = allocator(streets, streetReserved, random)
  for _, entity in ipairs(streetEntities) do
    local old = api.engine.util.getEntityName(entity)
    if names.needsChineseName(old) and names.hasName(entity) then
      byStreetName[old] = byStreetName[old] or nextStreet()
      add(entity, byStreetName[old], true)
      aliases[old] = aliases[old] or byStreetName[old]
    elseif old then
      aliases[old] = aliases[old] or old
    end
  end

  -- Only persisted resident names can safely be assigned. Computed names use
  -- the naming scheme; any remaining foreign display is reported by the audit.
  for _, entity in ipairs(entities(types.SIM_PERSON)) do
    local old = api.engine.util.getEntityName(entity)
    if names.needsChineseName(old) and names.hasName(entity) then
      add(entity, person.generate(randomFor(entity % 2147483646 + 1)), true)
    end
  end

  facilities.plan(aliases, townNames, add)
  -- Existing default numbered line/vehicle titles can be baked into a map.
  -- Branded vehicle models and custom company/line titles are not region names.
  for __, spec in ipairs({ {types.LINE, "Line", "lineNumber"},
    {types.TRANSPORT_VEHICLE, "Aircraft", "number"}, {types.TRANSPORT_VEHICLE, "Road Vehicle", "number"},
    {types.TRANSPORT_VEHICLE, "Ship", "number"}, {types.TRANSPORT_VEHICLE, "Train", "number"},
    {types.TRANSPORT_VEHICLE, "Tram", "number"} }) do
    for __, entity in ipairs(entities(spec[1])) do
      local old = api.engine.util.getEntityName(entity)
      local number = old and old:match("^" .. spec[2] .. " (%d+)$")
      if number then
        local template = _(spec[2] .. " {" .. spec[3] .. "}")
        local translated = template:gsub("{" .. spec[3] .. "}", number)
        if not names.needsChineseName(translated) then add(entity, translated, true) end
      end
    end
  end
  return entries
end

function M.build(towns, streets)
  return names.withScan(build, towns, streets)
end

return M
