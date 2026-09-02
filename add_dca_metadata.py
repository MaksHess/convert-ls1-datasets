"""Attach DCA metadata to already-exported zenodo dataset images."""

import copy
import json
from pathlib import Path

import rich_click as click

from export_zenodo_dataset import DATASET_SLICES

DCA_META_DIR = Path(__file__).parent / "dca_meta"


@click.command()
@click.argument(
    "dataset_dir", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
def main(dataset_dir: Path) -> None:
    import ngio

    for variant_dir in sorted(p for p in dataset_dir.iterdir() if p.is_dir()):
        dataset_id, sep, dataset_name = variant_dir.name.partition("-")
        if not sep or dataset_name not in DATASET_SLICES:
            click.echo(f"warning: could not determine dataset name for {variant_dir.name!r}, skipping.")
            continue
        slc = DATASET_SLICES[dataset_name]

        for container_dir in sorted(p for p in variant_dir.iterdir() if p.is_dir() and p.name.endswith(".ome.zarr")):
            step = container_dir.name.removesuffix(".ome.zarr")
            dca_meta = _combine_dca_metadata(DCA_META_DIR, dataset_id, step)
            if dca_meta is None:
                click.echo(f"warning: no DCA metadata found for {step!r} ({container_dir}), skipping.")
                continue

            click.echo(f"writing DCA metadata to {container_dir}...")
            sliced_dca_meta = _slice_dca_metadata(dca_meta, slc)
            container = ngio.open_ome_zarr_container(container_dir)
            attrs = container._group_handler.load_attrs()
            attrs["dca"] = sliced_dca_meta
            container._group_handler.write_attrs(attrs, overwrite=True)
            click.echo("done.")


def _load_dca_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)["dca"]


def _combine_dca_metadata(meta_dir: Path, dataset_id: str, step: str) -> dict | None:
    base = _load_dca_json(meta_dir / f"{dataset_id}.json")
    override = _load_dca_json(meta_dir / f"{dataset_id}-{step}.json")
    if base is None or override is None:
        return None
    return {**copy.deepcopy(base), **copy.deepcopy(override)}


def _slice_dca_metadata(dca_meta: dict, slc: "slice | list[int]") -> dict:
    from track_io import _slice_to_indices

    dca_meta = copy.deepcopy(dca_meta)
    for key, channel_stats in dca_meta.get("normalization_statistics", {}).items():
        if key == "metadata" or "timepoint_statistics" not in channel_stats:
            continue
        tp_stats = channel_stats["timepoint_statistics"]
        indices = _slice_to_indices(slc, extent=max(int(k) for k in tp_stats) + 1)
        channel_stats["timepoint_statistics"] = {
            str(new_idx): tp_stats[str(old_idx)] for new_idx, old_idx in enumerate(indices)
        }

    timestamps = dca_meta.get("acquisition", {}).get("timestamps")
    if timestamps is not None:
        indices = _slice_to_indices(slc, extent=len(timestamps))
        dca_meta["acquisition"]["timestamps"] = [timestamps[old_idx] for old_idx in indices]

    return dca_meta


if __name__ == "__main__":
    main()
