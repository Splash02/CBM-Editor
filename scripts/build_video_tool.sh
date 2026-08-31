#!/usr/bin/env bash
set -euo pipefail

target="${1:-}"
if [[ "$target" != "linux-x86_64" && "$target" != "windows-x64" ]]; then
    exit 2
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
work_root="$project_root/build/video-tool/$target"
source_root="$work_root/source"
prefix="$work_root/prefix"
jobs="${CBM_VIDEO_BUILD_JOBS:-$(getconf _NPROCESSORS_ONLN)}"
ffmpeg_url="https://ffmpeg.org/releases/ffmpeg-8.1.2.tar.xz"
ffmpeg_sha="464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c"
libvpx_url="https://github.com/webmproject/libvpx/archive/refs/tags/v1.16.0.tar.gz"
libvpx_sha="7a479a3c66b9f5d5542a4c6a1b7d3768a983b1e5c14c60a9396edc9b649e015c"
dav1d_url="https://download.videolan.org/pub/videolan/dav1d/1.5.4/dav1d-1.5.4.tar.xz"
dav1d_sha="686616b7c69eb88d44459391ab25cac13b6647a3b288835c5784e71c1514a5c5"
x264_commit="3a21e97bf23676a0bf4616df8bc2207c9fd7b1d3"

mkdir -p "$source_root" "$prefix"
cd "$source_root"

if [[ ! -f ffmpeg-8.1.2.tar.xz ]]; then
    curl --fail --location --proto '=https' --tlsv1.2 "$ffmpeg_url" --output ffmpeg-8.1.2.tar.xz
fi
printf '%s  %s\n' "$ffmpeg_sha" "ffmpeg-8.1.2.tar.xz" | sha256sum --check

if [[ ! -f libvpx-1.16.0.tar.gz ]]; then
    curl --fail --location --proto '=https' --tlsv1.2 "$libvpx_url" --output libvpx-1.16.0.tar.gz
fi
printf '%s  %s\n' "$libvpx_sha" "libvpx-1.16.0.tar.gz" | sha256sum --check

if [[ ! -f dav1d-1.5.4.tar.xz ]]; then
    curl --fail --location --proto '=https' --tlsv1.2 "$dav1d_url" --output dav1d-1.5.4.tar.xz
fi
printf '%s  %s\n' "$dav1d_sha" "dav1d-1.5.4.tar.xz" | sha256sum --check

if [[ ! -d x264 ]]; then
    git clone --filter=blob:none https://code.videolan.org/videolan/x264.git x264
fi
if ! git -C x264 cat-file -e "$x264_commit^{commit}" 2>/dev/null; then
    git -C x264 fetch --depth 1 origin "$x264_commit"
fi
git -C x264 checkout --detach "$x264_commit"
[[ "$(git -C x264 rev-parse HEAD)" == "$x264_commit" ]]

rm -rf ffmpeg-8.1.2 libvpx-1.16.0 dav1d-1.5.4 dav1d-build
tar -xf ffmpeg-8.1.2.tar.xz
mkdir libvpx-1.16.0
tar -xf libvpx-1.16.0.tar.gz --strip-components=1 -C libvpx-1.16.0
tar -xf dav1d-1.5.4.tar.xz

cross=()
x264_host=()
meson_cross=()
dav1d_prefix="$prefix"
vpx_target="x86_64-linux-gcc"
output_dir="$project_root/cbm_editor/vendor/video/linux-x86_64"
output_name="cbm_video_tool"
extra_ldflags="-L$prefix/lib"
if [[ -d /mingw64/bin ]]; then
    export PATH="/mingw64/bin:$PATH"
fi
if [[ "$target" == "linux-x86_64" && "${CBM_VIDEO_ZIG_CROSS:-0}" == "1" ]]; then
    export ZIG_GLOBAL_CACHE_DIR="$work_root/zig-cache/global"
    export ZIG_LOCAL_CACHE_DIR="$work_root/zig-cache/local"
    mkdir -p "$ZIG_GLOBAL_CACHE_DIR" "$ZIG_LOCAL_CACHE_DIR"
    export CC="$script_dir/zig_linux_cc"
    export CXX="$script_dir/zig_linux_cxx"
    export AR="$script_dir/zig_linux_ar"
    export RANLIB="$script_dir/zig_linux_ranlib"
    export STRIP="$script_dir/zig_linux_strip"
    x264_host=(--host=x86_64-linux)
    cross=(
        --enable-cross-compile
        --target-os=linux
        --arch=x86_64
        --cc="$CC"
        --cxx="$CXX"
        --ar="$AR"
        --ranlib="$RANLIB"
        --strip="$STRIP"
    )
    meson_cross_file="$work_root/dav1d-linux-x86_64.ini"
    zig_exe="$(cygpath -m /clang64/bin/zig.exe)"
    ar_exe="$(cygpath -m /usr/bin/ar.exe)"
    ranlib_exe="$(cygpath -m /usr/bin/ranlib.exe)"
    strip_exe="$(cygpath -m /usr/bin/strip.exe)"
    nasm_exe="$(cygpath -m /mingw64/bin/nasm.exe)"
    pkg_config_exe="$(cygpath -m /mingw64/bin/pkg-config.exe)"
    printf '%s\n' \
        '[binaries]' \
        "c = ['$zig_exe', 'cc', '-target', 'x86_64-linux-musl']" \
        "cpp = ['$zig_exe', 'c++', '-target', 'x86_64-linux-musl']" \
        "ar = '$ar_exe'" \
        "ranlib = '$ranlib_exe'" \
        "strip = '$strip_exe'" \
        "nasm = '$nasm_exe'" \
        "pkg-config = '$pkg_config_exe'" \
        '[host_machine]' \
        "system = 'linux'" \
        "cpu_family = 'x86_64'" \
        "cpu = 'x86_64'" \
        "endian = 'little'" \
        '[properties]' \
        'needs_exe_wrapper = true' > "$meson_cross_file"
    meson_cross=(--cross-file "$meson_cross_file")
    dav1d_prefix="/"
    extra_ldflags="$extra_ldflags -static"
fi
if [[ "$target" == "windows-x64" ]]; then
    export MSYSTEM=MINGW64
    vpx_target="x86_64-win64-gcc"
    output_dir="$project_root/cbm_editor/vendor/video/windows-x64"
    output_name="cbm_video_tool.exe"
    extra_ldflags="$extra_ldflags -static -static-libgcc"
fi

cd "$source_root/x264"
make distclean >/dev/null 2>&1 || true
./configure --prefix="$prefix" --enable-static --disable-cli --disable-opencl --bit-depth=8 "${x264_host[@]}"
make -j"$jobs"
make install

cd "$source_root/libvpx-1.16.0"
make clean >/dev/null 2>&1 || true
./configure --prefix="$prefix" --target="$vpx_target" --disable-examples --disable-tools --disable-docs --disable-unit-tests --disable-vp8 --enable-vp9 --enable-static --disable-shared
make -j"$jobs"
make install

cd "$source_root"
MSYS2_ARG_CONV_EXCL="--prefix=" meson setup dav1d-build dav1d-1.5.4 \
    --prefix="$dav1d_prefix" \
    --buildtype=release \
    --default-library=static \
    -Denable_tools=false \
    -Denable_tests=false \
    -Denable_examples=false \
    -Denable_docs=false \
    "${meson_cross[@]}"
meson compile -C dav1d-build -j "$jobs"
if [[ "$target" == "linux-x86_64" && "${CBM_VIDEO_ZIG_CROSS:-0}" == "1" ]]; then
    DESTDIR="$prefix" meson install -C dav1d-build
    sed -i "s|^prefix=.*|prefix=$prefix|" "$prefix/lib/pkgconfig/dav1d.pc"
else
    meson install -C dav1d-build
fi

export PKG_CONFIG_PATH="$prefix/lib/pkgconfig"
cd "$source_root/ffmpeg-8.1.2"
make distclean >/dev/null 2>&1 || true
./configure \
    --prefix="$prefix" \
    --pkg-config-flags=--static \
    --extra-cflags="-I$prefix/include" \
    --extra-ldflags="$extra_ldflags" \
    --extra-libs="-lpthread -lm" \
    --disable-everything \
    --disable-autodetect \
    --disable-network \
    --disable-doc \
    --disable-debug \
    --disable-ffplay \
    --disable-ffprobe \
    --disable-avdevice \
    --disable-swresample \
    --disable-shared \
    --enable-static \
    --enable-small \
    --enable-ffmpeg \
    --enable-gpl \
    --enable-libx264 \
    --enable-libvpx \
    --enable-libdav1d \
    --enable-protocol=file,pipe \
    --enable-demuxer=mov,matroska \
    --enable-muxer=mp4,webm,matroska,null \
    --enable-decoder=h264,hevc,mpeg4,vp8,vp9,libdav1d \
    --enable-encoder=libx264,libvpx_vp9,wrapped_avframe \
    --enable-parser=h264,hevc,mpeg4video,vp8,vp9,av1 \
    --enable-filter=trim,tpad,setpts,format,scale,transpose,hflip,vflip,ssim,null,split \
    "${cross[@]}"
make -j"$jobs"

mkdir -p "$output_dir"
cp ffmpeg "$output_dir/$output_name"
if [[ "$target" == "windows-x64" ]]; then
    strip "$output_dir/$output_name"
elif [[ "${CBM_VIDEO_ZIG_CROSS:-0}" == "1" ]]; then
    "$STRIP" "$output_dir/$output_name"
else
    strip "$output_dir/$output_name"
fi

cp "$source_root/ffmpeg-8.1.2/COPYING.GPLv2" "$project_root/cbm_editor/vendor/video/LICENSE_FFMPEG_GPLv2.txt"
cp "$source_root/x264/COPYING" "$project_root/cbm_editor/vendor/video/LICENSE_X264.txt"
cp "$source_root/libvpx-1.16.0/LICENSE" "$project_root/cbm_editor/vendor/video/LICENSE_LIBVPX.txt"
cp "$source_root/libvpx-1.16.0/PATENTS" "$project_root/cbm_editor/vendor/video/PATENTS_LIBVPX.txt"
cp "$source_root/dav1d-1.5.4/COPYING" "$project_root/cbm_editor/vendor/video/LICENSE_DAV1D.txt"
