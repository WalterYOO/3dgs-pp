"""Fill command - fill source PLY points into a target region of a destination PLY."""

import time
from pathlib import Path
from typing import Optional, Tuple

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)

from ..core.crop import _parse_point
from ..core.fill import fill_ply
from ..ply.header import PLYHeader


def _parse_offset(s: str) -> Tuple[float, float, float]:
    """Parse a comma-separated offset string 'dx,dy,dz' into floats."""
    parts = s.split(",")
    if len(parts) != 3:
        raise ValueError(f"Invalid offset format: '{s}'. Expected 'dx,dy,dz'")
    return float(parts[0]), float(parts[1]), float(parts[2])


def run_fill(
    target_file: str,
    source_file: str,
    p1: str,
    p2: Optional[str] = None,
    p3: Optional[str] = None,
    p4: Optional[str] = None,
    p5: Optional[str] = None,
    p6: Optional[str] = None,
    p7: Optional[str] = None,
    p8: Optional[str] = None,
    offset: str = "0,0,0",
    output: Optional[str] = None,
) -> int:
    """Run the fill command.

    Args:
        target_file: Path to target PLY file.
        source_file: Path to source PLY file.
        p1: First point of target region "x,y,z".
        p2: Second point (AABB mode). If None, hexahedron mode with p3-p8.
        p3-p8: Additional points for hexahedron mode.
        offset: Offset "dx,dy,dz" applied to source points.
        output: Output file path.

    Returns:
        Exit code (0 = success, 1 = error).
    """
    console = Console()

    if not Path(target_file).exists():
        console.print(f"[red]Error:[/red] Target file not found: {target_file}")
        return 1
    if not Path(source_file).exists():
        console.print(f"[red]Error:[/red] Source file not found: {source_file}")
        return 1

    try:
        start_time = time.time()
        off = _parse_offset(offset)
        pt1 = _parse_point(p1)

        # Estimate total for progress bar
        target_header = PLYHeader.parse(target_file)
        target_total = target_header.get_element("vertex").count
        source_header = PLYHeader.parse(source_file)
        source_total = source_header.get_element("vertex").count
        estimated_total = target_total + source_total

        console.print(f"[cyan]Target:[/cyan] {target_file} ({target_total:,} points)")
        console.print(f"[cyan]Source:[/cyan] {source_file} ({source_total:,} points)")
        console.print(f"[cyan]Offset:[/cyan] {off}")

        # Detect mode: eight-point if any p3-p8 is provided
        has_extra = any(x is not None for x in [p3, p4, p5, p6, p7, p8])

        if p2 is not None and not has_extra:
            pt2 = _parse_point(p2)
            console.print(f"[cyan]Region:[/cyan] Two-point (AABB)")
            console.print(f"[cyan]  P1:[/cyan] {pt1}")
            console.print(f"[cyan]  P2:[/cyan] {pt2}")

            out_path = output or str(
                Path(target_file).parent / f"{Path(target_file).stem}_filled.ply"
            )

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("({task.completed:,}/{task.total:,})"),
                TimeRemainingColumn(),
            ) as progress:
                write_task = progress.add_task("Writing...", total=estimated_total)
                target_total, added = fill_ply(
                    target_file,
                    source_file,
                    out_path,
                    p1=pt1,
                    p2=pt2,
                    offset=off,
                    progress_callback=lambda done, total: progress.update(
                        write_task, completed=done, total=total
                    ),
                )
        else:
            points = [pt1]
            if p2 is not None:
                points.append(_parse_point(p2))
            for p_str in [p3, p4, p5, p6, p7, p8]:
                if p_str is not None:
                    points.append(_parse_point(p_str))

            if len(points) != 8:
                console.print(
                    f"[red]Error:[/red] Eight-point mode requires exactly 8 points, "
                    f"got {len(points)}"
                )
                return 1

            console.print(f"[cyan]Region:[/cyan] Eight-point (Convex Hexahedron)")
            for i, pt in enumerate(points, 1):
                console.print(f"[cyan]  P{i}:[/cyan] {pt}")

            out_path = output or str(
                Path(target_file).parent / f"{Path(target_file).stem}_filled.ply"
            )

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("({task.completed:,}/{task.total:,})"),
                TimeRemainingColumn(),
            ) as progress:
                write_task = progress.add_task("Writing...", total=estimated_total)
                target_total, added = fill_ply(
                    target_file,
                    source_file,
                    out_path,
                    p1=points[0],
                    corners=points,
                    offset=off,
                    progress_callback=lambda done, total: progress.update(
                        write_task, completed=done, total=total
                    ),
                )

        elapsed = time.time() - start_time
        console.print(f"\n[green]Success![/green]")
        console.print(f"  Target points: {target_total:,}")
        console.print(f"  Added (from source): {added:,}")
        console.print(f"  Total: {target_total + added:,}")
        console.print(f"  Time: {elapsed:.2f}s")
        console.print(f"  Output: {out_path}")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0