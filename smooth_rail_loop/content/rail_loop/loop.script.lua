local geometry = require "xin_smooth_rail_loop_1::/rail_loop/geometry.lua"
local paramUtil = require "::/scripts/construction/param_util.tl"

local function value(values, index, fallback)
  return values[index or fallback] or values[fallback]
end

function data()
  return {
    updateFn = function(captureParams, params)
      local radius = value(captureParams.radii, params.loopRadius, 3)
      local spacing = value(captureParams.spacings, params.trackSpacing, 1)
      local elevation = value(captureParams.elevations, params.loopElevation, 4)
      local grade = value(captureParams.grades, params.loopGrade, 2)
      local trackTypes = paramUtil.getRailTrackTypes(params.catenary == 2)
      local trackType = params.streetTemplate or value(trackTypes, params.trackType, 1)
      local segments = geometry.generate(radius, spacing, elevation, grade)
      local result = { models = {}, groundFaces = {}, edgeLists = {}, cost = 0 }
      local group

      for index, segment in ipairs(segments) do
        if not group or group.edgeType ~= segment.kind then
          group = {
            type = "TRACK", edgeType = segment.kind,
            params = { type = trackType },
            edges = {}, snapNodes = {}, freeNodes = {},
            alignTerrain = segment.kind == "NORMAL",
            maxNodeSnapAngle = 10,
          }
          if segment.kind == "BRIDGE" then
            group.edgeTypeName = "::/infrastructure/bridge/concrete.bridge"
          elseif segment.kind == "TUNNEL" then
            group.edgeTypeName = "::/infrastructure/tunnel/tunnel_a.tunnel"
          end
          result.edgeLists[#result.edgeLists + 1] = group
        end
        local nodeIndex = #group.edges
        group.edges[#group.edges + 1] = { segment.p0, segment.t0 }
        group.edges[#group.edges + 1] = { segment.p1, segment.t1 }
        group.freeNodes[#group.freeNodes + 1] = nodeIndex
        group.freeNodes[#group.freeNodes + 1] = nodeIndex + 1
        if index == 1 then group.snapNodes[#group.snapNodes + 1] = nodeIndex end
        if index == #segments then group.snapNodes[#group.snapNodes + 1] = nodeIndex + 1 end
      end
      return result
    end,
  }
end
