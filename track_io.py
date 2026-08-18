# %%
import math
from enum import StrEnum
from pathlib import Path
from typing import Final, Literal, TypeGuard, TypeVar

from ngio.tables import GenericTable
from ngio.tables.backends import BackendMeta

import geff
import polars as pl
import rustworkx as rx
from geff_spec import PropMetadata
from geff_spec._axis import AxisType, SpaceUnits, TimeUnits

T = TypeVar("T")

type GeffLike = tuple[pl.DataFrame, pl.DataFrame]

type NodesGraph = rx.PyDiGraph
type TracksGraph = rx.PyDiGraph


class EdgeType(StrEnum):
    TRACK = "TRACK"
    SPLIT = "SPLIT"
    MERGE = "MERGE"


# GEFF-like parquet files for nodes graph
NODES_FILE_NAME: Final[str] = "nodes.parquet"
EDGES_FILE_NAME: Final[str] = "edges.parquet"
# GEFF-like parquet files for tracks graph
TRACK_NODES_FILE_NAME: Final[str] = "track_nodes.parquet"
TRACK_EDGES_FILE_NAME: Final[str] = "track_edges.parquet"

# Attribute name for persistent node ID's in rustworkx.PyDiGraph
PERSISTENT_NODE_ID_ATTR: Final[str] = "to_rx_id_map"

# GEFF-like node columns
NODE_ID_COLUMN: Final[str] = "node_id"
TRACK_ID_COLUMN: Final[str] = "track_id"
LINEAGE_ID_COLUMN: Final[str] = "lineage_id"
LABEL_ID_COLUMN: Final[str] = "label_id"
TIME_INDEX_COLUMN: Final[str] = "t_idx"
Z_COLUMN: Final[str] = "z"
Y_COLUMN: Final[str] = "y"
X_COLUMN: Final[str] = "x"

# GEFF-like edges columns
EDGE_ID_COLUMN_START: Final[str] = "node_start"
EDGE_ID_COLUMN_END: Final[str] = "node_end"
EDGE_TYPE_COLUMN: Final[str] = "edge_type"

# GEFF-like track_node columns
TRACK_NODE_ID_COLUMN: Final[str] = TRACK_ID_COLUMN
GENERATION_COLUMN: Final[str] = "generation"


# GEFF-like track_edges columns
TRACK_EDGE_ID_COLUMN_START: Final[str] = "track_start"
TRACK_EDGE_ID_COLUMN_END: Final[str] = "track_end"

DEFAULT_AXES_NAMES: tuple[str, str, str, str] = (
    TIME_INDEX_COLUMN,
    Z_COLUMN,
    Y_COLUMN,
    X_COLUMN,
)
DEFAULT_AXES_UNITS: tuple[TimeUnits, SpaceUnits, SpaceUnits, SpaceUnits] = (
    "frame",
    "micrometer",
    "micrometer",
    "micrometer",
)
DEFAULT_AXES_TYPES: tuple[AxisType, AxisType, AxisType, AxisType] = (
    "time",
    "space",
    "space",
    "space",
)

POLARS_DTYPE_TO_STR: dict[type[pl.DataType], str] = {
    pl.Int8: "int8",
    pl.Int16: "int16",
    pl.Int32: "int32",
    pl.Int64: "int64",
    pl.UInt8: "uint8",
    pl.UInt16: "uint16",
    pl.UInt32: "uint32",
    pl.UInt64: "uint64",
    pl.Float32: "float32",
    pl.Float64: "float64",
    pl.Boolean: "bool",
    pl.String: "str",
}


def prop_metadata_from_polars(
    s: pl.Series, unit: str | None = None, description: str | None = None
) -> PropMetadata:
    if s.dtype not in POLARS_DTYPE_TO_STR:
        raise TypeError(f"Unsupported polars dtype: {s.dtype}")

    return PropMetadata(
        identifier=s.name,
        dtype=POLARS_DTYPE_TO_STR[s.dtype],
        varlength=False,
        unit=unit,
        name=s.name,
        description=description,
    )


def is_di_graph(graph: rx.PyGraph | rx.PyDiGraph) -> TypeGuard[rx.PyDiGraph]:
    return isinstance(graph, rx.PyDiGraph)


def invert_map(d: dict[T, T]) -> dict[T, T]:
    return dict([e[::-1] for e in d.items()])


def _read_geff_like(path: str | Path) -> GeffLike:
    if not (Path(path) / NODES_FILE_NAME).exists():
        raise ValueError(f"Missing {NODES_FILE_NAME!r} in {path}")

    if not (Path(path) / EDGES_FILE_NAME).exists():
        raise ValueError(f"Missing {EDGES_FILE_NAME!r} in {path}")

    df_nodes = pl.read_parquet(Path(path) / NODES_FILE_NAME)
    df_edges = pl.read_parquet(Path(path) / EDGES_FILE_NAME)
    return df_nodes, df_edges


def _write_geff_like(path: str | Path, dfs: GeffLike) -> None:
    Path(path).mkdir(exist_ok=True)
    df_nodes, df_edges = dfs

    df_nodes.write_parquet(Path(path) / NODES_FILE_NAME)
    df_edges.write_parquet(Path(path) / EDGES_FILE_NAME)


def read_geff(path: str | Path) -> rx.PyDiGraph:
    graph, meta = geff.read(path, backend="rustworkx")
    # sort node data based on meta.node_props_metadata
    props_order = list(meta.node_props_metadata.keys())
    for node_index in graph.node_indices():
        data = graph[node_index]
        graph[node_index] = {k: data[k] for k in props_order if k in data}

    if is_di_graph(graph):
        return graph
    else:
        raise TypeError("Only directed GEFF graphs are supported.")

def write_geff(
    path: str | Path,
    graph: rx.PyDiGraph,
    metadata: geff.GeffMetadata | None = None,
    axis_names: tuple[str, ...] = DEFAULT_AXES_NAMES,
    axis_units: tuple[str, ...] = DEFAULT_AXES_UNITS,
    axis_types: tuple[AxisType, ...] = DEFAULT_AXES_TYPES,
    zarr_format: Literal[2, 3] = 3,
    overwrite: bool = True,
) -> None:

    # node id mapping from rx to geff. If no mapping is stored under
    # graph.attrs[PERSISTENT_NODE_ID_ATTR] write geff with rx node ids.
    if isinstance(graph.attrs, dict) and PERSISTENT_NODE_ID_ATTR in graph.attrs:
        to_rx_id_map = graph.attrs[PERSISTENT_NODE_ID_ATTR]
        from_rx_id_map = invert_map(to_rx_id_map)
    else:
        from_rx_id_map = None

    first_node = graph[graph.node_indices()[0]]

    _axis_names = [e for e in axis_names if e in first_node]
    _axis_units = [axis_units[axis_names.index(e)] for e in _axis_names]
    _axis_types = [axis_types[axis_names.index(e)] for e in _axis_names]

    # TODO: Check if this is correct!
    geff.write(
        graph,
        path,
        metadata=metadata,
        axis_names=_axis_names,
        axis_units=list(_axis_units),
        axis_types=list(_axis_types),
        zarr_format=zarr_format,
        node_id_dict=from_rx_id_map,
        overwrite=overwrite,
    )


def read_geff_like_to_rx(
    path: str | Path,
    node_id_column: str = NODE_ID_COLUMN,
    edge_id_column_start: str = EDGE_ID_COLUMN_START,
    edge_id_column_end: str = EDGE_ID_COLUMN_END,
) -> rx.PyDiGraph:
    geff_like = _read_geff_like(path)
    return geff_like_to_rx(
        geff_like,
        node_id_column=node_id_column,
        edge_id_column_start=edge_id_column_start,
        edge_id_column_end=edge_id_column_end,
    )


def geff_like_to_rx(
    dfs: GeffLike,
    node_id_column: str = NODE_ID_COLUMN,
    edge_id_column_start: str = EDGE_ID_COLUMN_START,
    edge_id_column_end: str = EDGE_ID_COLUMN_END,
) -> rx.PyDiGraph:

    df_nodes, df_edges = dfs

    df_nodes = df_nodes.with_row_index("_rx_node_id")

    to_rx_id_map: dict[int, int] = dict(
        df_nodes.select(node_id_column, "_rx_node_id").rows()
    )

    rx_graph = rx.PyDiGraph()
    # add node id mapping (rustworkx does not allow manually specifying ID's)
    rx_graph.attrs = {PERSISTENT_NODE_ID_ATTR: to_rx_id_map}
    rx_graph.add_nodes_from(
        {k: v for k, v in row.items() if v is not None}
        for row in df_nodes.drop("_rx_node_id")
        .drop(node_id_column)
        .iter_rows(named=True)
    )

    df_edges = (
        # df_edges.select(edge_id_column_start, edge_id_column_end)
        df_edges.join(
            df_nodes.select(node_id_column, "_rx_node_id"),
            left_on=edge_id_column_start,
            right_on=node_id_column,
        )
        .rename({"_rx_node_id": "_rx_node_start"})
        .join(
            df_nodes.select(node_id_column, "_rx_node_id"),
            left_on=edge_id_column_end,
            right_on=node_id_column,
        )
        .rename({"_rx_node_id": "_rx_node_end"})
    )

    for row in df_edges.iter_rows(named=True):
        start = row["_rx_node_start"]
        end = row["_rx_node_end"]
        rx_graph.add_edge(
            start,
            end,
            {
                k: v
                for k, v in row.items()
                if k
                not in [
                    "_rx_node_start",
                    "_rx_node_end",
                    edge_id_column_start,
                    edge_id_column_end,
                ]
                and v is not None
            },
        )
    return rx_graph


def rx_to_geff_like(
    graph: rx.PyDiGraph,
    node_id_column: str = NODE_ID_COLUMN,
    edge_id_column_start: str = EDGE_ID_COLUMN_START,
    edge_id_column_end: str = EDGE_ID_COLUMN_END,
) -> GeffLike:

    to_rx_id_map = graph.attrs.get(PERSISTENT_NODE_ID_ATTR, {})
    from_rx_id_map = invert_map(to_rx_id_map)

    df_nodes = pl.DataFrame(
        {node_id_column: [from_rx_id_map.get(e, e) for e in graph.node_indices()]}
    ).with_columns(pl.DataFrame(graph.nodes()).select(pl.exclude(node_id_column)))
    df_edges = pl.DataFrame(
        [
            (from_rx_id_map.get(e[0], e[0]), from_rx_id_map.get(e[1], e[1]))
            for e in graph.edge_list()
        ],
        orient="row",
        schema=(edge_id_column_start, edge_id_column_end),
    ).with_columns(
        pl.DataFrame(graph.edges()).select(
            pl.exclude(edge_id_column_start, edge_id_column_end)
        )
    )
    return df_nodes, df_edges


def _slice_to_indices(slc: slice | list[int], extent: int | None) -> list[int]:
    if not isinstance(slc, slice):
        return slc
    if slc.stop is None and extent is None:
        raise ValueError("Provide a slice with end or an extent")
    start = slc.start if slc.start else 0
    stop = slc.stop if slc.stop else extent
    step = slc.step if slc.step else 1
    return list(range(start, stop, step))


def slice_retain_edges(
    graph: rx.PyDiGraph,
    slc: slice | list[int],
    key: str = "t_idx",
    reset_index: bool = True,
) -> rx.PyDiGraph:
    indices = _slice_to_indices(slc, max([e[key] for e in graph.nodes()]) + 1)
    for node_id in graph.node_indexes():
        if graph[node_id][key] not in indices:
            graph.remove_node_retain_edges(node_id)
        else:
            if reset_index:
                old = graph[node_id][key]
                new = indices.index(old)
                graph[node_id][key] = new
    return graph


def find_root_nodes(graph: rx.PyDiGraph) -> list[int]:
    root_node_ids = []

    for node_id in graph.node_indices():
        if graph.in_degree(node_id) == 0:
            root_node_ids.append(node_id)
    return root_node_ids


def find_root_leaf_split_and_merge_nodes(
    rx_graph: rx.PyDiGraph,
) -> tuple[list[int], list[int], list[int], list[int]]:
    root_node_ids = []
    leaf_node_ids = []
    split_node_ids = []
    merge_node_ids = []

    for node_idx in rx_graph.node_indices():
        if rx_graph.in_degree(node_idx) == 0:
            root_node_ids.append(node_idx)
        if rx_graph.out_degree(node_idx) == 0:
            leaf_node_ids.append(node_idx)
        if rx_graph.in_degree(node_idx) > 1:
            merge_node_ids.append(node_idx)
        if rx_graph.out_degree(node_idx) > 1:
            split_node_ids.append(node_idx)

    return root_node_ids, leaf_node_ids, split_node_ids, merge_node_ids


def add_topological_generation(
    rx_graph: rx.PyDiGraph,
    overwrite: bool = False,
    key: str = GENERATION_COLUMN,
):
    for i, node_ids in enumerate(rx.topological_generations(rx_graph)):
        for node_id in node_ids:
            if key in rx_graph[node_id] and not overwrite:
                raise ValueError(
                    f"{key!r} exists on graph node {node_id}, set overwrite=True to overwrite."
                )
            rx_graph[node_id][key] = i


def add_track_id(
    rx_graph: rx.PyDiGraph,
    overwrite: bool = False,
    add_node_flags: bool = False,
    key: str = TRACK_ID_COLUMN,
) -> None:
    root_node_ids, leaf_node_ids, split_node_ids, merge_node_ids = (
        find_root_leaf_split_and_merge_nodes(rx_graph)
    )

    tracklet_graph = rx_graph.copy()
    # remove outgoing edges of split nodes
    for node_idx in split_node_ids:
        for edge in rx_graph.out_edges(node_idx):
            tracklet_graph.remove_edge(*edge[:2])

    # remove incoming edges of merge nodes
    for node_idx in merge_node_ids:
        for edge in rx_graph.in_edges(node_idx):
            tracklet_graph.remove_edge(*edge[:2])

    # assign track ID's (1 indexed) to weakly connected components in the original graph
    for tracklet_id, node_ids in enumerate(
        rx.weakly_connected_components(tracklet_graph), start=1
    ):
        for node_id in node_ids:
            if key in rx_graph[node_id] and not overwrite:
                raise ValueError(
                    f"{key!r} exists on graph node {node_id}, set overwrite=True to overwrite."
                )

            rx_graph[node_id][key] = tracklet_id

            if add_node_flags:
                rx_graph[node_id]["is_root_node"] = node_id in root_node_ids
                rx_graph[node_id]["is_leaf_node"] = node_id in leaf_node_ids
                rx_graph[node_id]["is_split_node"] = node_id in split_node_ids
                rx_graph[node_id]["is_merge_node"] = node_id in merge_node_ids


def add_lineage_id(
    rx_graph: rx.PyDiGraph,
    overwrite: bool = False,
    key: str = LINEAGE_ID_COLUMN,
) -> None:
    # assign lineage ID's (1 indexed) to weakly connected components
    for lineage_id, node_ids in enumerate(
        rx.weakly_connected_components(rx_graph), start=1
    ):
        for node_id in node_ids:
            if key in rx_graph[node_id] and not overwrite:
                raise ValueError(
                    f"{key!r} exists on graph node {node_id}, set overwrite=True to overwrite."
                )
            rx_graph[node_id][key] = lineage_id


def add_edge_type(
    rx_graph: rx.PyDiGraph,
    overwrite: bool = False,
    key: str = EDGE_TYPE_COLUMN,
) -> None:
    _, _, split_node_ids, merge_node_ids = find_root_leaf_split_and_merge_nodes(
        rx_graph
    )

    # set all track edge types to TRACK (default)
    for edge_index in rx_graph.edge_indices():
        edge_data = rx_graph.get_edge_data_by_index(edge_index)
        if key in edge_data and not overwrite:
            raise ValueError(
                f"{key!r} exists on graph edge {rx_graph.get_edge_endpoints_by_index(edge_index)}, set_overwrite=True to overwrite."
            )
        edge_data[key] = EdgeType.TRACK

    # set correct edge type
    for split_node_id in split_node_ids:
        for edge in rx_graph.out_edges(split_node_id):
            edge_data = rx_graph.get_edge_data(*edge[:2])
            edge_data[key] = EdgeType.SPLIT
    for merge_node_id in merge_node_ids:
        for edge in rx_graph.in_edges(merge_node_id):
            edge_data = rx_graph.get_edge_data(*edge[:2])
            edge_data[key] = EdgeType.MERGE


def add_track_and_lineage_ids(
    rx_graph: rx.PyDiGraph,
) -> tuple[rx.PyDiGraph, dict[int, list[int]]]:

    # remove split and merge edges from graph -> tracklet graph
    tracklet_graph = rx_graph.copy()

    root_node_ids = []
    split_node_ids = []
    merge_node_ids = []

    for node_idx in rx_graph.node_indices():
        if rx_graph.in_degree(node_idx) == 0:
            root_node_ids.append(node_idx)
        if rx_graph.out_degree(node_idx) > 1:
            split_node_ids.append(node_idx)
            for edge in rx_graph.out_edges(node_idx):
                tracklet_graph.remove_edge(*edge[:2])
        if rx_graph.in_degree(node_idx) > 1:
            merge_node_ids.append(node_idx)
            for edge in rx_graph.in_edges(node_idx):
                tracklet_graph.remove_edge(*edge[:2])

    # add track ID's to original graph based on connected components in tracklet graph
    for tracklet_id, node_ids in enumerate(
        rx.weakly_connected_components(tracklet_graph), start=1
    ):
        for node_id in node_ids:
            rx_graph[node_id][TRACK_ID_COLUMN] = tracklet_id
            rx_graph[node_id]["is_root_node"] = node_id in root_node_ids
            rx_graph[node_id]["is_split_node"] = node_id in split_node_ids
            rx_graph[node_id]["is_merge_node"] = node_id in merge_node_ids

    # add lineage ID's to original graph based on connected components
    for lineage_id, node_ids in enumerate(rx.weakly_connected_components(rx_graph)):
        for node_id in node_ids:
            rx_graph[node_id][LINEAGE_ID_COLUMN] = lineage_id

    # set all track edge types to TRACK (default)
    for edge_index in rx_graph.edge_indices():
        edge_data = rx_graph.get_edge_data_by_index(edge_index)
        edge_data[EDGE_TYPE_COLUMN] = EdgeType.TRACK

    # build napari compatible tracks graph {<track_id_child>: [<track_id_parent>, ...]}
    napari_tracks_graph = {}
    for split_node_id in split_node_ids:
        for edge in rx_graph.out_edges(split_node_id):
            tracklet_parent = rx_graph[edge[0]][TRACK_ID_COLUMN]
            tracklet_child = rx_graph[edge[1]][TRACK_ID_COLUMN]
            napari_tracks_graph.setdefault(tracklet_child, []).append(tracklet_parent)

            edge_data = rx_graph.get_edge_data(*edge[:2])
            edge_data[EDGE_TYPE_COLUMN] = EdgeType.SPLIT
    for merge_node_id in merge_node_ids:
        for edge in rx_graph.in_edges(merge_node_id):
            tracklet_parent = rx_graph[edge[0]][TRACK_ID_COLUMN]
            tracklet_child = rx_graph[edge[1]][TRACK_ID_COLUMN]
            napari_tracks_graph.setdefault(tracklet_child, []).append(tracklet_parent)

            edge_data = rx_graph.get_edge_data(*edge[:2])
            edge_data[EDGE_TYPE_COLUMN] = EdgeType.MERGE
    return rx_graph, napari_tracks_graph


def compute_circular_dendrogram(
    t: str, dendrogram: str, scale: float = 0.95
) -> list[pl.Expr]:
    return [
        (
            pl.col(t)
            * (
                pl.col(dendrogram) / pl.col(dendrogram).max() * scale * 2 * math.pi
            ).cos()
        ).alias(f"circ_{dendrogram}_x"),
        (
            pl.col(t)
            * (
                pl.col(dendrogram) / pl.col(dendrogram).max() * scale * 2 * math.pi
            ).sin()
        ).alias(f"circ_{dendrogram}_y"),
    ]


def slice_timestamps_table(
    table: GenericTable,
    slc: slice | list[int],
    index_column_name: str = "t_idx",
) -> GenericTable:
    df_timestamps = table.lazy_frame.collect()
    indices = _slice_to_indices(slc, extent=df_timestamps[index_column_name].max())
    df_timestamps_out = (
        df_timestamps.filter(pl.col(index_column_name).is_in(indices))
        .sort(index_column_name)
        .with_row_index()
        .select(pl.col("index").alias(index_column_name), pl.col("posix_timestamp"))
    )

    return GenericTable.from_table_data(
        df_timestamps_out,
        meta=BackendMeta(
            backend="parquet", index_key=index_column_name, index_type="int"
        ),
    )
