"""Subsampling of 002 dataset for publication on zenodo."""

# %%
from pathlib import Path
from typing import TYPE_CHECKING

import rich_click as click

if TYPE_CHECKING:
    import ngio


DATASET_SLICES = { # for 002
    "sample": slice(90, 350),
}

DATASET_IMAGES = (
    "raw.ome.zarr",
    "denoise.ome.zarr",
    "deconv.ome.zarr",
)

DATASET_LABELS = (
    "nucleus",
    "cell",
    "lumen",
)


@click.command()
@click.argument(
    "input_dir", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
@click.argument(
    "output_dir", type=click.Path(exists=False, file_okay=False, path_type=Path)
)
@click.option(
    "--dataset-name",
    "-n",
    type=click.Choice(DATASET_SLICES.keys()),
    default="tiny",
    show_default=True,
)
@click.option(
    "--dataset-images",
    "-img",
    type=click.Choice(DATASET_IMAGES),
    multiple=True,
    default=DATASET_IMAGES,
    show_default=True,
)
@click.option("--prefix", "-p", type=str, default="", show_default=True)
@click.option(
    "--overwrite/--no-overwrite",
    default=True,
    show_default=True,
    help="Overwrite existing output.",
)
def main(
    input_dir: Path, output_dir: Path, dataset_name: str, dataset_images: tuple[str], prefix: str, overwrite: bool
) -> None:
    import ngio
    import polars as pl
    import rustworkx as rx
    from track_io import (
        read_geff_like_to_rx,
        rx_to_geff_like,
        slice_retain_edges,
        _write_geff_like,
        slice_timestamps_table,
    )

    # input_dir = Path(r"N:\ldp_dev\data_zarr\Max\002")
    # output_dir = Path(r"N:\ldp_dev\data_zenodo")

    # prefix = "intestinal-organoid-medeiros"
    # dataset_name = "mini-varT"
    slc = DATASET_SLICES[dataset_name]
    output_path = output_dir / f"{prefix}{input_dir.name}-{dataset_name}"

    for processing_step in dataset_images:
        container_path = input_dir / processing_step
        out_container_path = output_path / processing_step
        tracks_path = container_path / "tracks" / "nucleus.geff.like"

        # print(f"slicing {processing_step!r}...")
        container = ngio.open_ome_zarr_container(container_path)
        img = container.get_image("0")
        arr = img.get_as_dask()

        out_arr = arr[slc]

        # t_scale = cast(float, img.pixel_size.get("t"))
        # if isinstance(slc, slice):
        #     new_t_scale = t_scale * (1 if slc.step is None else slc.step)
        #     new_t_unit = img.time_unit
        # else:
        new_t_scale = 1.0
        new_t_unit = None

        click.echo(f"dataset: {dataset_name}")
        click.echo(f"t_scale: {new_t_scale}")
        click.echo(f"t_unit:  {new_t_unit}")
        click.echo(f"shape:   {out_arr.shape}")
        click.echo(f"from:    {container_path}")
        click.echo(f"to:      {out_container_path}")
        click.echo()

        click.echo(f"deriving image...")
        out_container = container.derive_image(
            out_container_path,
            shape=out_arr.shape,
            time_spacing=new_t_scale,
            overwrite=overwrite,
        )
        if new_t_unit is None:
            _reset_time_unit_to_frames(out_container)
        out_img = out_container.get_image("0")
        click.echo("writing array...")
        out_img.set_array(out_arr)
        click.echo("consolidating...")
        out_img.consolidate()
        click.echo("done.")
        click.echo()

        for label_name in container.list_labels():
            click.echo(f"slicing {label_name!r}...")
            out_lbl_img = out_container.derive_label(label_name, overwrite=overwrite)
            lbl_img = container.get_label(label_name, path="0")
            lbl_arr = lbl_img.get_as_dask()

            out_lbl_arr = lbl_arr[slc]
            out_lbl_img.set_array(out_lbl_arr)
            click.echo("consolidating...")
            out_lbl_img.consolidate()
            click.echo("done.")
            click.echo()

        if "timestamps" in container.list_tables():
            click.echo("slicing timestamp table...")
            table = container.get_table("timestamps")
            out_table = slice_timestamps_table(table, slc)
            out_container.add_table(name="timestamps", table=out_table, backend="parquet", overwrite=overwrite)
            click.echo("done.")
            click.echo()

        if tracks_path.exists():
            click.echo("slicing tracking graph...")
            out_tracks_path = out_container_path / "tracks" / "nucleus.geff.like"
            out_tracks_path.mkdir(parents=True, exist_ok=True)
            graph = read_geff_like_to_rx(tracks_path)
            slice_retain_edges(graph, slc)
            geff_like = rx_to_geff_like(graph)
            _write_geff_like(out_tracks_path, geff_like)
            click.echo("done.")
            click.echo()


def _reset_time_unit_to_frames(container: "ngio.OmeZarrContainer") -> None:
    attrs = container._group_handler.load_attrs()
    attrs["ome"]["multiscales"][0]["axes"][0].pop("unit")
    container._group_handler.write_attrs(attrs, overwrite=True)


if __name__ == "__main__":
    main()
