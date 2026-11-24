# TapTap 下载客户端的本地私服接入（实验性）

此功能只在 `feature/official-capture` 分支。主干和现有 Release 不变。

## 适配范围

已经验证的客户端为 Windows x64《开放空间》1.1.12，QuickSDK PC 布局：

- `launcher_Data/app.info` 对应 Inutan / 开放空间。
- `launcher_Data/Plugins/Win/PCSDK_release/PCSDKUI.exe` 存在。
- `GameAssembly.dll` SHA-256 为 `2db98364241c95864781f77877523b9d2f728b22a91935fa30cdfb33a8b7f4ea`。

单纯出现 `tapsdkcore.dll` 或 `taptap_api.dll` 不能证明实际走 TapTap 登录。这里验证过的包使用 QuickSDK，渠道记录为 official。
其他版本拒绝套用本实验适配；不得猜测地址或盲目修改原始客户端。

## 使用方式

1. 使用含 Frida 17.24.3 的分支测试版；源码安装依赖见 requirements.txt。
2. 在启动器选择该游戏安装目录，即包含 `launcher.exe` 和 `launcher_Data` 的目录。
3. 选择单机模式，设置本地 UID；已有导入存档时使用对应 UID。
4. 点击启动单机游戏。启动器生成独立副本，给 QuickSDK PC 客户端加载本地适配。
5. 在游戏中点击登录/进入，并核对本地角色。失败时查看该模式 logs 内 `quicksdk-local.jsonl`、客户端 stderr 和 Player.log。

## 与公服认证的关系

本地适配在私服副本进程中返回 `local-session` 占位身份，不是公服凭证。
它不读取 QQBot 的公服 token，也不把公服密码/cookie写入私服或公开包。
QuickSDK 的旧启动凭证校验被禁用，dispatch 根地址被改为用户指定的本机或私有局域网服务。
公网目标、非隔离客户端、未知 GameAssembly 哈希均拒绝启动。
公服采集仍必须通过原版客户端正常认证，不使用这个适配器。

## 副本和存档保护

- 原始 exe、GameAssembly、服务器配置不修改。
- 只链接不可变资源；QuickSDK日志、插件cookies和缓存不与原始目录共享。
- 客户端来源和关键文件指纹必须匹配，旧 ready 标记不再足以复用副本。
- 来源变化时旧客户端副本移至当前模式 backups，账号数据库不移动或重置。
- 更新启动器采用文件级备份，不允许重建整个便携目录来删除已有 profiles。
- Unity及第三方SDK可能仍使用系统用户目录保存通用设置；日志可能包含个人信息，不应公开。

## 已验证与未验证

已验证：7项适配边界测试及18项现有回归测试；原型加载成功；本地 dispatch 请求收到 HTTP 200；本地UID 1000000在独立空数据库服务上登录成功；网关确认 uid-connected。
尚需用户验收：游戏实际场景渲染、角色创建后的持续游玩、联机模式，以及其他客户端版本。不得把“登录成功”描述为全版本全功能兼容。

## 第三方依赖

Frida 17.24.3 使用未修改的 Python wheel；实际包内许可证为 wxWindows Library Licence 3.1。
原文应随便携版置于 licenses。源码：https://github.com/frida/frida
Python发行包：https://pypi.org/project/frida/17.24.3/

研究性调试脚本、原始客户端日志、账号抓包与任何用户凭证不提交到仓库。
