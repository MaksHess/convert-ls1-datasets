# Conversion steps

convert_datasets.sh -> convert LSTree datasets to OME-Zarr
export_zenodo_dataset.sh -> export and sub-sample 001, convert the tracking tables to GEFF
"manually" added mips along z using `lightsheet-fusion` code (required folder renaming 🙃)
rechunk-ome-zarr-datasets /links/groups/liberali/ldp_dev/zenodo/data_zenodo .*mip-z.*
add-dca-metadata /links/groups/liberali/ldp_dev/zenodo/data_zenodo  # from `dca_meta/` provided by Mikala curated manually