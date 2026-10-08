function data()
  return {
    name = _("Chinese (preset maps)"),
    personNamesScript = {
      fileName = "xin_chinese_map_names_1::/chinese_map_names/person.script@generate",
      params = {},
    },
    townNamesScript = {
      fileName = "::/names/names.script@townsNameScriptFn",
      params = { path = "china", languages = { fallback = "zh_CN", zh_CN = "zh_CN" } },
    },
    streetNamesScript = {
      fileName = "::/names/names.script@streetsNameScriptFn",
      params = { path = "china", languages = { fallback = "zh_CN", zh_CN = "zh_CN" } },
    },
  }
end
