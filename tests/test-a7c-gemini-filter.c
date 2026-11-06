#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../source/ui/ui-raster.h"
#include "../source/ui/ui-gemini-raster.h"

static const float identity[16]={1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1};
static const unsigned char white[4]={255,255,255,255};
static struct ui_gemini_state state(unsigned w,unsigned h)
{
    struct ui_gemini_state s={.viewport={0,0,(int16_t)w,(int16_t)h},.rgb_write=1,.alpha_write=1,
                              .sampler={.min_filter=1,.mag_filter=1}};
    return s;
}
static uint16_t get(const unsigned char *p,unsigned x,unsigned y,unsigned width)
{
    return ui_u16(p+((size_t)y*width+x)*2);
}
static void put(unsigned char *p,size_t offset,uint16_t value) { memcpy(p+offset,&value,2); }
static size_t morton(unsigned x,unsigned y,unsigned width,unsigned height,int bottom_up)
{
    if (bottom_up) y=height-1-y;
    size_t offset=((size_t)(y/8)*(width/8)+x/8)*64;
    for (unsigned bit=0;bit<3;++bit) {
        offset+=((x>>bit)&1)<<(2*bit);
        offset+=((y>>bit)&1)<<(2*bit+1);
    }
    return offset*2;
}

static void interpolation_and_filter_selection(void)
{
    uint16_t source[4]={0x000f,0xf00f,0x0f0f,0xff0f};
    unsigned char output[32];
    struct ui_gemini_surface src={(unsigned char *)source,sizeof source,2,2,4,0,0};
    struct ui_gemini_surface dst={output,sizeof output,4,4,8,0,0};
    struct ui_gemini_rect sr={0,0,2,2},dr={0,0,4,4};
    struct ui_gemini_state s=state(4,4);
    assert(!ui_gemini_rect(&dst,&src,&s,identity,white,&sr,&dr,UI_GEMINI_TEXTURE));
    const unsigned n[4]={0,4,11,15};
    for (unsigned y=0;y<4;++y) for (unsigned x=0;x<4;++x)
        assert(get(output,x,y,4)==(uint16_t)((n[x]<<12)|(n[y]<<8)|15));
    s.sampler.mag_filter=0;
    assert(!ui_gemini_rect(&dst,&src,&s,identity,white,&sr,&dr,UI_GEMINI_TEXTURE));
    assert(get(output,1,1,4)==0x000f && get(output,2,2,4)==0xff0f);
    dst.width=dst.height=1; dst.stride=2; dr.w=dr.h=1;
    assert(!ui_gemini_rect(&dst,&src,&s,identity,white,&sr,&dr,UI_GEMINI_TEXTURE));
    assert(get(output,0,0,1)==0x880f); /* minification uses MIN even with MAG=nearest */
    s.sampler.min_filter=0;
    assert(!ui_gemini_rect(&dst,&src,&s,identity,white,&sr,&dr,UI_GEMINI_TEXTURE));
    assert(get(output,0,0,1)==0xff0f);
}

static void atlas_padding_and_wrap(void)
{
    uint16_t source[4]={0x000f,0xf00f,0x0f0f,0x000f};
    unsigned char output[8];
    struct ui_gemini_surface src={(unsigned char *)source,sizeof source,4,1,8,0,0};
    struct ui_gemini_surface dst={output,sizeof output,4,1,8,0,0};
    struct ui_gemini_rect sr={1,0,2,1},dr={0,0,4,1};
    struct ui_gemini_state s=state(4,1);
    assert(!ui_gemini_rect(&dst,&src,&s,identity,white,&sr,&dr,UI_GEMINI_TEXTURE));
    assert(get(output,0,0,4)==0xb00f && get(output,3,0,4)==0x0b0f); /* sample outside atlas subrect */
    source[0]=0x000f; source[1]=0xf00f; source[2]=0x000f;
    src.width=2; s.sampler.width=4; s.sampler.height=1; sr.x=0;
    assert(!ui_gemini_rect(&dst,&src,&s,identity,white,&sr,&dr,UI_GEMINI_TEXTURE));
    assert(get(output,3,0,4)==0xb00f); /* padded texel2 participates, not logical-edge clamp */
    s.sampler.width=2;
    for (unsigned mode=0;mode<4;++mode) {
        s.sampler.wrap_u=mode;
        assert(!ui_gemini_rect(&dst,&src,&s,identity,white,&sr,&dr,UI_GEMINI_TEXTURE));
        assert(get(output,0,0,4)==(mode==2 ? 0x400f : 0x000f));
        assert(get(output,3,0,4)==(mode==2 ? 0xb00f : 0xf00f));
    }
}

static void alpha_and_tiled(void)
{
    unsigned char mask[64]={0}, output[32]; mask[1]=255;
    struct ui_gemini_surface src={mask,sizeof mask,2,1,8,3,UI_GEMINI_MORTON_TOP_DOWN};
    struct ui_gemini_surface dst={output,sizeof output,4,1,8,0,0};
    struct ui_gemini_state s=state(4,1);
    struct ui_gemini_rect sr={0,0,2,1},dr={0,0,4,1};
    const unsigned char tint[4]={255,0,0,128};
    memset(output,0,sizeof output); s.blend_enabled=1; s.blend=0x00170067;
    assert(!ui_gemini_rect(&dst,&src,&s,identity,tint,&sr,&dr,UI_GEMINI_ALPHA_MASK));
    const uint16_t expected[4]={0,0x2002,0x6006,0x8008};
    for (unsigned x=0;x<4;++x) assert(get(output,x,0,4)==expected[x]);
}

static void actual_144_to_448_geometry(void)
{
    enum { SW=192,SH=32,DW=640,DH=480 };
    unsigned char *input=malloc(SW*SH*2+4), *output=malloc(DW*DH*2+4);
    assert(input && output); memset(input,0x5a,SW*SH*2+4); memset(output,0,DW*DH*2+4);
    for (unsigned y=0;y<SH;++y) for (unsigned x=0;x<SW;++x)
        put(input+2,morton(x,y,SW,SH,0),(uint16_t)((x&1 ? 0xf000 : 0)|15));
    struct ui_gemini_surface src={input+2,SW*SH*2,SW,28,SW*2,0,UI_GEMINI_MORTON_TOP_DOWN};
    struct ui_gemini_surface dst={output+2,DW*DH*2,DW,DH,DW*2,0,UI_GEMINI_MORTON_BOTTOM_UP};
    struct ui_gemini_state s=state(DW,DH); s.sampler.width=SW; s.sampler.height=SH;
    struct ui_gemini_rect sr={28,0,144,28},dr={28,0,448,28};
    assert(!ui_gemini_rect(&dst,&src,&s,identity,white,&sr,&dr,UI_GEMINI_MULTIPLY));
    assert(ui_u16(output+2+morton(28,0,DW,DH,1))==0x500f);
    assert(ui_u16(output+2+morton(475,27,DW,DH,1))==0xa00f);
    assert(ui_u16(output+2+morton(27,0,DW,DH,1))==0);
    assert(ui_u16(output+2+morton(476,27,DW,DH,1))==0);
    assert(ui_u16(output+2+morton(28,28,DW,DH,1))==0);
    for (unsigned i=0;i<2;++i) assert(input[i]==0x5a && input[SW*SH*2+2+i]==0x5a);
    assert(!output[0] && !output[1] && !output[DW*DH*2+2] && !output[DW*DH*2+3]);
    free(input);free(output);
}

static void atomic_rejection(void)
{
    unsigned char source[32]={0}, output[32];
    struct ui_gemini_surface src={source,sizeof source,2,2,4,0,0};
    struct ui_gemini_surface dst={output,sizeof output,4,4,8,0,0};
    struct ui_gemini_state s=state(4,4);
    struct ui_gemini_rect sr={0,0,2,2},dr={0,0,4,4};
    memset(output,0x5a,sizeof output);
    for (unsigned which=0;which<5;++which) {
        s=state(4,4);
        if (which==0) s.sampler.min_filter=2;
        if (which==1) s.sampler.wrap_v=4;
        if (which==2) s.sampler.width=3;
        if (which==3) s.sampler.height=9;
        if (which==4) s.sampler.height=1;
        assert(ui_gemini_rect(&dst,&src,&s,identity,white,&sr,&dr,UI_GEMINI_TEXTURE)==-5);
        for (unsigned i=0;i<sizeof output;++i) assert(output[i]==0x5a);
    }
    src.width=src.height=1;src.stride=2;s=state(1,1);s.sampler.height=16;
    dst.pixels=source+8;dst.capacity=2;dst.width=dst.height=1;dst.stride=2;
    sr.w=sr.h=dr.w=dr.h=1;
    assert(ui_gemini_rect(&dst,&src,&s,identity,white,&sr,&dr,UI_GEMINI_TEXTURE)==-5);
    for (unsigned i=0;i<sizeof source;++i) assert(!source[i]); /* alias in padded allocation */
}

int main(void)
{
    (void)ui_fill;(void)ui_blit;(void)ui_surface;
    interpolation_and_filter_selection();atlas_padding_and_wrap();alpha_and_tiled();
    actual_144_to_448_geometry();atomic_rejection();
    puts("PASS: real bilinear RGBA/A8, min/mag, atlas neighbors, padding, clamp/mirror/repeat, actual 144->448 Morton geometry and atomic rejection");
    return 0;
}
