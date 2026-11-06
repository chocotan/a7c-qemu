#include <assert.h>
#include <stdio.h>
#include "../source/qemu/hw/arm/a7c-gpe-init.h"

int main(void)
{
    uint32_t packet[8] = {0x0116f000, 0x02056db0, 0x0117f000, 1,
                          0x0044f000, 0, 0x0010f000, 0x12345678};
    assert(a7c_gpe_init_packet(packet));
    for (unsigned i = 0; i < 8; ++i) {
        if (i == 1) {
            continue;
        }
        packet[i] ^= 1;
        assert(!a7c_gpe_init_packet(packet));
        packet[i] ^= 1;
    }
    packet[1] = 0x02000000; assert(a7c_gpe_init_packet(packet));
    packet[1] = 0x027fffff; assert(a7c_gpe_init_packet(packet));
    packet[1] = 0x01ffffff; assert(!a7c_gpe_init_packet(packet));
    packet[1] = 0x02800000; assert(!a7c_gpe_init_packet(packet));
    packet[1] = 0; assert(!a7c_gpe_init_packet(packet));
    packet[1] = UINT32_MAX; assert(!a7c_gpe_init_packet(packet));
    puts("PASS: inherited startup fence and pointer boundaries accepted; unrelated packets rejected (14 checks)");
}
