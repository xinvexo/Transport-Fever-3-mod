# Transport Fever 3 Mods

《狂热运输 3》模组集合。

| 目录 | 模组 | 功能 | 状态 |
| --- | --- | --- | --- |
| [auto_alternatives](auto_alternatives/README.md) | 自动备用站台 | 为新停靠站和扩建站台补选备用位置 | 开发完成 |
| [auto_signal](auto_signal/README.md) | 自适应铁路信号灯 | 按设定间距自动布置信号灯 | 开发完成 |
| [station_rows](station_rows/README.md) | 车站整列配置 | 按住 Shift 整列增删车站模块 | 开发完成 |
| [tidy_fields](tidy_fields/README.md) | 工厂地块规整 | 按方向整理地块，并开放新建产业的完整成长上限 | 开发完成 |

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
