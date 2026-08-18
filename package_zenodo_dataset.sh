#!/bin/bash

input="/links/groups/liberali/ldp_dev/data_zenodo"
output="/links/groups/liberali/ldp_dev/data_zenodo_zip"

mkdir -p "$output"

for dir in "$input"/*/; do
    name=$(basename "$dir")
    zip -r "$output/$name.zip" "$dir"
done