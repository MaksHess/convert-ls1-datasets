#!/bin/bash
set -euo pipefail

input="/links/groups/liberali/ldp_dev/zenodo/data_zenodo"
output="/links/groups/liberali/ldp_dev/zenodo/data_zenodo_zip"

mkdir -p "$output"

for dir in "$input"/*/; do
    name=$(basename "$dir")
    rm -f "$output/$name.zip"
    (cd "$input" && zip -r "$output/$name.zip" "$name")
done