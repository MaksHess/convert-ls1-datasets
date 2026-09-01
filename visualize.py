# %%
import rustworkx as rx
import polars as pl
from rustworkx.visualization import mpl_draw
import colorcet as cc
from pathlib import Path

ORIGINAL_T_IDX_COLOR = "#212232"
SLICE_T_IDX_COLOR = "#275FA1"


def _draw_multicolor_label(ax, segments, fontsize=10, pad_points=18):
    """Draw a centered x-axis label made of differently-colored segments.

    segments: list of (text, color) pairs, concatenated left to right.
    """
    from matplotlib.transforms import offset_copy

    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    trans = offset_copy(ax.transAxes, fig=fig, x=0, y=-pad_points, units="points")

    texts = [
        ax.text(0, 0, text, transform=trans, color=color, fontsize=fontsize,
                 ha="left", va="top", clip_on=False)
        for text, color in segments
    ]
    widths = [t.get_window_extent(renderer=renderer).width for t in texts]
    axes_x0, _ = ax.transAxes.transform((0, 0))
    axes_x1, _ = ax.transAxes.transform((1, 0))
    axes_width = axes_x1 - axes_x0

    cur = 0.5 - (sum(widths) / 2) / axes_width
    for t, w in zip(texts, widths):
        t.set_position((cur, 0))
        cur += w / axes_width


def draw(
    graph: rx.PyDiGraph,
    pos_x="t_idx",
    pos_y="dendrogram_uniform",
    color="track_id",
    node_size=3,
    **kwargs,
):
    df = pl.DataFrame(graph.nodes())
    df_pos = df.select(pos_x, pos_y)
    color_arr = [cc.glasbey[e%len(cc.glasbey)] for e in df[color]]
    pos = {k: v for k, v in zip(graph.node_indices(), df_pos.rows())}
    return mpl_draw(
        graph, pos=pos, node_size=node_size, node_color=color_arr, **kwargs
    )


def plot_export_slices(
    dataset_path: Path | str,
    pos_x="t",
    pos_y="dendrogram_uniform",
    color="track_id",
    output_path: Path | None = Path('images'),
    high_res: bool = False,
    **kwargs,
):
    from track_io import slice_retain_edges, read_geff_like_to_rx
    from export_zenodo_dataset import DATASET_SLICES
    import matplotlib.pyplot as plt
    import copy

    STYLES = {
        'full': {'node_size': 0.5, 'width': 0.5, 'arrow_size': 2.0},
        'small': {'node_size': 3, 'width': 1, 'arrow_size': 4.0},
        'mini': {'node_size': 30, 'width': 1, 'arrow_size': 10}
    }

    graph = read_geff_like_to_rx(Path(dataset_path)/'deconv.ome.zarr'/'tracks'/'nucleus.geff.like')

    for name, slc in DATASET_SLICES.items():
        sub_graph = copy.deepcopy(graph)
        slice_retain_edges(sub_graph, slc)

        style = STYLES[name.split('-')[0]]
        fig, ax = plt.subplots(figsize=(4, 3), dpi=150)
        draw(sub_graph, pos_x=pos_x, pos_y=pos_y, color=color, ax=ax, **style, **kwargs)
        if output_path is None:
            ax.set_title(name)
        else:
            output_path.mkdir(exist_ok=True)
            fig.savefig(output_path / f"{name}.jpg")


def plot_export_slice_with_axis(
    dataset_path: Path | str,
    slice_name: str,
    pos_x="t",
    pos_y="dendrogram_uniform",
    color="track_id",
    output_path: Path | None = None,
    max_ticks: int = 5,
    show_slice_idx: bool = True,
    **kwargs,
):
    """Like plot_export_slices, but for a single named slice, with a bottom
    axis showing the compact (reset) t_idx and a top axis showing the
    original t_idx, both positioned by physical time (pos_x).

    show_slice_idx: also plot the compact per-slice index below the original
    index. Set to False when the slice is the full dataset, where the two
    are redundant.
    """
    from track_io import slice_retain_edges, read_geff_like_to_rx, _slice_to_indices
    from export_zenodo_dataset import DATASET_SLICES
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    import numpy as np
    import copy

    STYLES = {
        'full': {'node_size': 0.5, 'width': 0.5, 'arrow_size': 2.0},
        'small': {'node_size': 3, 'width': 1, 'arrow_size': 4.0},
        'mini': {'node_size': 30, 'width': 1, 'arrow_size': 10}
    }

    graph = read_geff_like_to_rx(Path(dataset_path)/'deconv.ome.zarr'/'tracks'/'nucleus.geff.like')
    slc = DATASET_SLICES[slice_name]

    # keep the original t_idx values around instead of collapsing them to 0..N-1,
    # so we can label the top axis with them
    sub_graph = copy.deepcopy(graph)
    slice_retain_edges(sub_graph, slc, reset_index=False)

    # mirrors slice_retain_edges(reset_index=True)'s own numbering
    full_extent = max(n["t_idx"] for n in graph.nodes()) + 1
    indices = _slice_to_indices(slc, full_extent)
    compact_of = {orig: i for i, orig in enumerate(indices)}

    style = STYLES[slice_name.split('-')[0]]
    fig, ax = plt.subplots(figsize=(4, 3), dpi=300)
    draw(sub_graph, pos_x=pos_x, pos_y=pos_y, color=color, ax=ax, **style, **kwargs)

    df = (
        pl.DataFrame(sub_graph.nodes())
        .select(pos_x, "t_idx")
        .unique()
        .sort(pos_x)
    )
    xs = df[pos_x].to_numpy()
    original_ticks = df["t_idx"].to_numpy()
    compact_ticks = np.array([compact_of[v] for v in original_ticks])

    # pick a handful of evenly-spaced candidate positions, then snap each to
    # the nearest timepoint that actually exists in this slice
    candidates = mticker.MaxNLocator(nbins=max_ticks).tick_values(xs.min(), xs.max())
    nearest = np.abs(xs[:, None] - candidates[None, :]).argmin(axis=0)
    tick_idx = np.unique(nearest)
    tick_x = xs[tick_idx]

    ax.set_axis_on()
    # draw_nodes() (called via draw() above) hides all ticks/labels via
    # tick_params(bottom=False, labelbottom=False, ...); undo that for x, but
    # suppress the default text labels since we draw our own below
    ax.tick_params(axis="x", which="both", bottom=True, labelbottom=False)
    for spine in ("left", "right", "top"):
        ax.spines[spine].set_visible(False)
    ax.set_yticks([])
    ax.set_xticks(tick_x)

    # both readings below the axis line, original stacked directly above
    # slice (like "20\n0"), distinguished by color
    fontsize = 8
    line_height = fontsize * 1.2
    rows = [(original_ticks[tick_idx], ORIGINAL_T_IDX_COLOR)]
    if show_slice_idx:
        rows.append((compact_ticks[tick_idx], SLICE_T_IDX_COLOR))

    for x, *values in zip(tick_x, *(vals for vals, _ in rows)):
        for row, ((_, color), value) in enumerate(zip(rows, values)):
            ax.annotate(
                str(value),
                xy=(x, 0),
                xycoords=("data", "axes fraction"),
                xytext=(0, -6 - row * line_height),
                textcoords="offset points",
                ha="center",
                va="top",
                fontsize=fontsize,
                color=color,
            )

    if show_slice_idx:
        label_segments = [
            ("t_idx (", "black"),
            ("full", ORIGINAL_T_IDX_COLOR),
            ("/", "black"),
            (slice_name, SLICE_T_IDX_COLOR),
            (")", "black"),
        ]
    else:
        label_segments = [("t_idx (", "black"), ("full", ORIGINAL_T_IDX_COLOR), (")", "black")]

    _draw_multicolor_label(
        ax,
        label_segments,
        pad_points=6 + len(rows) * line_height + 10,
    )

    ax.set_title(slice_name, fontweight="bold")
    if output_path is not None:
        output_path = Path(output_path)
        output_path.mkdir(exist_ok=True)
        fig.savefig(output_path / f"{slice_name}.png", bbox_inches="tight")
    return fig, ax


def export_highres(
    dataset_path: Path | str,
    output_path: Path = Path('images_highres'),
):
    from export_zenodo_dataset import DATASET_SLICES
    for dataset_name in DATASET_SLICES:
        print(dataset_name)
        if dataset_name == 'full':
            show_slice_idx=False
        else:
            show_slice_idx=True
        if dataset_name == 'small-varT':
            max_ticks = 6
        else:
            max_ticks = 5
        plot_export_slice_with_axis(dataset_path, slice_name=dataset_name, output_path=output_path, show_slice_idx=show_slice_idx, max_ticks=max_ticks)
# %%
export_highres(r"N:\ldp_dev\data_zarr\Max\001")

# %%
