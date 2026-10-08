local geometry = require "xin_smooth_rail_loop_1::/rail_loop/prefab_geometry.lua"
local paramUtil = require "::/scripts/construction/param_util.tl"
local bridgeChoices = require "xin_smooth_rail_loop_1::/rail_loop/bridge_choices.lua"
local terrainPlan = require "xin_smooth_rail_loop_1::/rail_loop/terrain_plan.lua"

function data()
  return {
    updateFn = function(captureParams, params)
      params = params or {}
      local trackTypes = paramUtil.getRailTrackTypes(params.catenary == 2)
      local index = math.max(1, math.min(#trackTypes, math.floor(tonumber(params.trackType) or 1)))
      local trackType = params.streetTemplate or trackTypes[index]
      local segments = geometry.network(captureParams.kind)
      if params.xinTerrainPlan then
        assert(params.xinGeometryVersion == 1, "Unsupported rail terrain geometry version")
        segments = terrainPlan.apply(segments, params.xinTerrainPlan)
      end
      local result = { models = {}, groundFaces = {}, edgeLists = {}, cost = 0 }
      local group, previousKind, previousRoute

      for _, segment in ipairs(segments) do
        if segment.kind ~= previousKind or segment.route ~= previousRoute then
          group = {
            type = "TRACK", params = { type = trackType },
            edges = {}, snapNodes = {}, freeNodes = {},
            alignTerrain = segment.kind == "NORMAL",
          }
          if segment.kind == "BRIDGE" then
            group.edgeType = "BRIDGE"
            group.edgeTypeName = bridgeChoices.resource(params.bridgeTypeModern or params.bridgeType)
          elseif segment.kind == "TUNNEL" then
            group.edgeType = "TUNNEL"
            group.edgeTypeName = "::/infrastructure/tunnel/tunnel_a.tunnel"
          end
          result.edgeLists[#result.edgeLists + 1] = group
          previousKind = segment.kind
          previousRoute = segment.route
        end
        local nodeIndex = #group.edges
        group.edges[nodeIndex + 1] = { segment.p0, segment.t0, segment.tag0 }
        group.edges[nodeIndex + 2] = { segment.p1, segment.t1, segment.tag1 }
        group.freeNodes[#group.freeNodes + 1] = nodeIndex
        group.freeNodes[#group.freeNodes + 1] = nodeIndex + 1
        if segment.snap0 then group.snapNodes[#group.snapNodes + 1] = nodeIndex end
        if segment.snap1 then group.snapNodes[#group.snapNodes + 1] = nodeIndex + 1 end
      end
      return result
    end,
  }
end
