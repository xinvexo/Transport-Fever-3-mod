local facilities = ug_require "xin_chinese_map_names_1::/chinese_map_names/facilities.lua"
local M = {}

local function priority(entity)
  local types = api.type.ComponentType
  local function has(kind) return api.engine.getComponent(entity, kind) ~= nil end
  if not api.engine.entityExists(entity) then return 6 end
  if has(types.TOWN) then return 1 end
  if has(types.CONSTRUCTION) or has(types.INDUSTRY) or has(types.STATION)
    or has(types.STATION_GROUP) or has(types.VEHICLE_DEPOT) or has(types.WAREHOUSE) then return 2 end
  if has(types.BASE_EDGE_STREET) then return 3 end
  if has(types.SIM_PERSON) then return 4 end
  return 5
end

function M.prepare(entries)
  local byEntity = {}
  for index, entry in ipairs(entries) do
    entry.priority, entry.order = priority(entry.entity), index
    byEntity[entry.entity] = entry
  end
  for _, entry in ipairs(entries) do
    entry.dependencies = {}
    if entry.nativeTown and byEntity[entry.nativeTown] then entry.dependencies[#entry.dependencies + 1] = entry.nativeTown end
    if entry.nativeOwner and byEntity[entry.nativeOwner] then entry.dependencies[#entry.dependencies + 1] = entry.nativeOwner end
    if entry.readDisplay and not entry.done and api.engine.entityExists(entry.entity) then
      local sources = {}
      local stem = api.engine.util.getEntityNameStem(entry.entity)
      if stem and stem[2] then sources[stem[2]] = true end
      local parent = facilities.parent(entry.entity)
      if parent then sources[parent] = true end
      for source in pairs(sources) do
        if source ~= entry.entity and byEntity[source] then
          entry.dependencies[#entry.dependencies + 1] = source
        end
      end
      table.sort(entry.dependencies)
    end
  end
  table.sort(entries, function(a, b)
    if a.priority ~= b.priority then return a.priority < b.priority end
    return a.order < b.order
  end)
end

function M.indexDependencies(entries)
  -- State:get returns a fresh queue. Persist only numeric positions for actual
  -- dependency sources, rather than rebuilding an entity->entry table per batch.
  local indices = {}
  for _, entry in ipairs(entries) do
    -- Stable-sort tie breakers are only needed during prepare, before the
    -- array order is fixed. Do not keep copying them with the saved queue.
    entry.order = nil
    if entry.dependencies and #entry.dependencies > 0 then
      for _, source in ipairs(entry.dependencies) do indices[source] = false end
    else
      -- Most entries are independent residents. Empty tables would otherwise
      -- be serialized and copied twice per batch for every one of them.
      entry.dependencies = nil
    end
  end
  if next(indices) == nil then return indices end
  for index, entry in ipairs(entries) do
    if indices[entry.entity] ~= nil then indices[entry.entity] = index end
  end
  return indices
end

function M.ready(entry, entries, indices)
  if not entry.dependencies then return true end
  for _, source in ipairs(entry.dependencies) do
    local index = indices[source]
    if index and not entries[index].done then return false end
  end
  return true
end

function M.mapLabelsDone(entries)
  for _, entry in ipairs(entries) do
    if entry.priority > 2 then break end
    if not entry.done then return false end
  end
  return true
end

function M.report(current)
  local towns, facilitiesLeft, processed = 0, 0, 0
  for _, entry in ipairs(current.entries) do
    if entry.done then
      processed = processed + 1
    elseif entry.priority == 1 then
      towns = towns + 1
    elseif entry.priority == 2 then
      facilitiesLeft = facilitiesLeft + 1
    end
  end
  log.message("[Chinese Map Names] Progress: " .. processed .. "/" .. #current.entries
    .. " processed, " .. current.renamed .. " changes verified; towns remaining=" .. towns
    .. ", facilities remaining=" .. facilitiesLeft .. ".")
end

return M
