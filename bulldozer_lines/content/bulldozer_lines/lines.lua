local nativeLines = ug_require "::/gui/line_vehicle_mgmt/line_util.tl"
local langUtil = ug_require "::/scripts/lang_util.tl"
local lines = {}

lines.categories = {
  { key = "ROAD", icon = "::/gui/line_vehicle_mgmt/icons/vehicle_bus_18.tga", tooltip = "Show Road Lines" },
  { key = "TRAM", icon = "::/gui/line_vehicle_mgmt/icons/vehicle_tram_18.tga", tooltip = "Show Tram Lines" },
  { key = "RAIL", icon = "::/gui/line_vehicle_mgmt/icons/vehicle_train_18.tga", tooltip = "Show Train Lines" },
  { key = "WATER", icon = "::/gui/line_vehicle_mgmt/icons/vehicle_ship_18.tga", tooltip = "Show Ship Lines" },
  { key = "AIR", icon = "::/gui/line_vehicle_mgmt/icons/vehicle_airplane_18.tga", tooltip = "Show Air Lines" },
}

local function allowedCarriers(filters)
  local allowed, mask = {}, 0
  for index, category in ipairs(lines.categories) do
    if filters and filters.carriers[category.key] then
      allowed[#allowed + 1] = api.type["enum"].Carrier[category.key]
      mask = mask + 2 ^ index
    end
  end
  return allowed, mask + (filters and filters.onlyVisible and 1 or 0)
end

function lines.read(filters, previous)
  local allowed, filterKey = allowedCarriers(filters)
  local result, oldById, byId = { filterKey = filterKey }, {}, {}
  for _, line in ipairs(previous or {}) do oldById[line.entity] = line end
  local orderChanged = false
  for _, entity in ipairs(api.engine.system.lineSystem.getLinesForPlayer(api.engine.util.getPlayer())) do
    if api.engine.entityExists(entity) then
      local old = oldById[entity]
      local name = api.engine.util.getEntityName(entity)
      local visible = not (filters and filters.onlyVisible) or api.gui.byEntity.isLineEmptyOrVisible(entity)
      local matches = #allowed == 0 or nativeLines.filterLine(allowed, entity)
      if not old or old.name ~= name then orderChanged = true end
      local line = old
      if not old or old.name ~= name or old.visible ~= visible or old.matchesTransport ~= matches then
        line = { entity = entity, name = name, visible = visible, matchesTransport = matches }
      end
      result[#result + 1], byId[entity] = line, line
    end
  end
  -- Camera/transport changes do not change name order. Reuse it even
  -- when the line system enumerates entities in a different order.
  if previous and not orderChanged and #previous == #result then
    for index, line in ipairs(previous) do result[index] = byId[line.entity] end
  else
    table.sort(result, function(a, b)
      -- Same comparator as the native manager/DataTable: natural numbers and
      -- language-aware names, without a mod-specific entity-ID tie breaker.
      return langUtil.compareStrings(a.name, b.name) < 0
    end)
  end
  return result
end

function lines.search(all, query)
  local result = {}
  query = string.lower(query or "")
  for _, line in ipairs(all) do
    if query == "" or string.find(string.lower(line.name), query, 1, true) then
      result[#result + 1] = line
    end
  end
  return result
end

function lines.setFilter(filters, key, enabled)
  local current = key == "onlyVisible" and filters.onlyVisible or filters.carriers[key]
  if (current == true) == enabled then return filters end
  local result = { carriers = {}, onlyVisible = filters.onlyVisible }
  for carrier, checked in pairs(filters.carriers) do result.carriers[carrier] = checked end
  if key == "onlyVisible" then result.onlyVisible = enabled
  else result.carriers[key] = enabled end
  return result
end

function lines.filter(all, filters)
  local allowed, filterKey = allowedCarriers(filters)
  local result, fromSnapshot = {}, all.filterKey == filterKey
  for _, line in ipairs(all) do
    if api.engine.entityExists(line.entity)
      and (not filters.onlyVisible or (fromSnapshot and line.visible)
        or (not fromSnapshot and api.gui.byEntity.isLineEmptyOrVisible(line.entity)))
      and (#allowed == 0 or (fromSnapshot and line.matchesTransport)
        or (not fromSnapshot and nativeLines.filterLine(allowed, line.entity))) then
      result[#result + 1] = line
    end
  end
  return result
end

-- Stable per-row values let native dependent states redraw only changed rows.
function lines.rows(shown, previous)
  local result, changed = {}, false
  for index, line in ipairs(shown) do
    local old = previous[line.entity]
    if old and old.name == line.name and old.index == index then
      result[line.entity] = old
    else
      result[line.entity] = { name = line.name, index = index }
      changed = true
    end
  end
  for entity in pairs(previous) do if not result[entity] then changed = true; break end end
  return changed and result or previous
end

function lines.select(all, selected, filters)
  local hasSelection = false
  for _, line in ipairs(all) do
    if selected[line.entity] and api.engine.entityExists(line.entity) then hasSelection = true; break end
  end
  local result = {}
  for _, line in ipairs(lines.filter(all, filters or { carriers = {} })) do
    if not hasSelection or selected[line.entity] then result[#result + 1] = line end
  end
  -- A checked line hidden by a filter must not reveal other, unchecked lines.
  return result
end

function lines.setChecked(selected, entity, checked)
  if (selected[entity] == true) == checked then return selected end
  local result = {}
  for id, value in pairs(selected) do
    if value and api.engine.entityExists(id) then result[id] = true end
  end
  result[entity] = checked and true or nil
  return result
end

function lines.selectionValue(shown, selected)
  local count, checked = 0, 0
  for _, line in ipairs(shown) do
    if api.engine.entityExists(line.entity) then
      count = count + 1
      if selected[line.entity] then checked = checked + 1 end
    end
  end
  if checked == 0 then return 0 end
  return checked == count and 1 or -1
end

function lines.toggleAll(shown, selected)
  local result = {}
  if lines.selectionValue(shown, selected) ~= 1 then
    for _, line in ipairs(shown) do
      if api.engine.entityExists(line.entity) then result[line.entity] = true end
    end
  end
  return result
end

return lines
