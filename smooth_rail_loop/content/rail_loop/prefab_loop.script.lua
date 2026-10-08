local geometry = require "xin_smooth_rail_loop_1::/rail_loop/prefab_geometry.lua"
local paramUtil = require "::/scripts/construction/param_util.tl"

function data()
  return {
    updateFn = function(captureParams, params)
      params = params or {}
      local trackTypes = paramUtil.getRailTrackTypes(params.catenary == 2)
      local index = math.max(1, math.min(#trackTypes, math.floor(tonumber(params.trackType) or 1)))
      local trackType = params.streetTemplate or trackTypes[index]
      local segments = geometry.generate(captureParams.kind)
      local result = { models = {}, groundFaces = {}, edgeLists = {}, cost = 0 }
      local group, previousKind

      for segmentIndex, segment in ipairs(segments) do
        if segment.kind ~= previousKind then
          group = {
            type = "TRACK", params = { type = trackType },
            edges = {}, snapNodes = {}, freeNodes = {},
            alignTerrain = segment.kind == "NORMAL",
          }
          if segment.kind == "BRIDGE" then
            group.edgeType = "BRIDGE"
            -- Native stone bridges support rail in every year.
            group.edgeTypeName = "::/infrastructure/bridge/stone.bridge"
          elseif segment.kind == "TUNNEL" then
            group.edgeType = "TUNNEL"
            group.edgeTypeName = "::/infrastructure/tunnel/tunnel_a.tunnel"
          end
          result.edgeLists[#result.edgeLists + 1] = group
          previousKind = segment.kind
        end
        local nodeIndex = #group.edges
        group.edges[nodeIndex + 1] = { segment.p0, segment.t0 }
        group.edges[nodeIndex + 2] = { segment.p1, segment.t1 }
        group.freeNodes[#group.freeNodes + 1] = nodeIndex
        group.freeNodes[#group.freeNodes + 1] = nodeIndex + 1
        if segmentIndex == 1 then group.snapNodes[#group.snapNodes + 1] = nodeIndex end
        if segmentIndex == #segments then group.snapNodes[#group.snapNodes + 1] = nodeIndex + 1 end
      end
      return result
    end,
  }
end
