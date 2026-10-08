# Transport Fever 3 Mods

Transport Fever 3 模组源码项目。后续开发统一在本仓库进行；游戏安装目录是部署目标，不作为另一份开发源。

| 目录 | 模组 | Mod ID |
| --- | --- | --- |
| `auto_alternatives` | 自动备用站台 | `xin_auto_alternatives_1` |
| `auto_signal` | 自适应铁路信号灯 | `xin_auto_signal_1` |
| `station_rows` | 车站整列配置 | `xin_station_rows_1` |
| `tidy_fields` | 工厂地块规整 | `xin_tidy_fields_1` |
| `smooth_rail_loop` | 两点铁路回环 | `xin_smooth_rail_loop_1` |

每个模组包含 `mod.json`、`content/`、必要的 `_metadata/` 资源，以及测试和工具。仓库只提交源码、测试、文档和运行资源。`dist/`、压缩包、Python 缓存、虚拟环境和系统杂项不入库，也不上传到 GitHub。

## 开发测试

游戏 build 40408 内嵌 Lua 5.2.2。主要回归测试显式使用 `lupa.lua52`，不能以 Lupa 默认选择的新版 Lua 代替。回环另有跨版本角度计算回归测试。

在仓库根目录建立 Python 开发环境：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe tools/test_mods.py
```

macOS/Linux 使用 `.venv/bin/python` 执行同样的命令。测试入口使用 UTF-8，默认不生成字节码、图片或测试报告文件。

只运行指定模组：

```powershell
.venv\Scripts\python.exe tools/test_mods.py tidy_fields smooth_rail_loop
```

部分工厂测试会读取本机游戏资源。可指定安装目录；未提供游戏资源时，这部分测试明确跳过，其余测试正常运行：

```powershell
$env:TF3_GAME_DIR = 'D:\Steam\steamapps\common\Transport Fever 3'
.venv\Scripts\python.exe tools/test_mods.py tidy_fields
```

## 本地打包和部署

按需进入某个模组目录运行 `python tools/package_mod.py`。产物位于该模组的 `dist/`，仅供本地使用，不提交、不上传。带 `--install` 时，工具会核对 Mod ID，再更新指定父目录下对应模组的资源。

```powershell
cd smooth_rail_loop
..\.venv\Scripts\python.exe tools/package_mod.py --install 'D:\Steam\userdata\<Steam用户ID>\3493540\local\staging_area'
```

游戏由用户进行实机测试；代码和本机日志用于定位问题。模拟接口测试不等于游戏内预览、施工或存档验证通过。各模组的使用方法和验证状态见对应 README。

## 已合入修复

- 工厂界面的方向按钮使用原生 `NinePatch` 对象，修复打开产业窗口时的类型错误，版本号更新为 16。
- 自动信号灯使用独立格式化函数标记，避免 Lua 5.2 下误接管其他控件，版本号更新为 15。
- 两点回环 r3.2 接入原生轨道菜单，复用高度、弯曲和桥隧选项；修复动作节点、模式切换及 Lua 5.2 角度函数兼容问题。原菜单与选点已得到实机日志确认，修正后的引擎预览、施工仍待用户验证。
