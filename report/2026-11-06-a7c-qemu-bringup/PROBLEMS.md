# 已定位的启动与 UI 适配问题

本文件记录实际失败及修复依据；最终运行验收另见本目录 README 与 `validation/ui-acceptance.json`。

## 外部 initramfs 解包耗尽内存

- 现象：`output/20261106-223652/serial.log` 在 `Trying to unpack rootfs image as initramfs` 后 OOM，没有进入原厂应用。未压缩归档为 252,054,016 字节；内核在预留原图像区及原始 initrd 后仅有 `237356k` 可分配。
- 原因：归档与解包后的 rootfs 同时占用 RAM，A7C 的系统树比 A7M3 更大。
- 修复：`a7c_defconfig` 和 `build-kernel.sh` 启用 `RD_GZIP`；`start-a7c-ui.sh` 使用 `gzip -n -1` 生成并原子发布外部 initramfs。图像保留区未缩小。
- 内容证据：后续 `output/20261106-224014/serial.log` 通过解包，14 个所需模块均 status=0，原 `bootin → im` 进入主页面构造并实际发布帧。该轮仍被后述缩放拒绝，不能记为 UI 通过。
- 收尾：失败原日志及 v1 Image／config 保留；QMP quit 返回 0，无 VM 信号。主机现对内核 panic 及时报错，回归覆盖原 printk 和时间戳两种行前缀。

## 原文件系统含 FIFO 和设备节点

- 现象：直接继承的 Python `shutil.copytree/copy2` 对 `dev/jet/TransferJet_*` 两个 FIFO 抛 `SpecialFileError`；原失败在 `work/preparation-failed-v1/`。
- 修复：`prepare-initramfs.py` 按 inode 类型复制，FIFO 使用 `mkfifo`，设备使用原 mode／major／minor。打包始终载入保存的 fakeroot 状态。
- 证据：原树两种读取通道、完整提取脚本重放、独立全树字节／链接／FIFO 读回，以及单独 fakeroot 会话下 1,686 个 inode 元信息和 365 个设备号核对均通过。见 `validation/firmware.json`、`main-firmware-readback.json`、`main-firmware-metadata.json`。不能用宿主未载入 fakeroot 时看到的普通占位文件推断原设备节点不存在。

## A7C 导航采用自己的 numeric ID

- 原生证据：两处真实 registration 都将 ROOT 注册为 `0x9c`、STLREC 为 `0xbf`，三个菜单为 `0x11 / 0x58 / 0xb6`。A7M3 原来的 `0xba / 0x5a` 在 A7C 指向其他页面。RootSelector 菜单接口偏移从 `+0x124` 变为 A7C 的 `+0x154`。
- 修复：`ui-observe.c` 使用 A7C 的 `ViewBase::openView(int,int,bool)`、`closeView(int)`；返回按内到外关闭三个真实菜单 ID。正常按下／释放回调和原菜单 helper 仍保留。
- 验证：主会话独立重跑 89 条原注册／工厂／RTTI／manager layout／helper byte 检查，保存于 `work/view-abi-main-review/`；生产 `relocate-ui.py` 同时核固定 ELF 身份、numeric API 和 registration immediate。源码／静态结果与最终原 AP 输入验收分别记账。

## A7C 主页面使用纹理缩放

- 现象：`output/20261106-224014/` 已创建原主页面并提交 640×480 帧，随后继承的后端拒绝 `GEMINI.cpu.source_filter_scale`，正常退出。
- 诊断：只增加失败参数观测，未放宽判据；`output/20261106-224252/` 原请求为 source `(28,0,144,28)`、destination `(28,0,448,28)`、filter word `0x00010001`，是一条真实横向缩放请求。
- 修复与最终结果：以 `source/ui/PORTING.md`、相应采样测试和最终原 AP 像素验收为准。前两轮缩放失败日志均保留，不回填为通过。

## 审查结论的核收

GLM 对集成中的快照指出 UI profile 缺失；该文件随后由 UI 移植任务交付，主已实际执行并核对 A7C 的 `imdb_raw=0xe2a4`、10 个精确 target-mask 修改及保留的三项原应用／图形组件。其建议让未实现 DMA 返回成功未采纳：本工程保留明确 `-EOPNOTSUPP`，原 AP-only profile 不加载依赖这些传输的 liro。真实运行若消费到未支持 DMA 会记录并立即拒绝，不将空成功作为 UI 完成证据。
