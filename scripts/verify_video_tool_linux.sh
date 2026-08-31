#!/usr/bin/env bash
set -euo pipefail

artifact="${1:-}"
[[ -f "$artifact" ]] || exit 2
file_output="$(file -b "$artifact")"
[[ "$file_output" == *"ELF 64-bit LSB executable"* ]]
[[ "$file_output" == *"x86-64"* ]]
[[ "$file_output" == *"statically linked"* ]]
if readelf -l "$artifact" | grep -q INTERP; then
    exit 3
fi
if readelf -d "$artifact" 2>/dev/null | grep -q NEEDED; then
    exit 4
fi
command -v clamscan >/dev/null
clamscan --no-summary "$artifact"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
scan_version="$(clamscan --version | head -n 1)"
python3 "$script_dir/update_video_manifest.py" linux-x86_64 "$artifact" --scan "$scan_version"
