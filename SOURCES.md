# 来源与构建输入

## A7C 2.03 官方开放源码

官方页面：<https://oss.sony.net/Products/Linux/DI/ILCE-7C_Ver203.html>。

该页的 26 个包已全部下载到 `sources/sony-ilce7c-ver203/`，总计 **271,399,908 字节**（4 个 tar.gz、22 个 src.rpm）。包含 Linux、compat-wireless、qrencode、strongSwan，以及页面列出的 BusyBox、coreutils、dosfstools、e2fsprogs、GCC 运行库、glibc、hostname、iperf、iptables、libnl、libusb-compat、procps、pump、rpm、soundtouch、util-linux 各版本。

[下载清单](validation/source-downloads.json)记录每包 URL、尺寸和 SHA256；本地 `manifest.json` 还保留 HTTP 元数据、下载尝试与内容校验。页面和 Sony notice 原件在 `sources/sony-ilce7c-ver203/pages/`。

```bash
python3 scripts/download-sources.py
(cd sources/sony-ilce7c-ver203 && sha256sum -c SHA256SUMS)
```

这些是 Sony 发布的开放源码，包内保留各自许可证；不包含 Sony 专有相机应用的完整源码。TAR 校验包含结构和完整压缩流，RPM 校验覆盖 lead/header magic；未声称验证 RPM 签名或展开其 payload。

## 内核

A7C 官方 `linux-kernel.tar.gz`：

```text
477dfb9c17aa585dc5713331ff22a43b508e3fc6a247b2458503b9c4672eaf7c
```

从该归档构建 Linux `3.0.27_nl-rt106+`。与 A7M3 官方归档逐个普通文件比对，各有 19,678 个文件，仅 13 个 USB 文件内容不同，见 [kernel-source-diff.json](validation/kernel-source-diff.json)。本工程基于 A7C 原包应用适配，没有替换成 A7M3 内核树。

`source/kernel/0001-a7c-qemu.patch` 和 `a7c_defconfig` 来源于同代 ZV-E10／A7M3 适配，支持现代汇编器、GCC 9、ATAGS、DDR alias、PL181 和已记录的 procfs 实验性绕行。它们只用于本机 QEMU；原 Sony 归档保持不变。内核使用外部 initramfs，构建不依赖打包后的专有系统树。

## 仿真与提取工具

| 输入 | 固定来源 |
| --- | --- |
| QEMU 11.1.2 | <https://download.qemu.org/qemu-11.1.2.tar.xz>；SHA256 `731b5681e4bb18be313231579b8efd0296c5b015fa36dc533874b639ba838016` |
| DTC | `source/qemu/dtc-b6910bec.tar.xz`；SHA256 `c1fb23f4f39fc88da4a1f89b06ea13e8683de886ee77dbb99369f8763dfe809e` |
| ARM 编译器 | [Bootlin ARMv7 EABIHF glibc stable-2020.08-1](https://toolchains.bootlin.com/downloads/releases/toolchains/armv7-eabihf/tarballs/armv7-eabihf--glibc--stable-2020.08-1.tar.bz2)，GCC 9.3.0 |
| fwtool | <https://github.com/ma1co/fwtool.py>，commit `72fbdd15ddcc2d2a24ccb52cf8e84b8de98c738a` |
| ZV-E10 参考 | <https://github.com/chocotan/zve10-qemu>；本地 `~/Downloads/zve10-qemu` 只读参考 |
| A7M3 参考 | 同工作区 `../a7m3-qemu` 只读参考；其固件、设置和构建输出未用作 A7C 运行资产 |

更新包由用户提供：`Update_ILCE7CV203.exe`。以数据方式提取，未执行 Windows 程序；真实 EXE／DAT 和提取文件身份以 [firmware.json](validation/firmware.json) 及本地 `work/firmware-manifest.json` 为准。

## 本地资产和公开代码

`work/` 是独立的 A7C 提取、构建和运行树，`output/` 保留每轮运行证据，`sources/` 保留官方源码原件。它们和 EXE／DAT 均被 `.gitignore` 排除，防止专有程序、设置和大型生成文件混入公开代码。发布时按白名单审核，不能仅凭 ignore 判断可以公开。
