# A7C 独立 QEMU 板级基础

本目录基于 A7M3 的 CXD90045-family 功能模型注册独立 `-M a7c`，使用本地 QEMU 11.1.2 归档重新编译。地址、IRQ、时钟和 GPU 启动包继承参考工程，尚未由 A7C 实机证据验证。板级构建、设备创建和正常 QMP 退出与内核、原 AP 启动分开验收；后两项在本报告中保持 false。

本项范围为本机隔离 QEMU 的 board、timer、构建脚本及相关自检，遵循[项目约定](../../../../AGENTS.md)。未连接物理设备，也未修改 A7M3 或 ZV-E10 参考环境。顶层源码、固件提取和内核集成由主任务维护。

## 构建与检查

从 `final/a7c-qemu/` 执行：

```bash
./build-qemu.sh
./work/qemu-src/build-a7c/qemu-system-arm -M help
```

默认归档为本项目的 `work/qemu-11.1.2.tar.xz`。也可指定相同摘要的本地归档；相对路径按调用时的工作目录解析：

```bash
QEMU_TARBALL=../../sources/qemu-11.1.2.tar.xz ./build-qemu.sh
```

需要 Bash、GNU coreutils、tar/xz、patch、C 编译器、Python 3.11 或更新版本、Meson、Ninja，以及 GLib、Pixman、SDL2 开发文件。脚本禁止 QEMU/Meson 下载依赖；DTC 使用本目录的固定归档。源目录 `work/qemu-src/` 和构建目录 `work/qemu-src/build-a7c/` 独立创建，已有残缺源码、注册补丁冲突和这两个目录的符号链接会被拒绝并保留。

| 固定输入 | SHA-256 |
| --- | --- |
| QEMU 11.1.2 | `731b5681e4bb18be313231579b8efd0296c5b015fa36dc533874b639ba838016` |
| [DTC b6910bec](dtc-b6910bec.tar.xz) | `c1fb23f4f39fc88da4a1f89b06ea13e8683de886ee77dbb99369f8763dfe809e` |

DTC 提交为 `b6910bec11614980a21e46fbccc35934b671bd81`，对应原 QEMU 的 `subprojects/dtc.wrap`，归档包含原许可证。QEMU 源码从固定原始归档提取，没有复制参考工程的构建目录或二进制。

脚本应用[注册补丁](0001-register-a7c.patch)，复制 [board](hw/arm/a7c.c)、[启动包守卫](hw/arm/a7c-gpe-init.h)和 [timer](hw/timer/sony_hwtimer.c)，再执行：

```bash
../configure --target-list=arm-softmmu --disable-download \
    --without-default-features --enable-tcg --enable-fdt=internal \
    --enable-pixman --enable-sdl --disable-werror \
    --disable-tools --disable-guest-agent --disable-docs
ninja -j8 qemu-system-arm
```

构建后自动编译并执行 [GPE C 自检](../../tests/test-a7c-gpe-init.c)，再使用无内核、无磁盘、无网卡且暂停 CPU 的 QMP 会话实际创建机器。检查包括机器类型、一个 Cortex-A9、九个 Sony timer、PL011、PL181、GPE/Sugilite 映射，以及 QMP `quit` 后退出码 0。构建启用 SDL 不表示相机显示硬件已经实现。

## 证据与结论

实际产物身份及验证时间以 [qemu-board.json](../../validation/qemu-board.json) 为准，其中记录二进制、全部 board 构建输入和主要原始日志的大小与 SHA-256。相同内容还保存在构建目录的 `verification.json`；二进制位于 `work/qemu-src/build-a7c/qemu-system-arm`。不同主机和工具链不承诺逐字节一致。

2026-11-06 14:24:32 UTC 的本次构建实际完成 2,015 个 Ninja 步骤，末步链接成功；构建日志无编译 warning/error。QMP 检查通过且 stderr 为空，`quit` 后退出码 0。二进制大小为 93,991,712 字节，SHA-256：

```text
97a04e44228807762fcfe259f1eddde44d4068edcf2bb733ceff85b57ea084fc
```

| 证据 | 来源 | 结论与复现路径 |
| --- | --- | --- |
| E-001：注册与源码 | [补丁](0001-register-a7c.patch)、[board](hw/arm/a7c.c)、[timer](hw/timer/sony_hwtimer.c) | F-001：独立 `CONFIG_A7C` 选择 A9MPCore、PL310、PL011、PL181、UNIMP；Sony timer 由 A7C 配置编译。执行 `./build-qemu.sh` 提取、注册并构建。 |
| E-002：实际构建与 QMP | [configure.log](../../work/qemu-src/build-a7c/configure.log)、[build.log](../../work/qemu-src/build-a7c/build.log)、[原始 QMP](../../work/qemu-src/build-a7c/verification-qmp.log)、[stderr](../../work/qemu-src/build-a7c/verification-stderr.log) | F-001：实际链接产物可创建 `a7c-machine` 和指定设备；无 guest 网卡/磁盘，QMP 正常退出。执行脚本末尾的自检重现。 |
| E-003：启动包守卫 | [guard](hw/arm/a7c-gpe-init.h)、[测试](../../tests/test-a7c-gpe-init.c)、[host 结果](../../work/qemu-src/build-a7c/verification-gpe-init.log)、[ASan/UBSan 结果](../../work/qemu-src/build-a7c/verification-gpe-init-sanitized.log) | F-002：继承的一种启动 fence、七个固定 word 和指针范围边界经 14 项 host 检查；该结论不覆盖通用 GPU 包解释或 A7C 固件实际消费。 |

P-001（构建与板级调用路径）：固定归档 SHA 检查 → 独立提取与注册（E-001）→ configure/Ninja 实际链接（E-002）→ GPE 守卫 host 检查（E-003）→ `-M a7c` QMP 创建、设备检查与正常退出（E-002/F-001）。F-002 仅是局部守卫的 host 结果。原始日志与产物摘要保留，后续内核/AP 集成不能把这里的板级通过提升为完整固件通过。

独立复现 sanitizer 检查：

```bash
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
    -g -fno-omit-frame-pointer tests/test-a7c-gpe-init.c \
    -o work/qemu-src/build-a7c/test-a7c-gpe-init-sanitized
./work/qemu-src/build-a7c/test-a7c-gpe-init-sanitized
```

## 模型边界

| 部分 | 当前实现 | 未验证能力 |
| --- | --- | --- |
| CPU / 启动 | Cortex-A9，默认 1 GiB DDR 从 0 起，继承 board ID 3497、loader `0x00128000` 与 ATAGS | A7C 物理布局、原内核启动、SMP、原 AP |
| IRQ / timer | A9 MPCore 与九个 4 MHz Sony timer | A7C 每路实际 IRQ、时钟与完整计数语义 |
| UART / 存储 | PL011、PL181 功能设备 | Sony SD 控制器/DMA、固件读写虚拟卡 |
| Sugilite / GPE | 电源状态局部固定读值；严格识别参考工程捕获的一种初始化 fence | A7C 包身份、实际图像消费、GPU 绘制/合成 |
| 其余 SoC | 未实现区读零、写忽略；已建模区域优先 | CP、USB、GPIO、CMOS、镜头、AF、ISP、JPEG/视频编码、拍照录像成片 |

`kernel_boot_verified`、`firmware_boot_verified`、`ap_verified`、`physical_asic_compatibility_verified` 均保持 false；本项没有把未实现寄存器、固定读值或 fence 返回记为硬件完成。
