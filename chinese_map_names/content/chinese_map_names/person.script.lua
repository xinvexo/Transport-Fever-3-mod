local person = ug_require "xin_chinese_map_names_1::/chinese_map_names/person.lua"

function data()
  return { generate = function() return person.generate() end }
end
