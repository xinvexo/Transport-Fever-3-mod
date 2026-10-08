function data()
  return {
    preRunFn = function(_, _, allModParams, baseConfig)
      local base = allModParams[""] or {}
      if not base.isMapEditor then
        baseConfig.nameId = "xin_chinese_map_names_1::/chinese_map_names/chinese.names"
      end
    end,
  }
end
