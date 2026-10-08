local depots = {
  ["depots/road/road_depot/road_depot.con"] = true,
  ["depots/road/tram_depot/tram_depot.con"] = true,
  ["depots/rail/rail_depot.con"] = true,
  ["depots/water/water_depot.con"] = true,
}

function data()
  return {
    runFn = function()
      addModifier("loadConstruction", function(fileName, construction)
        local path = fileName:gsub("^::/", ""):gsub("%.lua$", "")
        if not depots[path] or type(construction.namePrefix) ~= "string" then
          return construction
        end
        -- Change the translated default template; explicit entity names and
        -- the inherited subconstruction name remain controlled by the game.
        local label = construction.namePrefix:match("^%{townName%}%s*(.-)%s*$")
        if label and label ~= "" and label:sub(1, 1) ~= "-" then
          construction.namePrefix = "{townName} - " .. label
          log.message("[line_names] Depot name template updated: " .. fileName)
        end
        return construction
      end)
    end,
  }
end
