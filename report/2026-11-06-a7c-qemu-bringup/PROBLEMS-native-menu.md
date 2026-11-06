
## 原菜单首次显示与局部清屏

- `output/20261106-225802/` 已实际生成原主页面 PNG，并经原 MENU 进入菜单构造；旧 `ui_range_clear_span` 随后因只允许整屏 614,400 字节而拒绝原局部 clear `[0x20312200,0x20341a00)`。
- 功能模型现在接受同一 type3、零 pattern、`0x0f100001` control、8 字节对齐、同图像地址域、最大一帧范围内的非空 exclusive-end 子区间；实际执行 `memset`，再让原 RM skip-hardware 分支执行原完成回调。未知 pattern／control、反向／零长／过大／越界仍拒绝。
- 普通和 ASan／UBSan 测试覆盖实际 194,560 字节 clear、最小对齐区间、整屏、未写周围字节及全部失败不写。
- `output/20261106-230054/` 的 `main.png`、`menu-before-confirm.png` 和 `menu.png` 已实际读回。六分类、标题、条目及数值可见；该轮在裸 `closeView` 后没有新提交帧，返回未通过，原 owner 正常 QMP quit，未将菜单成功推广为返回成功。
- 后继改为关闭真实菜单后使用原 `openView(0xbf,0,false)` 重新激活拍摄页；最终 `output/20261106-233800` 与真实窗口 `output/20261106-233844` 都已通过，返回和重入各自原像素一致，两个 QMP0。

## 实验确认键未纳入首版

原表已证明 ENTER=`0x15010040`、MENU=`0x150100f0`、DISP=`0x15010180`。旧 `0x15010060` 实为 DOWN，旧 `0x15010110` 实为 AF/MF；早期菜单显示成功来自原 helper，不能用它给旧 raw key 命名。修正后 `20261106-231746` 的真实 ENTER 显示原“当前功能无效”提示；`231835` 的 GUI 截图早于提示提交，不算 coherent；`232601` 的 GUI 等待超时，未采到后继帧和释放记录，实际等待点未核。源码与原日志保留，未完成的 idle-update 实验已撤回。首版窗口仅提供 MENU／返回／刷新，不把已知不稳定的确认控制暴露给用户。

## 串口 META 与半截 timestamp 交错

`20261106-233325` 原字节出现 `[   2UI_CAPTURE_META {"frame":15,...}`。旧 parser 把所有 `[` 开头的行当 timestamp echo 跳过，误丢原 META，随后拒绝 page 数量。现只跳过完整的内核 timestamp echo；JSON、layout、页数、index、指纹和真实重复页的拒绝均保留。回归同时覆盖半截前缀与完整 echo，并验证真正重复页仍拒绝。原运行在旧 logger 自己报错后中断，末帧没有 READY，离线复核只承认完整 5–14 帧，未把部分 15 帧记为成功。后继最终两轮均按原像素通过。
