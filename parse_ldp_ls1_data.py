# %%
import polars as pl
from pathlib import Path
import re
import warnings
from functools import partial
import pandas as pd

CHANNEL_PATTERN = re.compile(
    r"^(?P<position>[^_/]+)\/(?P<channel>[^_/-]+)(-(?P<processing>[^_/]+))?\/.*-T(?P<t_id>\d+)\.(?P<file_type>tif)$"
)
CHANNEL_GLOB = "**/Channel*/*.tif"

CHANNEL_SCHEMA = {
    "position": pl.String,
    "channel": pl.String,
    "processing": pl.String,
    "t_id": pl.UInt32,
    "file_type": pl.String,
    "path": pl.String,
}

LABEL_PATTERN = re.compile(
    r"^(?P<position>[^_/]+)\/(?P<label_name>[^_/]+)_segmentation\/.*-T(?P<t_id>\d+)\.(?P<file_type>tif)$"
)
LABEL_GLOB = "**/*_segmentation/*.tif"

LABEL_SCHEMA = {
    "position": pl.String,
    "label_name": pl.String,
    "t_id": pl.UInt32,
    "file_type": pl.String,
    "path": pl.String,
}


MESH_PATTERN = re.compile(
    r"^(?P<position>[^_/]+)\/(?P<label_name>[^_/]+)_mesh\/.*-T(?P<t_id>\d+)\.(?P<file_type>vtp)$"
)

MESH_GLOB = "**/*_mesh/*.vtp"

MESH_SCHEMA = {
    "position": pl.String,
    "label_name": pl.String,
    "t_id": pl.UInt32,
    "file_type": pl.String,
    "path": pl.String,
}


TABLES_PATH = "agg_features.h5"
TABLE_KEYS = ['edges', 'nodes', 'organoid']

def _parse_element(
    root: Path,
    regex: re.Pattern[str],
    glob_pattern: str,
    table_schema: dict[str, pl.DataType]
) -> pl.DataFrame:
    acc = []
    for path in root.glob(glob_pattern):
        rel_path = path.relative_to(root.parent)
        mo = regex.match(rel_path.as_posix())
        if mo is None:
            warnings.warn(f"File path {rel_path} does not match expected pattern.")
        else:
            components = {
                **mo.groupdict(),
                "path": path.relative_to(root).as_posix(),
            }
            acc.append(components)

    df = pl.DataFrame(
        acc,
        schema=table_schema,
        strict=False,
    ).with_columns(
        pl.col("t_id") - pl.col("t_id").min(),
    )
    if 'processing' in df.columns:
        df = df.with_columns(pl.col('processing').fill_null('Raw'))
    return df.sort(df.columns)
    

parse_channels = partial(_parse_element, regex=CHANNEL_PATTERN, glob_pattern=CHANNEL_GLOB, table_schema=CHANNEL_SCHEMA)
parse_labels = partial(_parse_element, regex=LABEL_PATTERN, glob_pattern=LABEL_GLOB, table_schema=LABEL_SCHEMA)
parse_meshes = partial(_parse_element, regex=MESH_PATTERN, glob_pattern=MESH_GLOB, table_schema=MESH_SCHEMA)

def read_tables(root: Path):
    tables = {}
    for key in TABLE_KEYS:
        tables[key] = pl.DataFrame(pd.read_hdf(root/TABLES_PATH, key=key))
    return tables


def _validate_node_table(df: pl.DataFrame) -> None:
    assert df.select((pl.col('node_id')==pl.col('mamut_id')).all())[0, 0], "Mismatch between node_id and mamut_id"
    