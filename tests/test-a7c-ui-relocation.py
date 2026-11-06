#!/usr/bin/env python3
"""Static original-ELF and Thumb trampoline guard regressions."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('a7c_relocation', ROOT / 'scripts/relocate-ui.py')
relocation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relocation)


class RelocationTests(unittest.TestCase):
    def test_original_draw_prefix_is_relocatable(self):
        result = relocation.thumb_instructions(bytes.fromhex('b0b5044682b000af'), 0x6196f8, True)
        self.assertEqual(len(result), 4)

    def test_truncated_thumb32_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'split Thumb'):
            relocation.thumb_instructions(bytes.fromhex('2de9f0'), 0x775360, True)

    def test_pc_relative_copy_is_rejected(self):
        prefix = bytes.fromhex('034880b4784400af')
        with self.assertRaisesRegex(ValueError, 'PC-relative'):
            relocation.thumb_instructions(prefix, 0x7d5cb0, True)
        self.assertEqual(len(relocation.thumb_instructions(prefix, 0x7d5cb0)), 4)

    def test_branch_copy_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'control flow'):
            relocation.thumb_instructions(bytes.fromhex('00f000f8'), 0x1000, True)

    def test_wrong_elf_identity_is_rejected_before_parsing(self):
        with tempfile.TemporaryDirectory(prefix='a7c-elf-guard-') as directory:
            path = Path(directory) / 'libObj.so'
            path.write_bytes(b'wrong firmware')
            with self.assertRaisesRegex(ValueError, 'unsupported original ELF'):
                relocation.Elf(path, relocation.IDENTITY['libObj.so'])

    def test_original_a7c_elves(self):
        target = ROOT / 'work/usr/lib'
        if not all((target / name).is_file() for name in relocation.IDENTITY):
            self.skipTest('requires original A7C 2.03 ELF libraries')
        result = relocation.check(target)
        self.assertFalse(result['runtime_verified'])
        self.assertFalse(result['original_main_verified'])
        self.assertFalse(result['original_menu_verified'])
        self.assertEqual(result['code_entries'], 33)
        self.assertEqual(result['data_entries'], 12)
        self.assertEqual(len(result['hooks']), 14)
        self.assertEqual(sum(row['copies_to_trampoline'] for row in result['hooks']), 2)
        self.assertEqual(result['root_menu_subobject'], '0x154')


if __name__ == '__main__':
    unittest.main()
