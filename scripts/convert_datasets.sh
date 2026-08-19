#!/usr/bin/env bash
set -euo pipefail

INPUT_BASE="/links/groups/liberali/ldp_dev/data_ls1/data_ls1"
OUTPUT_BASE="/links/groups/liberali/ldp_dev/data_zarr/Max"

for dataset in 001 000 002 003 006 007 009; do
    echo "=== Converting $dataset ==="
    convert-ls1-dataset "$INPUT_BASE/$dataset" "$OUTPUT_BASE/$dataset" --overwrite
done
