local M = {}

local surnames = {
  "王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴", "徐", "孙", "胡", "朱", "高", "林",
  "何", "郭", "马", "罗", "梁", "宋", "郑", "谢", "韩", "唐", "冯", "于", "董", "萧", "程", "曹",
  "袁", "邓", "许", "傅", "沈", "曾", "彭", "吕", "苏", "卢", "蒋", "蔡", "贾", "丁", "魏", "薛",
  "叶", "阎", "余", "潘", "杜", "戴", "夏", "钟", "汪", "田", "任", "姜", "范", "方", "石", "姚",
}
local givenNames = {
  "晨", "宁", "安", "悦", "嘉", "佳", "明", "瑞", "文", "云", "星", "雨", "晓", "清", "思", "子",
  "景", "舒", "乐", "心", "言", "知", "若", "锦", "涵", "桐", "远", "希", "和", "亦", "新", "竹",
}

function M.generate(random)
  random = random or math.random
  local surname = surnames[random(#surnames)]
  local first = givenNames[random(#givenNames)]
  local second = givenNames[random(#givenNames)]
  return surname .. first .. (first == second and "" or second)
end

return M
