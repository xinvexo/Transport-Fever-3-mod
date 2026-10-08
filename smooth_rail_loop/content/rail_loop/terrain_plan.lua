-- Pure geometry: the GUI supplies world terrain samples; the construction
-- replays this saved plan without querying a different location or terrain.
local M = {}
local TYPES = { "NORMAL", "BRIDGE", "TUNNEL" }
local BRIDGE_CLEARANCE, TUNNEL_COVER = 5, 10

function M.point(edge, u)
  local p, t = {}, {}
  for j = 1, 3 do
    p[j] = (2*u^3-3*u*u+1)*edge.p0[j] + (u^3-2*u*u+u)*edge.t0[j]
      + (-2*u^3+3*u*u)*edge.p1[j] + (u^3-u*u)*edge.t1[j]
    t[j] = (6*u*u-6*u)*edge.p0[j] + (3*u*u-4*u+1)*edge.t0[j]
      + (-6*u*u+6*u)*edge.p1[j] + (3*u*u-2*u)*edge.t1[j]
  end
  return p, t
end

-- Column-major rigid transform, shared by sampling and construction placement.
function M.pose(x, y, z, rotation)
  local c, s = math.cos(rotation), math.sin(rotation)
  return { c, s, 0, 0, -s, c, 0, 0, 0, 0, 1, 0, x, y, z, 1 }
end

function M.world(p, m)
  return { m[1]*p[1]+m[5]*p[2]+m[9]*p[3]+m[13],
    m[2]*p[1]+m[6]*p[2]+m[10]*p[3]+m[14],
    m[3]*p[1]+m[7]*p[2]+m[11]*p[3]+m[15] }
end

local function finite(value)
  return type(value) == "number" and value == value and math.abs(value) < math.huge
end

local function material(gap)
  if gap >= BRIDGE_CLEARANCE then return 2 end
  if gap <= -TUNNEL_COVER then return 3 end
  return 1
end

function M.sample(edges, matrix, terrainHeight)
  local plan = {}
  for index, edge in ipairs(edges) do
    local function gap(u)
      local p = M.world(M.point(edge, u), matrix)
      local terrain = terrainHeight(p[1], p[2])
      assert(finite(terrain), "Terrain sample unavailable")
      return p[3] - terrain
    end
    local length = math.sqrt(edge.t0[1]^2 + edge.t0[2]^2 + edge.t0[3]^2)
    local epsilon = .02 / length
    local count = math.max(4, math.ceil(length / .5))
    local boundaries = { 0 }
    local previous = gap(0)
    for i = 1, count do
      local current = gap(i / count)
      local roots = {}
      for _, threshold in ipairs({ -TUNNEL_COVER, BRIDGE_CLEARANCE }) do
        if (previous < threshold) ~= (current < threshold) then
          local a, b = (i - 1) / count, i / count
          for _ = 1, 18 do
            local mid = (a + b) / 2
            if (gap(mid) < threshold) == (previous < threshold) then a = mid else b = mid end
          end
          roots[#roots + 1] = (a + b) / 2
        end
      end
      table.sort(roots)
      for _, root in ipairs(roots) do
        -- Coalesce centimetre-scale duplicate boundaries; do not impose an
        -- undocumented one-metre minimum on real bridge/tunnel transitions.
        if root - boundaries[#boundaries] > epsilon and 1 - root > epsilon then
          boundaries[#boundaries + 1] = root
        end
      end
      previous = current
    end
    boundaries[#boundaries + 1] = 1
    local pieces = {}
    for i = 1, #boundaries - 1 do
      local a, b = boundaries[i], boundaries[i + 1]
      local code = material(gap((a + b) / 2))
      pieces[#pieces + 1] = { a, b, code }
    end
    for i = #pieces, 2, -1 do
      if pieces[i][3] == pieces[i - 1][3] then
        pieces[i - 1][2] = pieces[i][2]
        table.remove(pieces, i)
      end
    end
    for _, piece in ipairs(pieces) do
      -- Preserve exact subcurves and let the engine check their buildability.
      if piece[3] == 1 then
        local function checkEarthwork(value)
          assert(value <= BRIDGE_CLEARANCE + 2 and value >= -TUNNEL_COVER - 2,
            "地形变化过急，无法在此衔接地面轨道与桥隧")
        end
        local samples = math.max(2, math.ceil((piece[2] - piece[1]) * length / .5))
        for i = 0, samples do
          checkEarthwork(gap(piece[1] + (piece[2] - piece[1]) * i / samples))
        end
        -- Retain the original sampling lattice: shifting the grid after a
        -- split must not hide a narrow terrain peak that was already found.
        for i = math.ceil(piece[1]*count), math.floor(piece[2]*count) do checkEarthwork(gap(i/count)) end
      end
    end
    plan[index] = pieces
  end
  return plan
end

-- Only for showing the design when terrain sampling fails. The caller must
-- mark this candidate as preview-only and must never commit it to the world.
function M.previewPlan(edges)
  local result = {}
  for index, edge in ipairs(edges) do
    result[index] = { { 0, 1, edge.kind == "BRIDGE" and 2 or edge.kind == "TUNNEL" and 3 or 1 } }
  end
  return result
end

function M.apply(edges, plan)
  assert(type(plan) == "table" and #plan == #edges, "Rail terrain plan does not match geometry")
  local result = {}
  for index, edge in ipairs(edges) do
    local previous = 0
    for i, piece in ipairs(plan[index]) do
      local a, b, code = piece[1], piece[2], piece[3]
      assert(finite(a) and finite(b) and a == previous and b > a and b <= 1 and TYPES[code],
        "Invalid rail terrain interval")
      local p0, t0 = M.point(edge, a)
      local p1, t1 = M.point(edge, b)
      for j = 1, 3 do t0[j], t1[j] = t0[j] * (b - a), t1[j] * (b - a) end
      result[#result + 1] = { p0 = p0, p1 = p1, t0 = t0, t1 = t1,
        kind = TYPES[code], route = edge.route,
        tag0 = a == 0 and edge.tag0 or "terrain:" .. index .. ":" .. (i - 1),
        tag1 = b == 1 and edge.tag1 or "terrain:" .. index .. ":" .. i,
        snap0 = a == 0 and edge.snap0, snap1 = b == 1 and edge.snap1 }
      previous = b
    end
    assert(previous == 1, "Incomplete rail terrain plan")
  end
  return result
end

function M.equal(a, b)
  if #a ~= #b then return false end
  for i, pieces in ipairs(a) do
    if #pieces ~= #b[i] then return false end
    for j, piece in ipairs(pieces) do
      local other = b[i][j]
      if piece[3] ~= other[3] or math.abs(piece[1]-other[1]) > 1e-6
        or math.abs(piece[2]-other[2]) > 1e-6 then return false end
    end
  end
  return true
end

-- Terrain crossings can sit centimetres from an existing curve division.
-- Remove that redundant division inside one material; never move a portal,
-- merge different materials, or remove a turnout. Refit only if geometry
-- stays within 15 mm of the original and retains native radius/grade limits.
function M.joinShortEdges(segments)
  local result, degree = {}, {}
  for i, edge in ipairs(segments) do
    result[i] = edge
    degree[edge.tag0] = (degree[edge.tag0] or 0) + 1
    degree[edge.tag1] = (degree[edge.tag1] or 0) + 1
  end
  local function length(edge)
    return (math.sqrt(edge.t0[1]^2 + edge.t0[2]^2) + math.sqrt(edge.t1[1]^2 + edge.t1[2]^2)) / 2
  end
  local function join(a, b)
    if a.tag1 ~= b.tag0 or degree[a.tag1] ~= 2 or a.kind ~= b.kind or a.route ~= b.route then return nil end
    local la, lb = length(a), length(b)
    if math.min(la, lb) >= 3 or la + lb > 24 then return nil end
    local fraction, total = la / (la + lb), la + lb
    local edge = { p0 = a.p0, p1 = b.p1, t0 = {}, t1 = {}, kind = a.kind, route = a.route,
      tag0 = a.tag0, tag1 = b.tag1, snap0 = a.snap0, snap1 = b.snap1 }
    for j = 1, 3 do edge.t0[j], edge.t1[j] = a.t0[j]*total/la, b.t1[j]*total/lb end
    for side, original in ipairs({ a, b }) do
      for i = 0, 32 do
        local v = i / 32
        local u = side == 1 and v*fraction or fraction + v*(1-fraction)
        local p, t = M.point(edge, u)
        local before = M.point(original, v)
        local distance = 0
        for j = 1, 3 do distance = distance + (p[j]-before[j])^2 end
        if distance > .015^2 then return nil end
        local speed = math.sqrt(t[1]^2 + t[2]^2)
        if speed < 1e-6 or math.abs(t[3])/speed > .085 then return nil end
        local second = {}
        for j = 1, 2 do
          second[j] = (12*u-6)*edge.p0[j] + (6*u-4)*edge.t0[j]
            + (-12*u+6)*edge.p1[j] + (6*u-2)*edge.t1[j]
        end
        if math.abs(t[1]*second[2]-t[2]*second[1]) > speed^3/55 then return nil end
      end
    end
    return edge
  end
  local i = 1
  while i < #result do
    local combined = join(result[i], result[i+1])
    if combined then
      result[i] = combined
      table.remove(result, i+1)
      i = math.max(1, i-1)
    else
      i = i+1
    end
  end
  return result
end

return M
