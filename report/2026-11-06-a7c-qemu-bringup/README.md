# A7C 2.03 原厂主页面与 MENU 运行报告

日期：2026-11-06。范围与授权见 [scope.md](scope.md)。本文为固件仿真技术报告，使用普通逆向报告结构。

## 已达到的结果

在独立 `-M a7c` 中，从 A7C 官方开放源码重建的内核实际加载 A7C 原模块，启动原 `bootin.elf → im.elf`。原拍摄页实例和 MENU 均已实际生成可读像素。最终 `output/20261106-233800`（自动验收）和 `output/20261106-233844`（真实 Tk 按钮／关闭）共 8 份原像素与 PNG 已分别独立读回；两轮返回拍摄页均与最初拍摄页 SHA256 完全相同，重入菜单也与首次菜单完全相同。两个原 QEMU 正常 quit 返回 0，无 VM 信号。

首版交付 MENU／返回／刷新三个控制。原 ENTER 映射及单次“当前功能无效”提示已核定，但独立真实窗口轮出现等待超时，未定位其实际 AP 等待点；该功能不作为稳定窗口控制。原失败、未采到的帧和不一致均保留，未以主机检查退出 0 推广为像素通过。

当前拍摄页显示原厂镜头收纳提示，未将其描述为镜头已就绪或完整拍摄 HUD。镜头／CMOS／AF、拍照录像和物理 ASIC 精确等价性保持未验证。MENU 输入经原 callback 按下／释放，AP-only profile 再在原 UI 线程调用原菜单 helper；返回通过原 numeric view API 恢复拍摄页。完整硬件输入路由没有验收。

## 输入与源码来源

| 项目 | 身份 |
| --- | --- |
| 更新包 | `Update_ILCE7CV203.exe`，SHA256 `e382c3deecb8d0fe8463a2451ddbfa897cd131a1797170d05936fabc4ffaf6f8` |
| 内嵌 DAT | SHA256 `b5c20ed18b656d22611aa0ee0c83c168bd247030dc7bcf249bdb60d1168c3f39` |
| 固件 | ILCE-7C 2.03，model `0x91030019`，CXD90045／ARM32 EABI5 |
| 内核 | A7C 官方 Linux 3.0.27，重建 release `3.0.27_nl-rt106+` |
| 设置模板 | `NB/CX88600_ALLLANG.bin`，原厂公开更新包内模板 |
| QEMU | 独立实际构建 11.1.2，`a7c-machine`，Cortex-A9，九个 Sony timer |
| 全部 OSS 包 | 26/26，271,399,908 字节；不同版本均保留 |

原始分区映像、更新包与提取树保持不变；运行副本另建。p7／p15 `e2fsck -fn` 均为 0；debugfs 和 fwtool 独立 ext2 通道核文件内容、元信息与节点。完整准备脚本在独立目录重放，再与主实际资产比对。主会话另外读回 1,076 个普通文件、160 个链接、两个 FIFO；单独 fakeroot 会话核 1,686 个 inode 和全部 365 个设备号。导入／依赖和 110 个原模块的 ABI 见 `validation/firmware.json`、`validation/elf-survey.json`。

## 适配与消费路径

1. 官方内核归档保持原件，在独立构建树应用同代 40 文件适配；QEMU 与参考工程、构建输出相互独立。
2. 从 A7C 原分区和 0800 应用包准备运行树。外部 gzip initramfs 避免原始归档与解包树同时耗尽 RAM。
3. AP-only IMDB 只清 10 个明确硬件目标项的 qemu mask，保留原 appFw／grm／uxengine；源身份、表结构与修改范围固定核对。
4. 原 ELF 地址分 33 个代码、12 个数据、6 个视图位置核定。14 个 hook、Thumb 前导、RM literal trampoline、RTTI、PC/GOT 和 numeric 注册均有原字节证据。
5. 软件后端实际消费原 Bitmap／A8、字体、LZ77、Morton、几何和 blend。A7C 的 `144×28 → 448×28` 请求通过原 filter 表确认 LINEAR 后，执行四邻点采样；保留原 finish、Bitmap 锁、sampler／metadata 稳定性和清理。
6. 原 MENU 新出现的局部 clear 保持 type／pattern／control／地址域／对齐和大小边界，真实清零请求范围，再由原 RM 路径退役回调。
7. 原提交帧在读锁下复制、pin 并公布实际 PFN；宿主暂停 QEMU，读取原快照，核 FNV／SHA256 和 PNG，恢复执行。

详见 [UI 移植说明](../../source/ui/PORTING.md)、[启动／提取失败](PROBLEMS.md) 和[原菜单局部清屏／返回问题](PROBLEMS-native-menu.md)。

## Evidence → Finding → Path

| 证据 | source_ref／artifact_path（工程根目录相对） | 复验 | 内容摘要 |
| --- | --- | --- | --- |
| E-OSS | `validation/source-downloads.json`，`sources/sony-ilce7c-ver203/SHA256SUMS` | `python3 scripts/download-sources.py --self-test`；在下载目录 `sha256sum -c SHA256SUMS` | 官方 26 包及两页原件完整读回 |
| E-FW | `validation/firmware.json`、`main-firmware-readback.json`、`main-firmware-metadata.json` | 按 `docs/setup.md` 在新 work 运行固定 prepare 脚本；既有树会明确拒绝覆盖 | 型号／版本／完整资产／原 inode 合同 |
| E-ABI | `validation/ui-relocation.json`、`work/view-abi-main-review/validation.json` | `python3 scripts/relocate-ui.py --check`；需要本人更新包提取 ELF | 原函数、原数据、原视图注册和 sampler 字节 |
| E-HOST | `validation/host-tests.json`、`work/partial-clear-v5-test.log` | `python3 tests/run-tests.py` | 16 组集中回归；新增 sampler 与 partial-clear 普通／sanitizer 检查 |
| E-AP | `validation/ui-acceptance-v10.json`、`output/20261106-233800/`、`output/20261106-233844/` | `python3 tests/check-runtime-evidence.py output/20261106-233800` | 原主页面／MENU／返回／重入、真 MENU 码和两个 QMP0 |
| E-INPUT | `validation/input-abi.json`、`validation/ui-abi-final.json` | `python3 scripts/relocate-ui.py --check` | 9 个具名原键表项、8 个原指令窗口；旧码误名的反证 |
| E-SERIAL | `validation/serial-publication-replay.json` | `python3 tests/test-camera.py` | 完整 timestamp echo 与原始 partial-prefix marker 区分；重复页面仍拒绝 |

这些 JSON 内记录每个源、原字节窗口、图片和原日志的 SHA256；失败原件未回填。

| 结论 | 状态／置信度 | Evidence | location |
| --- | --- | --- | --- |
| F-OSS：官方页全部公开包已归档 | validated／high，n/a_re | E-OSS | `sources/sony-ilce7c-ver203/` |
| F-BOOT：A7C 原程序与本机内核 ABI 可实际运行 | validated／high，n/a_re | E-FW、E-ABI、E-AP | `work/kbuild-ui`、原 bootin／im |
| F-MENU：原菜单可读且可返回／重进 | validated／high，n/a_re | E-ABI、E-AP | `source/ui/ui-observe.c` |
| F-LIMIT：完整镜头／取景／拍摄未完成 | confirmed limit／high，n/a_re | E-AP | 原拍摄页镜头提示；`capture_verified=false` |

P-UI，path_type=`callflow`：E-FW 的 A7C 原包 → E-ABI 的同版模块／界面适配 → E-AP 原 bootin／im 创建拍摄页 → 原 MENU callback 与 helper → 原绘图／原完成通知 → 原像素读回 → 原 numeric close／open 恢复拍摄页 → 再次 MENU → QMP quit0。剩余边界由 F-LIMIT 限定。

## 关键运行与否定记录

| 轮次 | 内容型结果 |
| --- | --- |
| `20261106-223652` | 未压缩 initramfs 解包 OOM；未进入 AP；原件保留，QMP0 |
| `20261106-224014` | gzip 后原模块、原 AP、拍摄页构造和帧提交完成；真实缩放拒绝；QMP0 |
| `20261106-224252` | 保留相同拒绝，取得原 `144→448`／filter 参数；QMP0 |
| `20261106-225802` | 缩放实际消费后原主页面已读回；MENU 触发新 partial-clear 拒绝；QMP0 |
| `20261106-230054` | 原 MENU 已读回，裸 close 后无新帧；返回失败保留；QMP0 |
| `20261106-230445` | 原拍摄页、原 helper 打开的 MENU、返回、重入像素通过；后来核明旧 MENU/ENTER 原始码实际是 AF/MF/DOWN，语义修正另记；QMP0 |
| `20261106-231746` | 修正真实 MENU／ENTER 码后，单轮原提示、菜单返回与重入通过；不提升为 ENTER 稳定性 |
| `20261106-231835` | GUI dispatch／MENU／返回通过；确认快照仍旧菜单，后续原提示晚到，未冒称 coherent |
| `20261106-232601` | ENTER GUI 等待超时，原 AP 等待点未核；原件保留，正常 QMP0，撤回未完成的 idle-update 实验 |
| `20261106-233325` | 原返回新帧 META 与半截内核 timestamp 交错；旧 host 把 META 丢掉后拒绝页数，部分末帧没有 READY，不冒称已完整 |
| `20261106-233800` | 最终三控制自动原主页面／MENU／返回／重入、真 MENU 码、原像素读回通过；QMP0 |
| `20261106-233844` | 最终真实 Tk 按钮与窗口关闭，4 份原像素独立读回通过；QMP0 |

首次提取探针、独立脚本重放中的原错误、FIFO copy 失败和编译缺少旧内核 header 的失败也分别保留在 `work/`，见对应专题。源码／构建／主机自测／原 AP 实际消费严格分账。
