#!/usr/bin/env bash
set -euo pipefail

INPUT_BASE="/links/groups/liberali/ldp_dev/data_zarr/Max/002"
OUTPUT_BASE="/links/groups/liberali/ldp_dev/data_zenodo"

for dataset in tiny "tiny-lowT" "tini-varT" "mini" "mini-lowT" "mini-varT"; do
    echo "=== Exporting $dataset ==="
    export-zenodo-dataset "$INPUT_BASE" "$OUTPUT_BASE" -n "$dataset" --overwrite
done
