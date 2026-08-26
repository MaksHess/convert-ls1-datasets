"""Double the dim-0 chunk size of multiscale image arrays in selected OME-Zarr datasets."""

from __future__ import annotations

import os
import re
import shutil
import time
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

import rich_click as click

if TYPE_CHECKING:
    import zarr


@click.command()
@click.argument("input_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("regex")
@click.option(
    "--dry-run/--no-dry-run",
    default=True,
    show_default=True,
    help="Preview the rechunk plan without writing anything.",
)
def main(input_dir: Path, regex: str, dry_run: bool) -> None:
    """Rechunk multiscale arrays of OME-Zarr datasets under INPUT_DIR matching REGEX.

    INPUT_DIR is expected to contain datasets two levels down, i.e.
    INPUT_DIR/<dataset>-<variant>/<step>.ome.zarr. REGEX is matched (re.search) against
    each container's path relative to INPUT_DIR, e.g. "deconv\\.ome\\.zarr$".

    Doubles the chunk size along dimension 0 (clamped to the array's extent) of every
    pyramid level array, in place.
    """
    pattern = re.compile(regex)

    containers = sorted(input_dir.glob("*/*.ome.zarr"))
    click.echo(f"found {len(containers)} ome-zarr container(s) under {input_dir}")

    matched = [
        c for c in containers if pattern.search(c.relative_to(input_dir).as_posix())
    ]
    click.echo(f"{len(matched)} container(s) match {regex!r}")

    n_ok = n_skipped = n_failed = n_manual = 0
    for container_path in matched:
        for level_path in _level_paths(container_path):
            status = _rechunk_level(container_path, level_path, dry_run=dry_run)
            if status == "ok":
                n_ok += 1
            elif status == "skipped":
                n_skipped += 1
            elif status == "manual":
                n_manual += 1
            else:
                n_failed += 1

    verb = "would rechunk" if dry_run else "rechunked"
    click.echo(
        f"{verb} {n_ok}, skipped {n_skipped}, failed {n_failed}, "
        f"needs manual rename {n_manual}"
    )
    if n_failed or n_manual:
        raise SystemExit(1)


def _level_paths(container_path: Path) -> list[str]:
    import ngio

    container = ngio.open_ome_zarr_container(container_path)
    return container.level_paths


def _rechunk_level(container_path: Path, level_path: str, dry_run: bool) -> str:
    import dask.array as da
    import ngio
    import zarr
    from dask.array.core import PerformanceWarning

    rel = container_path.name + "/" + level_path
    container = ngio.open_ome_zarr_container(container_path)
    arr = container.get_image(level_path).zarr_array

    old_chunks = arr.chunks
    new_chunks = (min(2 * old_chunks[0], arr.shape[0]), *old_chunks[1:])

    if arr.shards is not None:
        click.echo(f"{rel}: SHARDED - skipped, needs review")
        return "skipped"

    if new_chunks == old_chunks:
        click.echo(f"{rel}: unchanged ({old_chunks})")
        return "skipped"

    if dry_run:
        click.echo(f"{rel}: {old_chunks} -> {new_chunks}")
        return "ok"

    click.echo(f"{rel}: {old_chunks} -> {new_chunks}")
    level_dir = container_path / level_path
    temp_dir = container_path / f"{level_path}.rechunk_tmp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    target = zarr.create_array(
        temp_dir,
        shape=arr.shape,
        chunks=new_chunks,
        dtype=arr.dtype,
        zarr_format=3,
        compressors=arr.compressors,
        filters=arr.filters,
        serializer=arr.serializer,
        fill_value=arr.fill_value,
        dimension_names=arr.metadata.dimension_names,
        attributes=dict(arr.attrs),
    )
    # dask's "unsafe write" PerformanceWarning is about concurrent/partial region
    # writes racing on a shared physical chunk. It doesn't apply here: `target` is a
    # freshly created, empty array and this is a single full-array write, followed by
    # a full equality check below before the original is touched.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=PerformanceWarning)
        da.to_zarr(da.from_zarr(arr).rechunk(new_chunks), target, overwrite=True)

    try:
        if not _verify(arr, temp_dir, new_chunks):
            click.echo(f"{rel}: verification FAILED, original left untouched, see {temp_dir}")
            return "failed"
    except Exception as e:
        click.echo(f"{rel}: verification error ({e}), original left untouched, see {temp_dir}")
        return "failed"

    del arr, container  # drop zarr/ngio handles before touching the directory
    shutil.rmtree(level_dir)

    for attempt in range(5):
        try:
            os.rename(temp_dir, level_dir)
            return "ok"
        except OSError:
            if attempt == 4:
                click.echo(
                    f"{rel}: {level_dir} was deleted but renaming {temp_dir} -> {level_dir} "
                    f"failed after retries. Data is intact at {temp_dir} - rename it into "
                    "place manually."
                )
                return "manual"
            time.sleep(1)
    return "manual"


def _verify(arr: zarr.Array, temp_dir: Path, new_chunks: tuple[int, ...]) -> bool:
    import dask.array as da
    import zarr

    check = zarr.open(temp_dir, mode="r")
    if check.shape != arr.shape or check.dtype != arr.dtype or check.chunks != new_chunks:
        return False
    if dict(check.attrs) != dict(arr.attrs):
        return False
    return bool(da.equal(da.from_zarr(arr), da.from_zarr(check)).all().compute())


if __name__ == "__main__":
    main()
