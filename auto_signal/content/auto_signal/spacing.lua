-- Distances are measured along the track, in metres.
local spacing = {}
-- Cumulative track distances acquire small rounding differences when adding
-- and subtracting the same spacing. Snap these back to legal endpoints.
local ROUNDING_EPSILON = 1e-7

local function nextAllowed(intervals, value)
  local lo, hi = 1, #intervals
  while lo <= hi do
    local mid = math.floor((lo + hi) / 2)
    if intervals[mid][2] < value - ROUNDING_EPSILON then lo = mid + 1 else hi = mid - 1 end
  end
  if lo > #intervals then return nil end
  return math.min(intervals[lo][2], math.max(value, intervals[lo][1]))
end

local function previousAllowed(intervals, value)
  local lo, hi = 1, #intervals
  while lo <= hi do
    local mid = math.floor((lo + hi) / 2)
    if intervals[mid][1] <= value + ROUNDING_EPSILON then lo = mid + 1 else hi = mid - 1 end
  end
  if hi < 1 then return nil end
  return math.max(intervals[hi][1], math.min(value, intervals[hi][2]))
end

local function nearestAllowed(intervals, value, lower, upper)
  value = math.max(lower, math.min(upper, value))
  local before = previousAllowed(intervals, value)
  local after = nextAllowed(intervals, value)
  if before and before < lower - ROUNDING_EPSILON then before = nil end
  if after and after > upper + ROUNDING_EPSILON then after = nil end
  if not before then return after end
  if not after then return before end
  if value - before <= after - value then return before end
  return after
end

-- Subtract forbidden ranges from intervals in track order.
function spacing.exclude(intervals, excluded)
  table.sort(excluded, function(a, b) return a[1] < b[1] end)
  local result, firstBlocked = {}, 1
  for _, interval in ipairs(intervals) do
    local cursor, last = interval[1], interval[2]
    while firstBlocked <= #excluded and excluded[firstBlocked][2] <= cursor do
      firstBlocked = firstBlocked + 1
    end
    for index = firstBlocked, #excluded do
      local blocked = excluded[index]
      if blocked[1] > last then break end
      if blocked[2] > cursor then
        if blocked[1] >= cursor then
          result[#result + 1] = { cursor, math.min(last, blocked[1]) }
        end
        cursor = math.max(cursor, blocked[2])
        if cursor > last then break end
      end
    end
    if cursor <= last then result[#result + 1] = { cursor, last } end
  end
  return result
end

-- Allowed intervals exclude track joints and construction boundaries. Choose
-- the greatest feasible count, then distribute it within the usable span.
-- Backward feasibility bounds keep rounding around joints from making a gap
-- shorter than the requested minimum.
function spacing.plan(intervals, minimum, maximumCount, layout)
  assert(type(minimum) == "number" and minimum > 0, "invalid minimum spacing")
  maximumCount = maximumCount or 1000
  if #intervals == 0 then return {} end
  layout = layout or {}
  local spread, phase = layout.spread or 1, layout.phase or 0.5
  local first, last = intervals[1][1], intervals[#intervals][2]
  local count, cursor = 0, first
  while cursor and count < maximumCount do
    count = count + 1
    cursor = nextAllowed(intervals, cursor + minimum)
  end
  if count == 1 then
    return { nearestAllowed(intervals, first + (last - first) * phase, first, last) }
  end

  local latest = { [count] = last }
  for index = count - 1, 1, -1 do
    latest[index] = previousAllowed(intervals, latest[index + 1] - minimum)
  end
  local fullGap = (last - first) / (count - 1)
  local targetGap = minimum + (fullGap - minimum) * spread
  local occupied = (count - 1) * targetGap
  local start = first + ((last - first) - occupied) * phase
  local result = {}
  for index = 1, count do
    local ideal = start + (index - 1) * targetGap
    local lower = index == 1 and first or result[index - 1] + minimum
    -- Floating-point subtraction in the backward pass may differ by a few ulps.
    local upper = math.max(lower, latest[index])
    result[index] = assert(nearestAllowed(intervals, ideal, lower, upper))
  end
  return result
end

return spacing
