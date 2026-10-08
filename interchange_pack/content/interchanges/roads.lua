local M = {}
local root = "::/infrastructure/street/"
local function resource(name) return root .. name .. ".street_template" end

function M.select(params)
  params = params or {}
  local wide = params.lanes == 2
  return {
    main = resource("highway/highway_new_" .. (wide and "large" or "medium")),
    ramp = resource("highway/highway_new_small"),
    cross = resource("country/country_new_small"),
    shared = resource("country/country_new_small"),
    branch = resource("highway/highway_new_medium"), branchWidth = 18,
    connector = resource("highway/highway_new_large"), connectorWidth = 23,
    mainWidth = wide and 23 or 18, rampWidth = 9,
    crossWidth = 14, sharedWidth = 14,
  }
end

return M
