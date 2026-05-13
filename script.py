# %%
from lstree_to_tracks import load_lstree_h5
from parse_ldp_ls1_data import TABLES_PATH
from pathlib import Path
import colorcet as cc

# %%
root = Path(r"N:\ldp_dev\data_ls1\data_ls1\000")
tables_path = root / TABLES_PATH

# %%
df_nodes, df_edges, tracklet_graph = load_lstree_h5(tables_path)
# %%
import napari
# %%
viewer = napari.Viewer()
viewer.add_points(
    df_nodes.select("t_id", "z", "y", "x"),
    features=df_nodes.select("track_id").to_dict(),
    face_color="track_id",
    size=5,
    face_colormap=cc.glasbey,
)
viewer.add_tracks(
    df_nodes.select("track_id", "t_id", "z", "y", "x"),
    graph=tracklet_graph,
)