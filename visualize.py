import rustworkx as rx
import polars as pl
from rustworkx.visualization import mpl_draw
import colorcet as cc

def draw(
    graph: rx.PyDiGraph,
    pos_x="t_idx",
    pos_y="dendrogram_uniform",
    color="track_id",
    cmap="cet_glasbey",
    **kwargs,
) -> None:
    df = pl.DataFrame(graph.nodes())
    df_pos = df.select(pos_x, pos_y)
    color_arr = df[color]
    pos = {k: v for k, v in zip(graph.node_indices(), df_pos.rows())}
    return mpl_draw(graph, pos=pos, node_size=3, node_color=color_arr, cmap=cmap, **kwargs)
