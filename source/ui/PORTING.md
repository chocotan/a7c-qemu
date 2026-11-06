# A7C 2.03 原厂 UI 移植与静态验收

本目录是 ILCE-7C 2.03 的 ARM32 原厂 UI 软件绘图后端。固定地址来自 A7C 自身 ELF；参考 ZV-E10 与 A7M3 的消费机制，保留原页面、字体、图片、Bitmap 锁及显示完成通知。

**本页记录源码、静态检查、ARM 编译与 host 测试；原厂主页面、MENU、返回、重入的实际像素验收由主运行记录另行判定。首版窗口仅暴露 MENU／返回／刷新，ENTER／DISP 不算稳定交付。** [静态证据](../../validation/ui-relocation.json)中的 `runtime_verified`、`original_main_verified`、`original_menu_verified`、`capture_verified` 均保持 false，不用 host 测试代替原 AP 消费。

## 重新检查与构建

以下命令在 `a7c-qemu/` 根目录执行，需要自己从更新包提取的原始 `work/usr/lib/`、pyelftools、Capstone，以及已准备的 Bootlin ARM 工具链。

```bash
python3 -B scripts/relocate-ui.py --check
python3 -B tests/test-a7c-ui-profile.py
python3 -B tests/test-a7c-ui-relocation.py
work/armv7-eabihf--glibc--stable-2020.08-1/bin/arm-linux-gcc \
  -shared -fPIC -O2 -Wall -Wextra -Werror \
  -o source/ui/libuiobserve.so source/ui/ui-observe.c -ldl -pthread
```

可以额外核对只读参考：

```bash
python3 -B scripts/relocate-ui.py --check \
  --reference ../a7m3-qemu/work/usr/lib
```

`--reference` 检查 A7M3 `libObj.so` 身份及六个 RTTI 对应；它不是所有函数的生产差分测试。正常运行不依赖参考固件。`--rewrite` 仅供将固定逐项映射应用到新复制的参考源码／测试，**不能对已迁移目录重复应用，也不属于启动流程**。

主启动器在启动前将 `prepare-ui-profile.py` 应用于运行副本，随后编译 observer、打包外部 initramfs。不要在运行期间重写正在使用的运行副本。内核、QEMU、initramfs、host Camera、窗口与退出由主线集成，本目录不启动 VM。

## 输入身份与改动边界

| 原始文件 | SHA256 |
| --- | --- |
| `libObj.so` | `a05b335ef505cc830d1f7fbead792eca4e77dbdb4e642d2225bd9983201ddfa8` |
| `viewUnified2.so` | `236532d4434ceaf5b575aca284fbdca99c8bb4cf2eea638c3f2064feb3182d77` |
| `libIMDB.so` | `51a724171774d443504ca08d25c6e2d329450cc4b1002b3b13b06711d1263516` |

`relocate-ui.py --check` 在解释地址前拒绝错误摘要、非 ARM32 或非小端 ELF。运行库另核对 WidgetSystem 导出偏移、14 个原始八字节 hook 前导及 RM 十二字节前导，再安装冷 hook。原始 `work/usr/` 不修改；代码加载后的替换只发生在 guest 进程中。

IMDB 导出 `imdb_raw=0xe2a4`，`qemu` 目标在 `base+12`，表从 `base+0x84` 开始，每项 `0x2c` 字节，211 项后遇到 kind 40。AP-only 副本只清下列 10 项的 `targets & 2`，共改变 10 字节，保留其余 target 位，保留 `appFw.so`、`libgrm.so`、`libuxengine.so`：

- `/usr/kmod/liro.ko`
- `libUsbBusPower.so`、`libInfraUsbCmn.so`、`libsensapi.so`
- `libUsbControl.so`、`libBusPower.so`、`libHotplug.so`
- `libTetheringResource.so`、`libNetServiceTethering.so`
- `libInfraMediaPwrMgr.so`

读回的副本 SHA256 为 `b3bca8050d524ee9445f6ee2ae967d0e735e48471d908e178134daa20790cb4a`。原始 SHA、表结构、排除集合、保留集合、改变范围任一不符即拒绝。

## 地址如何确定

固定表共 **51 项：33 个代码、12 个数据、6 个视图位置**，见 [relocate-ui.py](../../scripts/relocate-ui.py) 的 `CODE`、`DATA`、`VIEWS`。这不是统一 text/BSS delta：例如绘图边界 `0x5e8490→0x6196f8`，Bitmap 读锁 `0x668589→0x69b8f9`，显示更新 `0x6bf350→0x6fb360` 的差值不同。

两个代码锚点可直接由 `.dynsym` 核对：`WidgetSystem::sys_getInstance=0x617025`、`GRM_bitmapGetPhysicalAddress=0x684e65`。其余定位先用 Thumb 指令形状／屏蔽 PC 与分支位移的签名找候选，再核对实际前导、调用关系、RTTI 或 PC/GOT 引用。短签名仅用于发现，不单独证明函数语义或运行成功。

六个图形 vptr 按原 RTTI 名称分别核对，包括 BitmapImpl、WindowImpl、PlaneTextureMusashi、两个 GraphicsContext 与 RenderTargetOGL。Bitmap 的原 `+0x44`／`+0x48` 槽分别指向 `0x69b8f9`／`0x69b295`。

| 全局项 | A7C 地址 | 独立原引用 |
| --- | --- | --- |
| graphics singleton pointer | `0x1457cf8` | `u32(0x63d258)+0x63d236` |
| DisplayManager | `0x1458220` | `u32(u32(0x6f512c)+0x6f50f0+u32(0x6f5134))` |
| 完成回调槽 | `0x1458cf0` | `u32(0x6fb0d4)+0x6fb0b6` |
| 完成参数槽 | `0x1458ce8` | `u32(0x6fb0d8)+0x6fb0be` |
| 完成信号量槽 | `0x1458cf4` | `u32(0x6fb3dc)+0x6fb37e` |
| pViewManager | `0x148d34c` | 同名导出 |

各条代码字节、literal 地址、原 word、PC/GOT 运算和结果已保存到证据的 `global_reference_pins`。代码调用点的原始 16 字节保存于 `callable_prefixes`。

`glFlush` 与 `glFinish` 的前 384 字节在屏蔽调用位移后仍可相同，不能据此任选。采用的 `glFinish=0x7c0e31` 在 `+0xf2` 实际 BL 到 `0x7a6570`，其 `0x7a6592` 原指令 `012331460093` 将 wait=1 放入栈参数；另一个候选走 wait=0 分支。

14 个冷 hook 的八字节前导均按完整 Thumb 指令边界核对。只有 draw 和 engine-wait 两个前导复制到 trampoline，它们没有 PC 相关读取或控制流转移。RM executor `0x775360` 的十二字节前导在 `+6` 有 literal LDR；原 literal 为 `0xc5da16`，复制后移到 trampoline `+20`，跳回原 `+12|1`。未知前导或结构拒绝安装。

## 原主页面与菜单接口

| 项目 | A7C 位置／契约 | 静态证据 |
| --- | --- | --- |
| RootSelector factory | `0x3ef9b9`，原分配 `0x184` 字节 | 同名导出、原指令 |
| RootSelector 主 vptr | `0xb17ce0` | RTTI `16ViewRootSelector`、offset-to-top 0 |
| 菜单子对象 vptr | `0xb17f10`，对象偏移 `+0x154` | 同 RTTI、offset-to-top `-0x154` |
| Root vptr | `0xb160c0` | RTTI `8ViewRoot` |
| STLREC vptr | `0xb128f8` | RTTI `10ViewStlrec` |
| 原菜单 helper | `0x42fa23` | 与 ZV-E10 `0x47de27` 的原 body、64b guard、原虚调用核对 |
| 原 Wi-Fi guard | `0x4a4525` | 导出 `CmnForUseMultipleViewStatus::isWiFiMode` |
| 原输入 callback | `libObj+0x11fc81` | 原导出 `InputService::callback_convert` |

A7M3 的 `RootSelector+0x124` 与菜单 helper 契约不同，不能只替换地址。主会话独立核对两处原 registration 和 89 项 view ABI 后，当前源在原 UI draw 线程使用 numeric `openView(int,int,bool)` 请求 ROOT `0x9c`，待原 manager 创建后请求 STLREC `0xbf`；MENU 发送原按下／释放，再由同 UI 线程调度 A7C 的菜单 helper。确认走原 callback，返回使用 numeric `closeView(int)` 依次关闭 Setting `0xb6`、Global `0x58`、Base `0x11`，再用原 `openView(0xbf,0,false)` 恢复拍摄页。A7M3 的旧 `0xba/0x5a` 在 A7C 指向别的页面。最终生命周期与像素以主线原 AP 实跑核定，不能声称完整硬件输入路由已恢复。

早期参考移植曾调用 A7C `0x4a43a5`：只有 setter 形状和相邻导出的 `getHalfShutterRelease` 对应，独立 boolean 未命名。主会话已撤回该额外写入；保留实际按下／释放、原 Wi-Fi guard 和原菜单 helper 的 `isInhOn` 分支。形状相同不提升为该 boolean 的业务语义或 MENU 前置完成证据。

## A7C 原输入表

主会话独立重读 `getConfigInputTable` 的 GOT 链、12 B 注册行、`SetEventKeyList` 复制和原 encoder 的 `+4` base 输出，核对 9 个具名键及 8 个指令窗口。实际控制使用 A7C 的表，不沿用参考工程的键码：

| 按键 | physical ID | application base | 原 callback 按下／释放 |
| --- | --- | --- | --- |
| ENTER | `0x1ac` | `0x15010040` | `0x15010041 / 0x15010042` |
| MENU | `0x1ab` | `0x150100f0` | `0x150100f1 / 0x150100f2` |
| DISP | `0x1f9` | `0x15010180` | `0x15010181 / 0x15010182` |

旧 `0x15010060` 实为 DOWN，旧 `0x15010110` 实为 AF/MF；具名字符串表的 ordinal 也不能编码 application base。`0x15010120` 已有 AEL 原行反证，只作为被否定的候选，从未接到 guest。`validation/input-abi.json` 记录原表和原 bytes；`relocate-ui.py` 同时校验相关行。历史轮原图不变，旧键码语义修正与后继真键码验收分开记录。

## 绘图、完成通知与取帧

原请求进入软件 DMP fill/blit、Gemini solid/texture/quad、A8／RGBA4444、Sony LZ77、整面 clear 与 present。后端验证尺寸、格式、当前 GL/target、metadata 稳定性、边界与别名；未知格式和未支持的 line／局部非线性绘图仍拒绝。

先执行原同步 finish，再在 Bitmap 原读锁下复制私有像素；显示更新使用原信号量和原完成函数 `0x6fb08d` 释放 gate、引用及 manager 锁。私有 snapshot pin 后发布真实 PFN、尺寸与 FNV，保留上一完整 snapshot；host 按完成记录暂停 QEMU、读取 PFN 并核摘要。该数据路径用真实消费与完成通知闭合，不把 DMA 空成功作为绘图实现。

## 原 AP 的 144→448 缩放与修复

主线 v2/v3 原 AP 已加载 bootin/im、完成模块加载并生成 frame5，随后遇到原 RECT `sr={28,0,144,28}`、`dr={28,0,448,28}`、filter `0x00010001`。旧 backend 只接受 1:1，真实拒绝并由主线正常 QMP quit 保全；原失败不回填为成功。

原 A7C `0x848260` 从第五参数的四个 s16 生成 UV、第六参数的四个 s16 生成目标顶点，确认这是横向缩放。原 sampler 函数 `0x8492c4` 经 `0x84caa0(T,param)` 读取参数：

| 原参数 | 对象位置 | 原 GL 目标／转换 |
| --- | --- | --- |
| param0 | `T+0x34` | 无 mip 时 MIN `0x2801`，经 `0x84bf14` |
| param1 | `T+0x36` | MAG `0x2800`，经 `0x84bf14` |
| param2 | `T+0x38` | mip MIN；max-mip 非零在本后端拒绝 |
| param3 | `T+0x3a` | U wrap `0x2802`，经 `0x84bf8c` |
| param4 | `T+0x3c` | V wrap `0x2803`，经 `0x84bf8c` |

`0x84932e→0x84caa0(T,1)→0x84bf14` 的 literal `u32(0x84bf4c)+0x84bf3c` 指向原表 `0x1022c68={0x2600,0x2601}`，因此 0=NEAREST、1=LINEAR。原 wrap 表 `0x1022c14={0x812f,0x8370,0x2901,0x812f}` 确认 0/3=CLAMP_TO_EDGE、1=MIRRORED_REPEAT、2=REPEAT；mip 表 `0x1022c24` 则为四个 `0x270x`。`T+0x18` 为 max mip，原 vtable `+0x4c` getter 从这里读取。

修复实际实现四邻点双线性：目标像素中心映射到原 UV，对 `u*allocation_width-0.5`／`v*allocation_height-0.5` 周围四个 texel 插值，之后处理原 texture*color／A8 tint、blend 和写掩码。atlas 子矩形边界不错误地当作 texture 边界；padded allocation 的邻点可参与插值，wrap 施加到完整 texture extent。源／目的 Morton 仍走已验布局，采样跨度和别名检查包含 padding，原 finish→读锁→消费→解锁／释放顺序保留。

`test-a7c-gemini.c`、`test-a7c-gemini-backend.c`、新增 `test-a7c-gemini-filter.c` 各执行普通 O2 与 ASan/UBSan 两配置，六次均通过；ARM observer 重新 `-Werror` 构建通过。覆盖四邻点 RGBA/A8、MIN/MAG 选择、atlas 邻点、padding、四种 wrap、真实 144→448 几何、Morton、原 lease 生命周期和中途 sampler 变化拒绝。源码、ARM 摘要、测试输出及原 enum bytes 见 JSON 的 `sampler_fix`；顶层早期构建与测试继续保留为 baseline。

Sony GPU 子 nibble 插值精度尚未逐像素对照。修复后原 AP 的实际内容消费由主线随后实跑判定，不用 host 测试回填 v2/v3。

## 已执行的检查与缺口

| 层次 | 实际结果 | 边界 |
| --- | --- | --- |
| 原 ELF 静态 | 三份固定 SHA、14 hooks、RM literal、RTTI、五独立全局引用通过 | 不是 guest 消费 |
| ARM observer 首版 | `-O2 -Wall -Wextra -Werror` 通过，58,192 B | 顶层 JSON 保留首版摘要 |
| 缩放修复版 | 3 个相关 C 程序 × 普通／ASanUBSan 六次通过，ARM 重建通过 | 当前摘要与输出见 `sampler_fix` |
| 8 个 C 程序 | 全部编译、退出 0 | 七个有实际 host 覆盖；image-decode 因 fixture 缺失整项 skip |
| LZ77 | 原始记录、literal、全部 16 长度、截断、越界等前置合成用例执行 | 原 border/icon 及其后测试段 skip |
| IMDB 离线 | 2 tests 通过，含 10 字节范围、原位保留、三处改字节／已改副本拒绝 | 不启动 AP |
| ELF／Thumb guard | 6 tests 通过，含错误 ELF、截断 Thumb32、PC-relative 和 BL 拒绝 | 不执行 Sony 代码 |
| 原 AP 主页面／菜单 | 本工作项未执行 | 由主线综合验收保存原像素、输入与 QMP 退出 |

[JSON](../../validation/ui-relocation.json) 保留编译／测试输出、skip 原文、原代码字节和冻结源码摘要，不回填运行结果。当前不扩展 CMOS、镜头、CP、拍照录像或物理 ASIC 一致性。

证据链为：原 ELF 身份与独立引用 → 固定源码／运行 ABI → 原 bootin/im → 原页面与原绘图请求 → 软件后端数据消费 → 原完成通知 → 私有像素快照 → 主线实际主页面及 MENU 验收。最后一段只有实际运行内容齐备后才可提升。
