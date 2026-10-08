-- The local diagnostic installer supplies directory without embedding personal
-- paths in the mod source. Normal packages fall back to resource loading.
return { enabled = false, observe = false, validateTwelve = false, directory = nil, loader = loadfile }
