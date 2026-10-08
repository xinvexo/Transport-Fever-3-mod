function data()
  return {
    type = "rename_scheme_component",
    data = {
      schemeComponentNameRaw = "xin_line_names_purpose",
      schemeComponentNameTranslated = _("Towns and industries - line purpose"),
      renameFnDefinition = { fileName = resolve("naming.script@renameFn"), params = {} },
    },
  }
end
