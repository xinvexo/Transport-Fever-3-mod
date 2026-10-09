# Transport Fever 3 Mods

《狂热运输 3》模组集合。

| 目录 | 模组 | 功能 | 状态 |
| --- | --- | --- | --- |
| [auto_alternatives](auto_alternatives/README.md) | 自动备用站台 | 为新停靠站和扩建站台补选备用位置 | 已补强失败回退并减少重复查询，待游戏内复验 |
| [auto_signal](auto_signal/README.md) | 自适应铁路信号灯 | 按指定间距从区段前端向后布灯 | 同向旧灯替换重建已补强失效实体检查与计算限额，待游戏内验证 |
| [clear_catchment](clear_catchment/README.md) | 清晰站点范围 | 建站时显示同色调加深边界与半透明范围填充，保持线宽 | 80% 填充已补强异常回退，待游戏内验证；近景仍有原生淡化 |
| [bulldozer_lines](bulldozer_lines/README.md) | 拆除时查看线路 | 左侧线路清单、多选筛选与定位，显示路线与房屋分区颜色 | 已补强显示异常回退和快照复用，原生排序及表格待游戏内复验 |
| [station_rows](station_rows/README.md) | 车站整列配置 | 按住 Shift 整列增删车站模块 | 已修正建造回调与异常收束，改用 Shift 输入事件，待游戏内复验 |
| [tidy_fields](tidy_fields/README.md) | 工厂地块规整 | 按方向整理地块，并开放新建产业的完整成长上限 | 已补强命令失败与窗口关闭处理，待游戏内复验 |
| [chinese_map_names](chinese_map_names/README.md) | 预设地图中文名称 | 中文地名与人物名，产业参照原生首次取名规则 | 已核实原生 MakeName 并实现标准产业命名，脚本测试通过，待实机复测 |
| [line_vehicle_colors](line_vehicle_colors/README.md) | 车辆跟随线路颜色 | 购车、派车或线路改色后同步对应车辆，平时保留手工配色 | 已改为操作完成通知，取消周期车队扫描；脚本测试通过，待游戏内复验 |
| [line_names](line_names/README.md) | 线路智能命名 | 按城市、产业与专线用途命名，并统一原版车库默认名称格式 | 已减少批量预览的重复计算，车库模板与命名待游戏内复验 |
| [interchange_pack](interchange_pack/README.md) | 常见立交桥合集 | 六类小型高速立交、两／三车道、混凝土桥 | 已按原生方式合并预览分组，拖动表现待实机确认 |

2026-10-09 稳定性检查：10 个模组的 371 项测试通过，使用 Lua 5.2 并通过 `TF3_GAME_DIR` 检查本机原生资源；共用工具 16 项通过，1 项 Windows 专用测试在 macOS 跳过。这些检查不代表游戏内验证。

## 安装

需要 Python 3.10 或更高版本。在仓库根目录执行，路径换成游戏的本地模组父目录。

安装全部模组：

```sh
python tools/package_mod.py --install "/path/to/game/mods"
```

只安装指定模组，用 `--mods` 选择一个或多个：

```sh
python tools/package_mod.py --mods auto_signal tidy_fields --install "/path/to/game/mods"
```

macOS 可将 `python` 换成 `python3`。只打包时去掉 `--install` 和路径，压缩包生成在对应模组的 `dist/` 下，可手动解压到本地模组目录。

安装后，在存档的模组列表中启用对应模组。具体操作见各模组说明。
