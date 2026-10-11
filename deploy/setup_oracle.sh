#!/usr/bin/env bash
set -euo pipefail

# swap: <2GB RAM olan VM'lerde ASan derlemesi OOM olmasin
if [ "$(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo)" -lt 2000 ] && [ -z "$(swapon --show --noheadings)" ]; then
  sudo dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none
  sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
fi

# paketler
if command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y dnf-plugins-core || true
  sudo dnf config-manager --set-enabled ol9_codeready_builder 2>/dev/null || true
  sudo dnf config-manager --set-enabled ol8_codeready_builder 2>/dev/null || true
  sudo dnf install -y gcc gcc-c++ make git cmake clang llvm llvm-devel compiler-rt zlib-devel python3 python3-devel automake flex bison glib2-devel
  sudo dnf install -y lld || true
else
  sudo apt-get update
  sudo apt-get install -y build-essential git cmake clang llvm llvm-dev lld zlib1g-dev python3 python3-dev automake flex bison libglib2.0-dev
fi
sudo sysctl -w kernel.core_pattern=core || true

mkdir -p ~/fuzz && cd ~/fuzz
[ -d AFLplusplus ] || git clone --depth 1 https://github.com/AFLplusplus/AFLplusplus
LLVMC="$(command -v llvm-config || ls /usr/bin/llvm-config* 2>/dev/null | head -1 || true)"
( cd AFLplusplus && LLVM_CONFIG="$LLVMC" make -j"$(nproc)" source-only && sudo make install )

[ -d libvgm ] || git clone --recursive https://github.com/ValleyBell/libvgm
cd libvgm
if [ -n "${COMMIT:-}" ]; then git checkout "$COMMIT" && git submodule update --init --recursive; fi
git rev-parse HEAD | tee ~/fuzz/COMMIT_oracle.txt

export AFL_USE_ASAN=1 ASAN_OPTIONS=detect_leaks=0
CC=afl-clang-fast CXX=afl-clang-fast++ cmake -S . -B build-afl \
  -DCMAKE_BUILD_TYPE=None -DCMAKE_C_FLAGS="-O2 -g" -DCMAKE_CXX_FLAGS="-O2 -g" \
  -DUSE_SANITIZERS=OFF -DBUILD_LIBAUDIO=OFF -DBUILD_PLAYER=OFF -DBUILD_VGM2WAV=ON -DBUILD_TESTS=OFF
cmake --build build-afl -j"$(nproc)"

# seed + dictionary
python3 - <<'PYEOF'
import struct, os
def build(gd3):
    h = bytearray(0x40)
    h[0:4] = b'Vgm '
    struct.pack_into('<I', h, 0x08, 0x150)
    struct.pack_into('<I', h, 0x0C, 3579545)
    struct.pack_into('<I', h, 0x18, 735)
    struct.pack_into('<I', h, 0x2C, 7670453)
    cmds = bytes([0x50,0x9F, 0x52,0x2B,0x80, 0x62, 0x66])
    tail = b''
    if gd3:
        tags = ['Track','','Game','','System','','Author','','2026','me','']
        s = b''.join(t.encode('utf-16-le') + b'\0\0' for t in tags)
        tail = b'Gd3 ' + struct.pack('<II', 0x100, len(s)) + s
        struct.pack_into('<I', h, 0x14, 0x40 + len(cmds) - 0x14)
    out = bytearray(bytes(h) + cmds + tail)
    struct.pack_into('<I', out, 0x04, len(out) - 4)
    return bytes(out)
d = os.path.expanduser('~/fuzz/seeds')
os.makedirs(d, exist_ok=True)
open(d + '/min.vgm', 'wb').write(build(False))
open(d + '/gd3.vgm', 'wb').write(build(True))
PYEOF
cat > ~/fuzz/vgm.dict <<'DEOF'
magic="Vgm "
gd3="Gd3 "
ver150="\x50\x01\x00\x00"
ver171="\x71\x01\x00\x00"
end="\x66"
datablock="\x67\x66"
DEOF

# 60 sn smoke fuzz
cd ~/fuzz
export AFL_SKIP_CPUFREQ=1 AFL_NO_UI=1 ASAN_OPTIONS=abort_on_error=1:symbolize=0:detect_leaks=0
timeout 60 afl-fuzz -i seeds -o out_smoke -x vgm.dict -t 2000 -m none -- \
  libvgm/build-afl/bin/vgm2wav @@ /dev/shm/o_smoke.wav || true
echo "--- fuzzer_stats ---"
grep -E "execs_done|execs_per_sec|corpus_count|saved_crashes|saved_hangs|stability" out_smoke/default/fuzzer_stats || echo "!! fuzzer_stats yok, afl-fuzz calismamis"
