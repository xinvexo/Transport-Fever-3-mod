local stringutil = ug_require "::/scripts/stringutil.lua"
local M = {}

-- Port of the verified construction_builder_util::MakeName branches.
-- The exported final resource table includes both prefixes even though the
-- shipped Teal declaration omits them. See NATIVE_NAMING.md for evidence.
function M.prefix(description)
  if type(description.namePrefix) ~= "string" then return nil, "missing native namePrefix" end
  if description.namePrefix ~= "" then return description.namePrefix end
  local name = description.description and description.description.name
  if type(name) ~= "string" or name == "" then return "" end
  return stringutil.interp(_("{townName} {constructionName}"), {
    townName = "{townName}", constructionName = name,
  })
end

local function direction(position, center)
  local dx, dy = position.x - center.x, position.y - center.y
  if math.sqrt(dx * dx + dy * dy) <= 400 then return nil end
  local angle, pi = math.atan2(dy, dx), math.pi
  if angle > -pi / 6 and angle < pi / 6 then return "{stationName} East" end
  if angle > pi / 3 and angle < 2 * pi / 3 then return "{stationName} North" end
  if angle > 5 * pi / 6 or angle < -5 * pi / 6 then return "{stationName} West" end
  if angle > -2 * pi / 3 and angle < -pi / 3 then return "{stationName} South" end
end

function M.make(description, townName, position, center, occupied, needsExtraVariants)
  local prefix, reason = M.prefix(description)
  if prefix == nil then return nil, reason end
  if prefix == "" then return nil, "native naming prefix is empty" end
  local base = stringutil.interp(prefix, {townName = townName})
  if base:find("%b{}") then return nil, "unresolved native template argument" end
  if not occupied(base) then return base end
  local quadrant = direction(position, center)
  if quadrant then
    local value = stringutil.interp(_(quadrant), {stationName = base})
    if not occupied(value) then return value end
  end
  -- Standard industries put the industry subconstruction first, so this is
  -- false for their native construction results. Do not invent the native
  -- coordinate-hashed shuffle for the separate land-station variant branch.
  local extra = needsExtraVariants()
  if extra ~= false then return nil, "native random station variants require a separate naming path" end
  for number = 1, 999 do
    local value = stringutil.interp(_("{stationName} #{number}"), {stationName = base, number = number})
    if not occupied(value) then return value end
  end
  return base
end

-- Same predicate as MakeName: the FIRST subconstruction must be a station,
-- and every terminal mode must belong to the native land-mode set.
function M.extraVariants(construction)
  if construction.subconstructions == nil then return nil end
  local first = construction.subconstructions[1]
  if not first then return false end
  if not api.engine.entityExists(first) then return nil end
  local station = api.engine.getComponent(first, api.type.ComponentType.STATION)
  if not station then return false end
  local allowed = { [3] = true, [4] = true, [5] = true, [6] = true,
    [7] = true, [8] = true, [14] = true, [15] = true,
    BUS = true, TRUCK = true, TRAM = true, ELECTRIC_TRAM = true,
    TRAIN = true, ELECTRIC_TRAIN = true, TRAM_TRACK = true, ELECTRIC_TRAM_TRACK = true }
  for _, terminal in ipairs(station.terminals or {}) do
    for key, value in pairs(terminal.transportModes or {}) do
      if value ~= false then
        local mode = value == true and key or value
        if not allowed[mode] then return false end
      end
    end
  end
  return true
end

return M
