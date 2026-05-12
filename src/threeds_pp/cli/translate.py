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
    _compute_stats_from_array,
    _is_stat_keyword,
    _load_axes,
    _resolve_offset_from_array,
    parse_translate_spec,
    TranslatePlan,
    translate_ply,
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

    # Load x/y/z columns once for all downstream use (offset resolution + bounds)
    console.print()
    console.print("[bold]Computing translation offsets...[/bold]")
    try:
        axes = _load_axes(analyzer)
    except Exception as e:
        console.print(f"[red]Error:[/red] Failed to read columns: {e}")
        return 1

    # Resolve offsets from in-memory arrays (no extra disk reads)
    plan = TranslatePlan()
    try:
        for axis, spec in [("x", x_s), ("y", y_s), ("z", z_s)]:
            if spec is not None and _is_stat_keyword(spec):
                offset, desc = _resolve_offset_from_array(axes[axis], axis, spec)
            elif spec is not None:
                offset, desc = float(spec), spec
            else:
                offset, desc = 0.0, "0"
            setattr(plan, f"{axis}_offset", offset)
            setattr(plan, f"{axis}_spec", desc)
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

    # Compute bounds from the already-loaded arrays (no extra disk reads)
    console.print()
    bmin = (float(np.min(axes["x"])), float(np.min(axes["y"])), float(np.min(axes["z"])))
    bmax = (float(np.max(axes["x"])), float(np.max(axes["y"])), float(np.max(axes["z"])))

    console.print()
    console.print("[bold]Before translation:[/bold]")
    console.print(f"  X: [{bmin[0]:.6f}, {bmax[0]:.6f}]")
    console.print(f"  Y: [{bmin[1]:.6f}, {bmax[1]:.6f}]")
    console.print(f"  Z: [{bmin[2]:.6f}, {bmax[2]:.6f}]")

    # After-translation bounds are just old bounds + offset (no need to re-read file)
    bmin_new = (
        bmin[0] + plan.x_offset,
        bmin[1] + plan.y_offset,
        bmin[2] + plan.z_offset,
    )
    bmax_new = (
        bmax[0] + plan.x_offset,
        bmax[1] + plan.y_offset,
        bmax[2] + plan.z_offset,
    )

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

    console.print()
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

    # Load x/y/z columns once — all stats computed from memory
    console.print()
    console.print("[bold]Loading coordinate data...[/bold]")
    try:
        axes = _load_axes(analyzer)
    except Exception as e:
        console.print(f"[red]Error:[/red] Failed to read columns: {e}")
        return 1

    # Compute stats from in-memory arrays
    stats = {}
    for axis in ("x", "y", "z"):
        stats[axis] = _compute_stats_from_array(axes[axis], axis)

    # Compute bounds from arrays
    bmin_orig = (
        float(np.min(axes["x"])),
        float(np.min(axes["y"])),
        float(np.min(axes["z"])),
    )
    bmax_orig = (
        float(np.max(axes["x"])),
        float(np.max(axes["y"])),
        float(np.max(axes["z"])),
    )

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
        console.print("  <      - Set current axis to min (lower bound to origin)")
        console.print("  >      - Set current axis to max (upper bound to origin)")
        console.print("  m      - Set current axis to mean")
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
            cmd = console.input(f"[bold]{current}>>[/bold] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print()
            return 0

        cmd_lower = cmd.lower()

        if cmd_lower == "q":
            console.print("[yellow]Cancelled.[/yellow]")
            return 0
        elif cmd_lower in ("x", "y", "z"):
            current = cmd_lower
        elif cmd == "<":
            s = stats[current]
            offsets[current] = -s.min_val
            specs[current] = f"min({s.min_val:.6f})"
        elif cmd == ">":
            s = stats[current]
            offsets[current] = -s.max_val
            specs[current] = f"max({s.max_val:.6f})"
        elif cmd_lower == "r":
            for ax in ("x", "y", "z"):
                offsets[ax] = 0.0
                specs[ax] = "0"
        elif cmd_lower == "m":
            s = stats[current]
            offsets[current] = -s.mean
            specs[current] = f"mean({s.mean:.6f})"
        elif cmd_lower == "d":
            s = stats[current]
            offsets[current] = -s.median
            specs[current] = f"median({s.median:.6f})"
        elif cmd_lower == "c":
            s = stats[current]
            val = (s.min_val + s.max_val) / 2
            offsets[current] = -val
            specs[current] = f"center({val:.6f})"
        elif cmd_lower == "p":
            try:
                pct_str = console.input("  Percentile (e.g. 50): ").strip()
                pct = int(pct_str)
                val = float(np.percentile(axes[current], pct))
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
            for ax in ("x", "y", "z"):
                offsets[ax] = target_offset
                specs[ax] = target_spec
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
