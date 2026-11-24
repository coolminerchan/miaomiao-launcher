# 开放空间私服启动器

Windows 单机 / 局域网服务端管理启动器，支持本地 UID 登录、独立存档、抓包数据导入与备份、房间和玩家管理。界面采用原创天空蓝/海洋青动漫海边插画、宽松按钮与可滚动卡片布局，不嵌入游戏截图或玩家数据。

## 致谢与声明

感谢各位大佬对服务端部分功能的实现，以及对账号数据采集、备份和解析工具的开发与分享。本项目的相关工作参考了 [BanterSR/Lolo](https://github.com/BanterSR/Lolo) 与 [byzp/of-ps](https://github.com/byzp/of-ps)。具体来源、版本与第三方许可证见 [组件声明](backup-tool/THIRD-PARTY.txt)。

**最终解释权归四川星期零信息科技有限公司。**

本项目为非官方社区工具，与上述公司不存在已确认的授权、合作或背书关系。以上声明不代表公司已授权本项目发布，不替代原游戏的用户协议、知识产权要求或各第三方组件的许可证；本工具自身的维护与缺陷处理由项目维护者负责。

## 构建

Windows 上需要 .NET Framework 4.x，以及 Visual Studio 2022 的 C++ x64 构建工具：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_launcher.ps1
cmd /c build_sdk.cmd
```

`build_sdk.cmd` 默认使用 VS 2022 Community 的工具环境；其他安装版本请调整该脚本。
启动器核心脚本使用 Python 3.12 标准库，不需要在线代理或 `mitmproxy` 才能启动本地 UID 服务。`requirements.txt` 的 `mitmproxy` 用于旧重定向脚本和相关回归测试；安装测试依赖可执行 `python -m pip install -r requirements.txt`。发布包不捆绑启动器的 Python。备份工具使用独立 Python/Protobuf/Cramjam 环境，见其说明。

## 下载后是否完整可运行

- **源码包**：开发用，需要按构建说明编译，并自行提供依赖和合法服务资源。
- **启动器组件包**：含编译好的 EXE、SDK、脚本、图标与完整说明；不包含 Python、Lolo 服务程序、服务资源或游戏客户端，**不是解压即玩的完整私服发行包**。
- **Windows 备份工具包**：独立附件包含 Python/TShark/解码依赖，用于本人数据备份；不会替启动器提供服务端和游戏资源。

首次启动前安装 Python 3.12 x64（标准安装位置或加入 PATH），提供服务资源，再运行只读检查：

```powershell
python preflight.py --mode host
python preflight.py --mode solo --game-root 'D:\Games\OverField'
```

退出码 0 表示文件和数据库架构检查通过，2 表示缺项；不会启动服务、读取账号列表或连接官服。此检查不能代替干净电脑上的游戏启动和协议兼容性验证。详细发布状态见 [发布复核结论](docs/release-audit.md)。

## 使用

1. 在可写目录运行 `OverFieldLauncher.exe`，更改目录，选择兼容的本地 B 站 PC 客户端安装目录；现有适配针对 1.1.12，其他版本不保证兼容。
2. 服务端需自行从合法来源提供 `LoloServer`，包括 `Lolo.exe`、`config.json`、`data/`、`Resource/` 和数据库架构。仅玩局域网服务端时可将这些内容放入启动器旁的 `server-kit/`。
3. 不要将个人数据库当作公开模板。新建单机/局域网存档只复制数据库架构，不复制模板中的账号或进度；已有模式存档保持不变。个人进度必须由用户明确导入。公开服务模板仍应只含架构，且 `data/` 内不能夹带密钥或个人数据。
4. 填入自己的本地 UID，选择单机或局域网服务。首次准备会创建独立数据目录。
5. 如需恢复个人资料，使用“导入数据”选择自己的解码抓包 ZIP，确认预览后导入。服务会先停止，原数据库自动备份。

存档、导入报告、管理密钥和日志在 `profiles/solo` 或 `profiles/host`；运行状态在 `runtime/`。不要上传这些目录。关闭启动器不代表所有已启动服务已停止，请使用停止按钮管理服务。

## 局域网与安全

局域网 HTTP / UID 网关 / 日志端口为 19080 / 19100 / 19200。房间管理接口仅监听本机，并在首次运行时生成管理密钥。Windows 防火墙规则仅允许同一局域网；本项目为本地 UID 模式，不具备公网身份认证，不应暴露到互联网。每台电脑自行导入自己的资料，存档不会自动同步。

## 玩家备份工具与登录流程

`backup-tool/` 收录玩家数据备份工具源码及协议许可证，支持本人官服数据抓包、PCAP 解码和家园归档。便携运行时不进入源码仓库，完整 Windows 工具另作 Release 附件。源码版依赖设置、导入 ZIP 结构和隐私警告见 [备份工具说明](backup-tool/README.md)。

官服原账号登录与本地 UID 登录不是同一机制；数据不会凭 UID 自动获取。完整流程见 [登录与数据获取方法](docs/login-and-data.md)。

## 测试与发布

```powershell
python -m unittest test_launcher -v
```

测试仅使用合成数据，不需要真实账号。构建后可将 EXE、SDK DLL、图标和必要脚本作为 GitHub Release 附件；不要直接压缩本地工作目录。提交前运行 `python privacy_check.py`，并按 `RELEASE-CHECKLIST.md` 人工复核。
