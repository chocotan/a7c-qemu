#!/usr/bin/env python3
"""Host checks for fixed update boundaries, preservation and filesystem readback."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'prepare_firmware', Path(__file__).resolve().parents[1] / 'scripts/prepare-firmware.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def fake_entry(path, mode, data=None):
    return SimpleNamespace(path=path, mode=mode, uid=os.getuid(), gid=os.getgid(),
                           mtime=1234567890, size=len(data) if data is not None else 0,
                           contents=io.BytesIO(data) if data is not None else None)


def application_tar(extra=()):
    stream = io.BytesIO()
    rows = [('0800_appli/setting', tarfile.DIRTYPE, None),
            ('0800_appli/setting/config', tarfile.REGTYPE, b'original setting'),
            ('0800_appli/tmp', tarfile.DIRTYPE, None),
            ('0800_appli/tmp/toprc', tarfile.REGTYPE, b'original tmp'),
            ('0800_appli/tmp/mtab', tarfile.SYMTYPE, '../proc/mounts'), *extra]
    with tarfile.open(fileobj=stream, mode='w') as archive:
        for name, kind, data in rows:
            member = tarfile.TarInfo(name)
            member.type, member.uid, member.gid = kind, os.getuid(), os.getgid()
            member.mode = 0o755 if kind != tarfile.SYMTYPE else 0o777
            if kind == tarfile.REGTYPE:
                member.size = len(data)
            elif kind == tarfile.SYMTYPE:
                member.linkname = data
            archive.addfile(member, io.BytesIO(data) if kind == tarfile.REGTYPE else None)
    stream.seek(0)
    return tarfile.open(fileobj=stream, mode='r:')


class UpdateExtraction(unittest.TestCase):
    def synthetic(self, root):
        cabinet = bytearray(40)
        cabinet[:4] = b'MSCF'
        struct.pack_into('<I', cabinet, 8, len(cabinet))
        source = root / 'update.exe'
        source.write_bytes(b'MZprefix' + bytes(value ^ 255 for value in cabinet) + b'footer')
        overrides = dict(EXE_SHA256=prepare.sha256(source), CAB_OFFSET=8,
                         CAB_SIZE=len(cabinet), CAB_SHA256=hashlib.sha256(cabinet).hexdigest(),
                         DAT_SHA256=hashlib.sha256(b'dat').hexdigest())
        return source, bytes(cabinet), overrides

    def test_digest_mismatch_writes_nothing_and_preserves_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'unexpected.exe'
            source.write_bytes(b'unsupported package')
            with self.assertRaisesRegex(ValueError, 'unsupported update'):
                prepare.extract_update(source, root / 'out')
            self.assertEqual(source.read_bytes(), b'unsupported package')
            self.assertFalse((root / 'out').exists())

    def test_exact_complemented_cab_and_dat_readback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, cabinet, overrides = self.synthetic(root)
            def extract(args, log, *, output):
                self.assertIn('-so', args)
                self.assertEqual(args[-1], prepare.DAT_NAME)
                output.write_bytes(b'dat')
            with patch.multiple(prepare, **overrides), patch.object(prepare, 'run', side_effect=extract):
                dat = prepare.extract_update(source, root / 'out')
            self.assertEqual(dat.read_bytes(), b'dat')
            self.assertEqual((root / 'out/payload.cab').read_bytes(), cabinet)
            self.assertEqual(prepare.sha256(source), overrides['EXE_SHA256'])

    def test_bad_dat_digest_preserves_original(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, _, overrides = self.synthetic(root)
            def extract(args, log, *, output):
                output.write_bytes(b'corrupt dat')
            with patch.multiple(prepare, **overrides), patch.object(prepare, 'run', side_effect=extract):
                with self.assertRaisesRegex(ValueError, 'DAT digest'):
                    prepare.extract_update(source, root / 'out')
            self.assertEqual(prepare.sha256(source), overrides['EXE_SHA256'])
            self.assertEqual((root / 'out/cab' / prepare.DAT_NAME).read_bytes(), b'corrupt dat')

    def test_existing_extraction_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, _, overrides = self.synthetic(root)
            (root / 'out').mkdir()
            (root / 'out/payload.cab').write_bytes(b'keep')
            with patch.multiple(prepare, **overrides), patch.object(prepare, 'run') as command:
                with self.assertRaises(FileExistsError):
                    prepare.extract_update(source, root / 'out')
                command.assert_not_called()
            self.assertEqual((root / 'out/payload.cab').read_bytes(), b'keep')

    def test_missing_and_short_cab_headers(self):
        for raw, error in [(b'no CAB', 'missing complemented'),
                           (bytes(value ^ 255 for value in b'MSCF'), 'truncated CAB header')]:
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, error):
                prepare.decode_cab(raw)

    def test_cab_lengths_and_boundary_rejected(self):
        for size in (0, 35, 4096):
            header = bytearray(36)
            header[:4] = b'MSCF'
            struct.pack_into('<I', header, 8, size)
            with self.subTest(size=size), self.assertRaisesRegex(ValueError, 'truncated CAB payload'):
                prepare.decode_cab(bytes(value ^ 255 for value in header))
        with tempfile.TemporaryDirectory() as temp:
            source, _, overrides = self.synthetic(Path(temp))
            with patch.multiple(prepare, **overrides):
                with self.assertRaisesRegex(ValueError, 'boundary'):
                    prepare.decode_cab(b'extra-prefix' + source.read_bytes())
                with self.assertRaisesRegex(ValueError, 'boundary'):
                    prepare.decode_cab(source.read_bytes() + bytes(value ^ 255 for value in b'MSCF'))

    def test_cab_digest_is_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            source, _, overrides = self.synthetic(Path(temp))
            raw = bytearray(source.read_bytes())
            raw[44] ^= 1
            with patch.multiple(prepare, **overrides), self.assertRaisesRegex(ValueError, 'CAB digest'):
                prepare.decode_cab(raw)

    def test_all_owned_outputs_are_exclusive(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            (work / 'linux-kernel').mkdir()
            prepare.check_outputs(work)
            for name in prepare.OWNED_OUTPUTS:
                with self.subTest(name=name):
                    (work / name).write_bytes(b'keep')
                    with self.assertRaisesRegex(ValueError, 'exists'):
                        prepare.check_outputs(work)
                    self.assertEqual((work / name).read_bytes(), b'keep')
                    (work / name).unlink()
            (work / 'tmp').symlink_to('missing-tree')
            with self.assertRaisesRegex(ValueError, 'exists'):
                prepare.check_outputs(work)
            self.assertTrue((work / 'linux-kernel').is_dir())

    def test_failed_commands_keep_raw_streams_and_returncode(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / 'failure'
            with self.assertRaises(subprocess.CalledProcessError) as error:
                prepare.run([sys.executable, '-c',
                             "import sys;sys.stdout.buffer.write(b'raw\\x00bytes');sys.stderr.write('failure');sys.exit(7)"], log)
            self.assertEqual(error.exception.returncode, 7)
            self.assertEqual(Path(str(log) + '.stdout').read_bytes(), b'raw\x00bytes')
            self.assertEqual(Path(str(log) + '.stderr').read_bytes(), b'failure')
            self.assertEqual(json.loads(Path(str(log) + '.json').read_text())['returncode'], 7)

    def test_binary_command_output_is_exclusive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / 'binary'
            prepare.run([sys.executable, '-c', "import sys;sys.stdout.buffer.write(b'\\x00\\xffdat')"],
                        root / 'extract', output=output)
            self.assertEqual(output.read_bytes(), b'\x00\xffdat')
            with self.assertRaises(FileExistsError):
                prepare.run([sys.executable, '-c', 'raise RuntimeError()'], root / 'second', output=output)
            self.assertEqual(output.read_bytes(), b'\x00\xffdat')


class FilesystemReadback(unittest.TestCase):
    def fixture(self, root, content=b'original'):
        image, target, logs = root / 'image', root / 'tree', root / 'logs'
        image.write_bytes(b'fake image')
        target.mkdir()
        logs.mkdir()
        (target / 'data').write_bytes(content)
        entries = [fake_entry('', stat.S_IFDIR | 0o755),
                   fake_entry('/data', stat.S_IFREG | 0o644, b'original')]
        ext2 = SimpleNamespace(readExt2=lambda source: iter(entries))
        return image, target, logs, entries, ext2

    def test_independent_ext2_data_and_fifo_readback(self):
        with tempfile.TemporaryDirectory() as temp:
            image, target, logs, entries, ext2 = self.fixture(Path(temp))
            entries.append(fake_entry('/original-fifo', stat.S_IFIFO | 0o640))
            entries.append(fake_entry('/original-link', stat.S_IFLNK | 0o777, b'data'))
            (target / 'original-link').symlink_to('data')
            rows = prepare.verify_ext2(image, target, logs, ext2)
            self.assertTrue(stat.S_ISFIFO((target / 'original-fifo').lstat().st_mode))
            self.assertEqual(os.readlink(target / 'original-link'), 'data')
            summary = prepare.tree_summary(rows)
            self.assertEqual((summary['files'], summary['directories'], summary['fifos'], summary['symlinks']), (1, 1, 1, 1))

    def test_ext2_data_corruption_is_not_repaired_or_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            image, target, logs, _, ext2 = self.fixture(Path(temp), b'corrupt')
            with self.assertRaisesRegex(ValueError, 'file data mismatch'):
                prepare.verify_ext2(image, target, logs, ext2)
            self.assertEqual((target / 'data').read_bytes(), b'corrupt')

    def test_ext2_extra_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            image, target, logs, _, ext2 = self.fixture(Path(temp))
            (target / 'extra').write_bytes(b'keep')
            with self.assertRaisesRegex(ValueError, 'inventory mismatch'):
                prepare.verify_ext2(image, target, logs, ext2)
            self.assertEqual((target / 'extra').read_bytes(), b'keep')

    def test_ext2_symlink_cannot_replace_regular_file(self):
        with tempfile.TemporaryDirectory() as temp:
            image, target, logs, _, ext2 = self.fixture(Path(temp))
            (target / 'data').unlink()
            (target / 'data').symlink_to(image)
            with self.assertRaisesRegex(ValueError, 'inode type mismatch'):
                prepare.verify_ext2(image, target, logs, ext2)

    def test_original_device_numbers_are_decimal(self):
        output = (b'debugfs: stat "/dev/console"\nDevice major/minor number: 05:01 (hex 05:01)\n'
                  b'debugfs: stat "/dev/nflasha3"\nDevice major/minor number: 252:03 (hex fc:03)\n')
        self.assertEqual(prepare.node_numbers(output), {'/dev/console': (5, 1), '/dev/nflasha3': (252, 3)})
        with self.assertRaisesRegex(ValueError, 'missing native device numbers'):
            prepare.node_numbers(b'debugfs: stat "/dev/missing"\nFile not found\n')

    def test_application_symlink_and_executable_mode_survive(self):
        with tempfile.TemporaryDirectory() as temp, application_tar() as archive:
            work = Path(temp)
            prepare.extract_appli(archive, work)
            self.assertEqual((work / 'setting/config').read_bytes(), b'original setting')
            self.assertEqual((work / 'tmp/toprc').read_bytes(), b'original tmp')
            self.assertEqual(stat.S_IMODE((work / 'tmp/toprc').stat().st_mode), 0o755)
            self.assertEqual(os.readlink(work / 'tmp/mtab'), '../proc/mounts')

    def test_application_paths_cannot_escape_work(self):
        for name in ('/absolute', '0800_appli/tmp/../../outside'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                with application_tar([(name, tarfile.REGTYPE, b'bad')]) as archive:
                    with self.assertRaisesRegex(ValueError, 'unsafe archive path'):
                        prepare.extract_appli(archive, Path(temp))
                self.assertFalse((Path(temp) / 'setting').exists())
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp) / 'work'
            work.mkdir()
            with application_tar([('0800_appli/tmp/escape', tarfile.SYMTYPE, '../../outside')]) as archive:
                with self.assertRaises(tarfile.LinkOutsideDestinationError):
                    prepare.extract_appli(archive, work)
            self.assertFalse((Path(temp) / 'outside').exists())

    def test_boot_fat_data_is_independently_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image, target = root / 'image', root / 'boot'
            image.write_bytes(b'fake FAT')
            target.mkdir()
            (target / 'kernel').write_bytes(b'kernel')
            def fat(contents):
                return SimpleNamespace(readFat=lambda source: iter([
                    fake_entry('/kernel', stat.S_IFREG, contents)]))
            self.assertEqual(len(prepare.verify_boot(image, target, fat(b'kernel'))), 1)
            with self.assertRaisesRegex(ValueError, 'FAT file data mismatch'):
                prepare.verify_boot(image, target, fat(b'bad'))
            (target / 'extra').write_bytes(b'keep')
            with self.assertRaisesRegex(ValueError, 'FAT tree inventory mismatch'):
                prepare.verify_boot(image, target, fat(b'kernel'))


if __name__ == '__main__':
    unittest.main()
