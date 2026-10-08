local rows = {}

local CARGO = 6400000
local PASSENGER = 7400000
local TRACK = 8400000
local ROOF = 10400000
local ADDON = 10800000
local BASES = { CARGO, PASSENGER, TRACK, ROOF, ADDON }
local MIN_J, MAX_J = -10, 10

local function coordinates(slot)
  for _, base in ipairs(BASES) do
    local offset = slot - base
    local i = math.floor((offset + 500) / 1000)
    local j = (offset - 1000 * i) / 10
    if i >= -8 and i <= 16 and j >= MIN_J and j <= MAX_J and j == math.floor(j) then
      return base, i, j
    end
  end
end

local function slotId(base, i, j)
  return base + 1000 * i + 10 * j
end

function rows.isRowSlot(slot)
  return coordinates(slot) ~= nil
end

local function occupied(modules, i, j)
  return modules[slotId(CARGO, i, j)]
    or modules[slotId(CARGO, i - 1, j)]
    or modules[slotId(PASSENGER, i, j)]
    or modules[slotId(TRACK, i, j)]
end

function rows.canAdd(modules, slot)
  local base, i, j = coordinates(slot)
  if not base or modules[slot] ~= nil then return false end
  if base == ROOF or base == ADDON then
    return modules[slotId(PASSENGER, i, j)] ~= nil
  end
  return not occupied(modules, i, j)
    and (base ~= CARGO or not occupied(modules, i + 1, j))
end

function rows.apply(params, change)
  local modules = params.modules or {}
  params.modules = modules
  local base, i, clickedJ = coordinates(change.slotId)
  if not change.added then
    for j = MIN_J, MAX_J do
      local id = slotId(base, i, j)
      if modules[id] then
        modules[id] = nil
        if base == CARGO or base == PASSENGER then
          modules[slotId(ROOF, i, j)] = nil
          modules[slotId(ADDON, i, j)] = nil
        end
      end
    end
    return params
  end

  if base == ROOF or base == ADDON then
    for j = MIN_J, MAX_J do
      local id = slotId(base, i, j)
      if rows.canAdd(modules, id) then modules[id] = change.module end
    end
  else
    -- Match the existing station's longitudinal span, including an end extension.
    local first, last = clickedJ, clickedJ
    for id in pairs(modules) do
      local kind, _, j = coordinates(id)
      if kind == CARGO or kind == PASSENGER or kind == TRACK then
        first, last = math.min(first, j), math.max(last, j)
      end
    end
    for j = first, last do
      local id = slotId(base, i, j)
      if rows.canAdd(modules, id) then modules[id] = change.module end
    end
  end
  return params
end

return rows
