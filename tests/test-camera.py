#!/usr/bin/env python3
import importlib.util
import io
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('camera', Path(__file__).resolve().parents[1] / 'scripts/camera.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SnapshotTests(unittest.TestCase):
    def exercise(self, corrupt=False):
        with tempfile.TemporaryDirectory() as temp:
            camera = module.Camera.__new__(module.Camera)
            camera.directory = camera.output = Path(temp)
            camera.closing = threading.Event()
            camera.frames = queue.Queue()
            camera.frame = 0
            camera.process = Mock()
            camera.process.poll.return_value = None
            camera.connect = Mock()
            raw = bytearray(module.capture.SPAN)
            raw[-2:] = b'\xff\xff'
            def publication(frame):
                meta = dict(frame=frame, width=640, height=480, format=1, bpp=2,
                    stride=1280, byte_length=len(raw), segments=150,
                    source_physical=0x22a80000,
                    fingerprint_fnv1a64=module.capture.fingerprint(raw))
                pages = [dict(frame=frame, index=i, physical=0x10000000+i*4096,
                    capture_offset=i*4096, length=4096) for i in range(150)]
                return meta, pages, dict(frame=frame, segments=150)
            camera.frames.put(publication(1))
            calls = []
            def call(name, args=None):
                calls.append(name)
                if name == 'stop':
                    camera.frames.put(publication(2))
                if name == 'pmemsave':
                    offset = args['val']-0x10000000
                    data = raw[offset:offset+args['size']]
                    if corrupt and offset == 0:
                        data = b'\x01' + data[1:]
                    Path(args['filename']).write_bytes(data)
            camera.call = call
            clock = iter(range(1000))
            with patch.object(module.time, 'monotonic', side_effect=lambda: next(clock)):
                if corrupt:
                    with self.assertRaisesRegex(RuntimeError, 'changed after publication'):
                        camera.snapshot('main')
                    self.assertFalse((camera.output/'main.png').exists())
                else:
                    image = camera.snapshot('main')
                    self.assertEqual(image.getpixel((639, 479)), (255, 255, 255))
                    self.assertEqual(camera.frame, 2)
                    self.assertTrue((camera.output/'main.json').is_file())
            self.assertEqual(calls[0], 'stop')
            self.assertEqual(calls[-1], 'cont')
            self.assertEqual(calls.count('pmemsave'), 150)

    def test_stop_selects_newest_complete_publication(self):
        self.exercise()

    def test_changed_snapshot_rejected_and_vm_resumed(self):
        self.exercise(corrupt=True)

    def test_shutdown_reconnects_and_waits_for_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            camera = module.Camera.__new__(module.Camera)
            camera.directory = Path(temp)/'run'
            camera.directory.mkdir()
            camera.output = Path(temp)/'evidence'
            camera.output.mkdir()
            camera.endpoint = camera.directory/'qmp'
            camera.endpoint.touch()
            camera.process = Mock(pid=123)
            camera.process.poll.return_value = None
            camera.reader = Mock()
            camera.stream = stale = Mock()
            camera.channel = Mock()
            camera.connect = Mock()
            def quit_call(name):
                self.assertEqual(name, 'quit')
                if camera.connect.call_count == 1:
                    raise OSError('timed out stream')
                camera.process.poll.return_value = 0
            camera.call = quit_call
            camera.close()
            self.assertEqual(camera.connect.call_count, 2)
            stale.close.assert_called_once()
            camera.process.wait.assert_called_once_with(timeout=10)
            self.assertFalse(camera.directory.exists())
            self.assertIn('"qemu_exit_code": 0', (camera.output/'shutdown.json').read_text())

    def test_failed_shutdown_keeps_run_and_owner(self):
        with tempfile.TemporaryDirectory() as temp:
            camera = module.Camera.__new__(module.Camera)
            camera.directory = Path(temp)
            camera.endpoint = camera.directory/'qmp'
            camera.endpoint.touch()
            camera.process = Mock(pid=123)
            camera.process.poll.return_value = None
            camera.reader = Mock()
            camera.stream = camera.channel = None
            camera.connect = Mock(side_effect=OSError('QMP unavailable'))
            with self.assertRaisesRegex(RuntimeError, 'PID=123 remains owned'):
                camera.close()
            self.assertTrue(camera.directory.exists())
            self.assertIsNone(camera.process.poll())
            self.assertEqual(camera.connect.call_count, 2)

    def test_kernel_fatal_is_reported_and_raw_log_is_preserved(self):
        for raw in (b'[ 1.23] Kernel panic - not syncing: Out of memory\n',
                    b'\r<0>Kernel panic - not syncing: Attempted to kill init!\n',
                    b'[ 2.34] A7C_UNSUPPORTED_DMA dma330 bytes=4096\n'):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as temp:
                camera = module.Camera.__new__(module.Camera)
                camera.output = Path(temp)
                camera.frames = queue.Queue()
                camera.process = Mock(stdout=io.BytesIO(raw))
                camera.read_log()
                error = camera.frames.get_nowait()
                self.assertIsInstance(error, RuntimeError)
                self.assertEqual(str(error), raw.decode().strip())
                self.assertEqual((camera.output / 'serial.log').read_bytes(), raw)

    def test_partial_timestamp_does_not_hide_a_native_publication(self):
        meta = dict(frame=15, width=640, height=480, format=1, bpp=2,
                    stride=1280, byte_length=614400, segments=150,
                    source_physical=0x22bb2000, fingerprint_fnv1a64='0'*16)
        pages = [dict(frame=15, index=i, physical=0x10000000+i*4096,
                      capture_offset=i*4096, length=4096) for i in range(150)]
        ready = dict(frame=15, segments=150)
        for duplicate in (False, True):
            records = [('UI_CAPTURE_META ', meta)] + [('UI_CAPTURE_PAGE ', p) for p in pages]
            if duplicate:
                records.append(('UI_CAPTURE_PAGE ', pages[0]))
            records.append(('UI_CAPTURE_READY ', ready))
            raw = bytearray()
            for i, (prefix, record) in enumerate(records):
                line = (prefix + module.json.dumps(record) + '\n').encode()
                raw.extend((b'[   2' if i == 0 else b'') + line)
                raw.extend(b'\r[   25.970120] ' + line)
            with self.subTest(duplicate=duplicate), tempfile.TemporaryDirectory() as temp:
                camera = module.Camera.__new__(module.Camera)
                camera.output = Path(temp)
                camera.frames = queue.Queue()
                camera.process = Mock(stdout=io.BytesIO(raw))
                camera.read_log()
                observed_meta, observed_pages, observed_ready = camera.frames.get_nowait()
                self.assertEqual(observed_meta, meta)
                if duplicate:
                    with self.assertRaises(ValueError):
                        module.capture.validate_segments(observed_meta, observed_pages, observed_ready)
                else:
                    self.assertEqual(len(module.capture.validate_segments(observed_meta, observed_pages, observed_ready)), 150)
                self.assertEqual((camera.output / 'serial.log').read_bytes(), raw)

    def test_unknown_uart_command_rejected(self):
        camera = module.Camera.__new__(module.Camera)
        with self.assertRaises(ValueError):
            camera.command('menu\nshutdown')


if __name__ == '__main__':
    unittest.main()
