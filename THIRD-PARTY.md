# 第三方与原厂资产

- 顶层主机工具和文档沿用本项目的 MIT 许可，见 `LICENSE`；保留原作者声明。
- `source/qemu/hw/arm/a7c.c`、Sony timer、注册适配源于 ZV-E10／A7M3 实验板级代码及 ma1co 的 BIONZ 模型，按文件中的 GPL-2.0-or-later 声明使用。上游 QEMU 为 GPL，不能用顶层 MIT 许可替代。
- `source/kernel/0001-a7c-qemu.patch` 应用于 Sony ILCE-7C 官方 Linux 3.0.27 源码；Linux 内核及该衍生修改遵循其 GPL-2.0 等原许可。`source/modules/` 的模块也保留其源文件许可声明。
- `source/qemu/dtc-b6910bec.tar.xz` 是离线构建用的 DTC 源码归档，摘要见 `SOURCES.md`；许可证保留在归档内。
- `sources/sony-ilce7c-ver203/` 中各源码包按各自内含许可证使用，下载时保留 Sony notice。源码包下载完整不等于 Sony 专有程序的源码完整。
- 更新 EXE／DAT、解包的 Sony ELF、内核模块、设置模板、图片和字体是用户本地资产，均不由本工程 MIT／GPL 声明重新授权；不混入公开源码交付。
- Bootlin 编译器与其运行库、fwtool、Python／Pillow／Tk／pyelftools／Capstone 各自保留上游许可证。来源、固定版本和摘要见 `SOURCES.md` 及 `validation/`。
