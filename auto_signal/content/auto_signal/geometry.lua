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

function geometry.forSegment(segment)
  if not segment.geometry then segment.geometry = curve(segment.base) end
  return segment.geometry
end

function geometry.parameterAt(segment, fraction)
  local curveData = geometry.forSegment(segment)
  return interpolate(curveData.points, fraction*curveData.length, "distance", "t")
end

-- Compare the native rendered pose in each edge's local track frame. Native
-- Mat4f uses columns 0..3. Keep both plane-axis signs to distinguish reflection
-- as well as rotation; complement both bits when the base edge is reversed.
function geometry.relativePose(data, transform, axis)
  assert(transform, "signal transform unavailable")
  local position = transform:cols(3)
  local nearest, tx, ty, tz = math.huge, nil, nil, nil
  for index = 1, #data.points-1 do
    local a, b = data.points[index].p, data.points[index+1].p
    local x, y, z = b.x-a.x, b.y-a.y, b.z-a.z
    local lengthSquared = x*x+y*y+z*z
    if lengthSquared > 0 then
      local t = math.max(0,math.min(1,((position.x-a.x)*x+(position.y-a.y)*y+(position.z-a.z)*z)/lengthSquared))
      local distance = squaredDistance(position, mix(a,b,t))
      if distance < nearest then nearest, tx, ty, tz = distance, x, y, z end
    end
  end
  assert(tx, "signal track tangent unavailable")
  local function projection(index)
    local column = transform:cols(index)
    return column.x*tx+column.y*ty+column.z*tz
  end
  if axis == nil then axis = math.abs(projection(0)) >= math.abs(projection(1)) and 0 or 1 end
  local dot = projection(axis)
  assert(math.abs(dot) > 1e-6*math.sqrt(tx*tx+ty*ty+tz*tz), "signal orientation unavailable")
  local other = transform:cols(1-axis)
  local side = -other.x*ty+other.y*tx
  assert(math.abs(side) > 1e-6*math.sqrt(tx*tx+ty*ty), "signal transverse orientation unavailable")
  return (dot > 0 and 1 or 0) + (side > 0 and 2 or 0), axis
end

return geometry
