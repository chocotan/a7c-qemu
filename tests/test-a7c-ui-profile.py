#!/usr/bin/env python3
"""AP-only selection invariants; original firmware cases skip when unavailable."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('a7c_profile', ROOT / 'scripts/prepare-ui-profile.py')
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class ProfileTests(unittest.TestCase):
    def test_wrong_identity_is_rejected(self):
        for raw in (b'', b'\x7fELF' + b'\0' * 128, b'not an original A7C ELF'):
            with self.subTest(length=len(raw)), self.assertRaisesRegex(ValueError, 'SHA256'):
                profile.prepare(raw)

    def test_exact_qemu_bit_changes(self):
        source = ROOT / 'work/usr/lib/libIMDB.so'
        if not source.is_file():
            self.skipTest('requires original A7C 2.03 libIMDB.so')
        raw = source.read_bytes()
        updated, evidence = profile.prepare(raw)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), profile.SOURCE_SHA256)
        self.assertEqual(len(updated), len(raw))
        self.assertEqual(evidence['records'], 211)
        self.assertEqual(set(row['name'] for row in evidence['changed']), profile.EXCLUDE)
        self.assertEqual(len(evidence['changed']), 10)
        self.assertEqual(evidence['retained'], ['appFw.so', 'libgrm.so', 'libuxengine.so'])
        expected = bytearray(raw)
        for row in evidence['changed']:
            self.assertEqual(row['before'] & 2, 2)
            self.assertEqual(row['after'], row['before'] & ~2)
            self.assertEqual(row['before'] & 1, row['after'] & 1)
            struct.pack_into('<I', expected, row['file_offset'], row['after'])
        self.assertEqual(updated, bytes(expected))
        self.assertEqual(sum(a != b for a, b in zip(raw, updated)), 10)
        for offset in (0, len(raw) // 2, len(raw) - 1):
            changed = bytearray(raw)
            changed[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, 'SHA256'):
                profile.prepare(bytes(changed))
        with self.assertRaisesRegex(ValueError, 'SHA256'):
            profile.prepare(updated)


if __name__ == '__main__':
    unittest.main()
