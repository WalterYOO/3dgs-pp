"""Downsample command - downsample 3DGS PLY files"""

import time
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn

from ..ply import LazyPLYReader, PLYWriter
from ..ply.writer import copy_header_for_partition
from ..core import Downsampler


def run_downsample(ply_file: str,
                   ratio: float = None,
                   count: int = None,
                   method: str = 'uniform',
                   output: str = None,
                   seed: int = None):
    """Run downsample command"""
    console = Console()

    if ratio is None and count is None:
        console.print("[red]Error:[/red] Either --ratio or --count must be specified")
        return 1

    if ratio is not None and count is not None:
        console.print("[red]Error:[/red] Cannot specify both --ratio and --count")
        return 1

    if not Path(ply_file).exists():
        console.print(f"[red]Error:[/red] File not found: {ply_file}")
        return 1

    # Determine output file
    if output is None:
        input_path = Path(ply_file)
        output = str(input_path.parent / f"{input_path.stem}_downsampled.ply")

    try:
        start_time = time.time()

        with LazyPLYReader(ply_file) as reader:
            console.print()
            console.print(f"[cyan]Input:[/cyan] {ply_file}")

            downsampler = Downsampler(reader)
            total_count = downsampler.total_count

            console.print(f"[cyan]Original points:[/cyan] {total_count:,}")

            # Calculate target count
            if ratio is not None:
                target_count = downsampler.calculate_target_count(ratio=ratio)
                console.print(f"[cyan]Target ratio:[/cyan] {ratio:.2%}")
            else:
                target_count = downsampler.calculate_target_count(count=count)
                console.print(f"[cyan]Target count:[/cyan] {count:,}")

            console.print(f"[cyan]Method:[/cyan] {method}")
            console.print(f"[cyan]Output:[/cyan] {output}")
            console.print()

            # Run sampling
            console.print("[bold]Step 1/2:[/bold] Selecting points...")
            result = downsampler.sample(method=method, ratio=ratio, count=count, seed=seed)

            console.print(f"  Selected {result.actual_count:,} points "
                        f"({result.actual_count / total_count:.2%} of original)")
            console.print()

            # Write output
            console.print("[bold]Step 2/2:[/bold] Writing output...")

            # Create header with comment
            new_header = copy_header_for_partition(reader.header, result.actual_count)
            ratio_str = f"{ratio:.4f}" if ratio is not None else "N/A"
            count_str = f"{count}" if count is not None else "N/A"
            new_header.comments.append(f"downsampled: method={method}, ratio={ratio_str}, count={count_str}, original={total_count}")

            with PLYWriter(output) as writer:
                writer.write_header(new_header)

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    TextColumn("({task.completed:,}/{task.total:,})"),
                    TimeRemainingColumn(),
                ) as progress:
                    write_task = progress.add_task("Writing...", total=result.actual_count)

                    for data in downsampler.iter_selected(result):
                        writer.write_element('vertex', data)
                        progress.update(write_task, advance=1)

            end_time = time.time()
            elapsed = end_time - start_time

            console.print()
            console.print("[green]Success![/green]")
            console.print(f"  Original: {total_count:,} points")
            console.print(f"  Retained: {result.actual_count:,} points")
            console.print(f"  Compression: {(1 - result.actual_count / total_count):.2%}")
            console.print(f"  Time: {elapsed:.2f}s")
            console.print(f"  Output: {output}")
            console.print()

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0
