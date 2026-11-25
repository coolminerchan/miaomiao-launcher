# 两版启动器 / Two launcher editions

## 中文国服版

- 中文界面，默认国服单机档案 `profiles/solo`。
- 使用已有的兼容国服 PC 客户端；不包含游戏，不自动下载游戏。
- 服务端端口为 18080 / 18100 / 18200，房间管理端口为 18300。

## English international edition

- English launcher UI; the default Steam world is stored in `profiles/steam`.
- Select your installed Steam OverField client folder containing `launcher.exe`.
- Uses a private copy; never changes the original official client or reuses official login credentials.
- Server ports: 20080 / 20100 / 20200; room administration: 20300.
- The Steam adapter is locked to a tested game binary hash. An unknown updated game build fails closed.
- Launcher UI language is independent of the game's own language setting. This release does not force an unverified game language enum value.

## Isolation and verification / 隔离与验证

Two local worlds have separate database paths, process records, controller locks, and ports. Keep the two portable packages in separate folders. Their local worlds can run concurrently. LAN mode still uses the existing dedicated host mode; do not publish two LAN host instances on the same default host ports.

验证结果：两份 EXE 编译成功；既有回归 113 项及新增隔离测试 3 项通过；两套真实空账号服务并行端口就绪；Steam 私服副本适配器在实机返回 `adapter-ready`，测试后自动关闭。

Verification scope: server concurrency and adapter installation. Full in-world login, international resource compatibility, and outfit rendering have not yet been verified. Do not interpret adapter readiness as proof that the previously reported outfit issue is fixed.

公服采集仍独立于私服目录：按原版客户端流程采集，保存账号 ZIP；不要公开个人存档或账号包。

## Credits / 致谢

沿用项目原有服务端与备份工具致谢，特别感谢水音的采集工具。

最终解释权归四川星期零信息科技有限公司。
