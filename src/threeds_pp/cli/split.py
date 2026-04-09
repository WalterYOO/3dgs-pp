"""Split command - spatial partitioning of PLY files"""

import json
from pathlib import Path
from typing import Dict, List, Any
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

from ..ply import LazyPLYReader, PLYWriter
from ..ply.writer import copy_header_for_partition
from ..core import Bounds, Partitioner
from ..core.partition import parse_split_spec, generate_block_filename


def run_split(ply_file: str, split_spec: str, output_dir: str = None):
    """Run split command"""
    console = Console()

    if not Path(ply_file).exists():
        console.print(f"[red]Error:[/red] File not found: {ply_file}")
        return 1

    try:
        splits = parse_split_spec(split_spec)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        return 1

    # Set output directory
    if output_dir is None:
        output_dir = str(Path(ply_file).parent)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    base_name = Path(ply_file).stem

    try:
        with LazyPLYReader(ply_file) as reader:
            vertex_elem = reader.header.get_element('vertex')
            if not vertex_elem:
                console.print("[red]Error:[/red] No 'vertex' element found in PLY file")
                return 1

            total_points = vertex_elem.count
            console.print()
            console.print(f"[cyan]Input:[/cyan] {ply_file}")
            console.print(f"[cyan]Points:[/cyan] {total_points:,}")
            console.print(f"[cyan]Split:[/cyan] {splits[0]} x {splits[1]} x {splits[2]} = {splits[0] * splits[1] * splits[2]} blocks")
            console.print(f"[cyan]Output:[/cyan] {output_path}")
            console.print()

            # Step 1: Calculate bounds
            console.print("[bold]Step 1/3:[/bold] Calculating bounds...")
            try:
                (min_x, min_y, min_z), (max_x, max_y, max_z) = reader.get_bounds('vertex')
            except ValueError as e:
                console.print(f"[red]Error:[/red] {e}")
                return 1

            bounds = Bounds(min_coords=(min_x, min_y, min_z), max_coords=(max_x, max_y, max_z))
            console.print(f"  Bounds: {bounds}")
            console.print()

            # Step 2: First pass - count points per block
            console.print("[bold]Step 2/3:[/bold] Counting points per block...")
            partitioner = Partitioner(bounds, splits)

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("({task.completed:,}/{task.total:,})"),
                TimeRemainingColumn(),
            ) as progress:
                count_task = progress.add_task("Counting...", total=total_points)

                for idx in range(total_points):
                    elem = reader.get_element(idx, 'vertex')
                    x, y, z = elem.x, elem.y, elem.z
                    block_idx = partitioner.get_block_index(x, y, z)
                    if block_idx:
                        i, j, k = block_idx
                        block = partitioner.get_block(i, j, k)
                        if block:
                            block.point_count += 1
                    progress.update(count_task, advance=1)

            console.print()

            # Display block counts
            console.print("[bold]Point counts per block:[/bold]")
            count_table = Table(show_header=True, header_style="magenta")
            count_table.add_column("Block", style="cyan")
            count_table.add_column("Points", style="green", justify="right")
            count_table.add_column("Bounds", style="dim")

            for block in partitioner.iter_blocks():
                count_table.add_row(
                    f"({block.index_i},{block.index_j},{block.index_k})",
                    f"{block.point_count:,}",
                    f"x:[{block.bounds.min_x:.2f},{block.bounds.max_x:.2f}]"
                )
            console.print(count_table)
            console.print()

            # Step 3: Second pass - write blocks
            console.print("[bold]Step 3/3:[/bold] Writing blocks...")

            # Open all writers
            writers: Dict[Tuple[int, int, int], PLYWriter] = {}
            for block in partitioner.iter_blocks():
                if block.point_count > 0:
                    filename = generate_block_filename(base_name, block.index_i, block.index_j, block.index_k)
                    block.filename = filename
                    writer = PLYWriter(str(output_path / filename))
                    writer.open()
                    new_header = copy_header_for_partition(reader.header, block.point_count)
                    writer.write_header(new_header)
                    writers[(block.index_i, block.index_j, block.index_k)] = writer

            # Write points
            try:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    TextColumn("({task.completed:,}/{task.total:,})"),
                    TimeRemainingColumn(),
                ) as progress:
                    write_task = progress.add_task("Writing...", total=total_points)

                    for idx in range(total_points):
                        elem = reader.get_element(idx, 'vertex')
                        x, y, z = elem.x, elem.y, elem.z
                        block_idx = partitioner.get_block_index(x, y, z)

                        if block_idx and block_idx in writers:
                            writer = writers[block_idx]
                            # Convert element data to dict
                            data = {p: elem[p] for p in reader.get_property_names('vertex')}
                            writer.write_element('vertex', data)

                        progress.update(write_task, advance=1)

            finally:
                # Close all writers
                for writer in writers.values():
                    writer.close()

            # Write block info JSON
            info_file = output_path / f"{base_name}_block_info.json"
            partition_info = partitioner.create_partition_info(
                original_file=str(Path(ply_file).name),
                total_points=total_points
            )
            partition_info.save(str(info_file))

            console.print()
            console.print(f"[green]Success![/green]")
            console.print(f"  Created {len(writers)} block files")
            console.print(f"  Block info: {info_file}")
            console.print()

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0
