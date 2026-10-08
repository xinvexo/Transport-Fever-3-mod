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
        if root - boundaries[#boundaries] > 1e-7 and 1 - root > 1e-7 then
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
    local minimum = 1.01 / length
    -- A tiny structural tail can stay with its adjoining ground entry; the
    -- earthwork bounds below still reject large cuts/fills on a cliff face.
    for i = #pieces, 1, -1 do
      local piece = pieces[i]
      if piece[3] ~= 1 and piece[2] - piece[1] < minimum then
        if pieces[i - 1] and pieces[i - 1][3] == 1 then
          pieces[i - 1][2] = piece[2]
          table.remove(pieces, i)
        elseif pieces[i + 1] and pieces[i + 1][3] == 1 then
          pieces[i + 1][1] = piece[1]
          table.remove(pieces, i)
        end
      end
    end
    for i = #pieces, 2, -1 do
      if pieces[i][3] == pieces[i - 1][3] then
        pieces[i - 1][2] = pieces[i][2]
        table.remove(pieces, i)
      end
    end
    -- Widen short ground entries INTO the adjoining structure, rather than
    -- turning an entire long tunnel/bridge edge into deep-cut earthwork.
    for i, piece in ipairs(pieces) do
      if piece[3] == 1 and piece[2] - piece[1] < minimum then
        local missing = minimum - (piece[2] - piece[1])
        local nextPiece, previousPiece = pieces[i + 1], pieces[i - 1]
        if nextPiece and nextPiece[2] - nextPiece[1] > minimum + missing then
          piece[2] = piece[2] + missing
          nextPiece[1] = piece[2]
        elseif previousPiece and previousPiece[2] - previousPiece[1] > minimum + missing then
          piece[1] = piece[1] - missing
          previousPiece[2] = piece[1]
        end
      end
    end
    for _, piece in ipairs(pieces) do
      -- Do not silently excavate a cliff when an extremely short transition
      -- cannot meet the native track/portal geometry constraints.
      assert((piece[2] - piece[1]) * length >= 1, "地形变化过急，桥隧衔接长度不足")
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

return M
