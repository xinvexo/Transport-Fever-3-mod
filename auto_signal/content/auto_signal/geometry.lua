-- Convert distances along a base-edge curve to its construction parameter.
-- This does not search for neighbours or choose signal locations.
local geometry = {}
local CURVE_TOLERANCE = 0.01

local function point(v)
  assert(v and v.x and v.y and v.z, "track geometry unavailable")
  return { x = v.x, y = v.y, z = v.z }
end

local function mix(a, b, t)
  return { x = a.x + (b.x - a.x) * t,
    y = a.y + (b.y - a.y) * t, z = a.z + (b.z - a.z) * t }
end

local function squaredDistance(a, b)
  return (a.x - b.x)^2 + (a.y - b.y)^2 + (a.z - b.z)^2
end

-- Base-edge endpoint tangents define a cubic spline. Subdivide its equivalent
-- Bezier control polygon, retaining the original edge parameter at each point.
local function curve(base)
  local p, q = point(base.position0), point(base.position1)
  local u, v = point(base.tangent0), point(base.tangent1)
  local a = { x=p.x+u.x/3, y=p.y+u.y/3, z=p.z+u.z/3 }
  local b = { x=q.x-v.x/3, y=q.y-v.y/3, z=q.z-v.z/3 }
  local points = { { p = p, t = 0 } }
  local function split(p0, p1, p2, p3, t0, t1, depth)
    -- Bound parameter interpolation error as well as shape error: a straight
    -- spline with unequal tangents does not advance linearly in its parameter.
    if math.max(squaredDistance(p1,mix(p0,p3,1/3)), squaredDistance(p2,mix(p0,p3,2/3)))
      <= CURVE_TOLERANCE^2 then
      points[#points + 1] = { p = p3, t = t1 }
      return
    end
    assert(depth < 20 and #points < 8192, "track curve too complex for distance conversion")
    local ab, bc, cd = mix(p0,p1,.5), mix(p1,p2,.5), mix(p2,p3,.5)
    local abc, bcd = mix(ab,bc,.5), mix(bc,cd,.5)
    local mid, tm = mix(abc,bcd,.5), (t0+t1)/2
    split(p0,ab,abc,mid,t0,tm,depth+1)
    split(mid,bcd,cd,p3,tm,t1,depth+1)
  end
  split(p,a,b,q,0,1,0)
  local length = 0
  points[1].distance = 0
  for index = 2, #points do
    length = length + math.sqrt(squaredDistance(points[index-1].p, points[index].p))
    points[index].distance = length
  end
  assert(length > 0, "track geometry has zero length")
  return { points = points, length = length }
end

local function interpolate(points, value, source, target)
  local lo, hi = 1, #points
  while lo+1 < hi do
    local mid = math.floor((lo+hi)/2)
    if points[mid][source] < value then lo = mid else hi = mid end
  end
  local a, b = points[lo], points[hi]
  local span = b[source]-a[source]
  local t = span > 0 and math.max(0,math.min(1,(value-a[source])/span)) or 0
  return a[target]+(b[target]-a[target])*t
end

function geometry.prepare(segments, cache)
  for _, segment in ipairs(segments) do
    segment.geometry = cache and cache[segment.entity] or curve(segment.base)
    if cache then cache[segment.entity] = segment.geometry end
  end
end

function geometry.parameterAt(segment, fraction)
  local curveData = segment.geometry
  return interpolate(curveData.points, fraction*curveData.length, "distance", "t")
end

-- Native mission 02 documents that a single lane keeps transport-edge and
-- base-edge directions aligned. Otherwise compare the transport direction
-- with the local base curve, not its overall chord or node-ID ordering.
function geometry.transportOpposite(base, transportGeometry, cachedCurve)
  if base.laneConfigs and #base.laneConfigs == 1 then return false, cachedCurve end
  local data = cachedCurve or curve(base)
  local sample = api.engine.util.transport.calcPosition
  local before, middle, after = sample(transportGeometry, .4), sample(transportGeometry, .5), sample(transportGeometry, .6)
  local dx, dy, dz = after.x-before.x, after.y-before.y, after.z-before.z
  assert(dx*dx+dy*dy+dz*dz > 0, "transport edge direction unavailable")
  local nearest, dot, magnitude = math.huge, nil, nil
  for index = 1, #data.points-1 do
    local a, b = data.points[index].p, data.points[index+1].p
    local x, y, z = b.x-a.x, b.y-a.y, b.z-a.z
    local lengthSquared = x*x+y*y+z*z
    if lengthSquared > 0 then
      local t = math.max(0,math.min(1,((middle.x-a.x)*x+(middle.y-a.y)*y+(middle.z-a.z)*z)/lengthSquared))
      local distance = squaredDistance(middle, mix(a,b,t))
      if distance < nearest then
        nearest, dot, magnitude = distance, dx*x+dy*y+dz*z, math.sqrt(lengthSquared*(dx*dx+dy*dy+dz*dz))
      end
    end
  end
  assert(dot and math.abs(dot) > magnitude*1e-6, "transport and base directions cannot be aligned")
  return dot < 0, data
end

return geometry
