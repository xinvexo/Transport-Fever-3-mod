# Transport Fever 3 Mods

Transport Fever 3 模组源码项目。后续开发统一在本仓库进行；游戏安装目录是部署目标，不作为另一份开发源。

| 目录 | 模组 | Mod ID |
| --- | --- | --- |
| [auto_alternatives](auto_alternatives/README.md) | 自动备用站台 | `xin_auto_alternatives_1` |
| [auto_signal](auto_signal/README.md) | 自适应铁路信号灯 | `xin_auto_signal_1` |
| [station_rows](station_rows/README.md) | 车站整列配置 | `xin_station_rows_1` |
| [tidy_fields](tidy_fields/README.md) | 工厂地块规整 | `xin_tidy_fields_1` |
| [smooth_rail_loop](smooth_rail_loop/README.md) | 两点铁路回环 | `xin_smooth_rail_loop_1` |

每个模组包含 `mod.json`、`content/`、必要的 `_metadata/` 资源，以及测试和工具。仓库只提交源码、测试、文档和运行资源。`dist/`、压缩包、Python 缓存、虚拟环境和系统杂项不入库，也不上传到 GitHub。

开发依赖只在根目录 `requirements-dev.txt` 维护；测试和打包的共用实现位于根目录 `tools/`。各模组的 `tools/package_mod.py` 仅转到共用入口。`tidy_fields/content/tidy_fields/generated/` 是运行必需的农场布局，回环模组的旧预制建筑资源用于兼容已有存档，均保留在源码中。

## 开发测试

游戏 build 40408 内嵌 Lua 5.2.2。主要回归测试显式使用 `lupa.lua52`，不能以 Lupa 默认选择的新版 Lua 代替。回环另有跨版本角度计算回归测试。

需要 Python 3.10 或更高版本。在仓库根目录建立并激活一个开发环境，所有模组共用。Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS/Linux：

```sh
python3 -m venv .venv
source .venv/bin/activate
```

激活后，两种系统均在仓库根目录执行：

```sh
python -m pip install -r requirements-dev.txt
python tools/test_mods.py
```

测试入口使用 UTF-8，不生成仓库内的字节码、图片或报告文件。共用工具的测试在系统临时目录验证打包和安装，结束后自动清理；不会部署到实际游戏目录。

只运行指定模组：

```sh
python tools/test_mods.py tidy_fields smooth_rail_loop
```

每次也会运行共用工具测试。部分工厂测试会读取本机游戏资源；将下列示例值替换为自己的游戏安装目录。未设置 `TF3_GAME_DIR` 或找不到资源时，这部分测试明确跳过，其余测试正常运行。Windows PowerShell：

```powershell
$env:TF3_GAME_DIR = '游戏安装目录'
python tools/test_mods.py tidy_fields
```

macOS/Linux：

```sh
export TF3_GAME_DIR='/path/to/Transport Fever 3'
python tools/test_mods.py tidy_fields
```

## 本地打包和部署

按需在仓库根目录运行共用打包工具，用模组目录名选择目标：

```sh
python tools/package_mod.py smooth_rail_loop
python tools/package_mod.py smooth_rail_loop --install '/path/to/game/mods'
```

产物位于该模组的 `dist/<Mod ID>.zip`，仅供本地使用，不提交、不上传。`--install` 指向本地模组父目录，会在打包后安装到其中的 `<Mod ID>/`。请按本机游戏配置替换示例路径，Windows 路径也可作为带引号的参数传入。原先进入模组目录运行 `python tools/package_mod.py` 的方式仍可使用。

工具只收集明确列出的游戏资源，并统一过滤 macOS/Windows 系统杂项与 Python 缓存。安装前核对 Mod ID，拒绝与源码重叠或带链接的覆盖目标；只更新该模组的资源，保留兄弟模组及目标目录内其他顶层文件。打包不需要安装开发依赖。

游戏由用户进行实机测试；代码和本机日志用于定位问题。模拟接口测试不等于游戏内预览、施工或存档验证通过。各模组的使用方法和验证状态见对应 README。

## 已合入修复

- 工厂界面的方向按钮使用原生 `NinePatch` 对象，修复打开产业窗口时的类型错误，版本号更新为 16。
- 自动信号灯使用独立格式化函数标记，避免 Lua 5.2 下误接管其他控件，版本号更新为 15。
- 两点回环 r3.2 接入原生轨道菜单，复用高度、弯曲和桥隧选项；修复动作节点、模式切换及 Lua 5.2 角度函数兼容问题。原菜单与选点已得到实机日志确认，修正后的引擎预览、施工仍待用户验证。
