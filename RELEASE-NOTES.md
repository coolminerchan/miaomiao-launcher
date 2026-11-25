# 开放空间私服启动器

清爽的天空蓝与海洋青动漫风界面，提供单机/局域网服务管理、本地 UID 登录、独立存档、账号数据导入与备份，以及房间和玩家管理。按钮加大、间距更宽，小窗口使用滚动布局，避免文字相互挤压。

## v1.2.1 更新

- 提供 **中文国服**与 **英文 Steam 国际服**两份独立便携包；正式版本号统一为 1.2.1。
- 整合 coolminerchan 的 PR #2：修复 Wi-Fi 与隧道裸 IP 混合抓包，恢复独立备份脚本连续采集与回车结束，完善残留会话清理，并支持 `OVERFIELD_TSHARK`。
- 在贡献基础上改为两遍流式修正，完整保留新接口的时间戳和其他选项，更新有限 section 长度，遇到非法接口引用不改写原文件。
- 补充大小端、多 section、后置接口、低内存、源文件变动和 CLI/GUI 控制分支回归。
- 修复英文版最小窗口下的按钮文字截断。135 项自动回归及 12 组两版界面布局检查通过，真实两服并行和 Steam 私服副本适配器复检通过。

下载：
- [中文国服便携包](https://github.com/inori-dream/miaomiao-launcher/releases/download/v1.2.1/OverFieldLauncher-CN-portable.zip)
- [英文国际服便携包](https://github.com/inori-dream/miaomiao-launcher/releases/download/v1.2.1/OverFieldLauncher-EN-portable.zip)

请分别解压到不同目录；游戏本体不包含在包内，不自动下载。国际服可用已由用户实机确认，本轮自动检查不代表覆盖所有游戏内容。

## v1.1.5 更新（历史）

- **支持 Steam 版公服客户端**：可直接选择 Steam 游戏快捷方式（`.url`）。这类客户端不固定游戏端口，改为按服务器地址采集。
- **修复 VPN / 隧道网卡抓包为空**：隧道网卡的裸 IP 包被误标为以太网，导致解包得到 0 条 TCP 流。现已自动识别并修正，原始抓包保留不变。
- **采集过程可见进度**：改为分段轮转，每段停止即落盘，采集中就能看到逐项结果。
- **退出即清理**：管理员模式下关闭启动器不再残留服务进程占用端口；游戏在运行时不会误停。
- 备份工具同步更新至 **1.0.9**。

## 致谢

感谢各位大佬对服务端部分功能的实现，以及对账号数据采集、备份和解析工具的开发与分享！感谢 [BanterSR/Lolo](https://github.com/BanterSR/Lolo)、[byzp/of-ps](https://github.com/byzp/of-ps) 及相关社区贡献者。具体来源和许可证见仓库的第三方组件声明。

**最终解释权归四川星期零信息科技有限公司。**

本项目为非官方社区工具，不代表已获得上述公司的授权、合作或背书。本声明不替代原游戏用户协议、知识产权要求或第三方许可证，工具自身由项目维护者维护。

## 下载选择

- 源码包：包含启动器、备份工具源码、构建脚本和使用说明。
- 启动器便携版：含 EXE、SDK、便携 Python、TShark 与解码依赖，解压即可运行；单机模式仍需兼容版本的本地 PC 客户端。
- 启动器组件包：仅 EXE、SDK、图标、核心脚本和文档；需自行提供 Python 3.12、合法来源的服务程序/资源。
- Windows 玩家备份工具：独立完整附件，含便携 Python、TShark 与解码依赖，用于本人账号备份；不能凭 UID 自动获取官服数据。

## 下载启动器

在本页底部 **Assets** 区域点击下载（国内网络打不开 GitHub 时，可让朋友下载后传给你）：

- **OverFieldLauncher-portable.zip** —— 便携版，解压即用（推荐）
- **OverFieldLauncher-components.zip** —— 仅启动器本体，需自备运行环境
- [直接下载便携版](https://github.com/inori-dream/miaomiao-launcher/releases/download/v1.1.5/OverFieldLauncher-portable.zip)
- [直接下载完整源码](https://github.com/inori-dream/miaomiao-launcher/releases/download/v1.1.5/OverFieldLauncher-source.zip)
- [直接下载 Windows 玩家备份工具](https://github.com/inori-dream/miaomiao-launcher/releases/download/v1.1.5/OverField-Backup-Windows.zip)

**使用步骤**

1. 完整解压到可写目录，例如 `D:\Games\OverFieldLauncher`，不要在压缩包里直接双击运行。
2. 双击 `OverFieldLauncher.exe`。单机模式先点“更改目录”选中本地 PC 客户端；局域网模式选择本机局域网地址后发布。
3. 便携版自带 Python、服务程序与资源，可直接使用；组件包需自行安装 Python 3.12 x64（勾选“Add python.exe to PATH”）并把 `Lolo.exe`、`config.json`、`data\`、`Resource\` 放进 `server-kit\`。
4. 可执行 `python preflight.py --mode host` 检查缺项，退出码 0 表示文件与数据库架构齐全。

便携版已包含 Python、服务程序与游戏资源，但仍需自备兼容版本的本地游戏客户端；组件包不含这些，**不是解压即玩的完整私服包**。

## 各文件说明

仓库中每个文件都有独立提交与用途说明，可在 [提交记录](https://github.com/inori-dream/miaomiao-launcher/commits/main) 逐条查看。`Launcher.cs` 是主界面与服务控制，`SeasideUI.cs` 是界面布局，`World-Control.ps1` 负责服务启停，`capture_import.py` 负责抓包导入，`backup-tool/` 是玩家数据备份工具。

## 账号与隐私

不附带作者真实 UID、账号凭据、个人存档、抓包、数据库或管理密钥。新模式只创建空数据库架构，个人资料必须由用户明确导入。默认 UID 是本地占位值，并非附送账号。

本地 UID 登录不具备账号所有权认证；不要将含私人存档的主机对公网或不可信玩家开放，不要上传抓包、导出 ZIP 或存档。

## 获取自己的账号数据

使用原客户端正常登录本人官服账号。以管理员身份先开始抓包，再重新登录并进入场景；打开需要保存的角色、背包、装备、宠物、邮件、家园等界面，等待加载。完成后核对解码摘要，只压缩输出中的 `export/` 文件夹，再在启动器中预览 UID 并确认导入。

详细步骤和限制见仓库的账号数据获取与导入说明。协议与服务端支持范围有限，不保证所有版本兼容或百分之百迁移。

## 支持的公服客户端

| 渠道 | 启动方式 | 采集适配 |
|---|---|---|
| B 站 PC 版 | 直接选择 `OverField.exe` | 按固定游戏端口采集 |
| Steam 版 | 选择 Steam 快捷方式（`.url`），经 Steam 启动 | 按服务器地址采集，自动修正隧道网卡帧 |

Steam 版需要先登录 Steam 客户端；启动时若弹出更新或登录窗口，需先完成再进入游戏操作界面。

## 已验证与限制

启动器 90 项回归测试、备份工具 4 项合成数据测试通过；单机/联机的默认与小窗口布局检查通过，公开包已进行已知个人信息扫描。Steam 版与 VPN 隧道抓包已在实机验证，可从真实流量解出游戏协议包。

尚未完成另一台干净电脑上的实际游戏启动验证。图标再分发许可、项目代码授权方式和 GPL 等第三方组件的发行义务仍需维护者确认；用户同意发布和上述声明不等于第三方授权。
