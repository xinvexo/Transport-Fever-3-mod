-- Draw the design independently of native construction validation. Invalid
-- proposals may have no transport network at all (and thus no model preview).
local M = {}

function M.geometry(api, segments, matrix)
  local result = {}
  local function transform(p, point)
    return { matrix[1]*p[1]+matrix[5]*p[2]+matrix[9]*p[3]+(point and matrix[13] or 0),
      matrix[2]*p[1]+matrix[6]*p[2]+matrix[10]*p[3]+(point and matrix[14] or 0),
      matrix[3]*p[1]+matrix[7]*p[2]+matrix[11]*p[3]+(point and matrix[15] or 0) }
  end
  for _, segment in ipairs(segments) do
    local p0, p1 = transform(segment.p0, true), transform(segment.p1, true)
    local t0, t1 = transform(segment.t0), transform(segment.t1)
    local length, previous = 0, p0
    for i = 1, 16 do
      local u, point = i/16, {}
      for j = 1, 2 do
        point[j] = (2*u^3-3*u*u+1)*p0[j] + (u^3-2*u*u+u)*t0[j]
          + (-2*u^3+3*u*u)*p1[j] + (u^3-u*u)*t1[j]
      end
      length = length + math.sqrt((point[1]-previous[1])^2 + (point[2]-previous[2])^2)
      previous = point
    end
    assert(length >= 2 and length < math.huge, "Invalid rail preview curve length")
    local spline = api.type.EdgeGeometry.CubicSpline.new()
    spline.pos = { api.type.Vec2f.new(p0[1], p0[2]), api.type.Vec2f.new(p1[1], p1[2]) }
    spline.tangent = { api.type.Vec2f.new(t0[1], t0[2]), api.type.Vec2f.new(t1[1], t1[2]) }
    local geom = api.type.EdgeGeometry.new()
    geom.type = api.type.EdgeGeometry.Type.CUBIC_SPLINE
    geom.cubicSpline = spline
    geom.height = api.type.Vec2f.new(p0[3], p1[3])
    geom.tangent = api.type.Vec2f.new(t0[3], t1[3])
    geom.length, geom.width = length, 1.5
    result[#result + 1] = geom
  end
  return result
end

function M.edges(api, builtin, geometries, allowed)
  local edges = {}
  local color = allowed == false and api.type.Vec4f.new(1, .25, .18, 1) or api.type.Vec4f.new(.2, .65, 1, 1)
  for _, geometry in ipairs(geometries) do
    local edge = builtin.type.EdgeRenderable.Edge.new(geometry)
    edge.colors = { color, color }
    edge.width, edge.offsetZ, edge.stepSize = 1.5, .15, 1
    edges[#edges + 1] = edge
  end
  return edges
end

return M
