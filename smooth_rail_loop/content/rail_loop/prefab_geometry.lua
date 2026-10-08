-- A compact balloon branch with short, level main-line connection stubs.
local geometry = {}
local pi, sin, cos = math.pi, math.sin, math.cos
local RADIUS, SPACING = 70, 5
local TRANSITION, FLARE_ANGLE = 4, pi / 3
local CIRCLE_LENGTH = RADIUS * 5 * pi / 3
local LEVEL_TURNOUT, GRADE, VERTICAL_BLEND = 30, 0.08, 20
local CONNECTION_LENGTH = 25

local function clamp(x, low, high) return math.max(low, math.min(high, x)) end

local function holdLength(radius)
  return radius * FLARE_ANGLE - TRANSITION + TRANSITION * radius / (2 * RADIUS)
end

-- Linear curvature transitions join the straight main line to a constant
-- left bend, then reverse smoothly into the clockwise return circle.
local function heading(s, radius)
  local hold = holdLength(radius)
  local u = clamp(s, 0, TRANSITION)
  local v = clamp(s - TRANSITION, 0, hold)
  local w = clamp(s - TRANSITION - hold, 0, TRANSITION)
  return pi / 2 + u * u / (2 * TRANSITION * radius) + v / radius
    + w / radius - (1 / radius + 1 / RADIUS) * w * w / (2 * TRANSITION)
end

local function integrate(first, last, radius, component)
  if last <= first then return 0 end
  local n = 96
  local step = (last - first) / n
  local sum = component(heading(first, radius)) + component(heading(last, radius))
  for i = 1, n - 1 do
    sum = sum + (i % 2 == 0 and 2 or 4) * component(heading(first + i * step, radius))
  end
  return sum * step / 3
end

local function flareIntegral(s, radius, component)
  local holdEnd = TRANSITION + holdLength(radius)
  return integrate(0, math.min(s, TRANSITION), radius, component)
    + integrate(TRANSITION, math.min(s, holdEnd), radius, component)
    + integrate(holdEnd, s, radius, component)
end

local low, high = 55, RADIUS
for _ = 1, 42 do
  local mid = (low + high) / 2
  local length = holdLength(mid) + 2 * TRANSITION
  local width = -flareIntegral(length, mid, cos)
  if width < RADIUS / 2 - SPACING / 2 then low = mid else high = mid end
end
local FLARE_RADIUS = (low + high) / 2
local FLARE = holdLength(FLARE_RADIUS) + 2 * TRANSITION
local TOTAL = 2 * FLARE + CIRCLE_LENGTH
local CENTER_Y = flareIntegral(FLARE, FLARE_RADIUS, sin) + RADIUS * math.sqrt(3) / 2
local DEPTH = CENTER_Y + RADIUS

local function planarPoint(s)
  if s >= TOTAL - FLARE then
    local q = TOTAL - s
    local angle = heading(q, FLARE_RADIUS)
    return { SPACING / 2 - flareIntegral(q, FLARE_RADIUS, cos),
      flareIntegral(q, FLARE_RADIUS, sin), 0 }, { cos(angle), -sin(angle), 0 }
  end
  if s <= FLARE then
    local angle = heading(s, FLARE_RADIUS)
    return { -SPACING / 2 + flareIntegral(s, FLARE_RADIUS, cos),
      flareIntegral(s, FLARE_RADIUS, sin), 0 }, { cos(angle), sin(angle), 0 }
  end
  local angle = 4 * pi / 3 - (s - FLARE) / RADIUS
  return { RADIUS * cos(angle), CENTER_Y + RADIUS * sin(angle), 0 },
    { sin(angle), -cos(angle), 0 }
end

local function ease(u) return u * u * (3 - 2 * u) end
local function easeIntegral(u) return u ^ 3 - u ^ 4 / 2 end

local function heightAt(q, height)
  local s = q - LEVEL_TURNOUT
  local climb = height / GRADE + VERTICAL_BLEND
  if s <= 0 then return 0, 0 end
  if s < VERTICAL_BLEND then
    local u = s / VERTICAL_BLEND
    return GRADE * VERTICAL_BLEND * easeIntegral(u), GRADE * ease(u)
  end
  if s <= climb - VERTICAL_BLEND then
    return GRADE * (s - VERTICAL_BLEND / 2), GRADE
  end
  if s < climb then
    local u = (climb - s) / VERTICAL_BLEND
    return height - GRADE * VERTICAL_BLEND * easeIntegral(u), GRADE * ease(u)
  end
  return height, 0
end

function geometry.generate(kind)
  assert(kind == "raised" or kind == "lowered", "Unknown rail loop prefab")
  -- Leave room for the through tracks, overhead wires and bridge deck.
  local elevation = kind == "raised" and 16 or -12
  local height, sign = math.abs(elevation), elevation > 0 and 1 or -1
  local climb = height / GRADE + VERTICAL_BLEND
  assert(LEVEL_TURNOUT + climb <= TOTAL / 2, "Not enough length for the rail grade")

  local function point(s)
    local p, t = planarPoint(s)
    local z, dz = heightAt(math.min(s, TOTAL - s), height)
    p[3] = sign * z
    t[3] = sign * dz * (s > TOTAL / 2 and -1 or 1)
    return p, t
  end

  local structureHeight = elevation > 0 and 5 or 10
  local first, last = LEVEL_TURNOUT, LEVEL_TURNOUT + climb
  for _ = 1, 42 do
    local mid = (first + last) / 2
    if heightAt(mid, height) < structureHeight then first = mid else last = mid end
  end
  local transition = (first + last) / 2
  local breaks = { 0, TOTAL / 2, TOTAL }
  for _, s in ipairs({ TRANSITION, FLARE - TRANSITION, FLARE, LEVEL_TURNOUT,
      LEVEL_TURNOUT + VERTICAL_BLEND, LEVEL_TURNOUT + climb - VERTICAL_BLEND,
      LEVEL_TURNOUT + climb, transition }) do
    breaks[#breaks + 1], breaks[#breaks + 2] = s, TOTAL - s
  end
  table.sort(breaks)
  -- Keep short plateau boundaries from introducing sub-metre track edges.
  local divisions = { breaks[1] }
  for i = 2, #breaks do
    if breaks[i] - divisions[#divisions] > 1 then divisions[#divisions + 1] = breaks[i] end
  end

  local segments = {}
  for i = 1, #divisions - 1 do
    local start, finish = divisions[i], divisions[i + 1]
    local count = math.max(1, math.ceil((finish - start) / 12))
    local length = (finish - start) / count
    for j = 0, count - 1 do
      local s0, s1 = start + j * length, start + (j + 1) * length
      local p0, t0 = point(s0)
      local p1, t1 = point(s1)
      local mid = (s0 + s1) / 2
      local segmentKind = "NORMAL"
      if mid > transition and mid < TOTAL - transition then
        segmentKind = elevation > 0 and "BRIDGE" or "TUNNEL"
      end
      segments[#segments + 1] = {
        kind = segmentKind, p0 = p0, p1 = p1,
        t0 = { t0[1] * length, t0[2] * length, t0[3] * length },
        t1 = { t1[1] * length, t1[2] * length, t1[3] * length },
      }
    end
  end
  return segments, { radius = RADIUS, length = TOTAL, width = 2 * RADIUS,
    depth = DEPTH + CONNECTION_LENGTH, loopDepth = DEPTH,
    elevation = elevation, spacing = SPACING, grade = GRADE,
    mainlineStart = -CONNECTION_LENGTH, mainlineEnd = CONNECTION_LENGTH }
end

function geometry.network(kind)
  local segments, info = geometry.generate(kind)
  for i, segment in ipairs(segments) do
    segment.route = "loop"
    segment.tag0 = i == 1 and "junction:left" or "loop:" .. (i - 1)
    segment.tag1 = i == #segments and "junction:right" or "loop:" .. i
  end
  for side, x in ipairs({ -info.spacing / 2, info.spacing / 2 }) do
    local name = side == 1 and "left" or "right"
    for half, bounds in ipairs({ { info.mainlineStart, 0 }, { 0, info.mainlineEnd } }) do
      local count = math.ceil((bounds[2] - bounds[1]) / 12)
      local length = (bounds[2] - bounds[1]) / count
      for i = 1, count do
        local y0, y1 = bounds[1] + (i - 1) * length, bounds[1] + i * length
        local tag0 = y0 == 0 and "junction:" .. name or "main:" .. name .. ":" .. half .. ":" .. (i - 1)
        local tag1 = y1 == 0 and "junction:" .. name or "main:" .. name .. ":" .. half .. ":" .. i
        segments[#segments + 1] = { kind = "NORMAL", route = "main",
          p0 = { x, y0, 0 }, p1 = { x, y1, 0 },
          t0 = { 0, length, 0 }, t1 = { 0, length, 0 }, tag0 = tag0, tag1 = tag1,
          snap0 = half == 1 and i == 1, snap1 = half == 2 and i == count }
      end
    end
  end
  return segments, info
end

return geometry
