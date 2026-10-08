local M = {}
local scan

-- Component iteration is only supported for some engine component types.
-- Share the fallback snapshot within a single read-only planning/audit pass,
-- never across updates where entities may be created or destroyed.
function M.withScan(fn, ...)
  local previous = scan
  scan = { byType = {} }
  local ok, result = pcall(fn, ...)
  scan = previous
  if not ok then error(result, 0) end
  -- Both planning and auditing return one table. The game's base/init.lua
  -- replaces table.unpack with a version that ignores start/end indices.
  return result
end

function M.entities(kind)
  if scan and scan.byType[kind] then return scan.byType[kind] end
  local result = {}
  local ok, entities = pcall(api.engine.getEntitiesWithComponent, kind)
  if ok then
    for _, entity in ipairs(entities) do result[#result + 1] = entity end
  else
    -- BASE_EDGE_STREET is readable but cannot be iterated directly in the
    -- native engine. Do not turn unrelated API failures into empty results.
    if not tostring(entities):find("Cannot loop over this component type", 1, true) then error(entities, 0) end
    local all = scan and scan.all
    if not all then
      all = {}
      api.engine.forEachEntity(function(entity) all[#all + 1] = entity end)
      if scan then scan.all = all end
    end
    for _, entity in ipairs(all) do
      if api.engine.getComponent(entity, kind) then result[#result + 1] = entity end
    end
  end
  table.sort(result)
  if scan then scan.byType[kind] = result end
  return result
end

function M.ownName(entity)
  local value = api.engine.getComponent(entity, api.type.ComponentType.NAME)
  return value and value.name ~= "" and value.name or nil
end

function M.hasName(entity)
  return api.engine.entityExists(entity)
    and api.engine.getComponent(entity, api.type.ComponentType.NAME) ~= nil
end

function M.submitName(entity, name)
  -- forceSameEntity does not create NAME. Calling it on a nameless station
  -- can assert in the native engine; pcall cannot contain that fatal error.
  -- Revalidate at the actual command boundary, including restored old jobs.
  if not M.hasName(entity) then return false end
  api.cmd.sendCommand(api.cmd.makeEntitySetNameCmd(entity, name, true))
  return true
end

local function codepoint(character)
  local a, b, c, d = character:byte(1, 4)
  if a < 128 then return a end
  if a < 224 then return (a - 192) * 64 + b - 128 end
  if a < 240 then return (a - 224) * 4096 + (b - 128) * 64 + c - 128 end
  return (a - 240) * 262144 + (b - 128) * 4096 + (c - 128) * 64 + d - 128
end

local function isHan(point)
  return (point >= 0x3400 and point <= 0x9fff) or (point >= 0xf900 and point <= 0xfaff)
    or (point >= 0x20000 and point <= 0x323af)
end

local characters = "[%z\1-\127\194-\244][\128-\191]*"
function M.hasChinese(value)
  for character in (value or ""):gmatch(characters) do
    if isHan(codepoint(character)) then return true end
  end
  return false
end

function M.needsChineseName(value)
  if not value or value == "" then return false end
  if not M.hasChinese(value) then return true end
  for character in value:gmatch(characters) do
    local point = codepoint(character)
    -- Latin (including accented/fullwidth), Greek, Cyrillic, kana and Hangul
    -- can be mixed with Han characters; a single Han character is not enough.
    if character:find("[A-Za-z]") or (point >= 0xc0 and point <= 0x2af)
      or (point >= 0x370 and point <= 0x52f) or (point >= 0x3040 and point <= 0x30ff)
      or (point >= 0xac00 and point <= 0xd7af) or (point >= 0xff21 and point <= 0xff3a)
      or (point >= 0xff41 and point <= 0xff5a) then return true end
  end
  return false
end

local function audit()
  local types = api.type.ComponentType
  local candidates, categories = {}, {}
  for _, category in ipairs({ "TOWN", "BASE_EDGE_STREET", "SIM_PERSON", "CONSTRUCTION",
    "INDUSTRY", "STATION", "STATION_GROUP", "VEHICLE_DEPOT", "WAREHOUSE", "LINE", "TRANSPORT_VEHICLE", "NAME" }) do
    for _, entity in ipairs(M.entities(types[category])) do
      if not categories[entity] then
        candidates[#candidates + 1], categories[entity] = entity, category
      end
    end
  end
  table.sort(candidates)
  local report = { remaining = 0, identities = 0, samples = {} }
  for _, entity in ipairs(candidates) do
    local name = api.engine.util.getEntityName(entity)
    if M.needsChineseName(name) then
      if api.engine.getComponent(entity, types.PLAYER) then
        report.identities = report.identities + 1 -- Platform nicknames are not region names.
      else
        report.remaining = report.remaining + 1
        if #report.samples < 10 then
          report.samples[#report.samples + 1] = {entity = entity, name = name, category = categories[entity]}
        end
      end
    end
  end
  return report
end

function M.audit()
  return M.withScan(audit)
end

return M
