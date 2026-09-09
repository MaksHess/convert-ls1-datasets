from __future__ import annotations

from pathlib import Path

import rich_click as click


@click.command()
@click.argument(
    "ome_path", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
@click.option(
    "--label-name",
    type=str,
    required=True,
    help="Name of the label image in the container.",
)
@click.option(
    "--label-id",
    type=int,
    required=True,
    help="Label id to compute the per-frame bounding box for.",
)
@click.option(
    "--level",
    type=str,
    default="0",
    show_default=True,
    help="Multiscale level as a string in the OME-Zarr container, e.g., '0'",
)
@click.option(
    "--overwrite/--no-overwrite",
    default=False,
    show_default=True,
    help="Overwrite an existing ROI table of the same name.",
)
def main(
    ome_path: Path,
    label_name: str,
    label_id: int,
    level: str,
    overwrite: bool,
) -> None:
    """Write a per-frame bounding-box ROI table for a label to an OME-Zarr container.

    OME_PATH is the OME-Zarr container holding the label image. For each timepoint,
    computes the bounding box (in physical/world coordinates) of the pixels matching
    LABEL_ID in the LABEL_NAME label image, and writes them as an ngio RoiTable
    indexed by t_idx, named '<label-name>-<label-id>-roi'.
    """
    add_roi_table_to_ome_zarr(
        ome_path,
        label_name=label_name,
        label_id=label_id,
        level=level,
        overwrite=overwrite,
    )


def add_roi_table_to_ome_zarr(
    ome_path: Path,
    label_name: str,
    label_id: int,
    level: str = "0",
    overwrite: bool = False,
) -> None:
    import ngio
    from ngio.common import Roi
    from ngio.tables import RoiTable
    from ngio.tables.v1 import RoiTableV1Meta
    from scipy.ndimage import find_objects

    container = ngio.open_ome_zarr_container(ome_path)
    labels = container.list_labels()
    if label_name not in labels:
        raise click.BadParameter(
            f"Label '{label_name}' not found in container; available labels: {labels}.",
            param_hint="--label-name",
        )

    label_image = container.get_label(label_name, path=level)
    pixel_size = label_image.pixel_size
    axes = label_image.axes
    spatial_axes = [axis for axis in axes if axis != "t"]
    has_t_axis = "t" in axes
    n_timepoints = label_image.dimensions.get("t", 1) if has_t_axis else 1

    rois = []
    skipped_t_idxs = []
    for t_idx in range(n_timepoints):
        if has_t_axis:
            frame = label_image.get_as_numpy(t=t_idx, axes_order=spatial_axes)
        else:
            frame = label_image.get_as_numpy(axes_order=spatial_axes)

        objects = find_objects(frame, max_label=label_id)
        slice_ = objects[label_id - 1] if objects else None
        if slice_ is None:
            skipped_t_idxs.append(t_idx)
            continue

        slices = dict(zip(spatial_axes, slice_, strict=True))
        roi = Roi.from_values(name=str(t_idx), slices=slices, space="pixel")
        roi = roi.to_world(pixel_size=pixel_size)
        rois.append(roi)

    meta = RoiTableV1Meta(index_key="t_idx", index_type="int", backend="parquet")
    table = RoiTable(rois=rois, meta=meta)
    table_name = f"{label_name}-{label_id}-roi"
    container.add_table(table_name, table, backend="parquet", overwrite=overwrite)

    click.echo(
        f"Wrote {len(rois)} rows to table '{table_name}'"
        + (
            f" ({len(skipped_t_idxs)} frames skipped, label absent: {skipped_t_idxs})"
            if skipped_t_idxs
            else ""
        )
    )


if __name__ == "__main__":
    main()
