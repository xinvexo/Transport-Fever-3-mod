local M = {}

function M.normalize(params)
  local fixed = {}
  for key,value in pairs(params or {}) do fixed[key]=value end
  fixed.lanes = fixed.lanes==2 and 2 or 1
  fixed.size,fixed.roadType,fixed.bridge = 1,1,1
  fixed.cloverLayout,fixed.crossApproach,fixed.crossLanes,fixed.loopSide = 1,1,1,1
  return fixed
end

return M
