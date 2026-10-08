local supported = {
  farm = true, livestock_farm = true, cotton_farm = true, rubber_farm = true, forest = true,
}

function data()
  return {
    runFn = function()
      addModifier("loadScript", function(fileName, scriptData)
        local isIndustry = fileName:find("/industries/", 1, true)
          or fileName:find("/tidy_fields/generated/", 1, true)
        if not isIndustry or type(scriptData.updateFn) ~= "function" then return scriptData end

        local originalUpdate = scriptData.updateFn
        scriptData.updateFn = function(captureParams, params)
          local results = table.pack(originalUpdate(captureParams, params))
          local fieldConfig = captureParams and captureParams.fieldConfig
          if fieldConfig and fieldConfig.fields and results[1] then
            for _, subconstruction in ipairs(results[1].subconstructions or {}) do
              if subconstruction.industry then
                subconstruction.industry.maxLevel = #fieldConfig.fields
              end
            end
          end
          return table.unpack(results, 1, results.n)
        end
        return scriptData
      end)

      addModifier("loadConstruction", function(fileName, construction)
        local industry, name = fileName:match("industries/([^/]+)/([^/.]+)%.con")
        if industry ~= name or not supported[industry] then
          return construction
        end
        construction.updateScript.fileName =
          "xin_tidy_fields_1::/tidy_fields/generated/" .. industry .. ".script@updateFn"
        log.message("[Tidy Fields] Layout hook loaded (revision 15): " .. industry)
        return construction
      end)
    end,
  }
end
