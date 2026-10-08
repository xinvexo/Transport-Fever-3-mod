local builtin = ug_require "::/gui/main/builtin.lua"
local react = ug_require "::/gui/main/react.lua"
local scriptParamUtil = ug_require "::/gui/main/script_param_util.tl"

local SpacingControl = react.RegisterRecipe("XinAutoSignalSpacingControl", function(param)
   local sliderStyle = api.gui.StyleSheet.new()
   sliderStyle.size = api.type.Vec2f.new(100, 32)
   local valueStyle = api.gui.StyleSheet.new()
   valueStyle.size = api.type.Vec2f.new(106, 32)
   valueStyle.padding = api.type.Vec4f.new(0, 3, 0, 3)
   local textStyle = api.gui.StyleSheet.new()
   textStyle.padding = api.type.Vec4f.new(0, 0, 0, 0)

   local editing = react.useState(false)
   local commit = function(value)
      param.onValueChange(math.max(50, math.min(2000, math.floor(value + 0.5))))
   end

   local valueControl
   if editing:old() then
      valueControl = builtin.DoubleSpinBox{
         meta = { class = "font-scale-body", styleSheet = valueStyle },
         min = 50,
         max = 2000,
         step = 1,
         value = param.currentValue,
         onValueChange = commit,
         startInEditMode = true,
         onStopEditMode = function()
            editing:set(false)
         end,
      }
   else
      valueControl = builtin.Button{
         meta = { styleSheet = valueStyle },
         content = builtin.TextView{
            meta = { class = "font-scale-body", styleSheet = textStyle },
            text = param.scriptParam.formatValueFn(param.currentValue),
         },
         onClick = function()
            editing:set(true)
         end,
      }
   end

   return builtin.BoxLayout{
      meta = { class = "right-parameters", onAttention = param.onHover },
      orientation = builtin.type.Orientation.Horizontal,
      children = {
         builtin.Slider{
            meta = { styleSheet = sliderStyle },
            horizontal = true,
            min = 50,
            max = 2000,
            step = 1,
            pageStep = 50,
            value = param.currentValue,
            onValueChange = commit,
            disableGamepadNavigation = param.disableGamepadNavigation,
         },
         valueControl,
      },
   }
end)

local widget = {}

function widget.build(param)
   local control = SpacingControl(param)
   if param.vertical == nil then return control end
   return scriptParamUtil.wrap(
      param.scriptParam.name, param.vertical, control, param.addSpacer, param.onHover
   )
end

return widget
