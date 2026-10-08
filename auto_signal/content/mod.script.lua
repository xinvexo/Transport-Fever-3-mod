function data()
   return {
      runFn = function()
         addModifier("loadConstruction", function(fileName, constructionData)
            if not string.find(fileName, "infrastructure/signal/signal_path", 1, true) then
               return constructionData
            end

            constructionData.params = constructionData.params or {}
            constructionData.params[#constructionData.params + 1] = {
               key = "asEnabled",
               name = _("Auto placement"),
               tooltip = _("Rearrange same-direction signals."),
               values = { _("Off"), _("On") },
               uiType = "Button",
               displayMode = "Horizontal",
               defaultIndex = 2,
               yearFrom = 0,
               yearTo = 0,
            }

            local values, numbers = {}, {}
            for meters = 50, 800 do
               values[#values + 1] = tostring(meters)
               numbers[#numbers + 1] = meters
            end
            constructionData.params[#constructionData.params + 1] = {
               key = "asMinimumSpacing",
               name = _("Signal spacing"),
               tooltip = _("Place signals at this exact interval."),
               values = values,
               numbers = numbers,
               uiType = "Slider",
               displayMode = "Horizontal",
               defaultIndex = 251,
               checkEnabledScript = {
                  fileName = "xin_auto_signal_1::/auto_signal/ui.script@spacingVisibility",
               },
               formatValueScript = {
                  fileName = "xin_auto_signal_1::/auto_signal/ui.script@formatMinimumSpacing",
               },
               stepValueScript = {
                  fileName = "xin_auto_signal_1::/auto_signal/ui.script@stepMinimumSpacing",
               },
               yearFrom = 0,
               yearTo = 0,
            }
            return constructionData
         end)
      end,
   }
end
