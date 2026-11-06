#!/usr/bin/env python3
"""Build the A7C 2.03 AP-only qemu IMDB copy without changing the original ELF."""
from io import BytesIO
from pathlib import Path
import hashlib
import json
import struct
from elftools.elf.elffile import ELFFile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = '51a724171774d443504ca08d25c6e2d329450cc4b1002b3b13b06711d1263516'
EXCLUDE = {
    'libUsbBusPower.so', 'libInfraUsbCmn.so', 'libsensapi.so', 'libUsbControl.so',
    'libBusPower.so', 'libHotplug.so', 'libInfraMediaPwrMgr.so', '/usr/kmod/liro.ko',
    'libNetServiceTethering.so', 'libTetheringResource.so',
}


def prepare(raw):
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError('unsupported original A7C 2.03 IMDB SHA256')
    elf = ELFFile(BytesIO(raw))
    if elf.elfclass != 32 or elf['e_machine'] != 'EM_ARM' or not elf.little_endian:
        raise ValueError('expected little-endian ARM32 IMDB')

    def offset(address):
        for segment in elf.iter_segments():
            if (segment['p_type'] == 'PT_LOAD' and segment['p_vaddr'] <= address <
                    segment['p_vaddr'] + segment['p_filesz']):
                return segment['p_offset'] + address - segment['p_vaddr']
        raise ValueError(f'unmapped IMDB address: {address:#x}')

    def string(address):
        start = offset(address)
        return raw[start:raw.index(b'\0', start)].decode('ascii')

    base = next(s['st_value'] for s in elf.get_section_by_name('.dynsym').iter_symbols()
                if s.name == 'imdb_raw')
    if base != 0xe2a4 or string(struct.unpack_from('<I', raw, offset(base + 12))[0]) != 'qemu':
        raise ValueError('unsupported IMDB target/table layout')
    result = bytearray(raw)
    changed, retained = [], set()
    for index in range(300):
        at = offset(base + 0x84 + index * 0x2c)
        kind, phase, targets, identity, pointer = struct.unpack_from('<5I', raw, at)
        if kind == 40:
            break
        name = string(pointer)
        if name in EXCLUDE:
            if not targets & 2:
                raise ValueError(f'{name} has no qemu target')
            struct.pack_into('<I', result, at + 8, targets & ~2)
            changed.append({'name': name, 'file_offset': at + 8, 'before': targets, 'after': targets & ~2})
        if name in {'appFw.so', 'libgrm.so', 'libuxengine.so'} and targets & 2:
            retained.add(name)
    else:
        raise ValueError('missing IMDB terminator')
    if ({c['name'] for c in changed} != EXCLUDE or len(changed) != len(EXCLUDE) or
            len(retained) != 3 or sum(a != b for a, b in zip(raw, result)) != len(EXCLUDE)):
        raise ValueError('incomplete or excessive AP-only target selection')
    return bytes(result), {'source_sha256': SOURCE_SHA256, 'imdb_raw': hex(base),
                           'records': index, 'changed': changed, 'retained': sorted(retained)}


def main():
    source = ROOT / 'work/usr/lib/libIMDB.so'
    destination = ROOT / 'work/initramfs-ui/usr/lib/libIMDB.so'
    data, evidence = prepare(source.read_bytes())
    destination.chmod(destination.stat().st_mode | 0o200)
    destination.write_bytes(data)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    if digest != hashlib.sha256(data).hexdigest():
        raise RuntimeError('AP-only IMDB readback mismatch')
    evidence['destination_sha256'] = digest
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
