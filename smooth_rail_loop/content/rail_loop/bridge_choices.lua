local M = {}

-- Stable values are stored with the construction, independent of the era's
-- visible order. These are the native bridges that support railway tracks.
local bridges = {
  { id = 2, name = "trestle", label = "INFRA_BRIDGE_TRESTLE_NAME", yearFrom = 0, yearTo = 1970 },
  { id = 1, name = "stone", label = "INFRA_BRIDGE_STONE_NAME", yearFrom = 0, yearTo = 0 },
  { id = 3, name = "steel", label = "INFRA_BRIDGE_STEEL_NAME", yearFrom = 1940, yearTo = 0 },
  { id = 5, name = "concrete", label = "INFRA_BRIDGE_CONCRETE_NAME", yearFrom = 1970, yearTo = 0 },
  { id = 4, name = "suspension", label = "INFRA_BRIDGE_SUSPENSION_NAME", yearFrom = 1940, yearTo = 0 },
  { id = 6, name = "cable", label = "INFRA_BRIDGE_CABLE_NAME", yearFrom = 2000, yearTo = 0 },
  { id = 7, name = "tarch", label = "INFRA_BRIDGE_TIEDARCH_NAME", yearFrom = 2010, yearTo = 0 },
}
local prefix = "::/infrastructure/bridge/"

function M.addParams(params)
  local eras = { 0, 1940, 1970, 2000, 2010 }
  for i, year in ipairs(eras) do
    local param = {
      -- Native numeric params do not clamp a retired stored value. Reset the
      -- menu selection when trestle retires, without changing saved bridges.
      key = year < 1970 and "bridgeType" or "bridgeTypeModern", name = _("Bridge"),
      values = {}, numbers = {}, tooltips = {},
      uiType = "IconButton", location = "Toolbar", displayMode = "Compact",
      yearFrom = year, yearTo = eras[i + 1] or 0,
    }
    for __, bridge in ipairs(bridges) do
      if bridge.yearFrom <= year and (bridge.yearTo == 0 or year < bridge.yearTo) then
        local index = #param.values + 1
        param.values[index] = prefix .. bridge.name .. ".tga"
        param.numbers[index] = bridge.id
        param.tooltips[index] = _(bridge.label)
        if bridge.id == 1 then param.defaultIndex = index end
      end
    end
    params[#params + 1] = param
  end
end

function M.resource(value)
  for __, bridge in ipairs(bridges) do
    if value == bridge.id then return prefix .. bridge.name .. ".bridge" end
  end
  return prefix .. "stone.bridge"
end

return M
