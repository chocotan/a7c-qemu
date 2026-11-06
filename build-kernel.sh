#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
work="$root/work"
archive="${SONY_KERNEL_ARCHIVE:-$root/sources/sony-ilce7c-ver203/linux-kernel.tar.gz}"
cross="${CROSS_COMPILE:-$work/armv7-eabihf--glibc--stable-2020.08-1/bin/arm-linux-}"
src="$work/linux-kernel"
build="$work/kbuild-ui"
patchfile="$root/source/kernel/0001-a7c-qemu.patch"
[[ ! -L "$src" && ! -L "$build" ]] || { echo 'Refusing symlinked source/build' >&2; exit 1; }
printf '%s  %s\n' 477dfb9c17aa585dc5713331ff22a43b508e3fc6a247b2458503b9c4672eaf7c "$archive" | sha256sum -c -
mkdir -p "$work"
if [[ ! -d "$src" ]]; then
    [[ ! -e "$work/linux" ]] || { echo 'work/linux exists; preserve it before retrying' >&2; exit 1; }
    tar -xzf "$archive" -C "$work"
    mv "$work/linux" "$src"
fi
if patch --batch --fuzz=0 --forward --dry-run -d "$src" -p1 < "$patchfile" >/dev/null 2>&1; then
    patch --batch --fuzz=0 --forward -d "$src" -p1 < "$patchfile"
elif ! patch --batch --fuzz=0 --reverse --dry-run -d "$src" -p1 < "$patchfile" >/dev/null 2>&1; then
    echo 'Kernel source differs from supplied patch; preserved for inspection' >&2
    exit 1
fi
if [[ -f "$src/.config" ]]; then
    [[ ! -e "$work/sony-original-kernel.config" ]] || { echo 'Original config already preserved; inspect source .config' >&2; exit 1; }
    mv "$src/.config" "$work/sony-original-kernel.config"
fi
mkdir -p "$build"
[[ -f "$build/.config" ]] || cp "$root/source/kernel/a7c_defconfig" "$build/.config"
# The launcher supplies the A7C filesystem as an external initramfs.
"$src/scripts/config" --file "$build/.config" --set-str INITRAMFS_SOURCE "" --enable RD_GZIP
make -C "$src" O="$build" ARCH=arm CROSS_COMPILE="$cross" oldnoconfig
make -C "$src" O="$build" ARCH=arm CROSS_COMPILE="$cross" -j"${JOBS:-8}" Image modules
mkdir -p "$work/modules"
cp -a "$root/source/modules/." "$work/modules/"
make -C "$src" O="$build" ARCH=arm CROSS_COMPILE="$cross" M="$work/modules/dma330-stub" modules
if [[ -d "$work/initramfs-ui/usr/kmod" ]]; then
    install -m 644 "$work/modules/dma330-stub/dma330_stub.ko" "$work/initramfs-ui/usr/kmod/"
fi
