#!/usr/bin/env bash
set -euo pipefail

INPUT_BASE="/links/groups/liberali/ldp_dev/data_ls1/data_ls1"
OUTPUT_BASE="/links/groups/liberali/ldp_dev/data_zarr/Max2"

for dataset in 002; do
    echo "=== Converting $dataset ==="
    convert-ls1-datasets "$INPUT_BASE/$dataset" "$OUTPUT_BASE/$dataset" --overwrite
done
