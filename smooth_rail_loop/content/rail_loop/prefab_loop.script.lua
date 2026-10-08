local geometry = require "xin_smooth_rail_loop_1::/rail_loop/prefab_geometry.lua"
local paramUtil = require "::/scripts/construction/param_util.tl"
local bridgeChoices = require "xin_smooth_rail_loop_1::/rail_loop/bridge_choices.lua"

function data()
  return {
    updateFn = function(captureParams, params)
      params = params or {}
      local trackTypes = paramUtil.getRailTrackTypes(params.catenary == 2)
      local index = math.max(1, math.min(#trackTypes, math.floor(tonumber(params.trackType) or 1)))
      local trackType = params.streetTemplate or trackTypes[index]
      local segments, info = geometry.generate(captureParams.kind)
      local result = { models = {}, groundFaces = {}, edgeLists = {}, cost = 0 }
      local group, previousKind

      for _, segment in ipairs(segments) do
        if segment.kind ~= previousKind then
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
        end
        local nodeIndex = #group.edges
        group.edges[nodeIndex + 1] = { segment.p0, segment.t0 }
        group.edges[nodeIndex + 2] = { segment.p1, segment.t1 }
        group.freeNodes[#group.freeNodes + 1] = nodeIndex
        group.freeNodes[#group.freeNodes + 1] = nodeIndex + 1
      end
      -- The loop ends are internal junctions. Only the four ends of the
      -- short main-line stubs snap to external rails. Leave the route through
      -- the loop open so players can continue it along their own alignment.
      local mainlines = {
        type = "TRACK", params = { type = trackType }, alignTerrain = true,
        edges = {}, snapNodes = {}, freeNodes = {},
      }
      for _, x in ipairs({ -info.spacing / 2, info.spacing / 2 }) do
        local index = #mainlines.edges
        local entryLength, exitLength = -info.mainlineStart, info.mainlineEnd
        mainlines.edges[index + 1] = { { x, info.mainlineStart, 0 }, { 0, entryLength, 0 } }
        mainlines.edges[index + 2] = { { x, 0, 0 }, { 0, entryLength, 0 } }
        mainlines.edges[index + 3] = { { x, 0, 0 }, { 0, exitLength, 0 } }
        mainlines.edges[index + 4] = { { x, info.mainlineEnd, 0 }, { 0, exitLength, 0 } }
        mainlines.snapNodes[#mainlines.snapNodes + 1] = index
        mainlines.snapNodes[#mainlines.snapNodes + 1] = index + 3
        for offset = 0, 3 do mainlines.freeNodes[#mainlines.freeNodes + 1] = index + offset end
      end
      result.edgeLists[#result.edgeLists + 1] = mainlines
      return result
    end,
  }
end
