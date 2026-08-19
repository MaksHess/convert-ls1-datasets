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
    **kwargs,
):
    df = pl.DataFrame(graph.nodes())
    df_pos = df.select(pos_x, pos_y)
    color_arr = [cc.glasbey[e%len(cc.glasbey)] for e in df[color]]
    pos = {k: v for k, v in zip(graph.node_indices(), df_pos.rows())}
    return mpl_draw(
        graph, pos=pos, node_size=3, node_color=color_arr, **kwargs
    )


def plot_export_slices(
    dataset_path: Path | str,
    pos_x="t",
    pos_y="dendrogram_uniform",
    color="track_id",
    **kwargs,
):
    from track_io import slice_retain_edges, read_geff_like_to_rx
    from export_zenodo_dataset import DATASET_SLICES
    import matplotlib.pyplot as plt
    import copy

    graph = read_geff_like_to_rx(Path(dataset_path)/'deconv.ome.zarr'/'tracks'/'nucleus.geff.like')

    for name, slc in DATASET_SLICES.items():
        sub_graph = copy.deepcopy(graph)
        slice_retain_edges(sub_graph, slc)
        fig, ax = plt.subplots()
        draw(sub_graph, pos_x=pos_x, pos_y=pos_y, color=color, ax=ax)
        ax.set_title(name)