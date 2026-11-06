#ifndef UI_FONT_PROBE_H
#define UI_FONT_PROBE_H
/* Native font rasterization stays in the firmware; only its GL clear needs software. */
#define FONT_PROBE_HOOKS \
    {0x7c9ca0, {0x2d,0xe9,0xf0,0x4f,0x2d,0xed,0x2,0x8b}, software_slow_clear, NULL}
#endif
