# 建站范围圈入口调查

直接修改建站原生预览圈的路线未实现。不要把 Lua 参数测试通过视为原生预览圈已生效，也不要把图层可见性当成 Builder 样式的开关。

用户随后同意改用可控覆盖图层。revision 3 开始在站点建造期间显示已有客货站点的边界；这是有意新增显示层，可能显示更多已有站点。它不宣称接管正在放置的新站预览。

2026-10-09，用户在报告“感觉没生效”后复核并明确确认“已经生效了，是我看错了”，随后提供了建造公交停靠点时已有站点圆圈清楚可见的截图。当前 revision 3 的覆盖图层方案据此记为实机确认有效。该次排查只有读取与分析，没有改动运行代码或部署新版本；无需进行此前考虑的最终绘制组件包装改造。

## 约束

保留游戏默认色调、线宽与覆盖半径。revision 3 保留原 RGB 且关闭填充；用户随后明确允许颜色加深和圈内填充，revision 4 因此统一缩放原 RGB 并增加半透明填色，仍不新增建筑染色或光柱。

## 实机日志

普通建筑与沿路停靠点两种入口均实际执行了当前 hook。原值为 active alpha 0.75、passive alpha 0.25、width 4；修改后以及合并图层后的读回值均为 1、1、4，isVisible 为 false，但用户看到的建站圈没有变化。

因此不是模组未启用、hook 没执行或数值写回失败。

## 独立原生实例

对 Windows Steam build 25754343 做了离线静态核验。可执行文件 SHA-256：

74861ac43b041aebc5179154345b3cf1ec83154c8e6cc58e0d9e02ff5fa602e4

以下为 RVA，仅用于描述这一版本，不能当成跨版本补丁地址：

- BuilderRenderer 构造路径在 0x7b6366 调用 CatchmentAreaRenderable 构造器 0x7d3fc0，把独立实例存入 BuilderRenderer + 0x1b8 所指对象的 +0x18a8。
- 地图图层另行创建一个实例：0x64c0d0 → 0x645bf0 → 0x7d3fc0。它经 0x65c110、0x87f660 传入 CatchmentAreaHelper。
- 图层设置应用函数 0x87a240 将 config 的显示设置传给这个 helper。0x87a313 的 isVisible 分支只控制范围数据；两条路径都到达 0x87a3de，并在 0x87a3ee–0x87a42a 复制显示设置至图层实例。
- 所以 **isVisible=false 不会阻止样式复制**。把它改成 true 并不能令 Builder 的另一实例采用这些设置，还可能额外显示圈。
- 已定位的公开 CatchmentAreaDisplaySettings / displaySettings 绑定指向 LayerConfig.CatchmentAreaRenderableConfig，没有找到通向 Builder 实例的公开 setter。

这证明当前图层 hook 修改了不同的对象；不构成“游戏内部永远不存在其他写入路径”的全局证明。

## 不采用的共享 shader 方案

CatchmentAreaRenderable 的纹理线通道确实使用 catchment_area.tga → lines_tex_color.prog。该纹理为 128×64 单通道，能通过图案与 line_terrain.tga 区分。

但区域颜色来自 GetCatchmentColor（0x7d5420），经 0x7d6154、0x7d620d、0x7d689c 进入另一 AreasRenderable / TriangleBuffer 通道。其通用颜色 shader 没有保留 catchment 身份标记。因此仅改纹理线 shader 不能证明会改到圆边界；泛改共享颜色 shader 又不能保证不影响其他图形。

本轮没有修改游戏二进制、注入运行进程或改写原生 shader。

## 后续有效方向

直接修改新站预览仍需要能控制 Builder 独立实例的入口。额外覆盖层只解决已有站点显示，不能当成该入口已经找到；通用 shader 按相似颜色猜测目标像素也不可替代。

## 已有模组参考与当前实现

Hub Coverage Filters 的公开包表明：启用 CatchmentAreaRenderableConfig，并在活动工具最终 LayerConfig 中保留它，可让已有站点范围在建造期间持续显示。作者页：https://mod.io/g/transportfever3/m/hub-coverage-filters

当前代码使用游戏公开接口独立实现，仅针对站点放置和站点模块操作启用。保留原来的图层其他字段；最终数据图层替换发生后只复制自己的 catchment 配置。无额外 ActionDescriptor/渲染节点包装。

## 近景淡化与性能约束

2026-10-09，用户进一步对比未启用模组的画面，确认增强有效，但镜头拉近后可见度下降。

静态核验发现 AreasRenderable 在 RVA 0x4a2849–0x4a28c1 计算相机 Z 高出区域包围盒顶部的距离，除以 area 的淡化高度并夹到 0–1；随后在 0x4a2ac4、0x4a2c61 乘入颜色 alpha。catchment area 构建处 0x7d6862–0x7d6873 使用固定高度 1000、线性曲线 0。这层衰减发生在 displaySettings 的基础 alpha 之后，不属于现有公开字段。

没有采用把 borderAlpha 提到 4/8 的盲目补偿：TriangleBuffer 在 0x843490 以 position 12 字节加 RGBA 16 字节原样追加顶点，上传前没有确认到 alpha 夹取，不能假设超过 1 的输入一定安全。没有修改运行代码或重新部署。

用户明确要求只在关键点触发，避免定时任务影响性能。当前方案不新增定时器、onStep/onStepTimer 或逐帧补偿循环；后续改进也应优先利用现有工具和配置更新入口，不能靠常驻轮询解决近景显示。

## 同色调加深和填充

用户请求进一步加深颜色或圈内填色，以减轻近景淡化后的不可辨认问题。revision 4 将 person/cargo/inactive/unreachable 四种基础颜色的 RGB 各通道统一乘 0.65，保留原色相；innerAlpha 从 0 调到 0.30。borderAlpha 与 borderAlphaPassive 仍为 1，线宽、半径、房屋 painter 和触发入口不变。

这只是提高可辨认度，不是消除原生距离衰减；新增填充也会受该衰减影响。没有加入相机轮询或定时补偿。
