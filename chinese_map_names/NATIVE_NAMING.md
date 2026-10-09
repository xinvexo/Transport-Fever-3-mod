# 原生首次建设命名核验

本文件记录开发依据，不代表实机验证。目标是对预设地图新开局的既有实体应用首次命名规则，不创建、拆除或替换产业。

## 核验版本

- Windows `TransportFever3.exe`：69,755,832 bytes。
- SHA-256：`74861ac43b041aebc5179154345b3cf1ec83154c8e6cc58e0d9e02ff5fa602e4`。
- 以下为 preferred image base `0x140000000` 的 VA；源码路径、RTTI、注册链和有限反汇编均来自本地安装文件，只读核验。

## 首次规则

`construction_builder_util::MakeName` 位于 `0x140A35F80–0x140A3665F`，断言字符串关联 `Game/construction/make_proposal.cpp:627`。

1. 建设变换的平移列为命名位置。调用者 `0x140A30D6F–0x140A30D8A` 读取矩阵 `+0x30/+0x34/+0x38`；另一个调用者 `0x140A30EFF–0x140A30F1A` 相同。
2. `0x140A35FDC` 调 `0x14097B0C0`，按 Town BoundingVolume 中心的 XYZ 平方距离选择最近城市。距离相同保留枚举中先遇到者。
3. 非空 `namePrefix` 优先；否则非空 `description.name` 使用本地化的 `{townName} {constructionName}`。描述名也为空则前缀为空，不用文件名猜类型。
4. ConstructionDesc 的 `description.name` 为 `+0x78`，`namePrefix` 为 `+0x9D8`，`subConstructionNamePrefix` 为 `+0x9F8`。字段转换器 `0x141240990` 与嵌套 description 转换器 `0x140D4B750` 明确确认这些字段名和偏移。
5. 默认模板先替换 `constructionName`，保留字面 `{townName}`；最终命名函数 `0x1425D7D90` 再替换城市名并去重。

### 直接复用的公开入口

- `api.res.constructionRep.getAsTable(id)` 读取最终资源，包括上述两个前缀，避免捕获时漏掉后置模组的修改。注册链：`0x1411D01BC → 0x1411AAE50 → 0x14110BFF0 → 0x1411D5010 → 0x14120E0F0 → 0x1411EF090 → 0x141222340 → 0x141240990`。输出转换器会写入空前缀。
- `api.engine.util.town.getClosestTown(position)` 与 MakeName 调用同一个 `0x14097B0C0`。公开绑定链：`0x14254220C → 0x142456050 → 0x1424C9BD0 → 0x1424FC990 → 0x1424E25F0 → 0x14097B0C0`。
- `scripts/stringutil.lua::interp` 是原生 `scripts/lang_util.tl::format` 的实际实现，用于命名参数替换。
- BoundingVolume 中心表达式参考 `scripts.zip!scripts/entity_util.tl:48–55`，建设位置参考 `game_mechanics.zip!game_mechanics/celebrations/celebrations.script.tl:208–212`。

### 重名规则

`0x1425D7D90` 的顺序为：基础名称 → 方位 → 可选随机附加词 → 编号。

- 占名集合 `0x1425D5E70` 来自 StationGroup 的 NAME，以及 VehicleDepot 所属 Construction 的 NAME；不是统计所有产业名称的数量。
- 基础名未占用即返回，不因距离远而额外添加方位。
- 仅 XY 距离严格大于 400 米才尝试方位（`0x1425D8176`）。角度为 `atan2f(dy, dx)`：东 `(-π/6, π/6)`；北 `(π/3, 2π/3)`；西 `θ>5π/6 或 θ<-5π/6`；南 `(-2π/3, -π/3)`。边界和夹角空隙跳过方位。
- 方位模板为原生 `{stationName} East/North/West/South`。
- 无附加词分支时，按 `{stationName} #{number}` 从 1 到 999 找第一个完整名称未占用的候选；全部占用退回基础名（`0x1425D8BC7–0x1425D8F90`）。
- 随机附加词仅在第一个 subconstruction 含 station，且其所有 terminal 模式属于 BUS/TRUCK/TRAM/ELECTRIC_TRAM/TRAIN/ELECTRIC_TRAIN/TRAM_TRACK/ELECTRIC_TRAM_TRACK 时启用。转换器链确认 optional station 存在标志与 terminals/transportModes；不是 cargo 或 passengers 标记。
- 原生标准产业由 `industries/industryutil.lua:368–374,489–514` 先放 industrySubconstruction，再追加 stationSubconstruction；第一个没有 station，因此不走随机附加词。

## 写入与显示必须区分

MakeName 输出一个完整名称，保存到 proposal `+0xE18`：两个调用点为 `0x140A30DAA/0x140A30F3A`，`0x140A368A4–0x140A368B9` 搬入该字段。

- Construction.NAME：`0x1409FD5FB → 0x1409FD644 → 0x1409F60C0 → 0x14016BB20`；同一实体 ID 在 `0x1409FE959` 写入 Construction 组件。
- 新 StationGroup.NAME：`0x1409FED66–0x1409FED91` 复制同一个完整名；`0x1425D47D4` 写 StationGroup、`0x1425D47ED` 写 NAME。
- `Game/ecs/name_util.cpp` 的 `GetEntityName` 是另一条显示流程。其子类型分支为 Station、VehicleDepot、TownBuilding，没有统一的 Industry 类型追加分支。不能据此把完整产业名改为裸城名。
- 原生 `mission.zip!mission/name_util.tl:100–128` 也同步父建设与站点组；子 station/industry/depot 预期没有 NAME。
- `forceSameEntity=true` 不会创建 NAME。所有实际提交仍须重新检查目标已有 NAME；不对产业、站点或车库子实体直接强写。

## 适配既有预设地图

城市转换与产业转换属于同一次有限任务。名称规划使用已选中国城市名，但产业命令等待对应城市改名完成，并在提交前核对实际城市名未发生变化。

站点组命令还要等待主体建设的实际名称等于计划的完整名；主体改名失败或被外部修改时，站点组保留原名。

既有实体已经占用名字，因此给每个建设重新计算时暂时扣除自身关联站点组/车库的旧占用，生成后把新的占用加入规划集合。编号按原生完整字符串查重，不沿用旧名字的数字，也不解析旧标题来推断类型。

只在新开局触发。旧版本队列退役、不回放，旧名称不追改；任务完成后停止扫描。

## 明确边界

- 没有发现最终 MakeName/NameSystem 取名函数的公开 Lua 绑定，因此参考已核实原生分支实现规则；不是声称直接调用了整个 C++ 命名函数。
- 没有城市时，原生用 NameRep 按坐标种子生成一个城名。该调用层未公开；本模组保留这类已有名称，不改全局随机状态。豪华版三张地图均有城市。
- 特殊陆上站点的九个附加词依坐标哈希随机排序。目前不重现该独立分支；如基础名及方位均冲突且该分支启用，保留该对象名称。标准原生产业不进入此分支。
- 本实现遵循原生数学边界；Lua 计算与原生 float 运算在极端边界附近可能存在精度差异。
- 站点组首次创建同名的路径已核实；后续玩家合并形成的多建设站点组不当作单一产业的所有物重命名。
