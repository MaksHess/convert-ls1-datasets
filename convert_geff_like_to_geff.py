from __future__ import annotations

from pathlib import Path

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
def main(input: Path, overwrite: bool) -> None:
    """Convert geff.like tracking graphs found in INPUT to .geff graphs in place."""
    convert_geff_like_datasets(input, overwrite=overwrite)


def convert_geff_like_datasets(input: Path, overwrite: bool = False) -> None:
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


if __name__ == "__main__":
    main()
