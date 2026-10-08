local world = ug_require "xin_line_names_1::/line_names/world.lua"
local names = ug_require "xin_line_names_1::/line_names/names.lua"
local globals = ug_require "::/gui/main/game_react_globals.tl"
local cached, warned

local function warn(message)
  if not warned then
    log.warning("[line_names] Naming unavailable; keeping affected names: " .. tostring(message))
    warned = true
  end
end

local function makePlan()
  local context, lines, healthy = world.new(), {}, true
  for _, id in ipairs(api.engine.system.lineSystem.getLinesForPlayer(api.engine.util.getPlayer())) do
    local ok, record = pcall(function()
      local value = context.line(id)
      if value then value.base, value.numbered = names.base(value) end
      return value
    end)
    if ok and record then
      lines[#lines + 1] = record
    elseif api.engine.entityExists(id) then
      lines[#lines + 1] = { id = id, name = api.engine.util.getEntityName(id) }
      if not ok then healthy = false; warn(record) end
    end
  end
  return names.plan(lines), healthy
end

local function rename(params)
  -- GAME_TIME belongs to the world singleton and is not an enumerable type.
  local time = api.engine.getComponent(api.engine.util.getWorld(), api.type.ComponentType.GAME_TIME)
  local tick = time and time.tickCount
  local session, player = globals.getDefaultWindowApi(), api.engine.util.getPlayer()
  -- The native dialog calls the component once per selected line. Reuse only
  -- within one simulation tick and GUI session; paused games still tick.
  if not cached or not cached.healthy or not session or not tick or cached.session ~= session
    or cached.tick ~= tick or cached.player ~= player then
    local plan, healthy = makePlan()
    cached = { session = session, tick = tick, player = player, plan = plan, healthy = healthy }
  end
  return cached.plan[params.lineEntity] or api.engine.util.getEntityName(params.lineEntity)
end

function data()
  return { renameFn = function(params)
    local ok, result = pcall(rename, params)
    if ok and type(result) == "string" then return result end
    cached = nil
    warn(result)
    return api.engine.util.getEntityName(params.lineEntity) or _("Line naming: line")
  end }
end
