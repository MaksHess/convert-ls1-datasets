# %%
import rustworkx as rx
import polars as pl
from rustworkx.visualization import mpl_draw
import colorcet as cc
from pathlib import Path


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
    **kwargs,
):
    from track_io import slice_retain_edges, read_geff_like_to_rx
    from export_zenodo_dataset import DATASET_SLICES
    import matplotlib.pyplot as plt
    import copy

    STYLES = {
        'full': {'node_size': 1.5, 'width': 0.5, 'arrow_size': 2.0},
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
            fig.savefig(output_path / f"{name}.jpg")



# plot_export_slices(r"N:\ldp_dev\data_zarr\Max\001")
