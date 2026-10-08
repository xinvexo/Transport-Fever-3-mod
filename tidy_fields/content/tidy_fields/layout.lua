local layout = {}

-- Local factory bounds; the road entrance faces negative Y.
local sites = {
  farm_field = { left = -60, right = 60, front = -90, rear = 90, roadY = -100.5 },
  livestock_field = { left = -81.1353, right = 68.8647, front = -60, rear = 60, roadY = -72.5 },
  cotton_field = { left = -60, right = 60, front = -80, rear = 60, roadY = -90.5 },
  rubber_field = { left = -90, right = 90, front = -50, rear = 50, roadY = -61.3 },
  forest_field = { left = -70, right = 60, front = -60, rear = 60, roadY = -70.5 },
}

local choices = {
  left = { "left" },
  right = { "right" },
  front = { "front" },
  back = { "back" },
  left_right = { "left", "right" },
  left_front = { "left", "front" },
  left_back = { "left", "back" },
  right_front = { "right", "front" },
  right_back = { "right", "back" },
  front_back = { "front", "back" },
  left_right_front = { "left", "right", "front" },
  left_right_back = { "left", "right", "back" },
  left_front_back = { "left", "front", "back" },
  right_front_back = { "right", "front", "back" },
  all = { "left", "right", "front", "back" },
}

local function copy(source)
  local result = {}
  for key, value in pairs(source) do result[key] = value end
  return result
end

local function copyField(field)
  local result = copy(field)
  result.pos = copy(field.pos)
  if field.size then result.size = copy(field.size) end
  if field.road then result.road = copy(field.road) end
  return result
end

function layout.makeOrder(modules, fieldCount)
  local order = {}
  for id = 1, fieldCount do
    if modules[id] then order[#order + 1] = id end
  end
  for id = 1, fieldCount do
    if not modules[id] then order[#order + 1] = id end
  end
  return order
end

local function candidates(fieldConfig, params)
  local site = sites[fieldConfig.type]
  local sides, selected = {}, {}
  -- Facing out through the entrance (-Y), the factory's left is local +X.
  for _, side in ipairs(choices[params.xinTidyLayout or "all"]) do
    sides[#sides + 1] = side == "left" and "right" or side == "right" and "left" or side
    selected[sides[#sides]] = true
  end
  local positions = { left = {}, right = {}, front = {}, back = {} }
  local grid = {}

  -- The selection outline extends four metres beyond each field edge.
  local step, border, roadClearance = 80, 4, 8
  local center = (site.left + site.right) / 2
  local middle = (site.front + site.rear) / 2
  local columns = math.ceil((site.right - site.left) / step)
  local rows = math.ceil((site.rear - site.front) / step)
  local radius = math.ceil(math.sqrt(#fieldConfig.fields)) + 1

  local function axisCell(index, first, last, count)
    if index < 0 then return first + (index + 0.5) * step, step end
    if index >= count then return last + (index - count + 0.5) * step, step end
    local size = (last - first) / count
    return first + (index + 0.5) * size, size
  end

  for column = -radius, columns + radius - 1 do
    grid[column] = {}
    for row = -radius, rows + radius - 1 do
      local x, width = axisCell(column, site.left, site.right, columns)
      local y, height = axisCell(row, site.front, site.rear, rows)
      if row < 0 then
        y = site.roadY - roadClearance - border - height / 2 + (row + 1) * step
      end
      local outward = {
        left = -column, right = column - columns + 1,
        front = -row, back = row - rows + 1,
      }
      local side
      if row < 0 then
        side = selected.front and "front" or nil
      elseif row >= rows and selected.back then
        side = "back"
      elseif column < 0 and selected.left then
        side = "left"
      elseif column >= columns and selected.right then
        side = "right"
      end

      if side then
        local ring = 1
        for direction, distance in pairs(outward) do
          if distance > 0 then
            ring = math.max(ring, distance + (selected[direction] and 0 or 1))
          end
        end
        local targetX = side == "left" and site.left or side == "right" and site.right or center
        local targetY = side == "front" and site.front or side == "back" and site.rear or middle
        local position = {
          x = x, y = y, distance = (x - targetX) ^ 2 + (y - targetY) ^ 2,
          width = width, height = height,
          column = column, row = row, layer = outward[side], ring = ring,
        }
        positions[side][#positions[side] + 1] = position
        grid[column][row] = position
      end
    end
  end
  for _, side in ipairs(sides) do
    table.sort(positions[side], function(a, b)
      if a.distance ~= b.distance then return a.distance < b.distance end
      if a.y ~= b.y then return a.y < b.y end
      return a.x < b.x
    end)
  end
  return positions, sides, grid, columns, rows
end

function layout.plan(fieldConfig, params, canPlace, canConnect)
  local site = sites[fieldConfig.type]
  if not site then return nil, "This industry does not support plot rearrangement." end
  local positions, sides, grid, columns, rows = candidates(fieldConfig, params)
  local modules = params.modules or {}
  local order = params.xinTidyFieldOrder or layout.makeOrder(modules, #fieldConfig.fields)
  local fields, availableSlots, used, frontier, land = {}, {}, {}, {}, {}
  local minColumn, maxColumn, minRow, maxRow = 0, columns - 1, 0, rows - 1
  local placedCount = columns * rows
  local neighbours = { {-1, 0}, {1, 0}, {0, -1}, {0, 1} }

  local function makeField(id, position)
    local field = copy(fieldConfig.fields[id])
    field.pos = { position.x, position.y }
    field.size = { position.width, position.height }
    field.road = { 0, 0, 0, 0 }
    return field
  end

  local function offer(position, from)
    if not position or used[position] or frontier[position] then return end
    if land[position] == nil then
      land[position] = not canPlace or canPlace(makeField(order[1], position))
    end
    if land[position] and (not canConnect or canConnect(from, { position.x, position.y })) then
      frontier[position] = true
    end
  end

  local function rootAnchor(side, position)
    if side == "left" or side == "right" then
      if position.y < site.front or position.y > site.rear then return nil end
      return { side == "left" and site.left or site.right, position.y }
    end
    if position.x < site.left - 80 or position.x > site.right + 80 then return nil end
    return {
      math.max(site.left, math.min(site.right, position.x)),
      side == "front" and site.front or site.rear,
    }
  end

  -- Choose the nearest geometric root layer before checking land. A failed
  -- shore-side root must not be replaced by a dry root on a distant island.
  for _, side in ipairs(sides) do
    local layer
    for _, position in ipairs(positions[side]) do
      if rootAnchor(side, position) and (not layer or position.layer < layer) then
        layer = position.layer
      end
    end
    for _, position in ipairs(positions[side]) do
      if position.layer == layer then
        local anchor = rootAnchor(side, position)
        if anchor then offer(position, anchor) end
      end
    end
  end

  local function score(position, remaining)
    local left, right = math.min(minColumn, position.column), math.max(maxColumn, position.column)
    local front, back = math.min(minRow, position.row), math.max(maxRow, position.row)
    local width, height = right - left + 1, back - front + 1
    local completesRectangle = width * height == placedCount + remaining
    if completesRectangle then
      for column = left, right do
        for row = front, back do
          if column < 0 or column >= columns or row < 0 or row >= rows then
            local candidate = grid[column] and grid[column][row]
            if not candidate or land[candidate] == false then completesRectangle = false end
          end
        end
      end
    end
    local adjacent = 0
    for _, direction in ipairs(neighbours) do
      local column, row = position.column + direction[1], position.row + direction[2]
      local neighbour = grid[column] and grid[column][row]
      if (column >= 0 and column < columns and row >= 0 and row < rows)
        or (neighbour and used[neighbour]) then
        adjacent = adjacent + 1
      end
    end
    -- Fill the near rectangle and its notches before extending its outline.
    return { position.ring, completesRectangle and 0 or 1,
      width * height - placedCount - 1, -adjacent,
      math.max(width, height), width + height, position.distance }
  end

  local function place(id, remaining)
    local best, bestScore
    for _, side in ipairs(sides) do
      for _, position in ipairs(positions[side]) do
        if frontier[position] then
          local candidateScore = score(position, remaining)
          local preferred = not best
          if best then
            for index, value in ipairs(candidateScore) do
              if value ~= bestScore[index] then
                preferred = value < bestScore[index]
                break
              end
            end
          end
          if preferred then best, bestScore = position, candidateScore end
        end
      end
    end
    if not best then return false end
    fields[id], availableSlots[id] = makeField(id, best), true
    used[best], frontier[best] = true, nil
    minColumn, maxColumn = math.min(minColumn, best.column), math.max(maxColumn, best.column)
    minRow, maxRow = math.min(minRow, best.row), math.max(maxRow, best.row)
    placedCount = placedCount + 1
    for _, direction in ipairs(neighbours) do
      local column = grid[best.column + direction[1]]
      if column then offer(column[best.row + direction[2]], { best.x, best.y }) end
    end
    return true
  end

  local remaining = 0
  for _, id in ipairs(order) do
    if modules[id] then remaining = remaining + 1 end
  end
  local emptyCount = #order - remaining
  for _, id in ipairs(order) do
    if modules[id] then
      if not place(id, remaining) then
        return nil, "Not enough connected land in the selected directions for the existing plots."
      end
      remaining = remaining - 1
    end
  end
  -- Future growth uses the same connected frontier. Unavailable empty slots
  -- retain their descriptors, but are omitted from the construction's slots.
  for _, id in ipairs(order) do
    if not modules[id] then
      if not place(id, emptyCount) then fields[id] = copyField(fieldConfig.fields[id]) end
      emptyCount = emptyCount - 1
    end
  end
  return fields, nil, availableSlots
end

function layout.rearrange(fieldConfig, params)
  if not sites[fieldConfig.type] then return fieldConfig end
  local result = copy(fieldConfig)
  if params.xinTidyFieldLayout then
    result.fields = {}
    for id, field in pairs(params.xinTidyFieldLayout) do
      result.fields[id] = copyField(field)
    end
  else
    local fields, reason = layout.plan(fieldConfig, params)
    if not fields then error(reason) end
    result.fields = fields
  end
  return result
end

function layout.wrap(update)
  return function(captureParams, params)
    if not params.xinTidyFields then return update(captureParams, params) end
    local capture = copy(captureParams)
    capture.fieldConfig = layout.rearrange(captureParams.fieldConfig, params)
    local results = table.pack(update(capture, params))
    local result = results[1]
    if params.xinTidyFieldSlots and result.slots then
      local slots, modules = {}, params.modules or {}
      for _, slot in ipairs(result.slots) do
        if slot.type ~= capture.fieldConfig.type or modules[slot.id] or params.xinTidyFieldSlots[slot.id] then
          slots[#slots + 1] = slot
        end
      end
      result.slots = slots
    end
    return table.unpack(results, 1, results.n)
  end
end

return layout
