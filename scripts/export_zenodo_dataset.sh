#!/usr/bin/env bash
set -euo pipefail

INPUT_BASE="/links/groups/liberali/ldp_dev/data_zarr/Max/001"
OUTPUT_BASE="/links/groups/liberali/ldp_dev/zenodo/data_zenodo"

for dataset in mini "mini-lowT" "mini-varT" "small" "small-lowT" "small-varT" "full"; do
    echo "=== Exporting $dataset ==="
    export-zenodo-dataset "$INPUT_BASE" "$OUTPUT_BASE" -n "$dataset" -img "deconv.ome.zarr" -img "raw.ome.zarr" --overwrite
done

for dataset_dir in "$OUTPUT_BASE"/*/; do
    echo "=== Converting $dataset_dir ==="
    convert-geff-like-to-geff "$dataset_dir" --overwrite --remove-geff-like
done