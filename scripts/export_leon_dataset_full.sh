#!/usr/bin/env bash
set -euo pipefail

INPUT_BASE="/links/groups/liberali/ldp_dev/data_zarr/Max"
OUTPUT_BASE="/links/groups/liberali/ldp_dev/data_zarr/Leon/full"

for dataset_id in 001 002; do
    echo "=== Exporting $dataset_id ==="
    export-leon-dataset "$INPUT_BASE/$dataset_id" "$OUTPUT_BASE" -n "full" -img "deconv.ome.zarr" --overwrite
done

for dataset_dir in "$OUTPUT_BASE"/*/; do
    echo "=== Converting $dataset_dir ==="
    convert-geff-like-to-geff "$dataset_dir" --overwrite
done
