#!/usr/bin/env python3
"""Prepare the ILCE-7C 2.03 filesystems without executing the Windows updater.

Run from the project root after preparing the pinned fwtool and its Python env:
  python3 scripts/prepare-firmware.py --fwtool-python /path/to/fwtool-venv/bin/python

A saved fakeroot session is started automatically. All outputs are exclusive;
keep or rename an earlier extraction before rerunning. --work selects a separate
local experiment directory without touching kernel or emulator build files.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'work'
EXE_SHA256 = 'e382c3deecb8d0fe8463a2451ddbfa897cd131a1797170d05936fabc4ffaf6f8'
DAT_SHA256 = 'b5c20ed18b656d22611aa0ee0c83c168bd247030dc7bcf249bdb60d1168c3f39'
CAB_SHA256 = '58b7d77dd10402de37cae26efe56e539bc009084366ef11b95ca7abec5e26428'
CAB_OFFSET = 465440
CAB_SIZE = 366615519
DAT_NAME = 'FirmwareData_ILCE7CV203.dat'
FWTOOL_COMMIT = '72fbdd15ddcc2d2a24ccb52cf8e84b8de98c738a'
BACKUP = '0110_backup/SYSASTRA-DSLR/NB/CX88600_ALLLANG.bin'
BACKUP_SHA256 = '446ba0c6b36c5fe99cc4d2b0e1b03461ca3d40d8c3b2e3121fae506875258ccf'
REQUIRED = (
    'rootfs/bin/busybox', 'rootfs/kmod/devno.ko', 'rootfs/kmod/emmc.ko',
    'usr/bin/bootin.elf', 'usr/bin/im.elf', 'usr/lib/libObj.so',
    'usr/lib/libIMDB.so', 'usr/lib/viewUnified2.so',
    'boot/vmlinux.bin', 'boot/initrd.img', 'setting/DmmConfig.bin',
    'setting/Backup.bin', 'setting/Backup.bak',
)
OWNED_OUTPUTS = (
    'rootfs', 'usr', 'boot', 'setting', 'tmp', 'update', 'unpacked',
    'firmware-logs', 'firmware-manifest.json', 'filesystem-validation.json',
    'devices-rootfs.json', 'fakeroot-extract.state',
)


def need(condition, message):
    if not condition:
        raise ValueError(message)


def stream_sha256(stream):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(block)
    return digest.hexdigest()


def sha256(path):
    with Path(path).open('rb') as stream:
        return stream_sha256(stream)


def write_json(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def run(args, log, *, input=None, output=None):
    args = [str(arg) for arg in args]
    if output is None:
        result = subprocess.run(args, input=input, capture_output=True)
    else:
        with Path(output).open('xb') as stream:
            result = subprocess.run(args, input=input, stdout=stream, stderr=subprocess.PIPE)
    Path(str(log) + '.stdout').write_bytes(result.stdout or b'')
    Path(str(log) + '.stderr').write_bytes(result.stderr)
    if input is not None:
        Path(str(log) + '.stdin').write_bytes(input)
    write_json(Path(str(log) + '.json'), {
        'argv': args, 'returncode': result.returncode,
        'stdout_file': str(output) if output else str(log) + '.stdout',
        'stderr_file': str(log) + '.stderr',
    })
    result.check_returncode()
    return result


def check_outputs(work):
    for name in OWNED_OUTPUTS:
        need(not os.path.lexists(work / name),
             f'{work / name} exists; keep or rename it before preparing again')


def decode_cab(raw):
    signature = bytes(value ^ 255 for value in b'MSCF')
    start = raw.find(signature)
    need(start >= 0, 'missing complemented CAB header')
    need(len(raw) - start >= 36, 'truncated CAB header')
    header = bytes(value ^ 255 for value in raw[start:start + 36])
    size = struct.unpack_from('<I', header, 8)[0]
    need(size >= 36 and size <= len(raw) - start, 'truncated CAB payload')
    need(start == CAB_OFFSET and size == CAB_SIZE and raw.find(signature, start + 1) < 0,
         'unsupported CAB extraction boundary')
    cabinet = raw[start:start + size].translate(
        bytes.maketrans(bytes(range(256)), bytes(reversed(range(256)))))
    need(hashlib.sha256(cabinet).hexdigest() == CAB_SHA256, 'CAB digest mismatch')
    return cabinet


def extract_update(source, destination):
    need(sha256(source) == EXE_SHA256,
         'unsupported update package: expected ILCE-7C 2.03 SHA256')
    cabinet = decode_cab(source.read_bytes())
    destination.mkdir(parents=True, exist_ok=False)
    (destination / 'payload.cab').write_bytes(cabinet)
    (destination / 'cab').mkdir()
    dat = destination / 'cab' / DAT_NAME
    # -so extracts only the DAT even though earlier CAB entries share its LZX block.
    run(['7z', 'x', '-so', '-bd', destination / 'payload.cab', DAT_NAME],
        destination / 'extract-dat', output=dat)
    need(sha256(dat) == DAT_SHA256, 'firmware DAT digest mismatch')
    return dat


def archive_path(name):
    path = PurePosixPath(name)
    need(not path.is_absolute() and '..' not in path.parts,
         f'unsafe archive path: {name!r}')
    return path


def verify_tar(archive, tree):
    count = 0
    for member in archive:
        relative = archive_path(member.name)
        if member.isfile():
            with archive.extractfile(member) as source:
                need(stream_sha256(source) == sha256(tree / relative),
                     f'fwtool tar member mismatch: {relative}')
            count += 1
    return count


def extract_appli(archive, work):
    selected = []
    for member in archive:
        path = archive_path(member.name)
        if len(path.parts) < 2 or path.parts[:2] not in (
                ('0800_appli', 'setting'), ('0800_appli', 'tmp')):
            continue
        need(member.isfile() or member.isdir() or member.issym(),
             f'unsupported application tar inode: {member.name}')
        member = copy.copy(member)
        member.name = '/'.join(path.parts[1:])
        selected.append(member)
    need(any(member.name == 'setting' for member in selected)
         and any(member.name == 'tmp' for member in selected), 'missing 0800 settings or tmp')
    # Root is work, so the original tmp/mtab -> ../proc/mounts stays within it.
    archive.extractall(work, members=selected, filter='data')
    for member in selected:
        path = work / member.name
        os.chown(path, member.uid, member.gid, follow_symlinks=False)
        if not member.issym():
            os.chmod(path, member.mode)
        if member.isfile():
            with archive.extractfile(member) as source:
                need(stream_sha256(source) == sha256(path), f'application tar data mismatch: {path}')
        elif member.issym():
            need(path.is_symlink() and os.readlink(path) == member.linkname,
                 f'application tar symlink mismatch: {path}')
        else:
            need(path.is_dir() and not path.is_symlink(), f'application tar directory mismatch: {path}')


def verify_boot(image, target, fat):
    entries = []
    with image.open('rb') as source:
        for entry in fat.readFat(source):
            relative = entry.path.lstrip('/')
            archive_path(relative)
            path = target / relative
            need(path.exists() and not path.is_symlink(), f'missing FAT entry: {path}')
            row = {'path': relative, 'mode': oct(entry.mode)}
            if stat.S_ISREG(entry.mode):
                row.update(size=entry.size, sha256=stream_sha256(entry.contents))
                need(path.is_file() and path.stat().st_size == entry.size
                     and sha256(path) == row['sha256'], f'FAT file data mismatch: {path}')
            else:
                need(stat.S_ISDIR(entry.mode) and path.is_dir(), f'unsupported FAT entry: {path}')
            entries.append(row)
    need({str(path.relative_to(target)) for path in target.rglob('*')} ==
         {row['path'] for row in entries}, f'FAT tree inventory mismatch: {target}')
    return sorted(entries, key=lambda row: row['path'])


def set_metadata(path, entry):
    os.chown(path, entry.uid, entry.gid, follow_symlinks=False)
    if not stat.S_ISLNK(entry.mode):
        os.chmod(path, stat.S_IMODE(entry.mode))
    os.utime(path, (entry.mtime, entry.mtime), follow_symlinks=False)
    actual = path.lstat()
    need((actual.st_mode, actual.st_uid, actual.st_gid) ==
         (entry.mode, entry.uid, entry.gid), f'inode metadata mismatch: {path}')


def node_numbers(stdout):
    blocks = re.split(r'debugfs: stat "([^"\n]+)"\n', stdout.decode())
    numbers = {}
    for name, block in zip(blocks[1::2], blocks[2::2]):
        match = re.search(r'Device major/minor number:\s*(\d+):(\d+)', block)
        need(match is not None, f'missing native device numbers: {name}')
        numbers[name] = tuple(map(int, match.groups()))
    return numbers


def verify_ext2(image, target, logdir, ext2):
    """Cross-check debugfs output with fwtool's independent ext2 reader."""
    entries, nodes, directories = [], [], []
    with image.open('rb') as source:
        for entry in ext2.readExt2(source):
            relative = entry.path.lstrip('/')
            archive_path(relative)
            path = target / relative
            row = {'path': relative, 'mode': oct(entry.mode), 'uid': entry.uid,
                   'gid': entry.gid, 'mtime': entry.mtime}
            if stat.S_ISCHR(entry.mode) or stat.S_ISBLK(entry.mode):
                need('"' not in entry.path and '\n' not in entry.path,
                     f'unsupported debugfs path: {entry.path!r}')
                nodes.append((entry, row))
                continue
            if stat.S_ISFIFO(entry.mode) and not os.path.lexists(path):
                os.mkfifo(path, stat.S_IMODE(entry.mode))
            need(os.path.lexists(path), f'debugfs omitted {path}')
            actual = path.lstat()
            need(stat.S_IFMT(actual.st_mode) == stat.S_IFMT(entry.mode),
                 f'inode type mismatch: {path}')
            if stat.S_ISREG(entry.mode):
                row['size'] = entry.size
                row['sha256'] = stream_sha256(entry.contents)
                need(actual.st_size == entry.size and sha256(path) == row['sha256'],
                     f'ext2 file data mismatch: {path}')
            elif stat.S_ISLNK(entry.mode):
                row['link'] = entry.contents.read().decode('ascii')
                need(os.readlink(path) == row['link'], f'ext2 symlink mismatch: {path}')
            elif stat.S_ISDIR(entry.mode):
                directories.append((path, entry))
            else:
                need(stat.S_ISFIFO(entry.mode), f'unsupported ext2 inode: {path}')
            set_metadata(path, entry)
            entries.append(row)
    if nodes:
        commands = ''.join(f'stat "{entry.path}"\n' for entry, _ in nodes).encode('ascii')
        result = run(['debugfs', '-f', '-', image], logdir / f'devices-{target.name}', input=commands)
        numbers = node_numbers(result.stdout)
        for entry, row in nodes:
            need(entry.path in numbers, f'missing device stat: {entry.path}')
            major, minor = numbers[entry.path]
            path = target / row['path']
            device = os.makedev(major, minor)
            if not os.path.lexists(path):
                os.mknod(path, entry.mode, device)
            need(path.lstat().st_rdev == device, f'device number mismatch: {path}')
            set_metadata(path, entry)
            row.update(major=major, minor=minor)
            entries.append(row)
    for path, entry in reversed(directories):
        os.utime(path, (entry.mtime, entry.mtime))
    actual_paths = {''} | {str(path.relative_to(target)) for path in target.rglob('*')}
    need(actual_paths == {row['path'] for row in entries}, f'ext2 tree inventory mismatch: {target}')
    return sorted(entries, key=lambda row: row['path'])


def tree_summary(entries):
    counts = {'entries': len(entries)}
    for name, predicate in [('files', stat.S_ISREG), ('directories', stat.S_ISDIR),
                            ('symlinks', stat.S_ISLNK), ('devices', lambda mode:
                             stat.S_ISCHR(mode) or stat.S_ISBLK(mode)), ('fifos', stat.S_ISFIFO)]:
        counts[name] = sum(predicate(int(row['mode'], 8)) for row in entries)
    counts['tree_sha256'] = hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()
    return counts


def kernel_identity(work):
    module = (work / 'rootfs/kmod/devno.ko').read_bytes()
    match = re.search(rb'vermagic=([^\0]+)', module)
    need(match is not None, 'devno.ko has no vermagic')
    image = (work / 'boot/vmlinux.bin').read_bytes()
    banner = re.search(rb'Linux version [^\0\n]+', image)
    need(banner is not None, 'original kernel has no Linux banner')
    return {'version': match.group(1).decode().split()[0],
            'vermagic': match.group(1).decode(), 'banner': banner.group().decode(),
            'ikconfig_embedded': b'IKCFG_ST' in image}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--update', type=Path, default=ROOT / 'Update_ILCE7CV203.exe')
    parser.add_argument('--work', type=Path, default=WORK)
    parser.add_argument('--fwtool', type=Path, default=WORK / 'fwtool/fwtool.py')
    parser.add_argument('--fwtool-python', default=sys.executable)
    args = parser.parse_args()
    work = args.work.absolute()
    check_outputs(work)
    need(sha256(args.update) == EXE_SHA256, 'update digest mismatch: expected ILCE-7C 2.03')
    for command in ('7z', 'debugfs', 'e2fsck', 'fakeroot', 'git'):
        need(shutil.which(command), f'missing required command: {command}')
    need(args.fwtool.is_file(), f'missing pinned fwtool: {args.fwtool}')
    work.mkdir(parents=True, exist_ok=True)
    if not os.environ.get('FAKEROOTKEY'):
        # Keep the venv interpreter spelling: resolving its symlink discards its env.
        os.execvp('fakeroot', ['fakeroot', '-s', str(work / 'fakeroot-extract.state'),
                              sys.executable, str(Path(__file__).absolute()), *sys.argv[1:]])
    need(os.geteuid() == 0, 'fakeroot metadata session is not active')
    logdir = work / 'firmware-logs'
    logdir.mkdir()
    tool_root = args.fwtool.absolute().parent
    revision = run(['git', '-C', tool_root, 'rev-parse', 'HEAD'], logdir / 'fwtool-revision').stdout.decode().strip()
    need(revision == FWTOOL_COMMIT, 'unsupported fwtool commit')
    run(['git', '-C', tool_root, 'diff', '--exit-code', 'HEAD', '--'], logdir / 'fwtool-clean')
    dat = extract_update(args.update, work / 'update')
    run([args.fwtool_python, args.fwtool, 'unpack', '-f', dat, '-o', work / 'unpacked'],
        logdir / 'unpack')
    # YAML belongs to the unpacker's environment, not the host script's dependencies.
    result = run([args.fwtool_python, '-c',
                  'import json,sys,yaml; print(json.dumps(yaml.safe_load(open(sys.argv[1]))))',
                  work / 'unpacked/config.yaml'], logdir / 'identity')
    identity = json.loads(result.stdout)
    need(identity['fdat'] == {'model': 0x91030019, 'region': 0, 'version': '2.03', 'isAccessory': False}
         and identity['dat']['crypterName'] == 'CXD90045', 'unexpected Sony firmware identity')
    tree = work / 'unpacked/firmware.tar_unpacked'
    with tarfile.open(work / 'unpacked/firmware.tar') as archive:
        tar_files = verify_tar(archive, tree)
    sys.path.insert(0, str(tool_root))
    from fwtool.archive import ext2, fat
    trees, images = {}, {}
    for partition, name in [('nflasha7', 'rootfs'), ('nflasha15', 'usr')]:
        image = tree / '0700_part_image/dev' / partition
        before = sha256(image)
        run(['e2fsck', '-fn', image], logdir / f'e2fsck-{name}')
        target = work / name
        target.mkdir()
        run(['debugfs', '-R', f'rdump / "{target}"', image], logdir / f'extract-{name}')
        trees[name] = verify_ext2(image, target, logdir, ext2)
        need(sha256(image) == before, f'partition image changed: {image}')
        images[partition] = {'size': image.stat().st_size, 'sha256': before, 'e2fsck_returncode': 0}
    image = tree / '0700_part_image/dev/nflasha3'
    images['nflasha3'] = {'size': image.stat().st_size, 'sha256': sha256(image)}
    run(['7z', 'x', '-y', image, f'-o{work / "boot"}'], logdir / 'extract-boot')
    trees['boot'] = verify_boot(image, work / 'boot', fat)
    with tarfile.open(work / 'unpacked/firmware.tar') as archive:
        extract_appli(archive, work)
    need(sha256(tree / BACKUP) == BACKUP_SHA256, 'ALLLANG backup template digest mismatch')
    need((tree / '0110_backup/MainDest.txt').read_bytes() == b'SYSASTRA-DSLR\nNB\nCX88600_UC2.bin\n',
         'unexpected backup model selection')
    for name in ('Backup.bin', 'Backup.bak'):
        shutil.copy2(tree / BACKUP, work / 'setting' / name)
    for name in REQUIRED:
        need((work / name).is_file(), f'incomplete extraction: {name}')
    write_json(work / 'filesystem-validation.json', trees)
    write_json(work / 'devices-rootfs.json', [row for row in trees['rootfs'] if 'major' in row])
    manifest = {
        'schema': 1, 'camera': 'ILCE-7C', 'version': '2.03', 'model': '0x91030019',
        'update_sha256': sha256(args.update), 'dat_sha256': sha256(dat),
        'cab': {'offset': CAB_OFFSET, 'size': CAB_SIZE, 'sha256': CAB_SHA256},
        'sony_identity': identity, 'fwtool_commit': revision,
        'backup_template': BACKUP, 'backup_sha256': BACKUP_SHA256,
        'files': {name: sha256(work / name) for name in REQUIRED}, 'images': images,
        'trees': {name: tree_summary(entries) for name, entries in trees.items()},
        'kernel': kernel_identity(work), 'tar_regular_files_verified': tar_files,
        'fakeroot_state': 'fakeroot-extract.state',
        'metadata_source': 'original ext2 modes/owners/device numbers; debugfs + independent fwtool ext2 readback',
    }
    write_json(work / 'firmware-manifest.json', manifest)
    print('Prepared ILCE-7C 2.03 under', work)
    print('Original module vermagic:', manifest['kernel']['vermagic'])


if __name__ == '__main__':
    main()
