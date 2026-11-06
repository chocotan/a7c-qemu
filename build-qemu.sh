#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
archive=$(realpath -- "${QEMU_TARBALL:-"$root/work/qemu-11.1.2.tar.xz"}")
src="$root/work/qemu-src"
build="$src/build-a7c"
overlay="$root/source/qemu"

# Only local archives are used; configure and Meson must never fetch dependencies.
printf '%s  %s\n' 731b5681e4bb18be313231579b8efd0296c5b015fa36dc533874b639ba838016 "$archive" | sha256sum --check --status
printf '%s  %s\n' c1fb23f4f39fc88da4a1f89b06ea13e8683de886ee77dbb99369f8763dfe809e "$overlay/dtc-b6910bec.tar.xz" | sha256sum --check --status
if [[ -L "$src" || -L "$build" ]]; then
    echo 'Refusing a symlinked QEMU source/build directory.' >&2
    exit 1
fi
if [[ ! -f "$src/configure" ]]; then
    mkdir -p "$src"
    if [[ -n "$(ls -A -- "$src")" ]]; then
        echo "Incomplete source directory: $src (preserved; move it aside before retrying)." >&2
        exit 1
    fi
    tar -xJf "$archive" --strip-components=1 -C "$src"
fi
[[ $(<"$src/VERSION") == 11.1.2 ]]
if [[ ! -f "$src/subprojects/dtc/meson.build" ]]; then
    tar -xJf "$overlay/dtc-b6910bec.tar.xz" -C "$src/subprojects"
fi

cd "$src"
registration="$overlay/0001-register-a7c.patch"
if patch --batch --fuzz=0 --forward -p1 --dry-run < "$registration" >/dev/null 2>&1; then
    patch --batch --fuzz=0 --forward -p1 < "$registration"
elif ! patch --batch --fuzz=0 --reverse -p1 --dry-run < "$registration" >/dev/null 2>&1; then
    echo 'QEMU registration differs from the supplied patch; existing files preserved.' >&2
    exit 1
fi
for file in hw/arm/a7c.c hw/arm/a7c-gpe-init.h hw/timer/sony_hwtimer.c; do
    if ! cmp -s "$overlay/$file" "$src/$file"; then
        install -m 644 "$overlay/$file" "$src/$file"
    fi
done

mkdir -p "$build"
cd "$build"
../configure --target-list=arm-softmmu --disable-download \
    --without-default-features --enable-tcg --enable-fdt=internal \
    --enable-pixman --enable-sdl --disable-werror \
    --disable-tools --disable-guest-agent --disable-docs \
    2>&1 | tee configure.log
ninja -j8 qemu-system-arm 2>&1 | tee build.log
cc -std=c11 -Wall -Wextra -Werror "$root/tests/test-a7c-gpe-init.c" -o test-a7c-gpe-init
./test-a7c-gpe-init | tee verification-gpe-init.log

# Realize the board with no guest network or disks, inspect devices, then QMP quit.
python3 - "$build/qemu-system-arm" "$build" "$root" "$archive" <<'PY'
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys

binary, output, root, archive = map(pathlib.Path, sys.argv[1:])
commands = [
    {"execute": "qmp_capabilities", "id": "capabilities"},
    {"execute": "qom-get", "arguments": {"path": "/machine", "property": "type"}, "id": "type"},
    {"execute": "query-machines", "id": "machines"},
    {"execute": "query-status", "id": "status"},
    {"execute": "query-cpus-fast", "id": "cpus"},
    {"execute": "query-block", "id": "disks"},
    {"execute": "query-rx-filter", "id": "network"},
    {"execute": "human-monitor-command", "arguments": {"command-line": "info qtree"}, "id": "devices"},
    {"execute": "human-monitor-command", "arguments": {"command-line": "info mtree"}, "id": "memory"},
    {"execute": "quit", "id": "quit"},
]
argv = [str(binary), "-M", "a7c", "-cpu", "cortex-a9", "-smp", "1", "-m", "1024",
        "-S", "-nodefaults", "-display", "none", "-serial", "none", "-monitor", "none",
        "-nic", "none", "-qmp", "stdio"]
result = subprocess.run(
    argv, input="".join(json.dumps(command) + "\n" for command in commands),
    text=True, capture_output=True, timeout=30,
)
(output / "verification-qmp.log").write_text(result.stdout)
(output / "verification-stderr.log").write_text(result.stderr)
assert result.returncode == 0, (result.returncode, result.stderr)
messages = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
responses = {message["id"]: message for message in messages if "id" in message}
for command in commands:
    assert "return" in responses.get(command["id"], {}), responses.get(command["id"])
values = {key: response["return"] for key, response in responses.items()}
assert values["type"] == "a7c-machine", values["type"]
assert any(machine["name"] == "a7c" for machine in values["machines"])
assert not any(machine["name"] in {"a7m3", "zve10"} for machine in values["machines"])
assert values["status"]["running"] is False, values["status"]
assert len(values["cpus"]) == 1, values["cpus"]
assert values["disks"] == [] and values["network"] == [], (values["disks"], values["network"])
assert values["devices"].count("dev: sony-hwtimer,") == 9, values["devices"]
assert "dev: pl181," in values["devices"], values["devices"]
assert "dev: pl011," in values["devices"], values["devices"]
assert "a7c-gpe" in values["memory"] and "a7c-sugi" in values["memory"]
version = subprocess.check_output([binary, "--version"], text=True).splitlines()[0]


def identity(path):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path.relative_to(root) if path.is_relative_to(root) else path),
            "bytes": path.stat().st_size, "sha256": digest}


report = {
    "tested_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "version": version, "machine": values["type"], "cpu_model": "cortex-a9", "cpus": 1,
    "ram_mib": 1024, "model": "experimental CXD90045-family functional model",
    "sony_timers": 9, "pl181": True, "pl011": True,
    "guest_disks": [], "guest_network": [], "qmp_quit_exit_code": result.returncode,
    "board_realization_verified": True, "gpe_startup_guard_host_verified": True,
    "kernel_boot_verified": False, "firmware_boot_verified": False,
    "ap_verified": False, "physical_asic_compatibility_verified": False,
    "binary": identity(binary), "qmp_argv": argv,
    "inputs": [identity(path) for path in [
        archive, root / "source/qemu/dtc-b6910bec.tar.xz", root / "build-qemu.sh",
        root / "source/qemu/0001-register-a7c.patch", root / "source/qemu/hw/arm/a7c.c",
        root / "source/qemu/hw/arm/a7c-gpe-init.h", root / "source/qemu/hw/timer/sony_hwtimer.c",
        root / "tests/test-a7c-gpe-init.c",
    ]],
    "evidence": [identity(output / name) for name in (
        "configure.log", "build.log", "verification-qmp.log", "verification-stderr.log",
        "verification-gpe-init.log",
    )],
}
serialized = json.dumps(report, indent=2) + "\n"
(output / "verification.json").write_text(serialized)
(root / "validation").mkdir(exist_ok=True)
(root / "validation/qemu-board.json").write_text(serialized)
print(serialized, end="")
PY
sha256sum qemu-system-arm | tee qemu-system-arm.sha256
printf 'QEMU ready: %s\n' "$build/qemu-system-arm"
