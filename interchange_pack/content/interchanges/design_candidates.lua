-- Private read-only engine comparisons. These are not construction UI options.
local M = {}
local shared = {
  {name="fork-10",fork=10},
  {name="fork-20",fork=20},
  {name="fork-30",fork=30},
  {name="ground-deck-20",fork=20,sharedGround=true},
  {name="ground-loop-20",fork=20,sharedGround=true,approachGround=true},
  {name="ground-loop-30",fork=30,sharedGround=true,approachGround=true},
  {name="wide-fork-20",fork=20,portOffset=4.5,sharedGround=true},
}
local hubs = {
  {name="long-flat",approach=20,wideMedian=true,arch=false},
  {name="stagger-20",stagger=20},
  {name="stagger-30",stagger=30},
  {name="wide-stagger-20",stagger=20,wideMedian=true},
  {name="gentle-stagger-20",stagger=20,approach=18},
  {name="gentle-wide-stagger-20",stagger=20,approach=18,wideMedian=true},
  {name="flat-stagger-20",stagger=20,approach=20,wideMedian=true,arch=false},
  {name="clearance-9",stagger=20,approach=18,wideMedian=true,height=9},
}
local tees = {
  {name="approach-11",approach=11},
  {name="approach-10.5",approach=10.5},
  {name="approach-10",approach=10},
  {name="arch-10.5",approach=10.5,teeArch=true},
}

function M.options(kind)
  if kind=="cloverleaf" then return shared end
  if kind=="turbine" or kind=="stack" then return hubs end
  if kind=="directional" or kind=="trumpet" then return tees end
  return {}
end

function M.get(kind,index)
  return M.options(kind)[index or 0] or {}
end

return M
