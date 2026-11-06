# 构建与运行 A7C 原厂界面

在本工程根目录执行以下命令，使用 Linux x86_64、Python 3.12+。本地构建输出已经就位时，直接运行 `./start.sh`。

## 依赖

需要 GCC、Make、Ninja、Meson、GLib、Pixman、SDL2、cpio、7-Zip、e2fsprogs、fakeroot、patch、Git、curl，以及 Python Pillow、Tk、pyelftools 和 Capstone。Debian／Ubuntu 可用：

```bash
sudo apt install build-essential ninja-build meson pkg-config \
  libglib2.0-dev libpixman-1-dev libsdl2-dev python3 python3-venv \
  python3-pil python3-tk python3-pyelftools python3-capstone \
  cpio p7zip-full e2fsprogs fakeroot patch git curl bc bison flex
mkdir -p work
```

## 下载源码与构建工具

```bash
python3 scripts/download-sources.py
(cd sources/sony-ilce7c-ver203 && sha256sum -c SHA256SUMS)
git clone https://github.com/ma1co/fwtool.py work/fwtool
git -C work/fwtool checkout 72fbdd15ddcc2d2a24ccb52cf8e84b8de98c738a
python3 -m venv work/fwtool-venv
work/fwtool-venv/bin/pip install pycryptodome pyyaml
curl -fL --retry 3 \
  https://toolchains.bootlin.com/downloads/releases/toolchains/armv7-eabihf/tarballs/armv7-eabihf--glibc--stable-2020.08-1.tar.bz2 \
  -o work/armv7-toolchain.tar.bz2
tar -xjf work/armv7-toolchain.tar.bz2 -C work
curl -fL --retry 3 https://download.qemu.org/qemu-11.1.2.tar.xz \
  -o work/qemu-11.1.2.tar.xz
```

构建脚本会核对 QEMU、DTC 和 A7C 内核归档的固定摘要，来源见 [SOURCES.md](../SOURCES.md)。本次工作区复用了已有的同版本编译工具，其 A7C 内核与 QEMU 在独立目录实际重建。

## 提取固件和构建

将用户自备的 `Update_ILCE7CV203.exe` 放在根目录。准备工具核对完整包、CAB、DAT、型号和版本，以数据方式解包；不会运行 Windows 程序。原分区映像保持不变。

```bash
python3 scripts/prepare-firmware.py --fwtool-python work/fwtool-venv/bin/python
./build-kernel.sh
./build-qemu.sh
fakeroot -i work/fakeroot-extract.state -s work/fakeroot.state \
  python3 scripts/prepare-initramfs.py
```

准备脚本拒绝覆盖已有提取／运行树。重做前保留旧目录；不要删除正在使用的实验。`fakeroot-extract.state` 记录原节点，`fakeroot.state` 记录运行副本节点；后续 cpio 打包必须加载该状态。运行树中的 FIFO 用 `mkfifo` 复制，设备用原 mode／major／minor 重建，不能用普通文件代替。

内核从 A7C 自己的 Linux 3.0.27 归档构建，启用 `RD_GZIP`，生成 `work/kbuild-ui/arch/arm/boot/Image`；通过压缩的外部 initramfs 运行。启动脚本编译 A7C 专用界面适配库，核对 AP-only IMDB 副本，打包 `work/ui.cpio` 并生成 `work/ui.cpio.gz`。压缩可避免约 240 MiB 的原始归档与解包树同时占满 guest 可分配 RAM；图像区预留不变。原厂程序和原菜单资源来自 A7C 更新包。

## 启动与验证

```bash
./start.sh
```

窗口按钮：MENU、返回、刷新；键盘：`M`、`Esc`、`R`。每次运行的原始日志、原像素、PNG、页映射与退出记录放在独立的 `output/` 子目录。ENTER／DISP 原始码仅保留为开发调查，不是首版窗口功能。

```bash
./start.sh --smoke
python3 tests/check-runtime-evidence.py output/20261106-233800
python3 tests/run-tests.py
python3 scripts/download-sources.py --self-test
xvfb-run -a python3 tests/check-gui.py
```

`--smoke` 依次采集主页面、MENU、返回和 MENU 重入，然后正常 QMP quit。最后一条命令另外验证真实 Tk 按钮与窗口关闭；有图形桌面时直接打开窗口即可。证据检查器核原字节、PNG、指纹和退出状态，菜单文案和主页面的视觉内容还需看图核对。

窗口关闭失败会保留本轮进程所有权并显示错误，再次关闭可重试。不要对其他工程的 QEMU、串口或窗口发送关闭命令。

仅运行本机虚拟资源；当前验收针对原厂主页面／MENU。CMOS、镜头、自动对焦及拍照录像没有作为本阶段功能交付。
