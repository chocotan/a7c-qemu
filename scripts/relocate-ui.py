#!/usr/bin/env python3
"""Fixed ILCE-7C 2.03 UI ABI, checked against the original firmware ELFs.

--check validates A7C identity, native references, hooks and trampoline safety.
--reference optionally compares the A7M3 4.04 reference ELFs as well.
--rewrite applies only the explicitly verified map to copied source/test files.
"""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = {
    'libObj.so': 'a05b335ef505cc830d1f7fbead792eca4e77dbdb4e642d2225bd9983201ddfa8',
    'viewUnified2.so': '236532d4434ceaf5b575aca284fbdca99c8bb4cf2eea638c3f2064feb3182d77',
    'libIMDB.so': '51a724171774d443504ca08d25c6e2d329450cc4b1002b3b13b06711d1263516',
}
# A7M3 -> A7C; independent function/RTTI/native-reference matches, not a section delta.
CODE = {
    0x5e5dc0: 0x617024, 0x5e8490: 0x6196f8,
    0x799790: 0x7d5cb0, 0x7997b0: 0x7d5cd0,
    0x7997d0: 0x7d5cf0, 0x799860: 0x7d5d80,
    0x73a100: 0x774ff0, 0x73a330: 0x775220,
    0x73a470: 0x775360, 0x73bce0: 0x776bd0,
    0x6bf350: 0x6fb360, 0x60ec64: 0x63e1b0,
    0x80ad58: 0x848578, 0x80aa40: 0x848260,
    0x80a758: 0x847f78, 0x80aedc: 0x8486fc,
    0x78d780: 0x7c9ca0,
    0x669dcd: 0x69d13d, 0x64f9b9: 0x684e65,
    0x668589: 0x69b8f9, 0x667f25: 0x69b295,
    0x6badbb: 0x6f6dcb, 0x6bf07d: 0x6fb08d,
    0x77f711: 0x7bbc31, 0x77f721: 0x7bbc41,
    0x77f7c1: 0x7bbce1, 0x77f801: 0x7bbd21,
    0x784911: 0x7c0e31, 0x755a71: 0x791f91,
    0x825349: 0x862b69, 0x826169: 0x863989,
    0x82617b: 0x86399b, 0x6158e1: 0x644e31,
}
DATA = {
    0x124e600: 0x13b5700, 0x124f9b0: 0x13b6f40,
    0x1252f90: 0x13ba2b0, 0x1253120: 0x13ba440,
    0x1253398: 0x13ba6b8, 0x12537f8: 0x13bab18,
    0x12f3394: 0x1457cf8, 0x12f38b8: 0x1458220,
    0x12f4380: 0x1458ce8, 0x12f4388: 0x1458cf0,
    0x12f438c: 0x1458cf4, 0x13289f4: 0x148d34c,
}
VIEWS = {
    0x2839a4: 0x3ef9b8, 0x87d738: 0xb17ce0, 0x87d930: 0xb17f10,
    0x87ba90: 0xb160c0, 0x878328: 0xb128f8, 0x2bcfe1: 0x42fa23,
}
MAP = CODE | DATA | VIEWS
RTTI = {
    0x13b5700: 'N3grm3bmp10BitmapImplE',
    0x13b6f40: 'N9dmpNative10WindowImplE',
    0x13ba2b0: 'N6gemini19PlaneTextureMusashiE',
    0x13ba440: 'N6gemini30GraphicsContext3DShaderMusashiE',
    0x13ba6b8: 'N6gemini24GraphicsContext3DMusashiE',
    0x13bab18: 'N6gemini15RenderTargetOGLE',
}


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


class Elf:
    def __init__(self, path, expected=None):
        from elftools.elf.elffile import ELFFile
        self.path = Path(path)
        self.raw = self.path.read_bytes()
        self.sha256 = hashlib.sha256(self.raw).hexdigest()
        if expected is not None:
            require(self.sha256 == expected, f'unsupported original ELF: {self.path}')
        self.elf = ELFFile(BytesIO(self.raw))
        require(self.elf.elfclass == 32 and self.elf['e_machine'] == 'EM_ARM' and
                self.elf.little_endian, f'expected little-endian ARM32 ELF: {self.path}')
        self.sections = list(self.elf.iter_sections())

    def read(self, address, size):
        for section in self.sections:
            if (section['sh_type'] != 'SHT_NOBITS' and section['sh_addr'] <= address and
                    address + size <= section['sh_addr'] + section['sh_size']):
                offset = section['sh_offset'] + address - section['sh_addr']
                return self.raw[offset:offset + size]
        raise ValueError(f'unbacked VA {address:#x}')

    def u32(self, address):
        return struct.unpack('<I', self.read(address, 4))[0]

    def typename(self, vptr):
        typeinfo = self.u32(vptr - 4)
        address = self.u32(typeinfo + 4)
        return self.read(address, 100).split(b'\0', 1)[0].decode('ascii')

    def symbols(self):
        return {s.name: s['st_value'] for s in self.elf.get_section_by_name('.dynsym').iter_symbols()
                if s['st_value']}


def thumb_instructions(raw, address, copied=False):
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_GRP_JUMP, CS_GRP_CALL, CS_GRP_RET
    from capstone.arm import ARM_OP_MEM, ARM_OP_REG, ARM_REG_PC
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    md.detail = True
    instructions = list(md.disasm(raw, address))
    require(sum(i.size for i in instructions) == len(raw), f'split Thumb prefix at {address:#x}')
    if copied:
        for instruction in instructions:
            require(not any(group in instruction.groups for group in
                            (CS_GRP_JUMP, CS_GRP_CALL, CS_GRP_RET)), 'control flow in copied prefix')
            require(not any((op.type == ARM_OP_MEM and op.mem.base == ARM_REG_PC) or
                            (op.type == ARM_OP_REG and op.reg == ARM_REG_PC)
                            for op in instruction.operands), 'PC-relative copied prefix')
    return [i.mnemonic + ' ' + i.op_str for i in instructions]


def check(target, reference=None):
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
    objects = {name: Elf(target / name, digest) for name, digest in IDENTITY.items()}
    obj, views = objects['libObj.so'], objects['viewUnified2.so']
    symbols = obj.symbols()
    require(symbols['_ZN2ux6wgtsys12WidgetSystem15sys_getInstanceEv'] == 0x617025, 'WidgetSystem anchor')
    require(symbols['GRM_bitmapGetPhysicalAddress'] == 0x684e65, 'physical getter anchor')
    require(symbols['pViewManager'] == 0x148d34c, 'pViewManager anchor')
    require(symbols['_ZN12InputService16callback_convertEiP16_InfraInputEvent'] == 0x11fc81,
            'native input callback')
    require(symbols['_ZN8ViewBase8openViewEiib'] == 0x1392e1, 'numeric view open')
    require(symbols['_ZN8ViewBase9closeViewEi'] == 0x139339, 'numeric view close')
    navigation = {
        'root': (0x9c, 0x4173f2), 'stlrec': (0xbf, 0x417c58),
        'base_menu': (0x11, 0x41692a), 'global_menu': (0x58, 0x416eb6),
        'setting_menu': (0xb6, 0x4175fa),
    }
    for name, (view_id, address) in navigation.items():
        require(views.read(address, 2) == struct.pack('<H', 0x2100 | view_id),
                f'native view registration {name}')
    input_keys = {
        'enter': (0x1ac, 0xb9e150, 0x15010040),
        'menu': (0x1ab, 0xb9e3fc, 0x150100f0),
        'disp': (0x1f9, 0xb9e48c, 0x15010180),
        'down': (0x30, 0xb9df38, 0x15010060),
    }
    require(views.u32(0xb8d628) == 0xb9dbbc, 'original input registry GOT')
    for name, (key, address, base) in input_keys.items():
        require(views.read(address, 12) == struct.pack('<3I', key, base, 0x7ffffffe),
                f'original input mapping {name}')
    for vptr, name in RTTI.items():
        require(obj.typename(vptr) == name and obj.u32(vptr - 8) == 0, f'RTTI {vptr:#x}')
    for vptr, name, offset in [(0xb17ce0, '16ViewRootSelector', 0),
                              (0xb17f10, '16ViewRootSelector', -0x154),
                              (0xb160c0, '8ViewRoot', 0), (0xb128f8, '10ViewStlrec', 0)]:
        require(views.typename(vptr) == name and views.u32(vptr - 8) == offset & 0xffffffff,
                f'view RTTI {vptr:#x}')
    require(views.symbols()['ViewRootSelectorToInstance'] == 0x3ef9b9, 'RootSelector factory')
    require(views.symbols()['_ZN27CmnForUseMultipleViewStatus10isWiFiModeEv'] == 0x4a4525,
            'native Wi-Fi guard')
    # Original PC-relative instructions and GOT, independently derived for each global.
    pins = [
        ('graphics', (obj.u32(0x63d258) + 0x63d236) & 0xffffffff, 0x1457cf8),
        ('DisplayManager', obj.u32(obj.u32(0x6f512c) + 0x6f50f0 + obj.u32(0x6f5134)), 0x1458220),
        ('completion_callback', obj.u32(0x6fb0d4) + 0x6fb0b6, 0x1458cf0),
        ('completion_argument', obj.u32(0x6fb0d8) + 0x6fb0be, 0x1458ce8),
        ('completion_semaphore', obj.u32(0x6fb3dc) + 0x6fb37e, 0x1458cf4),
        ('Bitmap.read', obj.u32(0x13b5700 + 0x44), 0x69b8f9),
        ('Bitmap.unlock', obj.u32(0x13b5700 + 0x48), 0x69b295),
    ]
    for name, actual, expected in pins:
        require(actual == expected, f'native reference {name}: {actual:#x} != {expected:#x}')
    # glFlush has the same prefix as glFinish: the real wait=1 callee distinguishes them.
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    finish_call = list(md.disasm(obj.read(0x7c0e30 + 0xf2, 4), 0x7c0e30 + 0xf2))
    require(len(finish_call) == 1 and finish_call[0].mnemonic == 'bl' and
            finish_call[0].op_str == '#0x7a6570', 'glFinish wait=1 call')
    require(obj.read(0x7a6592, 6) == bytes.fromhex('012331460093'), 'glFinish wait flag')
    source = '\n'.join((ROOT / 'source/ui' / name).read_text() for name in
                       ('ui-observe.c', 'ui-draw-probe.h', 'ui-font-probe.h'))
    pattern = r'\{(0x[0-9a-f]+),\s*\{((?:\s*0x[0-9a-f]+,?){8})\},\s*([^,]+),\s*([^}]+)\}'
    hooks = []
    for match in re.finditer(pattern, source):
        address = int(match[1], 16)
        raw = bytes(int(s, 16) for s in re.findall(r'0x[0-9a-f]+', match[2]))
        require(address % 4 == 0 and obj.read(address, 8) == raw, f'hook prologue {address:#x}')
        copied = match[4].strip() != 'NULL'
        instructions = thumb_instructions(raw, address, copied)
        hooks.append({'address': hex(address), 'replacement': match[3].strip(), 'prologue': raw.hex(),
                      'copies_to_trampoline': copied, 'instructions': instructions})
    require(len(hooks) == 14, 'expected fourteen cold UI hooks')
    address = 0x775360
    prefix = bytes.fromhex('2de9f04f87b0c64d04af0446')
    require(obj.read(address, 12) == prefix, 'RM executor prefix')
    thumb_instructions(prefix[:6], address, True)
    thumb_instructions(prefix[8:], address + 8, True)
    load = struct.unpack_from('<H', prefix, 6)[0]
    require(load & 0xf800 == 0x4800, 'RM literal LDR at +6')
    literal = obj.u32(((address + 10) & ~3) + (load & 255) * 4)
    trampoline = bytearray(prefix + bytes.fromhex('dff800f0') + struct.pack('<II', (address + 12) | 1, literal))
    struct.pack_into('<H', trampoline, 6, (load & 0xff00) | 3)
    require(struct.unpack_from('<I', trampoline, 20)[0] == literal, 'RM relocated literal')
    reference_checked = False
    if reference is not None:
        old = Elf(reference / 'libObj.so', '1117453a969c9dedeb9bf6b006514fd9c2644a79085590a797189df109d64d23')
        for old_vptr, new_vptr in DATA.items():
            if new_vptr in RTTI:
                require(old.typename(old_vptr) == obj.typename(new_vptr), 'reference RTTI')
        reference_checked = True
    return {
        'status': 'static A7C ELF/native-reference/prologue/trampoline checks passed',
        'runtime_verified': False, 'original_main_verified': False, 'original_menu_verified': False,
        'capture_verified': False,
        'sha256': {name: elf.sha256 for name, elf in objects.items()},
        'code_entries': len(CODE), 'data_entries': len(DATA), 'view_entries': len(VIEWS),
        'reference_checked': reference_checked,
        'numeric_navigation': {name: {'id': hex(view_id), 'registration_immediate': hex(address)}
                               for name, (view_id, address) in navigation.items()},
        'input_keys': {name: {'physical_key': hex(key), 'mapping_row': hex(address), 'base': hex(base)}
                       for name, (key, address, base) in input_keys.items()},
        'map': {hex(k): hex(v) for k, v in sorted(MAP.items())},
        'native_references': [{'name': name, 'actual': hex(actual), 'expected': hex(expected)}
                              for name, actual, expected in pins],
        'rtti': {hex(k): v for k, v in RTTI.items()}, 'root_menu_subobject': '0x154',
        'hooks': hooks,
        'callable_prefixes': {hex(address): obj.read(address & ~1, 16).hex() for address in CODE.values()},
        'menu_helper': {'address': '0x42fa23', 'bytes': views.read(0x42fa22, 92).hex()},
        'rm_trampoline': {'address': hex(address), 'literal': hex(literal), 'bytes': trampoline.hex()},
    }


def rewrite(path):
    original = path.read_text()
    updated = re.sub(r'0x[0-9a-fA-F]+', lambda m: hex(MAP.get(int(m[0], 16), int(m[0], 16))), original)
    if original != updated:
        path.write_text(updated)
    return {'file': str(path), 'changed': original != updated}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--target', type=Path, default=ROOT / 'work/usr/lib')
    parser.add_argument('--reference', type=Path, help='optional A7M3 4.04 original library directory')
    parser.add_argument('--rewrite', type=Path, nargs='+', default=[])
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = check(args.target, args.reference) if args.check else {'map': {hex(k): hex(v) for k, v in MAP.items()}}
    if args.rewrite:
        result['rewritten'] = [rewrite(path) for path in args.rewrite]
    output = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.write_text(output)
    else:
        print(output, end='')


if __name__ == '__main__':
    main()
