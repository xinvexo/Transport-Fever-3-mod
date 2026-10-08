local nativeLines = ug_require "::/gui/line_vehicle_mgmt/line_util.tl"
local lines = {}

lines.categories = {
  { key = "ROAD", icon = "::/gui/line_vehicle_mgmt/icons/vehicle_bus_18.tga", tooltip = "Show Road Lines" },
  { key = "TRAM", icon = "::/gui/line_vehicle_mgmt/icons/vehicle_tram_18.tga", tooltip = "Show Tram Lines" },
  { key = "RAIL", icon = "::/gui/line_vehicle_mgmt/icons/vehicle_train_18.tga", tooltip = "Show Train Lines" },
  { key = "WATER", icon = "::/gui/line_vehicle_mgmt/icons/vehicle_ship_18.tga", tooltip = "Show Ship Lines" },
  { key = "AIR", icon = "::/gui/line_vehicle_mgmt/icons/vehicle_airplane_18.tga", tooltip = "Show Air Lines" },
}

local function allowedCarriers(filters)
  local allowed = {}
  for _, category in ipairs(lines.categories) do
    if filters and filters.carriers[category.key] then
      allowed[#allowed + 1] = api.type["enum"].Carrier[category.key]
    end
  end
  return allowed
end

function lines.read(filters)
  local allowed = allowedCarriers(filters)
  local result = {}
  for _, entity in ipairs(api.engine.system.lineSystem.getLinesForPlayer(api.engine.util.getPlayer())) do
    if api.engine.entityExists(entity) then
      result[#result + 1] = {
        entity = entity, name = api.engine.util.getEntityName(entity),
        -- Make camera movement invalidate the mirrored list while the eye is on.
        visible = not (filters and filters.onlyVisible) or api.gui.byEntity.isLineEmptyOrVisible(entity),
        matchesTransport = #allowed == 0 or nativeLines.filterLine(allowed, entity),
      }
    end
  end
  table.sort(result, function(a, b)
    if a.name == b.name then return a.entity < b.entity end
    return a.name < b.name
  end)
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
  local result = { carriers = {}, onlyVisible = filters.onlyVisible }
  for carrier, checked in pairs(filters.carriers) do result.carriers[carrier] = checked end
  if key == "onlyVisible" then result.onlyVisible = enabled
  else result.carriers[key] = enabled end
  return result
end

function lines.filter(all, filters)
  local allowed, result = allowedCarriers(filters), {}
  for _, line in ipairs(all) do
    if api.engine.entityExists(line.entity)
      and (not filters.onlyVisible or api.gui.byEntity.isLineEmptyOrVisible(line.entity))
      and (#allowed == 0 or nativeLines.filterLine(allowed, line.entity)) then
      result[#result + 1] = line
    end
  end
  return result
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
