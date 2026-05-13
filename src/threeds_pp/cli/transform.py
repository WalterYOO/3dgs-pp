"""Transform command - axis swap and n*pi/2 rotation for PLY files"""

import time
from pathlib import Path
from typing import Optional

import numpy as np
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
)

from ..core import StatsAnalyzer
from ..core.transform import get_transform, _is_identity, transform_ply


def run_transform(
    ply_file: str,
    swap: Optional[str] = None,
    inv: Optional[str] = None,
    rot: Optional[str] = None,
    transform_expr: Optional[str] = None,
    output: Optional[str] = None,
    interactive: bool = False,
) -> int:
    """Run transform command"""
    console = Console()

    if not Path(ply_file).exists():
        console.print(f"[red]Error:[/red] File not found: {ply_file}")
        return 1

    if interactive:
        return _run_interactive(console, ply_file)

    plan = None
    try:
        plan = get_transform(swap=swap, inv=inv, rot=rot, transform_expr=transform_expr)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        return 1

    if output is None:
        stem = Path(ply_file).stem
        output = str(Path(ply_file).parent / f"{stem}_transformed.ply")

    try:
        analyzer = StatsAnalyzer(ply_file)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        return 1

    if not analyzer.header.format.startswith("binary"):
        console.print(
            "[yellow]Warning:[/yellow] ASCII PLY support is slow; consider converting to binary first"
        )

    vertex_elem = analyzer.vertex_elem
    total = vertex_elem.count

    # Show plan
    console.print()
    console.print(
        Panel(
            f"[bold]Transform:[/bold] {plan.description}",
            title="Axis Transform",
        )
    )

    # Compute bounds from memmap
    console.print()
    console.print("[bold]Reading bounds...[/bold]")
    dtype = analyzer._get_struct_dtype()
    mm = np.memmap(
        analyzer.file_path,
        dtype=dtype,
        mode="r",
        offset=analyzer.header.header_size,
        shape=total,
    )
    coords = np.stack([mm["x"], mm["y"], mm["z"]], axis=-1)

    bmin = (
        float(np.min(coords[:, 0])),
        float(np.min(coords[:, 1])),
        float(np.min(coords[:, 2])),
    )
    bmax = (
        float(np.max(coords[:, 0])),
        float(np.max(coords[:, 1])),
        float(np.max(coords[:, 2])),
    )
    del mm

    # Compute transformed bounds
    t = plan.transform
    t_coords = (
        np.empty_like(coords) if _is_identity(t) else _preview_transform(bmin, bmax, t)
    )
    if _is_identity(t):
        tbmin = bmin
        tbmax = bmax
    else:
        tbmin = tuple(float(np.min(t_coords[:, i])) for i in range(3))
        tbmax = tuple(float(np.max(t_coords[:, i])) for i in range(3))

    console.print()
    console.print("[bold]Before transform:[/bold]")
    console.print(f"  X: [{bmin[0]:.6f}, {bmax[0]:.6f}]")
    console.print(f"  Y: [{bmin[1]:.6f}, {bmax[1]:.6f}]")
    console.print(f"  Z: [{bmin[2]:.6f}, {bmax[2]:.6f}]")
    console.print()

    # Transform
    t0 = time.time()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed:,}/{task.total:,})"),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("Transforming...", total=total)

        def _cb(done, _total):
            progress.update(task, completed=done)

        count = transform_ply(ply_file, plan, output, progress_callback=_cb)

    elapsed = time.time() - t0

    console.print()
    console.print("[bold]After transform:[/bold]")
    console.print(f"  X: [{tbmin[0]:.6f}, {tbmax[0]:.6f}]")
    console.print(f"  Y: [{tbmin[1]:.6f}, {tbmax[1]:.6f}]")
    console.print(f"  Z: [{tbmin[2]:.6f}, {tbmax[2]:.6f}]")
    console.print()
    console.print("[green]Success![/green]")
    console.print(f"  Points: {count:,}")
    console.print(f"  Time: {elapsed:.2f}s")
    console.print(f"  Output: {output}")
    console.print()

    return 0


def _preview_transform(bmin, bmax, t):
    """Compute transformed bounding box corners to estimate new bounds."""
    # Generate all 8 corners of the bounding box
    corners = np.array(
        [
            [bmin[0], bmin[1], bmin[2]],
            [bmax[0], bmin[1], bmin[2]],
            [bmin[0], bmax[1], bmin[2]],
            [bmax[0], bmax[1], bmin[2]],
            [bmin[0], bmin[1], bmax[2]],
            [bmax[0], bmin[1], bmax[2]],
            [bmin[0], bmax[1], bmax[2]],
            [bmax[0], bmax[1], bmax[2]],
        ],
        dtype=np.float64,
    )

    # Apply transform to corners
    src = [abs(v) - 1 for v in t]
    signs = [v < 0 for v in t]
    result = np.empty_like(corners)
    result[:, 0] = -corners[:, src[0]] if signs[0] else corners[:, src[0]]
    result[:, 1] = -corners[:, src[1]] if signs[1] else corners[:, src[1]]
    result[:, 2] = -corners[:, src[2]] if signs[2] else corners[:, src[2]]
    return result


def _run_interactive(console: Console, ply_file: str) -> int:
    """Run interactive transform mode"""
    try:
        analyzer = StatsAnalyzer(ply_file)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        return 1

    vertex_elem = analyzer.vertex_elem
    prop_names = [p.name for p in vertex_elem.properties]
    for axis in ("x", "y", "z"):
        if axis not in prop_names:
            console.print(f"[red]Error:[/red] Property '{axis}' not found in PLY file")
            return 1

    total = vertex_elem.count

    # Read bounds
    console.print()
    console.print("[bold]Loading coordinate data...[/bold]")
    dtype = analyzer._get_struct_dtype()
    mm = np.memmap(
        analyzer.file_path,
        dtype=dtype,
        mode="r",
        offset=analyzer.header.header_size,
        shape=total,
    )
    bmin = (float(np.min(mm["x"])), float(np.min(mm["y"])), float(np.min(mm["z"])))
    bmax = (float(np.max(mm["x"])), float(np.max(mm["y"])), float(np.max(mm["z"])))
    del mm

    console.print()
    console.print("[bold cyan]Transform Interactive Mode[/bold cyan]")
    console.print()
    console.print("[bold]Current bounding box:[/bold]")
    console.print(f"  X: [{bmin[0]:.6f}, {bmax[0]:.6f}]")
    console.print(f"  Y: [{bmin[1]:.6f}, {bmax[1]:.6f}]")
    console.print(f"  Z: [{bmin[2]:.6f}, {bmax[2]:.6f}]")
    console.print()

    plan = None

    while True:
        if plan:
            # Preview
            t = plan.transform
            corners = _preview_transform(bmin, bmax, t)
            tbmin = tuple(float(np.min(corners[:, i])) for i in range(3))
            tbmax = tuple(float(np.max(corners[:, i])) for i in range(3))

            console.print()
            console.print(f"[bold]Transform:[/bold] {plan.description}")
            console.print()
            console.print("[bold]New bounding box (preview):[/bold]")
            console.print(f"  X: [{tbmin[0]:.6f}, {tbmax[0]:.6f}]")
            console.print(f"  Y: [{tbmin[1]:.6f}, {tbmax[1]:.6f}]")
            console.print(f"  Z: [{tbmin[2]:.6f}, {tbmax[2]:.6f}]")

        console.print()
        console.print("[dim]Commands:[/dim]")
        console.print("  s  - Swap (axis exchange / mirror)")
        console.print("  v  - Invert (single axis mirror)")
        console.print("  r  - Rotate (n*pi/2 around axis)")
        console.print("  t  - Custom transform expression (e.g. x->y,y->-x,z->z)")
        console.print("  Enter - Confirm and write")
        console.print("  q  - Quit")
        console.print()

        try:
            cmd = console.input(">> ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            console.print()
            return 0

        if cmd == "q":
            console.print("[yellow]Cancelled.[/yellow]")
            return 0
        elif cmd == "s":
            try:
                console.print()
                console.print("[bold]Swap pair:[/bold]")
                console.print("  1. xy")
                console.print("  2. xz")
                console.print("  3. yz")
                pair = console.input(">> ").strip().lower()
                if pair in ("1", "xy"):
                    pair_name = "xy"
                elif pair in ("2", "xz"):
                    pair_name = "xz"
                elif pair in ("3", "yz"):
                    pair_name = "yz"
                else:
                    console.print("[red]Invalid choice.[/red]")
                    continue
                console.print()
                console.print("[bold]Sign:[/bold]")
                console.print("  1. positive (x=y mirror)")
                console.print("  2. negative (x=-y mirror)")
                sign = console.input(">> ").strip().lower()
                if sign == "2":
                    pair_name = f"n{pair_name}"
                elif sign != "1":
                    console.print("[red]Invalid choice.[/red]")
                    continue
                plan = get_transform(swap=pair_name)
            except (ValueError, EOFError) as e:
                console.print(f"[red]Error:[/red] {e}")
        elif cmd == "v":
            try:
                console.print()
                console.print("[bold]Invert axis (single axis mirror):[/bold]")
                console.print("  1. x")
                console.print("  2. y")
                console.print("  3. z")
                axis = console.input(">> ").strip().lower()
                if axis in ("1", "x"):
                    axis_name = "x"
                elif axis in ("2", "y"):
                    axis_name = "y"
                elif axis in ("3", "z"):
                    axis_name = "z"
                else:
                    console.print("[red]Invalid choice.[/red]")
                    continue
                plan = get_transform(inv=axis_name)
            except (ValueError, EOFError) as e:
                console.print(f"[red]Error:[/red] {e}")
        elif cmd == "r":
            try:
                console.print()
                console.print("[bold]Rotation axis:[/bold]")
                console.print("  1. x")
                console.print("  2. y")
                console.print("  3. z")
                axis = console.input(">> ").strip().lower()
                if axis in ("1", "x"):
                    axis_name = "x"
                elif axis in ("2", "y"):
                    axis_name = "y"
                elif axis in ("3", "z"):
                    axis_name = "z"
                else:
                    console.print("[red]Invalid choice.[/red]")
                    continue
                console.print()
                console.print("[bold]Angle:[/bold]")
                console.print("  1. 90")
                console.print("  2. 180")
                console.print("  3. 270")
                angle = console.input(">> ").strip()
                if angle in ("1", "90"):
                    angle_name = "90"
                elif angle in ("2", "180"):
                    angle_name = "180"
                elif angle in ("3", "270"):
                    angle_name = "270"
                else:
                    console.print("[red]Invalid choice.[/red]")
                    continue
                plan = get_transform(rot=f"{axis_name} {angle_name}")
            except (ValueError, EOFError) as e:
                console.print(f"[red]Error:[/red] {e}")
        elif cmd == "t":
            try:
                expr = console.input("  Expression (e.g. x->y,y->-x,z->z): ").strip()
                if not expr:
                    continue
                plan = get_transform(transform_expr=expr)
            except (ValueError, EOFError) as e:
                console.print(f"[red]Error:[/red] {e}")
        elif cmd == "":
            if plan is None:
                console.print(
                    "[red]No transform selected. Choose s, r, or t first.[/red]"
                )
                continue
            break
        else:
            console.print("[red]Unknown command.[/red]")

    # Write output
    stem = Path(ply_file).stem
    default_output = str(Path(ply_file).parent / f"{stem}_transformed.ply")
    output_input = console.input(f"  Output file [{default_output}]: ").strip()
    output = output_input if output_input else default_output

    console.print()
    console.print("[bold]Transforming...[/bold]")
    t0 = time.time()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed:,}/{task.total:,})"),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("Transforming...", total=vertex_elem.count)

        def _cb(done, _total):
            progress.update(task, completed=done)

        count = transform_ply(ply_file, plan, output, progress_callback=_cb)

    elapsed = time.time() - t0
    console.print()
    console.print("[green]Success![/green]")
    console.print(f"  Points: {count:,}")
    console.print(f"  Time: {elapsed:.2f}s")
    console.print(f"  Output: {output}")
    console.print()

    return 0
