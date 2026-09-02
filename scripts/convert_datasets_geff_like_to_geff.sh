#!/usr/bin/env bash
set -euo pipefail

OUTPUT_BASE="/links/groups/liberali/ldp_dev/data_zarr/Max"

for dataset_dir in "$OUTPUT_BASE"/*/; do
    echo "=== Converting $dataset_dir ==="
    convert-geff-like-to-geff "$dataset_dir" --overwrite
done
