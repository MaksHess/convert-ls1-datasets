from __future__ import annotations

import math
from pathlib import Path

import rich_click as click


@click.command()
@click.argument(
    "ome_zarr_path", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
@click.argument(
    "geff_path", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
@click.option(
    "--label-name",
    default=None,
    help="Name of the label image in CONTAINER. Required if the container has more than one label.",
)
@click.option(
    "--level",
    type=str,
    default="0",
    help="Multiscale level as a string in the OME-Zarr container, e.g., '0'",
)
@click.option(
    "--overwrite/--no-overwrite",
    default=False,
    show_default=True,
    help="Overwrite existing radius/ellipsoid properties on GEFF_PATH.",
)
def main(
    ome_zarr_path: Path,
    geff_path: Path,
    label_name: str | None,
    level: str,
    overwrite: bool,
) -> None:
    """Compute per-node radius and ellipsoid properties from a label image and add them to a geff graph.

    CONTAINER is an OME-Zarr container holding the label image. GEFF_PATH is the geff
    graph, updated in place.
    """
    add_radius_and_ellipsoid_to_geff(
        ome_zarr_path,
        geff_path,
        label_name=label_name,
        level=level,
        overwrite=overwrite,
    )


def add_radius_and_ellipsoid_to_geff(
    container: Path,
    geff_path: Path,
    label_name: str | None = None,
    level: str = "0",
    overwrite: bool = False,
) -> None:
    import ngio
    import numpy as np
    from skimage.measure import regionprops

    from track_io import (
        LABEL_ID_COLUMN,
        TIME_INDEX_COLUMN,
        add_radius_and_ellipsoid,
        read_geff,
        write_geff,
    )

    ome_zarr_container = ngio.open_ome_zarr_container(container)
    labels = ome_zarr_container.list_labels()
    if label_name is None:
        if len(labels) != 1:
            raise click.BadParameter(
                f"Container has {len(labels)} labels ({labels}); specify one with --label-name.",
                param_hint="--label-name",
            )
        label_name = labels[0]

    label_image = ome_zarr_container.get_label(label_name, path=level)
    label_dask = label_image.get_as_dask()  # (t, z, y, x)
    pixel_size = label_image.pixel_size
    spacing = np.array([pixel_size.z, pixel_size.y, pixel_size.x])
    voxel_volume = float(spacing.prod())
    eps = float((spacing.min() / 10) ** 2)

    graph, meta = read_geff(geff_path, return_metadata=True)

    nodes_by_frame: dict[int, list[int]] = {}
    for node_id in graph.node_indices():
        nodes_by_frame.setdefault(graph[node_id][TIME_INDEX_COLUMN], []).append(node_id)

    radius_by_node: dict[int, float] = {}
    ellipsoid_by_node: dict[int, np.ndarray] = {}

    for t_idx, node_ids in nodes_by_frame.items():
        frame = np.asarray(label_dask[t_idx].compute())
        regions = {region.label: region for region in regionprops(frame)}
        for node_id in node_ids:
            label_id = graph[node_id][LABEL_ID_COLUMN]
            region = regions.get(label_id)
            if region is None:
                raise ValueError(
                    f"No region with label_id={label_id} found in frame t_idx={t_idx} "
                    f"(node {node_id})."
                )
            volume = region.num_pixels * voxel_volume
            radius_by_node[node_id] = (3 * volume / (4 * math.pi)) ** (1 / 3)
            coords = region.coords * spacing
            ellipsoid_by_node[node_id] = np.cov(coords, rowvar=False) + eps * np.eye(3)

    add_radius_and_ellipsoid(
        graph, radius_by_node, ellipsoid_by_node, overwrite=overwrite
    )

    meta.sphere = "radius"
    meta.ellipsoid = "ellipsoid"
    write_geff(geff_path, graph, metadata=meta, overwrite=True)
    click.echo(f"Added radius and ellipsoid properties to {geff_path}")


if __name__ == "__main__":
    main()
