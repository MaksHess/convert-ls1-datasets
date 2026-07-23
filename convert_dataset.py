# %%
from __future__ import annotations
from ast import Assert

from enum import StrEnum
from typing import TYPE_CHECKING, Sequence, Any
from pathlib import Path
from itertools import chain, cycle
import rich_click as click
import warnings
import polars as pl

if TYPE_CHECKING:
    from ngio.ome_zarr_meta.ngio_specs import Channel

# remapping of names applied in the output
NAMING_CONSISTENCY = {
    "Deconv": "deconv",
    "Denoise": "denoise",
    "Raw": "raw",
    "Channel0": "mem9",
    "Channel1": "H2B",
    "nuclei": "nucleus",
}

WRITE_LABELS_TO = "Deconv"
SCALE_T = 600.0
UNIT_XYZ = "micrometers"
UNIT_T = "seconds"
CHANNEL_DISPLAY_RANGE = {"Deconv": {"Channel0": (0, 27000), "Channel1": (0, 8000)}}
DEFAULT_DISPLAY_RANGE = (0, 1500)

PIXEL_SCALES = {
    "000": (2.0, 0.26, 0.26),
    "001": (2.0, 0.26, 0.26),
    "002": (2.0, 0.26, 0.26),
    "003": (2.0, 0.26, 0.26),
    "004": (2.0, 0.26, 0.26),
    "005": (2.0, 0.26, 0.26),
    "006": (2.0, 0.173333, 0.173333),
    "007": (2.0, 0.173333, 0.173333),
    "008": (2.0, 0.173333, 0.173333),
    "009": (2.0, 0.26, 0.26),
    "010": (2.0, 0.173333, 0.173333),
    "011": (2.0, 0.173333, 0.173333),
    "012": (2.0, 0.173333, 0.173333),
    "013": (2.0, 0.173333, 0.173333),
    "014": (2.0, 0.173333, 0.173333),
    "015": (2.0, 0.26, 0.26),
}

# renaming applied at the very end
NODE_SELECTOR = [
    # index
    pl.col("rx_node_id").alias("node_id"),
    # GEFF special
    pl.col("t_id").alias("t_idx"),
    "t",
    "z",
    "y",
    "x",
    "label_id",
    "track_id",  # computed here
    # additional graph stuff
    pl.col("is_root_node").cast(pl.Boolean),  # computed here
    pl.col("is_split_node").cast(pl.Boolean),  # computed here
    pl.col("is_merge_node").cast(pl.Boolean),  # computed here
    # props
    "nuclei_volume",
    "nuclei_mean_radius",
    "nuclei_max_radius",
    "nuclei_dist_to_basal_mean",
    "nuclei_dist_to_lumen_mean",
    "cell_volume",
    "cell_mean_radius",
    "cell_max_radius",
]

EDGE_SELECTOR = [
    # index
    "node_start",
    "node_end",
    # props
    "displacement",
    "edge_type",  # computed here
]


def _create_selector(d: dict[str, str | None]) -> pl.Expr:
    return [pl.col(k).alias(v) if v is not None else pl.col(k) for k, v in d.items()]


def _consistent_name(name: str) -> str:
    return NAMING_CONSISTENCY.get(name, name)


@click.command()
@click.argument("input", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("output", type=click.Path(file_okay=False, path_type=Path))
@click.option(
    "--overwrite/--no-overwrite",
    default=False,
    show_default=True,
    help="Overwrite existing output.",
)
def main(input: Path, output: Path, overwrite: bool) -> None:
    """Convert an LS1 dataset from INPUT to OME-Zarr in OUTPUT."""
    dataset_id = input.name
    if dataset_id not in PIXEL_SCALES:
        raise click.BadParameter(
            f"{dataset_id!r} not in PIXEL_SCALES. Add it or use a known dataset folder.",
            param_hint="INPUT",
        )
    scale = PIXEL_SCALES[dataset_id]
    click.echo(f"Pixel scale: {scale}")
    create_channels(input, output, scale=scale, overwrite=overwrite)
    create_labels(input, output, overwrite=overwrite)
    # add_image_roi_table(output) # not needed anymore
    create_tables(input, output)


def get_voxel_dimensions(filepath: Path | str) -> tuple[float, float, float]:
    """return z, y, x scale"""
    import xml.etree.ElementTree as ET

    root = ET.parse(filepath).getroot()
    image_data = root.find(".//ImageData")
    if image_data is None:
        raise ValueError("xml does not contain 'ImageData'")
    return (
        float(image_data.get("voxeldepth")),
        float(image_data.get("pixelheight")),
        float(image_data.get("pixelwidth")),
    )


def create_tables(root: Path | str, output: Path | str) -> None:
    import polars as pl
    from parse_ldp_ls1_data import TABLES_PATH
    from lstree_to_tracks import load_lstree_h5

    root = Path(root)
    output = Path(output)

    tbl_path = root / TABLES_PATH
    zarr_path = output / f"{_consistent_name(WRITE_LABELS_TO)}.ome.zarr"
    tables_group = zarr_path / "tracks" / "nucleus.geff.like"
    tables_group.mkdir(exist_ok=True, parents=True)

    df_nodes, df_edges, track_graph = load_lstree_h5(tbl_path)
    df_track_edges = (
        pl.DataFrame(
            list(track_graph.items()), orient="row", schema=["track_end", "track_start"]
        )
        .explode("track_start")
        .select("track_start", "track_end")
    )
    click.echo(f"Writing tables to {tables_group}")
    df_nodes.drop("t").with_columns((pl.col("t_id") * SCALE_T).alias("t")).select(
        NODE_SELECTOR
    ).write_parquet(tables_group / "nodes.parquet")
    df_edges.select(EDGE_SELECTOR).write_parquet(tables_group / "edges.parquet")
    df_track_edges.write_parquet(tables_group / "track_edges.parquet")


def add_image_roi_table(output: Path | str, overwrite: bool = True) -> None:
    import ngio

    click.echo("adding image roi table...")
    for fn in Path(output).glob("*.ome.zarr"):
        click.echo(fn.name)
        container = ngio.open_ome_zarr_container(fn)
        img_table = container.build_image_roi_table()
        container.add_table(
            "image", table=img_table, backend="parquet", overwrite=overwrite
        )


def create_channels(
    root: Path | str,
    output: Path | str,
    scale: tuple[float, float, float],
    overwrite: bool = False,
) -> None:
    import ngio
    import tifffile
    import numpy as np
    import polars as pl
    from parse_ldp_ls1_data import parse_channels, parse_labels

    root = Path(root)
    output = Path(output)
    scale_z, scale_y, scale_x = scale
    df_channels = parse_channels(Path(root))
    df_labels = parse_labels(Path(root))

    processing_steps = df_channels["processing"].unique(maintain_order=True).to_list()
    label_objects = df_labels["label_name"].unique(maintain_order=True).to_list()

    df_ch = {
        step: df_channels.filter(pl.col("processing") == step)
        for step in processing_steps
    }
    df_lbl = {
        label_object: df_labels.filter(pl.col("label_name") == label_object)
        for label_object in label_objects
    }

    if WRITE_LABELS_TO not in processing_steps:
        raise ValueError(f"{WRITE_LABELS_TO!r} not in {processing_steps!r}")

    ref_frame_shape = _validate_matching_timepoints_and_channels(root, df_ch, df_lbl)
    containers: dict[str, ngio.OmeZarrContainer] = {}
    images: dict[str, ngio.Image] = {}

    for step, df in df_ch.items():
        click.echo(f"Processing {step!r}")
        channels = df["channel"].unique(maintain_order=True).to_list()
        n_channels = len(channels)

        timepoints = df["t_id"].unique(maintain_order=True).to_list()
        n_timepoints = len(timepoints)

        shape = (n_timepoints, n_channels, *ref_frame_shape)

        shard_shape = _shape_to_shard_shape(shape)

        ngio_meta: dict[str, Any] = {
            "shape": shape,
            "pixelsize": (scale_y, scale_x),
            "z_spacing": scale_z,
            "time_spacing": SCALE_T,
            "space_unit": UNIT_XYZ,
            "time_unit": UNIT_T,
            "axes_names": ["t", "c", "z", "y", "x"],
            "channels_meta": _channel_meta(channels, processing_step=step),
            "overwrite": overwrite,
            "ngff_version": "0.5",
            "shards": None,
            "chunks": shard_shape,
        }

        containers[step] = ngio.create_empty_ome_zarr(
            output / f"{_consistent_name(step)}.ome.zarr",
            **ngio_meta,
        )
        images[step] = containers[step].get_image("0")

        for row in df.iter_rows(named=True):
            t_id = row["t_id"]
            channel = row["channel"]
            channel_id = channels.index(channel)
            click.echo(f"{channel_id=}\t{t_id=}")

            t_slice = slice(t_id, t_id + 1)
            c_slice = slice(channel_id, channel_id + 1)

            fn = root / row["path"]
            frame = tifffile.imread(fn)

            images[step].set_array(
                np.expand_dims(frame, (0, 1)),
                t=t_slice,
                c=c_slice,
            )
        click.echo("consolidating...")
        images[step].consolidate()

    # for label_object, df in df_lbl.items():
    #     print(f"Processing {label_object!r}")
    #     container = containers[WRITE_LABELS_TO]
    #     label_image = container.derive_label(label_object)

    #     for row in df.iter_rows(named=True):
    #         t_id = row["t_id"]
    #         print(f"{t_id=}")
    #         t_slice = slice(t_id, t_id + 1)

    #         fn = root / row["path"]
    #         frame = tifffile.imread(fn)

    #         label_image.set_array(np.expand_dims(frame, 0), t=t_slice)

    #     print("consolidating...")
    #     label_image.consolidate()


def create_labels(
    root: Path | str,
    output: Path | str,
    overwrite: bool = False,
) -> None:
    import ngio
    import tifffile
    import numpy as np
    import polars as pl
    from parse_ldp_ls1_data import parse_channels, parse_labels

    root = Path(root)
    output = Path(output)
    df_channels = parse_channels(Path(root))
    df_labels = parse_labels(Path(root))

    processing_steps = df_channels["processing"].unique(maintain_order=True).to_list()
    label_objects = df_labels["label_name"].unique(maintain_order=True).to_list()

    df_lbl = {
        label_object: df_labels.filter(pl.col("label_name") == label_object)
        for label_object in label_objects
    }

    if WRITE_LABELS_TO not in processing_steps:
        raise ValueError(f"{WRITE_LABELS_TO!r} not in {processing_steps!r}")

    for label_object, df in df_lbl.items():
        click.echo(f"Processing {label_object!r}")
        container = ngio.open_ome_zarr_container(
            output / f"{_consistent_name(WRITE_LABELS_TO)}.ome.zarr"
        )
        label_image = container.derive_label(
            _consistent_name(label_object), overwrite=overwrite
        )

        for row in df.iter_rows(named=True):
            t_id = row["t_id"]
            click.echo(f"{t_id=}")
            t_slice = slice(t_id, t_id + 1)

            fn = root / row["path"]
            frame = tifffile.imread(fn)

            label_image.set_array(np.expand_dims(frame, 0), t=t_slice)

        click.echo("consolidating...")
        label_image.consolidate()


class HexColors(StrEnum):
    white = "FFFFFF"
    red = "FF0000"
    green = "00FF00"
    blue = "0000FF"
    magenta = "FF00FF"
    cyan = "00FFFF"
    yellow = "FFFF00"
    black = "000000"
    gray = "808080"

    def color_cycle():
        return cycle(
            [
                HexColors.blue,
                HexColors.green,
                HexColors.red,
                HexColors.cyan,
                HexColors.magenta,
                HexColors.yellow,
            ]
        )


CHANNEL_COLORS = {
    1: (HexColors.white,),
    2: (HexColors.magenta, HexColors.green),
    3: (HexColors.blue, HexColors.green, HexColors.red),
}


def _channel_meta(channels: Sequence[str], processing_step: str) -> list[Channel]:
    from ngio.ome_zarr_meta.ngio_specs import Channel, ChannelVisualisation

    n_channels = len(channels)
    if n_channels in CHANNEL_COLORS:
        colors = CHANNEL_COLORS[n_channels]
    else:
        colors = HexColors.color_cycle()

    out = []
    for channel, color in zip(channels, colors):
        display_range = CHANNEL_DISPLAY_RANGE.get(processing_step, {}).get(
            channel, DEFAULT_DISPLAY_RANGE
        )
        out.append(
            Channel(
                label=_consistent_name(channel),
                channel_visualisation=ChannelVisualisation(
                    color=color,
                    start=display_range[0],
                    end=display_range[1],
                    active=True,
                ),
            )
        )
    return out


def _shape_to_shard_shape(
    shape: tuple[int, int, int, int, int],
) -> tuple[int, int, int, int, int]:
    return (1, 1, shape[2], shape[3], shape[4])


def _validate_matching_timepoints_and_channels(root, df_ch, df_lbl, emit_warnings=True):
    import tifffile

    df_ref = df_ch[list(df_ch.keys())[0]]
    ref_tps = df_ref["t_id"].unique(maintain_order=True).to_list()
    ref_chs = df_ref["channel"].unique(maintain_order=True).to_list()
    ref_frame = tifffile.imread(root / df_ref[0, "path"])

    if not ref_tps == list(range(len(ref_tps))):
        if emit_warnings:
            warnings.warn("Timepoints must be consecutive and 0 indexed.")
        else:
            raise AssertionError("Timepoints must be consecutive and 0 indexed.")

    for k, df in chain(df_ch.items(), df_lbl.items()):
        tps = df["t_id"].unique(maintain_order=True).to_list()
        if not len(tps) == len(ref_tps):
            if emit_warnings:
                warnings.warn(
                    f"Mismatching number of timepoints {len(ref_tps)} {len(tps)} in {k!r}."
                )
            else:
                raise AssertionError(
                    f"Mismatching number of timepoints {len(ref_tps)} {len(tps)} in {k!r}."
                )

        if not tps == ref_tps:
            if emit_warnings:
                warnings.warn(f"Timepoint mismatch in {k!r}.")
            else:
                raise AssertionError(f"Timepoint mismatch in {k!r}.")

        frame = tifffile.imread(root / df[0, "path"])

        if not ref_frame.shape == frame.shape:
            if emit_warnings:
                warnings.warn(f"Shape mismatch: {ref_frame.shape} {frame.shape} in {k}")
            else:
                raise AssertionError(
                    f"Shape mismatch: {ref_frame.shape} {frame.shape} in {k}"
                )

    for k, df in df_ch.items():
        if not all(ref_chs == df["channel"].unique(maintain_order=True)):
            if emit_warnings:
                warnings.warn(
                    f"Channel mismatch {ref_chs} {df['channel'].unique(maintain_order=True)} in {k}."
                )
            else:
                raise AssertionError(
                    f"Channel mismatch {ref_chs} {df['channel'].unique(maintain_order=True)} in {k}."
                )

    return ref_frame.shape


if __name__ == "__main__":
    main()
