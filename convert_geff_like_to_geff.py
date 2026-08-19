from __future__ import annotations

from pathlib import Path
import shutil

import rich_click as click

from track_io import read_geff_like_to_rx, write_geff


@click.command()
@click.argument("input", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--overwrite/--no-overwrite",
    default=False,
    show_default=True,
    help="Overwrite existing output.",
)
@click.option(
    "--remove-geff-like/--no-remove-geff-like",
    default=False,
    show_default=True,
    help="Remove .geff.like after converting to .geff",
)
def main(input: Path, overwrite: bool, remove_geff_like: bool) -> None:
    """Convert .geff.like tracking graphs found in INPUT to .geff graphs."""
    convert_geff_like_datasets(
        input, overwrite=overwrite, remove_geff_like=remove_geff_like
    )


def convert_geff_like_datasets(
    input: Path, overwrite: bool = False, remove_geff_like: bool = False
) -> None:
    input = Path(input)

    geff_like_dirs = sorted(input.glob("*.ome.zarr/tracks/*.geff.like"))
    if not geff_like_dirs:
        click.echo(f"No geff.like tracking graphs found in {input}")
        return

    for geff_like_dir in geff_like_dirs:
        geff_dir = geff_like_dir.with_name(
            f"{geff_like_dir.name.removesuffix('.geff.like')}.geff"
        )

        click.echo(f"Converting {geff_like_dir} -> {geff_dir}")
        graph = read_geff_like_to_rx(geff_like_dir)
        write_geff(geff_dir, graph, overwrite=overwrite)
        if remove_geff_like:
            shutil.rmtree(geff_like_dir)


if __name__ == "__main__":
    main()
