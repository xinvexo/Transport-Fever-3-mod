-- Compact prefab geometry.
-- Both main-line connections stay at the placement height and 5 m apart.
local geometry = {}
local pi = math.pi
local sin, cos = math.sin, math.cos
local FLARE_ANGLE = pi / 3
local CIRCLE_ANGLE = 5 * pi / 3

local function smooth(u)
  return u ^ 3 * (10 - 15 * u + 6 * u * u)
end

local function smoothDerivative(u)
  return 30 * u * u * (1 - u) * (1 - u)
end

-- The flare begins with zero curvature and ends with the circle's
-- clockwise curvature. This removes curvature jumps at both joins.
local function heading(u, lambda)
  return pi / 2 + (FLARE_ANGLE + lambda / 2) / 2 * (1 - cos(pi * u))
    - lambda * (u ^ 3 - u ^ 4 / 2)
end

local function integrate(u, lambda, component)
  if u == 0 then return 0 end
  local n = 96
  local step = u / n
  local sum = component(heading(0, lambda)) + component(heading(u, lambda))
  for i = 1, n - 1 do
    sum = sum + (i % 2 == 0 and 2 or 4) * component(heading(i * step, lambda))
  end
  return sum * step / 3
end

local function flareLength(radius, spacing)
  local target = 0.5 - spacing / (2 * radius)
  local low, high = 0.05, 2
  for _ = 1, 42 do
    local mid = (low + high) / 2
    local width = -mid * integrate(1, mid, cos)
    if width < target then low = mid else high = mid end
  end
  return radius * (low + high) / 2
end

local function heightFraction(fraction)
  local low, high = 0, 1
  for _ = 1, 42 do
    local mid = (low + high) / 2
    if smooth(mid) < fraction then low = mid else high = mid end
  end
  return (low + high) / 2
end

function geometry.generate(kind)
  assert(kind == "raised" or kind == "lowered", "Unknown rail loop prefab")
  local radius, spacing, grade = 130, 5, 0.08
  local elevation = kind == "raised" and 8 or -12
  local flare = flareLength(radius, spacing)
  local lambda = flare / radius
  -- The quintic height profile has zero slope and vertical curvature at
  -- both ends, with a peak derivative of 1.875. Leave a small margin for
  -- the cubic track approximation's horizontal arc length.
  local lead = math.max(40, 1.9 * math.abs(elevation) / grade - flare)
  lead = math.ceil(lead / 5) * 5
  local approach = lead + flare
  local circleLength = radius * CIRCLE_ANGLE
  local total = 2 * approach + circleLength
  local centerY = lead + flare * integrate(1, lambda, sin) + radius * math.sqrt(3) / 2

  local function incoming(s)
    local u = math.max(0, math.min(1, s / approach))
    local z = elevation * smooth(u)
    local dz = elevation * smoothDerivative(u) / approach
    if s <= lead then return { -spacing / 2, s, z }, { 0, 1, dz } end
    local f = math.min(1, (s - lead) / flare)
    local angle = heading(f, lambda)
    return {
      -spacing / 2 + flare * integrate(f, lambda, cos),
      lead + flare * integrate(f, lambda, sin), z,
    }, { cos(angle), sin(angle), dz }
  end

  local function point(s)
    if s <= approach then return incoming(s) end
    if s >= approach + circleLength then
      local p, t = incoming(total - s)
      return { -p[1], p[2], p[3] }, { t[1], -t[2], -t[3] }
    end
    local angle = 4 * pi / 3 - (s - approach) / radius
    return { radius * cos(angle), centerY + radius * sin(angle), elevation },
      { sin(angle), -cos(angle), 0 }
  end

  -- Start elevated structures after an earthwork approach; keep the
  -- tunnel's railhead deep enough for the native railway tunnel envelope.
  local transition
  if elevation ~= 0 then
    local structureHeight = elevation > 0 and 5 or 10
    transition = approach * heightFraction(structureHeight / math.abs(elevation))
  end
  local breaks = { 0, lead, approach, approach + circleLength, total - lead, total }
  if transition then
    breaks[#breaks + 1] = transition
    breaks[#breaks + 1] = total - transition
  end
  table.sort(breaks)

  local segments = {}
  for i = 1, #breaks - 1 do
    local first, last = breaks[i], breaks[i + 1]
    local inFlare = (first >= lead and last <= approach)
      or (first >= approach + circleLength and last <= total - lead)
    local count = math.max(1, math.ceil((last - first) / (inFlare and 12 or 20)))
    local length = (last - first) / count
    if length > 1e-6 then
      for j = 0, count - 1 do
        local s0, s1 = first + j * length, first + (j + 1) * length
        local p0, t0 = point(s0)
        local p1, t1 = point(s1)
        local mid = (s0 + s1) / 2
        local kind = "NORMAL"
        if transition and mid > transition and mid < total - transition then
          kind = elevation > 0 and "BRIDGE" or "TUNNEL"
        end
        segments[#segments + 1] = {
          kind = kind, p0 = p0, p1 = p1,
          t0 = { t0[1] * length, t0[2] * length, t0[3] * length },
          t1 = { t1[1] * length, t1[2] * length, t1[3] * length },
        }
      end
    end
  end
  return segments, { radius = radius, lead = lead, approach = approach,
    length = total, width = 2 * radius, depth = centerY + radius,
    elevation = elevation, spacing = spacing, grade = grade }
end

return geometry
