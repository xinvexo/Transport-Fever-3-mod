function data()
   return {
      spacingVisibility = function(scriptParams, params)
         -- Hide the control while retaining its value in the native parameter map.
         return params.asEnabled == 2 and "Enabled" or "InputActionOnly"
      end,
      formatMinimumSpacing = function(scriptParams, meters)
         return string.format(_("%d m"), meters)
      end,
      stepMinimumSpacing = function(scriptParams, meters, direction)
         return math.max(50, math.min(2000, meters + direction * 50))
      end,
   }
end
