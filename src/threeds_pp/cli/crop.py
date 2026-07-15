"""Crop command - crop Gaussian ellipsoids by spatial region from PLY files."""

import time
from pathlib import Path
from typing import Optional

from rich.console import Console

from ..core.crop import _parse_point, crop_ply


def run_crop(
    ply_file: str,
    p1: str,
    p2: Optional[str] = None,
    p3: Optional[str] = None,
    p4: Optional[str] = None,
    p5: Optional[str] = None,
    p6: Optional[str] = None,
    p7: Optional[str] = None,
    p8: Optional[str] = None,
    outside: bool = False,
    output: Optional[str] = None,
) -> int:
    """Run the crop command.

    Args:
        ply_file: Path to input PLY file.
        p1: First point "x,y,z".
        p2: Second point "x,y,z" (AABB mode). If None, hexahedron mode with p3-p8.
        p3-p8: Additional points for hexahedron mode.
        outside: Keep points outside the region (default: keep inside).
        output: Output file path.

    Returns:
        Exit code (0 = success, 1 = error).
    """
    console = Console()

    if not Path(ply_file).exists():
        console.print(f"[red]Error:[/red] File not found: {ply_file}")
        return 1

    try:
        start_time = time.time()

        pt1 = _parse_point(p1)

        # Detect mode: eight-point if any p3-p8 is provided
        has_extra = any(x is not None for x in [p3, p4, p5, p6, p7, p8])

        if p2 is not None and not has_extra:
            # Two-point mode (AABB)
            pt2 = _parse_point(p2)
            console.print(f"[cyan]Mode:[/cyan] Two-point (AABB)")
            console.print(f"[cyan]  P1:[/cyan] {pt1}")
            console.print(f"[cyan]  P2:[/cyan] {pt2}")
            console.print(f"[cyan]Keep:[/cyan] {'outside region' if outside else 'inside region'}")

            out_path = output or str(
                Path(ply_file).parent / f"{Path(ply_file).stem}_cropped.ply"
            )
            total_kept = crop_ply(
                ply_file,
                out_path,
                p1=pt1,
                p2=pt2,
                outside=outside,
            )
        else:
            # Eight-point mode (hexahedron)
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

            console.print(f"[cyan]Mode:[/cyan] Eight-point (Convex Hexahedron)")
            for i, pt in enumerate(points, 1):
                console.print(f"[cyan]  P{i}:[/cyan] {pt}")
            console.print(f"[cyan]Keep:[/cyan] {'outside region' if outside else 'inside region'}")

            out_path = output or str(
                Path(ply_file).parent / f"{Path(ply_file).stem}_cropped.ply"
            )
            total_kept = crop_ply(
                ply_file,
                out_path,
                p1=points[0],
                corners=points,
                outside=outside,
            )

        elapsed = time.time() - start_time

        console.print(f"\n[green]Success![/green]")
        console.print(f"  Kept: {total_kept:,} points")
        console.print(f"  Time: {elapsed:.2f}s")
        console.print(f"  Output: {out_path}")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0