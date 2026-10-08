# Transport Fever 3 Mods

《狂热运输 3》模组集合。

| 目录 | 模组 | 功能 | 状态 |
| --- | --- | --- | --- |
| [auto_alternatives](auto_alternatives/README.md) | 自动备用站台 | 为新停靠站和扩建站台补选备用位置 | 开发完成 |
| [auto_signal](auto_signal/README.md) | 自适应铁路信号灯 | 按指定间距从区段前端向后布灯 | 倒排与道口顺延已更新，待游戏内验证 |
| [clear_catchment](clear_catchment/README.md) | 清晰站点范围 | 建站时显示同色调加深边界与半透明范围填充，保持线宽 | 深色与填充已更新，待游戏内验证；近景仍有原生淡化 |
| [bulldozer_lines](bulldozer_lines/README.md) | 拆除时查看线路 | 左侧线路清单、多选筛选与定位，显示路线与房屋分区颜色 | 基础功能已实机反馈，新布局与筛选待游戏内验证 |
| [station_rows](station_rows/README.md) | 车站整列配置 | 按住 Shift 整列增删车站模块 | 开发完成 |
| [tidy_fields](tidy_fields/README.md) | 工厂地块规整 | 按方向整理地块，并开放新建产业的完整成长上限 | 开发完成 |
| [chinese_map_names](chinese_map_names/README.md) | 预设地图中文名称 | 新开预设地图时替换已有名称，后续继续生成中文名称 | 城市汉化已实机确认；已封堵无名称组件站点的强制改名路径，待复测 |
| [line_vehicle_colors](line_vehicle_colors/README.md) | 车辆跟随线路颜色 | 购车、派车或线路改色后同步对应车辆，平时保留手工配色 | 已改为操作完成通知，取消周期车队扫描；脚本测试通过，待游戏内复验 |
| [line_names](line_names/README.md) | 线路智能命名 | 按城市、产业与专线用途命名，并统一原版车库默认名称格式 | 车库命名模板已更新，脚本检查通过，待游戏内复验 |
| [interchange_pack](interchange_pack/README.md) | 常见立交桥合集 | 六类小型高速立交、两／三车道、混凝土桥 | 开发中，12 种组合验收中 |

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
