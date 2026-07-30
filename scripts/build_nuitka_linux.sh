#!/usr/bin/env bash
set -euo pipefail

edition="${CBM_BUILD_EDITION:-both}"
python_exe="${PYTHON_EXE:-python3}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
output_root="${CBM_BUILD_OUTPUT_ROOT:-$project_root/build/nuitka/linux}"

build_cbm() {
    local entry_file="$1"
    local output_file="$2"
    local output_dir="$3"

    mkdir -p "$output_dir"
    cd "$project_root"
    "$python_exe" -m nuitka \
        --onefile \
        --enable-plugin=pyqt6 \
        --include-data-dir=cbm_editor/sounds=cbm_editor/sounds \
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
        --output-dir="$output_dir" \
        --output-filename="$output_file" \
        "$entry_file"
}

case "${edition,,}" in
    preview)
        build_cbm "scripts/CBM_Editor_preview.py" "CBM_Editor_PREVIEW" "$output_root/preview"
        ;;
    release)
        build_cbm "scripts/CBM_Editor_release.py" "CBM_Editor" "$output_root/release"
        ;;
    both)
        build_cbm "scripts/CBM_Editor_preview.py" "CBM_Editor_PREVIEW" "$output_root/preview"
        build_cbm "scripts/CBM_Editor_release.py" "CBM_Editor" "$output_root/release"
        ;;
    *)
        exit 2
        ;;
esac
