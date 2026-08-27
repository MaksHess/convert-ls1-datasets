#!/usr/bin/env bash
set -euo pipefail

INPUT_BASE="/links/groups/liberali/ldp_dev/data_zarr/Max/002"
OUTPUT_BASE="/links/groups/liberali/ldp_dev/data_zarr/Leon/subsampled"

for dataset in sample; do
    echo "=== Exporting $dataset ==="
    export-leon-dataset "$INPUT_BASE" "$OUTPUT_BASE" -n "$dataset" -img "deconv.ome.zarr" --overwrite
done

for dataset_dir in "$OUTPUT_BASE"/*/; do
    echo "=== Converting $dataset_dir ==="
    convert-geff-like-to-geff "$dataset_dir" --overwrite
done