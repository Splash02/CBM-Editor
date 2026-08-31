#!/usr/bin/env bash
set -euo pipefail

edition="${CBM_BUILD_EDITION:-both}"
python_exe="${PYTHON_EXE:-python3}"
no_compression="${CBM_BUILD_NO_COMPRESSION:-0}"
output_suffix="${CBM_BUILD_OUTPUT_SUFFIX:-}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
output_root="${CBM_BUILD_OUTPUT_ROOT:-$project_root/build/nuitka/linux}"

build_cbm() {
    local entry_file="$1"
    local output_file="$2"
    local output_dir="$3"

    mkdir -p "$output_dir"
    video_vendor="$project_root/cbm_editor/vendor/video"
    for video_file in \
        "$video_vendor/linux-x86_64/cbm_video_tool" \
        "$video_vendor/manifest.json" \
        "$video_vendor/THIRD_PARTY_NOTICES.txt" \
        "$video_vendor/LICENSE_FFMPEG_GPLv2.txt" \
        "$video_vendor/LICENSE_X264.txt" \
        "$video_vendor/LICENSE_LIBVPX.txt" \
        "$video_vendor/LICENSE_DAV1D.txt" \
        "$video_vendor/PATENTS_LIBVPX.txt"; do
        [[ -f "$video_file" ]] || exit 3
    done
    cd "$project_root"
    expected_video_hash="$("$python_exe" -c "import json; print(json.load(open('cbm_editor/vendor/video/manifest.json', encoding='utf-8'))['artifacts']['linux-x86_64']['sha256'])")"
    video_scan="$("$python_exe" -c "import json; print(json.load(open('cbm_editor/vendor/video/manifest.json', encoding='utf-8'))['artifacts']['linux-x86_64']['scan'])")"
    [[ -n "$expected_video_hash" && -n "$video_scan" ]]
    printf '%s  %s\n' "$expected_video_hash" "$video_vendor/linux-x86_64/cbm_video_tool" | sha256sum --check
    chmod 755 "$video_vendor/linux-x86_64/cbm_video_tool"
    nuitka_mode=(--onefile)
    if [[ "$no_compression" == "1" ]]; then
        nuitka_mode=(--onefile-no-compression --onefile)
    fi
    "$python_exe" -m nuitka \
        "${nuitka_mode[@]}" \
        --enable-plugin=pyqt6 \
        --include-qt-plugins=multimedia \
        --include-module=PyQt6.QtMultimedia \
        --include-data-dir=cbm_editor/sounds=cbm_editor/sounds \
        --include-data-dir=cbm_editor/fonts=cbm_editor/fonts \
        --include-data-file=cbm_editor/vendor/bass/manifest.json=cbm_editor/vendor/bass/manifest.json \
        --include-data-file=cbm_editor/vendor/bass/LICENSE.txt=cbm_editor/vendor/bass/LICENSE.txt \
        --include-data-file=cbm_editor/vendor/bass/LICENSE_BASSALAC.txt=cbm_editor/vendor/bass/LICENSE_BASSALAC.txt \
        --include-data-file=cbm_editor/vendor/bass/LICENSE_BASSENC.txt=cbm_editor/vendor/bass/LICENSE_BASSENC.txt \
        --include-data-file=cbm_editor/vendor/bass/LICENSE_BASSENC_MP3.txt=cbm_editor/vendor/bass/LICENSE_BASSENC_MP3.txt \
        --include-data-file=cbm_editor/vendor/bass/LICENSE_BASSFLAC.txt=cbm_editor/vendor/bass/LICENSE_BASSFLAC.txt \
        --include-data-file=cbm_editor/vendor/bass/LICENSE_BASSMIX.txt=cbm_editor/vendor/bass/LICENSE_BASSMIX.txt \
        --include-data-file=cbm_editor/vendor/bass/LICENSE_BASSOPUS.txt=cbm_editor/vendor/bass/LICENSE_BASSOPUS.txt \
        --include-data-file=cbm_editor/vendor/bass/THIRD_PARTY_NOTICES.txt=cbm_editor/vendor/bass/THIRD_PARTY_NOTICES.txt \
        --include-data-file=cbm_editor/vendor/bass/linux-x86_64/libbass.so=cbm_editor/vendor/bass/linux-x86_64/libbass.so \
        --include-data-file=cbm_editor/vendor/bass/linux-x86_64/libbassalac.so=cbm_editor/vendor/bass/linux-x86_64/libbassalac.so \
        --include-data-file=cbm_editor/vendor/bass/linux-x86_64/libbassenc.so=cbm_editor/vendor/bass/linux-x86_64/libbassenc.so \
        --include-data-file=cbm_editor/vendor/bass/linux-x86_64/libbassenc_mp3.so=cbm_editor/vendor/bass/linux-x86_64/libbassenc_mp3.so \
        --include-data-file=cbm_editor/vendor/bass/linux-x86_64/libbassflac.so=cbm_editor/vendor/bass/linux-x86_64/libbassflac.so \
        --include-data-file=cbm_editor/vendor/bass/linux-x86_64/libbassmix.so=cbm_editor/vendor/bass/linux-x86_64/libbassmix.so \
        --include-data-file=cbm_editor/vendor/bass/linux-x86_64/libbassopus.so=cbm_editor/vendor/bass/linux-x86_64/libbassopus.so \
        --include-data-file=cbm_editor/vendor/video/manifest.json=cbm_editor/vendor/video/manifest.json \
        --include-data-file=cbm_editor/vendor/video/THIRD_PARTY_NOTICES.txt=cbm_editor/vendor/video/THIRD_PARTY_NOTICES.txt \
        --include-data-file=cbm_editor/vendor/video/LICENSE_FFMPEG_GPLv2.txt=cbm_editor/vendor/video/LICENSE_FFMPEG_GPLv2.txt \
        --include-data-file=cbm_editor/vendor/video/LICENSE_X264.txt=cbm_editor/vendor/video/LICENSE_X264.txt \
        --include-data-file=cbm_editor/vendor/video/LICENSE_LIBVPX.txt=cbm_editor/vendor/video/LICENSE_LIBVPX.txt \
        --include-data-file=cbm_editor/vendor/video/LICENSE_DAV1D.txt=cbm_editor/vendor/video/LICENSE_DAV1D.txt \
        --include-data-file=cbm_editor/vendor/video/PATENTS_LIBVPX.txt=cbm_editor/vendor/video/PATENTS_LIBVPX.txt \
        --include-data-file=cbm_editor/vendor/video/linux-x86_64/cbm_video_tool=cbm_editor/vendor/video/linux-x86_64/cbm_video_tool \
        --output-dir="$output_dir" \
        --output-filename="$output_file" \
        "$entry_file"
}

case "${edition,,}" in
    preview)
        build_cbm "scripts/CBM_Editor_preview.py" "CBM_Editor_PREVIEW${output_suffix}" "$output_root/preview"
        ;;
    release)
        build_cbm "scripts/CBM_Editor_release.py" "CBM_Editor${output_suffix}" "$output_root/release"
        ;;
    both)
        build_cbm "scripts/CBM_Editor_preview.py" "CBM_Editor_PREVIEW${output_suffix}" "$output_root/preview"
        build_cbm "scripts/CBM_Editor_release.py" "CBM_Editor${output_suffix}" "$output_root/release"
        ;;
    *)
        exit 2
        ;;
esac
