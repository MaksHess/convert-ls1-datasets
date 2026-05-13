# %%
import polars as pl
import rustworkx as rx
import pandas as pd
from pathlib import Path
import math

FEATURE_ALIASES: dict[str, str | None] = {
    "mamut_id": "mamut_node_id",
    "mamut_parent_id": "mamut_parent_node_id",
    "mamut_t": "t_id",
    "time": "t",
    "mamut_z": "z",
    "mamut_y": "y",
    "mamut_x": "x",
    "label_id": None,
    "nuclei_volume": None,
    "nuclei_mean_radius": None,
    "nuclei_max_radius": None,
    "nuclei_dist_to_basal_mean": None,
    "nuclei_dist_to_lumen_mean": None,
    "nuclei_nuclei_intensity_mean": None,
    "cell_volume": None,
    "cell_mean_radius": None,
    "cell_max_radius": None,
    # "cell_neighbors": None,
    "dendogram_symmetric": None,
    "dendogram_uniform": None,
    "generation": None,
    "branch_id": "lstree_branch_id",
    "merge": None,
    "merged_track": None,
}


EDGE_TYPES = ["TRACK", "SPLIT", "MERGE"]


def _build_selector(feature_aliases: dict[str, str | None]):
    return [
        pl.col(k).alias(v) if v is not None else pl.col(k)
        for k, v in feature_aliases.items()
    ]


def load_lstree_h5(
    table_path: Path, features: dict[str, str | None] | None = None
) -> tuple[pl.DataFrame, pl.DataFrame, dict[int, list[int]]]:
    if features is None:
        features = FEATURE_ALIASES
    _df_edges = pd.read_hdf(table_path, key="edges")
    _df_nodes = pd.read_hdf(table_path, key="nodes")

    rx_graph = to_rx_graph(_df_nodes, _df_edges, features=features)
    rx_graph, tracklet_graph = add_tracklet_ids(rx_graph)

    df_nodes = pl.DataFrame(rx_graph.nodes())
    df_edges = pl.DataFrame(
        list(rx_graph.edge_list()), orient="row", schema=["node_start", "node_end"]
    ).with_columns(
        pl.DataFrame(
            rx_graph.edges(),
            schema={"displacement": pl.Float64, "edge_type": pl.Enum(EDGE_TYPES)},
        )
    )
    return (
        df_nodes.with_columns(
            *compute_circular_dendogram("t_id", "dendogram_symmetric"),
            *compute_circular_dendogram("t_id", "dendogram_uniform"),
        ),
        df_edges,
        tracklet_graph,
    )


def load_lstree_h5_to_rx(
    table_path: Path, features: dict[str, str | None] | None = None
) -> rx.PyDiGraph:
    if features is None:
        features = FEATURE_ALIASES
    _df_edges = pd.read_hdf(table_path, key="edges")
    _df_nodes = pd.read_hdf(table_path, key="nodes")

    return to_rx_graph(_df_nodes, _df_edges, features=features)


def to_rx_graph(
    df_nodes: pd.DataFrame,
    df_edges: pd.DataFrame,
    features: dict[str, str | None],
) -> rx.PyDiGraph:
    rx_df_nodes = (
        pl.DataFrame(df_nodes)
        .with_row_index(name="rx_node_id")
        .with_columns(pl.col("mamut_t") - 1)
        .select(
            "rx_node_id",
            *_build_selector(features),
            pl.col("label_id").alias("seg_label_id"),
        )
    )

    rx_df_edges = (
        pl.DataFrame(df_edges)
        .join(
            rx_df_nodes.select("rx_node_id", "mamut_node_id"),
            left_on="node_start",
            right_on="mamut_node_id",
        )
        .rename({"rx_node_id": "rx_node_start"})
        .join(
            rx_df_nodes.select("rx_node_id", "mamut_node_id"),
            left_on="node_stop",
            right_on="mamut_node_id",
        )
        .rename({"rx_node_id": "rx_node_stop"})
    )

    rx_graph = rx.PyDiGraph()
    rx_graph.add_nodes_from(rx_df_nodes.iter_rows(named=True))
    for start, stop, displacement in rx_df_edges.select(
        "rx_node_start", "rx_node_stop", "displacement"
    ).iter_rows():
        rx_graph.add_edge(
            start, stop, {"displacement": displacement, "edge_type": "TRACK"}
        )
    return rx_graph


def add_tracklet_ids(
    rx_graph: rx.PyDiGraph,
) -> tuple[rx.PyDiGraph, dict[int, list[int]]]:
    tracklet_graph = rx_graph.copy()

    root_node_ids = []
    split_node_ids = []
    merge_node_ids = []

    for node_idx in rx_graph.node_indices():
        if rx_graph.in_degree(node_idx) == 0:
            root_node_ids.append(node_idx)
        if rx_graph.in_degree(node_idx) > 1:
            merge_node_ids.append(node_idx)
            for edge in rx_graph.in_edges(node_idx):
                tracklet_graph.remove_edge(*edge[:2])
            # tracklet_graph.remove_edge(*rx_graph.in_edges(node_idx)[0][:2])
        if rx_graph.out_degree(node_idx) > 1:
            split_node_ids.append(node_idx)
            for edge in rx_graph.out_edges(node_idx):
                tracklet_graph.remove_edge(*edge[:2])
            # tracklet_graph.remove_edge(*rx_graph.out_edges(node_idx)[0][:2])

    for tracklet_id, node_ids in enumerate(
        rx.connected_components(tracklet_graph.to_undirected())
    ):
        for node_id in node_ids:
            rx_graph[node_id]["track_id"] = tracklet_id
            rx_graph[node_id]["is_root_node"] = int(node_id in root_node_ids)
            rx_graph[node_id]["is_split_node"] = int(node_id in split_node_ids)
            rx_graph[node_id]["is_merge_node"] = int(node_id in merge_node_ids)

    tracklet_graph = {}
    for split_node_id in split_node_ids:
        for edge in rx_graph.out_edges(split_node_id):
            tracklet_parent = rx_graph[edge[0]]["track_id"]
            tracklet_child = rx_graph[edge[1]]["track_id"]
            tracklet_graph.setdefault(tracklet_child, []).append(tracklet_parent)

            edge_data = rx_graph.get_edge_data(*edge[:2])
            edge_data["edge_type"] = "SPLIT"
            # tracklet_graph[tracklet_child] = [tracklet_parent]
    for merge_node_id in merge_node_ids:
        for edge in rx_graph.in_edges(merge_node_id):
            tracklet_parent = rx_graph[edge[0]]["track_id"]
            tracklet_child = rx_graph[edge[1]]["track_id"]
            tracklet_graph.setdefault(tracklet_child, []).append(tracklet_parent)

            edge_data = rx_graph.get_edge_data(*edge[:2])
            edge_data["edge_type"] = "MERGE"
    return rx_graph, tracklet_graph


def compute_circular_dendogram(t: str, dendogram: str, scale: float = 0.95) -> list[pl.Expr]:
    return [
        (
            pl.col(t)
            * (pl.col(dendogram) / pl.col(dendogram).max() * scale * 2 * math.pi).cos()
        ).alias(f"circ_{dendogram}_x"),
        (
            pl.col(t)
            * (pl.col(dendogram) / pl.col(dendogram).max() * scale * 2 * math.pi).sin()
        ).alias(f"circ_{dendogram}_y"),
    ]
