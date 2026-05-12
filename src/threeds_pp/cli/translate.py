"""Translate command - shift PLY coordinates"""

import time
from pathlib import Path
from typing import Optional

import numpy as np
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn

from ..core import StatsAnalyzer
from ..core.translate import (
    compute_plan,
    parse_translate_spec,
    TranslatePlan,
    translate_ply,
)


def _get_bounds(analyzer: StatsAnalyzer):
    """Return ((min_x, min_y, min_z), (max_x, max_y, max_z))"""
    bounds = {}
    for axis in ("x", "y", "z"):
        col = analyzer.read_column(axis)
        bounds[f"min_{axis}"] = float(np.min(col))
        bounds[f"max_{axis}"] = float(np.max(col))
    return (
        (bounds["min_x"], bounds["min_y"], bounds["min_z"]),
        (bounds["max_x"], bounds["max_y"], bounds["max_z"]),
    )


def run_translate(
    ply_file: str,
    x: Optional[str] = None,
    y: Optional[str] = None,
    z: Optional[str] = None,
    all_val: Optional[str] = None,
    output: Optional[str] = None,
    interactive: bool = False,
) -> int:
    """Run translate command"""
    console = Console()

    if not Path(ply_file).exists():
        console.print(f"[red]Error:[/red] File not found: {ply_file}")
        return 1

    if interactive:
        return _run_interactive(console, ply_file)

    # Validate: at least one axis must be specified (check raw args before --all expansion)
    if all_val is None and x is None and y is None and z is None:
        console.print("[red]Error:[/red] At least one of --x, --y, --z, or --all must be specified")
        return 1

    try:
        x_s, y_s, z_s = parse_translate_spec(x=x, y=y, z=z, all_val=all_val)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        return 1

    try:
        analyzer = StatsAnalyzer(ply_file)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        return 1

    vertex_elem = analyzer.vertex_elem
    total = vertex_elem.count

    # Check that x, y, z exist
    prop_names = [p.name for p in vertex_elem.properties]
    for axis in ("x", "y", "z"):
        if axis not in prop_names:
            console.print(f"[red]Error:[/red] Property '{axis}' not found in PLY file")
            return 1

    console.print()
    console.print("[bold]Computing translation offsets...[/bold]")

    # Compute plan
    try:
        plan = compute_plan(analyzer, x_s, y_s, z_s)
    except Exception as e:
        console.print(f"[red]Error:[/red] Failed to compute translation plan: {e}")
        return 1

    # Determine output path
    if output is None:
        stem = Path(ply_file).stem
        output = str(Path(ply_file).parent / f"{stem}_translated.ply")

    # Show plan
    console.print()
    console.print(Panel(
        f"[bold]X:[/bold] {plan.x_spec}  (offset: {plan.x_offset:.6f})\n"
        f"[bold]Y:[/bold] {plan.y_spec}  (offset: {plan.y_offset:.6f})\n"
        f"[bold]Z:[/bold] {plan.z_spec}  (offset: {plan.z_offset:.6f})",
        title="Translation Plan",
    ))

    # Compute bounds before
    console.print()
    console.print("[bold]Computing bounding box...[/bold]", end="\r")
    try:
        bmin, bmax = _get_bounds(analyzer)
    except Exception as e:
        console.print(f"[red]Error:[/red] Failed to compute bounds: {e}")
        return 1

    console.print()
    console.print("[bold]Before translation:[/bold]")
    console.print(f"  X: [{bmin[0]:.6f}, {bmax[0]:.6f}]")
    console.print(f"  Y: [{bmin[1]:.6f}, {bmax[1]:.6f}]")
    console.print(f"  Z: [{bmin[2]:.6f}, {bmax[2]:.6f}]")
    console.print()

    # Translate
    t0 = time.time()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed:,}/{task.total:,})"),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("Translating...", total=total)

        def _cb(done, _total):
            progress.update(task, completed=done)

        kept = translate_ply(ply_file, plan, output, progress_callback=_cb)

    elapsed = time.time() - t0

    # Compute bounds after
    try:
        analyzer_out = StatsAnalyzer(output)
        bmin_new, bmax_new = _get_bounds(analyzer_out)
    except Exception:
        bmin_new = bmax_new = None

    console.print()
    if bmin_new is not None:
        console.print("[bold]After translation:[/bold]")
        console.print(f"  X: [{bmin_new[0]:.6f}, {bmax_new[0]:.6f}]")
        console.print(f"  Y: [{bmin_new[1]:.6f}, {bmax_new[1]:.6f}]")
        console.print(f"  Z: [{bmin_new[2]:.6f}, {bmax_new[2]:.6f}]")
        console.print()

    console.print("[green]Success![/green]")
    console.print(f"  Points: {kept:,}")
    console.print(f"  Time: {elapsed:.2f}s")
    console.print(f"  Output: {output}")
    console.print()

    return 0


def _run_interactive(console: Console, ply_file: str) -> int:
    """Run interactive translate mode"""
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

    # Compute stats for each axis
    stats = {}
    for axis in ("x", "y", "z"):
        stats[axis] = analyzer.compute_stats(axis)

    console.print()
    console.print("[bold cyan]Translate Interactive Mode[/bold cyan]")
    console.print()
    console.print("[bold]Coordinate Statistics:[/bold]")
    console.print()

    for axis in ("x", "y", "z"):
        s = stats[axis]
        console.print(f"  [bold]{axis}[/bold]:")
        console.print(f"    Min:     {s.min_val:.6f}")
        console.print(f"    Max:     {s.max_val:.6f}")
        console.print(f"    Mean:    {s.mean:.6f}")
        console.print(f"    Median:  {s.median:.6f}")
        console.print(f"    Center:  {(s.min_val + s.max_val) / 2:.6f}")
        console.print()

    offsets = {"x": 0.0, "y": 0.0, "z": 0.0}
    specs = {"x": "0", "y": "0", "z": "0"}
    current = "x"

    bmin_orig, bmax_orig = _get_bounds(analyzer)

    while True:
        console.print("[bold]Current offsets:[/bold]")
        for axis in ("x", "y", "z"):
            marker = ">>>" if axis == current else "   "
            console.print(f"  {marker} {axis}: {offsets[axis]:.6f}  ({specs[axis]})")
        console.print()

        new_bmin = tuple(bmin_orig[i] + offsets["xyz"[i]] for i in range(3))
        new_bmax = tuple(bmax_orig[i] + offsets["xyz"[i]] for i in range(3))

        console.print("[bold]New bounding box (preview):[/bold]")
        console.print(f"  X: [{new_bmin[0]:.6f}, {new_bmax[0]:.6f}]")
        console.print(f"  Y: [{new_bmin[1]:.6f}, {new_bmax[1]:.6f}]")
        console.print(f"  Z: [{new_bmin[2]:.6f}, {new_bmax[2]:.6f}]")
        console.print()
        console.print("[dim]Commands:[/dim]")
        console.print("  x/y/z  - Switch axis")
        console.print("  m      - Set current axis to mean (center at origin)")
        console.print("  d      - Set current axis to median")
        console.print("  c      - Set current axis to center ((min+max)/2)")
        console.print("  p      - Enter percentile (e.g. 50)")
        console.print("  n      - Enter a numeric offset")
        console.print("  a      - Apply same setting to all axes")
        console.print("  r      - Reset all offsets to 0")
        console.print("  Enter  - Confirm and write")
        console.print("  q      - Quit")
        console.print()

        try:
            cmd = console.input(f"[bold]{current}>>[/bold] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            console.print()
            return 0

        if cmd == "q":
            console.print("[yellow]Cancelled.[/yellow]")
            return 0
        elif cmd in ("x", "y", "z"):
            current = cmd
        elif cmd == "r":
            for axis in ("x", "y", "z"):
                offsets[axis] = 0.0
                specs[axis] = "0"
        elif cmd == "m":
            s = stats[current]
            offsets[current] = -s.mean
            specs[current] = f"mean({s.mean:.6f})"
        elif cmd == "d":
            s = stats[current]
            offsets[current] = -s.median
            specs[current] = f"median({s.median:.6f})"
        elif cmd == "c":
            s = stats[current]
            val = (s.min_val + s.max_val) / 2
            offsets[current] = -val
            specs[current] = f"center({val:.6f})"
        elif cmd == "p":
            try:
                pct_str = console.input("  Percentile (e.g. 50): ").strip()
                pct = int(pct_str)
                col = analyzer.read_column(current)
                val = float(np.percentile(col, pct))
                offsets[current] = -val
                specs[current] = f"P{pct}({val:.6f})"
            except (ValueError, EOFError):
                console.print("[red]Invalid input.[/red]")
        elif cmd == "n":
            try:
                val_str = console.input(f"  Offset for {current}: ").strip()
                offsets[current] = float(val_str)
                specs[current] = val_str
            except (ValueError, EOFError):
                console.print("[red]Invalid input.[/red]")
        elif cmd == "a":
            target_offset = offsets[current]
            target_spec = specs[current]
            for axis in ("x", "y", "z"):
                offsets[axis] = target_offset
                specs[axis] = target_spec
        elif cmd == "":
            break
        else:
            console.print("[red]Unknown command.[/red]")

        console.print()

    # Build plan and write
    plan = TranslatePlan(
        x_offset=offsets["x"],
        y_offset=offsets["y"],
        z_offset=offsets["z"],
        x_spec=specs["x"],
        y_spec=specs["y"],
        z_spec=specs["z"],
    )

    stem = Path(ply_file).stem
    default_output = str(Path(ply_file).parent / f"{stem}_translated.ply")
    output_input = console.input(f"  Output file [{default_output}]: ").strip()
    output = output_input if output_input else default_output

    console.print()
    console.print("[bold]Translating...[/bold]")
    t0 = time.time()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed:,}/{task.total:,})"),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("Translating...", total=vertex_elem.count)

        def _cb(done, _total):
            progress.update(task, completed=done)

        kept = translate_ply(ply_file, plan, output, progress_callback=_cb)

    elapsed = time.time() - t0
    console.print()
    console.print("[green]Success![/green]")
    console.print(f"  Points: {kept:,}")
    console.print(f"  Time: {elapsed:.2f}s")
    console.print(f"  Output: {output}")
    console.print()

    return 0
