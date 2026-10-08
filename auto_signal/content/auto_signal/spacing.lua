-- Count from the forward end. If a target is blocked, move it backwards to
-- the nearest allowed boundary and measure the next gap from that actual light.
local spacing = {}
local EPSILON = 1e-7

local function merge(excluded)
  local ordered, result = {}, {}
  for _, range in ipairs(excluded or {}) do ordered[#ordered+1] = {range[1], range[2]} end
  table.sort(ordered, function(a,b) return a[1] < b[1] end)
  for _, range in ipairs(ordered) do
    local previous = result[#result]
    if previous and range[1] <= previous[2]+EPSILON then
      previous[2] = math.max(previous[2], range[2])
    else
      result[#result+1] = range
    end
  end
  return result
end

function spacing.plan(length, gap, reversed, endClearance, maximumCount, excluded)
  assert(type(gap) == "number" and gap > 0 and gap < math.huge, "invalid signal spacing")
  local first = endClearance or 0
  local last = length-first
  if last < first then return nil, "no room for signals" end
  local blocked = merge(excluded)
  local candidate = reversed and first or last
  local result = {}
  while candidate >= first-EPSILON and candidate <= last+EPSILON do
    for _, range in ipairs(blocked) do
      if candidate <= range[1]+EPSILON then break end
      if candidate < range[2]-EPSILON then
        candidate = reversed and range[2] or range[1]
        break
      end
    end
    if candidate < first-EPSILON or candidate > last+EPSILON then break end
    if #result >= (maximumCount or 1000) then return nil, "section exceeds signal count limit" end
    candidate = math.max(first, math.min(last, candidate))
    result[#result+1] = candidate
    candidate = candidate + (reversed and gap or -gap)
  end
  if #result == 0 then return nil, "no room for signals" end
  -- Return in canonical track order so network.plan can walk segments once.
  if not reversed then
    for i = 1, math.floor(#result/2) do
      local j = #result-i+1
      result[i], result[j] = result[j], result[i]
    end
  end
  return result
end

return spacing
