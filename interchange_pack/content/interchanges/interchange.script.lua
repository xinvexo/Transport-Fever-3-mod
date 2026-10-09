local geometry = require "xin_interchange_pack_1::/interchanges/geometry.lua"
local roads = require "xin_interchange_pack_1::/interchanges/roads.lua"
local settings = require "xin_interchange_pack_1::/interchanges/settings.lua"
local cachedKey,cachedNetwork
local function networkFor(kind,params)
  local values = {kind}
  for key,value in pairs(params) do
    if key~="seed" and key~="year" and key~="rotation" and key~="height" then
      values[#values+1]=key.."="..tostring(value)
    end
  end
  table.sort(values)
  local key=table.concat(values,";")
  if key~=cachedKey then
    cachedNetwork=geometry.generate(kind,params)
    cachedKey=key
  end
  return cachedNetwork
end
local function point(p) return {p[1],p[2],p[3]} end

function data()
  return {
    updateFn = function(captureParams, params)
      params = settings.normalize(params)
      local network = networkFor(captureParams.kind, params)
      local result = { models = {}, groundFaces = {}, edgeLists = {}, cost = 0 }
      local groups = {}
      local profile = roads.select(params)
      local bridge = "::/infrastructure/bridge/concrete.bridge"
      for _, path in ipairs(network.roads) do
        local street = profile[path.profile or path.role] or profile.ramp
        for index, s in ipairs(path.segments) do
          local kind = s.bridge and "BRIDGE" or nil
          -- Native interchanges batch disconnected edges with the same road
          -- and bridge properties. Tags, not list boundaries, connect nodes.
          local key = street .. "\0" .. (kind or "NORMAL") .. "\0" .. (s.bridge and bridge or "")
          local group = groups[key]
          if not group then
            group = { type = "STREET", edgeType = kind, params = { type = street },
              edges = {}, snapNodes = {}, freeNodes = {} }
            if s.bridge then group.edgeTypeName = bridge end
            groups[key] = group
            result.edgeLists[#result.edgeLists+1] = group
          end
          local n = #group.edges
          -- Explicit internal tags also join normal/bridge edge-list boundaries.
          group.edges[n+1] = { point(s.p0), point(s.t0), s.tag0 or ("ip:" .. path.id .. ":" .. (index-1)) }
          group.edges[n+2] = { point(s.p1), point(s.t1), s.tag1 or ("ip:" .. path.id .. ":" .. index) }
          group.freeNodes[#group.freeNodes+1] = n
          group.freeNodes[#group.freeNodes+1] = n+1
        end
      end
      return result
    end,
  }
end
