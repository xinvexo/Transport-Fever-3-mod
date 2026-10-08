local M = {}

local function lane(width, modes, speed, sidewalk)
  return { forward = true, width = width, transportModes = modes, speed = speed,
    height = sidewalk and 0.15 or 0, offset = 0 }
end

function M.make(kind)
  local urban = kind ~= "shared_highway"
  local speed = urban and 8.33 or 27.78
  local car = { "CAR", "BUS", "TRUCK" }
  local lanes, name, icon
  if kind == "town_three" then
    speed = 13.89
    lanes = {
      lane(3,{"PERSON","CARGO"},speed,true),
      lane(5,car,speed), lane(5,car,speed), lane(5,car,speed),
      lane(3,{"PERSON","CARGO"},speed,true),
    }
    lanes[1].forward = false
    name, icon = "Three-lane one-way street", "town/town_new_one_way_medium"
  else
    -- One half of the two-lane shared corridor. There is no node connecting
    -- the opposing halves, so vehicles cannot switch direction at either fork.
    lanes = { lane(5,car,speed), lane(urban and 3 or 2,
      urban and {"PERSON","CARGO"} or {},speed,urban) }
    name = "Shared interchange arc lane"
    icon = urban and "constructions/entrance_new_one_way" or "highway/highway_new_small"
  end
  return {
    availability = { yearFrom = 1940, yearTo = 0 },
    description = { name = _(name), description = _(name),
      icon = "::/infrastructure/street/" .. icon .. ".tga",
      previewIcon = "::/infrastructure/street/" .. icon .. "_preview.tga" },
    laneConfigs = lanes, roadType = "STREET", initiallyLocked = true,
    country = not urban, defaultWithCrosswalk = false, simBuildable = false,
    modifiers = { maxSpeedModifier = 0, noiseModifier = 0, pollutionModifier = 0 },
    emissions = { noise = 0, pollution = 0, pollutionRadius = 0, radius = 0 },
    priority = kind == "town_three" and 420 or 20,
    cost = kind == "town_three" and 180 or 32, maintenanceCost = 6,
    streetStyle = "::/infrastructure/street/" .. (urban and "town/town_new.street" or "highway/highway.street"),
    fillGroundTex = "::/infrastructure/street/shared/street_fill.gtex",
    borderGroundTex = "::/infrastructure/street/shared/street_border.gtex",
    sidewalkFillGroundTex = "::/infrastructure/street/shared/" ..
      (urban and "street_sidewalk_fill.gtex" or "highway_safety_lane.gtex"),
    builderAudioRes = "::/gui/construction/sound/buildoze_street.builder_audio",
  }
end

return M
