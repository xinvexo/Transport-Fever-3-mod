local names = ug_require "xin_chinese_map_names_1::/chinese_map_names/entity_names.lua"
local initialNames = ug_require "xin_chinese_map_names_1::/chinese_map_names/initial_names.lua"
local M = {}

function M.parent(entity)
  local types = api.type.ComponentType
  local connector = api.engine.system.streetConnectorSystem
  local function construction(candidate)
    return candidate and candidate >= 0 and api.engine.entityExists(candidate)
      and api.engine.getComponent(candidate, types.CONSTRUCTION) and candidate or nil
  end
  local industry = api.engine.getComponent(entity, types.INDUSTRY)
  if industry then
    return construction(industry.construction)
      or construction(connector.getConstructionEntityForSubconstruction(entity))
      or construction(connector.getConstructionEntityForIndustry(entity))
  elseif api.engine.getComponent(entity, types.STATION) then
    return construction(connector.getConstructionEntityForStation(entity))
  elseif api.engine.getComponent(entity, types.VEHICLE_DEPOT) then
    return construction(connector.getConstructionEntityForDepot(entity))
  end
  local warehouse = api.engine.getComponent(entity, types.WAREHOUSE)
  if warehouse then return construction(warehouse.construction) end
  local group = api.engine.getComponent(entity, types.STATION_GROUP)
  local owner
  for _, station in ipairs(group and group.stations or {}) do
    if not api.engine.entityExists(station) then return nil end
    local parent = construction(connector.getConstructionEntityForStation(station))
    if not parent or (owner and owner ~= parent) then return nil end
    owner = parent
  end
  return owner
end

-- The native collision set consists of station-group names and the parent
-- construction names of depots. Counts let an existing owner be temporarily
-- excluded while applying the creation rule to its replacement name.
function M.plan(_, townNames, add)
  local types = api.type.ComponentType
  local byOwner, occupied, caches = {}, {}, {}
  local function count(name, delta)
    if name then occupied[name] = (occupied[name] or 0) + delta end
  end
  local function reference(owner, entity, name)
    if owner and name then
      byOwner[owner] = byOwner[owner] or {}
      byOwner[owner][#byOwner[owner] + 1] = {entity = entity, name = name}
    end
  end
  for _, entity in ipairs(names.entities(types.STATION_GROUP)) do
    local owner, name = M.parent(entity), names.ownName(entity)
    count(name, 1)
    reference(owner, entity, name)
  end
  for _, entity in ipairs(names.entities(types.VEHICLE_DEPOT)) do
    local owner = M.parent(entity)
    local name = owner and names.ownName(owner)
    count(name, 1)
    reference(owner, nil, name)
  end
  local unresolved = 0
  local function preserve(owner, reason)
    unresolved = unresolved + 1
    if unresolved <= 5 then
      log.warning("[Chinese Map Names] Native initial naming unavailable for construction "
        .. owner .. ": " .. tostring(reason))
    end
  end
  for _, owner in ipairs(names.entities(types.CONSTRUCTION)) do
    local before = names.ownName(owner)
    if names.needsChineseName(before) then
      local construction = api.engine.getComponent(owner, types.CONSTRUCTION)
      local fileName = construction.fileName
      if caches[fileName] == nil then
        local id = api.res.constructionRep.find(fileName)
        caches[fileName] = id and id >= 0 and api.res.constructionRep.getAsTable(id) or false
      end
      local description = caches[fileName]
      if not description then
        preserve(owner, "construction descriptor not found")
      else
        local position = construction.transf:getTransl()
        -- This public binding calls the exact same native closest-town
        -- function as first-time MakeName (see the recorded binding chain).
        local town = api.engine.util.town.getClosestTown(position)
        local townName = town and town >= 0 and (townNames[town] or names.ownName(town))
        local volume = town and town >= 0 and api.engine.getComponent(town, types.BOUNDING_VOLUME)
        if not townName or not volume then
          -- The engine's no-town NameRep fallback is not publicly callable.
          -- The three Deluxe maps have towns; do not reseed simulation RNG.
          preserve(owner, "no named town with a bounding volume")
        else
          local center = (volume.bbox.min + volume.bbox.max) * 0.5
          for _, ref in ipairs(byOwner[owner] or {}) do count(ref.name, -1) end
          local value, reason = initialNames.make(description, townName, position, center,
            function(candidate) return (occupied[candidate] or 0) > 0 end,
            function() return initialNames.extraVariants(construction) end)
          if value then
            -- Native proposal application writes the SAME complete generated
            -- name to Construction.NAME and each newly created StationGroup.
            -- Station/industry/depot subconstruction NAME is never assigned.
            add(owner, value, false, town, townName)
            for _, ref in ipairs(byOwner[owner] or {}) do
              if ref.entity and names.hasName(ref.entity) then add(ref.entity, value, false, town, townName, owner) end
              count(value, 1)
            end
          else
            for _, ref in ipairs(byOwner[owner] or {}) do count(ref.name, 1) end
            preserve(owner, reason)
          end
        end
      end
    end
  end
  if unresolved > 5 then
    log.warning("[Chinese Map Names] Preserved " .. unresolved .. " constructions outside the verified initial-naming branches.")
  end
end

return M
