local M = {}

local function text(value)
  if type(value) ~= "string" then return "" end
  return (value:gsub("%s+", " "):match("^%s*(.-)%s*$"))
end

local function shortName(point)
  local name, town = text(point.name), point.town and text(point.town.name)
  -- Strip only a separated, complete town prefix; preserve custom names such
  -- as 北京老字号食品厂 and town names containing Lua pattern characters.
  if town and name:sub(1, #town) == town then
    local rest = name:sub(#town + 1)
    if rest:match("^%s+") then return text(rest) end
  end
  return name
end

local function fullName(point)
  local name, town = text(point.name), point.town and text(point.town.name)
  if town and point.kind ~= "town" then
    local short = shortName(point)
    if short ~= name or name:sub(1, #town) ~= town then
      return town .. " - " .. short
    end
  end
  return name
end

local function outbound(stops)
  local count = #stops
  if count > 2 and stops[count].group == stops[1].group then count = count - 1 end
  -- A B C B [A] and A B C D C B [A]. No geometric guess about rings.
  if count >= 4 and count % 2 == 0 then
    local mirrored = true
    for index = 2, count / 2 do
      if stops[index].group ~= stops[count - index + 2].group then mirrored = false; break end
    end
    if mirrored then count = count / 2 + 1 end
  end
  local result = {}
  for index = 1, count do
    local point, previous = stops[index].point, result[#result]
    if not previous or previous.kind ~= point.kind or previous.id ~= point.id then
      result[#result + 1] = point
    end
  end
  return result
end

local function joinRoute(parts)
  if #parts > 4 then parts = { parts[1], parts[2], "…", parts[#parts] } end
  return table.concat(parts, " - ")
end

function M.base(line)
  if line.invalid or #line.stops < 2 then return nil end
  local towns, unknownTown, allTown, hasTown, hasIndustry = {}, false, true, false, false
  -- Inspect every stop, including the return leg. Equal end towns do not make
  -- an A -> B -> A service local.
  for _, stop in ipairs(line.stops) do
    local point = stop.point
    if not next(point.towns) then unknownTown = true end
    for id, town in pairs(point.towns) do towns[id] = town end
    allTown = allTown and point.kind == "town"
    hasTown = hasTown or point.kind == "town"
    hasIndustry = hasIndustry or point.kind == "industry"
  end
  local townCount, localTown = 0, nil
  for _, town in pairs(towns) do townCount = townCount + 1; localTown = town end
  local localLine = townCount == 1 and not unknownTown
  local points, parts = outbound(line.stops), {}
  local route
  if localLine and allTown then
    route = text(localTown.name)
  elseif localLine then
    for _, point in ipairs(points) do
      parts[#parts + 1] = point.kind == "town" and text(point.name) or shortName(point)
    end
    route = joinRoute(parts)
    if not hasTown then route = text(localTown.name) .. " - " .. route end
  else
    for _, point in ipairs(points) do parts[#parts + 1] = fullName(point) end
    route = joinRoute(parts)
  end
  if route == "" then return nil end
  local purpose
  if line.kind == "passenger" then
    if hasIndustry and hasTown then purpose = _("Line naming: workers")
    elseif line.carrier == "ROAD" and localLine then purpose = _("Line naming: bus")
    elseif line.carrier == "TRAM" then purpose = _("Line naming: tram")
    elseif line.carrier == "WATER" then purpose = _("Line naming: ferry")
    elseif line.carrier == "AIR" then purpose = _("Line naming: flight")
    else purpose = _("Line naming: passenger") end
  elseif line.kind == "freight" then
    purpose = text(line.cargo)
    if purpose == "" then purpose = _("Line naming: freight")
    elseif localLine and allTown and line.carrier == "ROAD" then
      purpose = purpose .. _("Line naming: delivery")
    end
  elseif line.kind == "mixed" then purpose = _("Line naming: mixed")
  else purpose = _("Line naming: line") end
  local separator = line.kind == "freight" and " · " or " - "
  return route .. separator .. purpose, not (line.kind == "passenger" and townCount > 1)
end

-- Pure full-player plan: preview order/cancellation cannot consume numbers.
-- Existing names reserve their slots, even for lines outside the selection.
function M.plan(lines)
  local ordered, occupied, retained, result, counts, fixed = {}, {}, {}, {}, {}, {}
  for _, line in ipairs(lines) do
    ordered[#ordered + 1] = line
    occupied[line.name] = (occupied[line.name] or 0) + 1
    if line.base then counts[line.base] = (counts[line.base] or 0) + 1 end
    if not line.base then fixed[line.name] = true end
  end
  table.sort(ordered, function(a, b) return a.id < b.id end)
  for _, line in ipairs(ordered) do
    local base = line.base
    local suffix = base and line.name:sub(1, #base) == base and line.name:sub(#base + 1)
    local number = suffix and suffix:match("^%d+$") and tonumber(suffix)
    local keepNumber = number and number >= 1 and suffix == string.format("%02d", number)
      and not retained[line.name] and not fixed[line.name]
    if not base then result[line.id] = line.name
    elseif keepNumber then
      result[line.id], retained[line.name] = line.name, true
    elseif line.numbered == false and counts[base] == 1
      and (not occupied[base] or (line.name == base and occupied[base] == 1)) then
      result[line.id], occupied[base] = base, 1
    end
  end
  local nextNumber = {}
  for _, line in ipairs(ordered) do
    if not result[line.id] then
      local base, number = line.base, nextNumber[line.base] or 1
      local candidate = base .. string.format("%02d", number)
      while occupied[candidate] do
        number = number + 1
        candidate = base .. string.format("%02d", number)
      end
      result[line.id], occupied[candidate] = candidate, true
      nextNumber[base] = number + 1
    end
  end
  return result
end

return M
