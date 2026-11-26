# 开放空间私服启动器

清爽的天空蓝与海洋青动漫风界面，提供单机/局域网服务管理、本地 UID 登录、独立存档、账号数据导入与备份，以及房间和玩家管理。按钮加大、间距更宽，小窗口使用滚动布局，避免文字相互挤压。

## v1.4.2 进入频道断链修复

- 修复v1.4.1房间加固的回归：进入尚未登记的自己的频道时，网关把合法1201误判为不可用并断链，客户端随即崩溃重连。
- 未登记频道不再提前拒绝，改为透明转发，收到服务端成功响应/场景观察后再自动登记；明确关闭或已满房间仍拒绝，自己当前房间重入允许。
- 1201频道ID仍严格校验uint32和解析完整性；1001认证fail-closed、空昵称回包补齐、观察异常不丢帧、脱敏握手日志全部保留。
- 不修改存档、数据库、rooms.json或官方资源；更新后重启私服使新网关生效。
- 23项网关专项与237项全量回归通过（1项符号链接权限跳过）；从真实1.4.1到1.4.2的CN/EN签名升级验证通过，私有数据及本地修改保持。最终以用户重新进入频道的实测为准。
- 已有v1.4.1可由内置更新器获取。详见[频道修复说明](docs/channel-switch.md)。

## v1.4.1 私服空昵称登录兼容（历史）

- 修复当前国服热补丁对成功登录回包空昵称的拒绝：仅明确成功的1004空player_name补账号已有昵称或本地UID显示名，失败状态及已有昵称保持。
- 不修改数据库、存档、官方资源或游戏补丁；保留所有包头字段和压缩信息，只修必要昵称/长度。
- 服务端透传与房间观察分离，观察解析异常不丢原帧；客户端认证/房间权限仍严格校验，握手诊断不记录UID、昵称、token或正文。
- 232项回归通过（1项符号链接权限跳过）；隔离真实后端1004空名补齐且status保持1，1006正常。最终恢复仍以用户重试为准。
- 已有v1.4.0可由内置更新器获取签名小型修复包，无需重下完整便携包。详见[空昵称登录说明](docs/login-empty-name.md)。

## v1.4.0 内置可信自动更新（历史）

- 国服/国际服启动时自动后台检查对应正式版本，下载小型核心更新包；底部保留检查更新、暂停自动和稍后入口。
- 更新清单以专用RSA2048/SHA-256签名，客户端固定公开校验参数；下载包和每个安装文件核对SHA-256与大小，拒绝错误版本/仓库/路径、降级和符号链接。
- 游戏、服务、采集空闲后进入可推迟倒计时，旧窗口退出后应用并重启；不强停游戏或服务。事务备份及日志用于失败回滚。
- 存档、配置、运行数据、游戏本体、运行时依赖和第三方安卓APK不自动覆盖；本地受管文件修改会暂停更新并保留，而不是静默重置。
- 首次需升级到带更新模块的v1.4.0，之后日常版本不用手动重下整个便携包。更新包与签名清单供软件使用，首次安装仍选CN/EN便携包。
- 安全范围与维护者发布要求见 [自动更新说明](docs/auto-update.md)。

## v1.3.0 采集增强集成与安卓原包附件（历史）

- 更新中文国服与英文 Steam 国际服两版，融合 Windows 1.0.12 新手增强：双语只读预检查、管理员确认后安全重启本版启动器、指南与结果导航。
- 保留当前 GUI 就绪/停止接口、Steam 地址和协议方向、混合 Wi-Fi/RAW流式修正、敏感登录过滤及 Lolo 导入门禁，不整体倒灌旧控制脚本或 of-ps SQL。
- 成功服务端响应生成 exploration.json / exploration.txt 并纳入账号ZIP；未采到为 null，总量未验证不计算百分比，地图3声明264/目录269保留为不一致提示。报告不等于已恢复Lolo游戏进度。
- 增加解码成功数、残缺流尾和解压预算；GUI只传有界摘要。状态未知或等待超时不强杀PID、不虚报完成，关闭启动器给本安装发送协作停止信号。
- 167 项自动回归与 12 组双版布局检查通过；最终便携包在发布前另行进行内置运行时和控制器检查。
- 新增 **安卓3.1第三方原包**附件，在安卓手机独立使用，非本项目开发/修改；只恢复外部.apk文件名，原字节和签名保持。SHA-256: `08dc8ed0a91e15b752a8a7014b40889028db8d9b18fabf2ea5cd5cfebd1becc6`。

**安卓提醒：**原包需要ADB/Shizuku等授权，主动登录可能顶号/切换家园；无障碍原版有全窗口明文日志风险，备份可能含登录信息。未安装、未修改、未作安全或全设备兼容认证；不要公开分享账号备份。安卓输出目前不能直接导入默认Lolo。详见 [安卓说明](docs/android-backup.md) 与 [采集集成说明](docs/collector-1012.md)。

下载：
- [中文国服便携版](https://github.com/inori-dream/miaomiao-launcher/releases/download/v1.3.0/OverFieldLauncher-CN-portable.zip)
- [英文国际服便携版](https://github.com/inori-dream/miaomiao-launcher/releases/download/v1.3.0/OverFieldLauncher-EN-portable.zip)
- [安卓第三方原包](https://github.com/inori-dream/miaomiao-launcher/releases/download/v1.3.0/OverField-Android-Backup-v3.1-third-party.apk)

## v1.2.2 国际服专用热修复（历史）

- 仅更新英文 Steam 国际服，国服 v1.2.1 便携包字节不变。
- 对已验证 Steam 私服副本的 GM 配置关闭开发 Error 窗口策略，不全局替换日志或吞异常，保留普通失败及断线提示。
- 实际 IL2CPP setter/getter 验证开关为 false，其他 GM 字段不变；138 项回归通过。
- 退出私服游戏后重新启动才能加载补丁；无需删除或重新导入存档。
- 截图提示的 ShopPoolConfigure 缺项属于独立兼容性问题，本补丁不宣称商店功能已全部实现。
- [英文国际服下载](https://github.com/inori-dream/miaomiao-launcher/releases/download/v1.2.2/OverFieldLauncher-EN-portable.zip)
- [国服原版下载（不变）](https://github.com/inori-dream/miaomiao-launcher/releases/download/v1.2.1/OverFieldLauncher-CN-portable.zip)

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
