# A7C QEMU 主页面与 MENU 验收范围

- auth：用户提供 `Update_ILCE7CV203.exe`，要求参考现有 ZV-E10／A7M3 在 `final/a7c-qemu` 开发；随后明确目标为“启动进入主页面，能进菜单”。
- in_scope：Sony ILCE-7C 2.03 官方开放源码全部下载、更新包离线提取、独立 QEMU／内核构建、原厂主页面和 MENU 的绘图／输入适配、本机窗口、自动截图、返回／重入和正常 QMP 退出。ENTER 映射与原提示保留为研究，真实窗口超时轮没有提升为稳定功能，首版只暴露 MENU／返回／刷新。
- storage：只使用本工程普通文件和生成的 initramfs；原固件与已下载的 Sony 源码归档保持不变。
- network_profile：下载 Sony 公开源码与原 notice；guest 使用 `-nic none`，仅本机 UART／QMP。
- out_of_scope：真机、物理 SD、刷机、完整 CMOS／镜头／AF、拍照录像、物理 ASIC 等价性。
- acceptance：必须实际启动 A7C 自己的原厂应用，看到主页面与 MENU 原生像素，保留原输入和帧摘要、正常关闭证据。静态映射、编译或空成功返回均不单独算运行通过。
