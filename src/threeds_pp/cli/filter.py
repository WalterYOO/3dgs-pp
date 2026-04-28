"""Filter command - filter Gaussian ellipsoids from PLY files."""

import sys
import time
from pathlib import Path
from typing import List, Optional

import numpy as np
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text

from ..core.filter import (
    DERIVED_PROPERTIES,
    FilterCondition,
    FilterEngine,
    _build_filter_comment,
    parse_filter_expression,
)
from ..core.stats import PropertyStats


def _get_key() -> str:
    """Capture a single keypress using raw terminal mode."""
    try:
        import tty
        import termios

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)

            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    if ch3 == "A":
                        return "k"
                    elif ch3 == "B":
                        return "j"
                    elif ch3 == "H":
                        return "g"
                    elif ch3 == "F":
                        return "G"
                    elif ch3 == "D":
                        return "a"
                    elif ch3 == "C":
                        return "d"
                elif ch2 == "\x1b":
                    return "\x1b"
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except Exception:
        return ""


def _get_input(prompt: str = "") -> str:
    """Get line input from user."""
    if prompt:
        print(prompt, end="")
        sys.stdout.flush()
    return sys.stdin.readline().strip()


def _format_val(value: float, decimals: int = 4) -> str:
    """Format a float value."""
    return f"{value:.{decimals}f}"


def run_filter(
    ply_file: str,
    filters: Optional[List[str]] = None,
    and_logic: bool = False,
    keep: bool = False,
    output: Optional[str] = None,
    interactive: bool = False,
) -> int:
    """Run the filter command.

    Args:
        ply_file: Path to input PLY file.
        filters: List of filter expression strings.
        and_logic: Use AND instead of OR for combining conditions.
        keep: Invert logic (keep matching, discard others).
        output: Output file path.
        interactive: Enter interactive mode.

    Returns:
        Exit code (0 = success, 1 = error).
    """
    console = Console()
    filters = filters or []

    if not Path(ply_file).exists():
        console.print(f"[red]Error:[/red] File not found: {ply_file}")
        return 1

    if not filters and not interactive:
        console.print(
            "[red]Error:[/red] No filter expressions provided. Use --filter or --interactive."
        )
        return 1

    if interactive:
        return _run_interactive(ply_file, console, filters, and_logic, keep, output)

    return _run_non_interactive(ply_file, console, filters, and_logic, keep, output)


def _run_non_interactive(
    ply_file: str,
    console: Console,
    filters: List[str],
    and_logic: bool,
    keep: bool,
    output: Optional[str],
) -> int:
    """Non-interactive filter execution."""
    try:
        start_time = time.time()
        engine = FilterEngine(ply_file)
        total_points = engine.analyzer.vertex_elem.count
        logic = "and" if and_logic else "or"

        # Parse expressions
        all_properties = engine.get_all_properties()
        conditions: List[FilterCondition] = []
        for expr in filters:
            try:
                cond = parse_filter_expression(expr)
                if cond.property_name not in all_properties:
                    console.print(
                        f"[red]Error:[/red] Unknown property '{cond.property_name}' "
                        f"in '{expr}'"
                    )
                    return 1
                conditions.append(cond)
            except ValueError as e:
                console.print(f"[red]Error parsing '{expr}':[/red] {e}")
                return 1

        console.print(f"[cyan]Input:[/cyan] {ply_file}")
        console.print(f"[cyan]Total points:[/cyan] {total_points:,}")
        console.print(f"[cyan]Conditions ({'AND' if and_logic else 'OR'}):[/cyan]")
        for expr in filters:
            console.print(f"  - {expr}")
        if keep:
            console.print("[cyan]Mode:[/cyan] keep matching, discard others")

        # Build mask
        console.print("\n[bold]Building filter mask...[/bold]")
        mask, per_counts = engine.build_mask(conditions, logic=logic, keep=keep)
        filtered_count = int(np.sum(mask))
        kept_count = total_points - filtered_count

        console.print(f"[green]Matched:[/green] {filtered_count:,} points")
        for cond, count in zip(conditions, per_counts):
            console.print(f"  {cond}: {count:,} points")
        console.print(
            f"[green]Will keep:[/green] {kept_count:,} points ({kept_count / total_points:.2%})"
        )

        # Determine output
        if output is None:
            input_path = Path(ply_file)
            output = str(input_path.parent / f"{input_path.stem}_filtered.ply")

        console.print(f"[cyan]Output:[/cyan] {output}")

        if filtered_count == 0:
            console.print(
                "[yellow]Warning:[/yellow] No points matched the filter conditions."
            )
            return 0

        # Write output
        console.print("\n[bold]Writing filtered PLY...[/bold]")
        filter_comment = _build_filter_comment(conditions, logic, keep)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed:,}/{task.total:,})"),
            TimeRemainingColumn(),
        ) as progress:
            write_task = progress.add_task("Writing...", total=kept_count)
            kept = engine.write_filtered(
                mask,
                output,
                filter_comment,
                progress_callback=lambda done, total: progress.update(
                    write_task, advance=1
                ),
            )

        elapsed = time.time() - start_time
        console.print("\n[green]Success![/green]")
        console.print(f"  Original: {total_points:,} points")
        console.print(
            f"  Filtered: {filtered_count:,} points ({filtered_count / total_points:.2%})"
        )
        console.print(f"  Kept: {kept:,} points ({kept / total_points:.2%})")
        console.print(f"  Time: {elapsed:.2f}s")
        console.print(f"  Output: {output}")

    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted[/dim]")
        return 1
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


def _run_interactive(
    ply_file: str,
    console: Console,
    initial_filters: List[str],
    and_logic: bool,
    keep: bool,
    output: Optional[str],
) -> int:
    """Interactive filter mode: stat viewing + filter expression input."""
    try:
        engine = FilterEngine(ply_file)
        total_points = engine.analyzer.vertex_elem.count
        all_properties = engine.get_all_properties()

        if not all_properties:
            console.print("[red]Error:[/red] No numeric properties found")
            return 1

        # Parse initial conditions
        conditions: List[FilterCondition] = []
        for expr in initial_filters:
            try:
                conditions.append(parse_filter_expression(expr))
            except ValueError as e:
                console.print(f"[yellow]Skipping invalid filter:[/yellow] {e}")

        logic = "and" if and_logic else "or"
        prop_index = 0
        stats_cache: dict[str, PropertyStats] = {}

        while True:
            console.print("\033c", end="")
            _render_screen(
                engine,
                ply_file,
                total_points,
                all_properties,
                prop_index,
                stats_cache,
                conditions,
                logic,
                keep,
                console,
            )

            # Update stats cache for current property
            current_prop = all_properties[prop_index]
            if current_prop not in stats_cache:
                stats_cache[current_prop] = engine._get_stats(current_prop)

            ch = _get_key()
            if not ch:
                continue

            if ch == "q":
                console.print("\n[dim]Exiting filter mode[/dim]")
                return 0
            elif ch == "?":
                _print_filter_help(console)
                _wait_enter()
            elif ch == "\x1b":
                # Escape - remove last condition
                if conditions:
                    conditions.pop()
                else:
                    _wait_enter()
            elif ch in ("\n", "\r"):
                # Enter line-input mode for filter expression
                _render_screen(
                    engine,
                    ply_file,
                    total_points,
                    all_properties,
                    prop_index,
                    stats_cache,
                    conditions,
                    logic,
                    keep,
                    console,
                )
                print("\n> ", end="", flush=True)
                expr = input()
                if not expr.strip():
                    continue
                try:
                    cond = parse_filter_expression(expr)
                    # Validate property exists
                    if cond.property_name not in all_properties:
                        console.print(
                            f"[red]Unknown property:[/red] {cond.property_name}"
                        )
                        _wait_enter()
                        continue
                    conditions.append(cond)
                except ValueError as e:
                    console.print(f"[red]Parse error:[/red] {e}")
                    _wait_enter()
            elif ch == "a":
                prop_index = max(0, prop_index - 1)
            elif ch == "d":
                prop_index = min(len(all_properties) - 1, prop_index + 1)
            elif ch == "w":
                and_logic = not and_logic
                logic = "and" if and_logic else "or"
            elif ch == "k":
                keep = not keep
            elif ch == "c":
                conditions.clear()
            elif ch == "s":
                if not conditions:
                    console.print("[yellow]No filters to apply.[/yellow]")
                    _wait_enter()
                    continue
                return _save_interactive(
                    engine,
                    ply_file,
                    total_points,
                    conditions,
                    logic,
                    keep,
                    output,
                    console,
                )

    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted[/dim]")
        return 1
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        import traceback

        traceback.print_exc()
        return 1


def _render_screen(
    engine: FilterEngine,
    ply_file: str,
    total_points: int,
    all_properties: List[str],
    prop_index: int,
    stats_cache: dict[str, PropertyStats],
    conditions: List[FilterCondition],
    logic: str,
    keep: bool,
    console: Console,
):
    """Render the interactive filter screen."""
    current_prop = all_properties[prop_index]
    stats = stats_cache.get(current_prop)

    # Header
    logic_str = "AND" if logic == "and" else "OR"
    mode_str = "KEEP matching" if keep else "REJECT matching"
    title = Text.assemble(
        f"Filter Mode: {Path(ply_file).name}  ",
        f"|  {total_points:,} points  ",
        f"|  {mode_str}  ",
        f"|  {logic_str}",
        style="bold cyan",
    )
    console.print(Panel(title))

    # Stats for current property
    if stats:
        _render_prop_stats(stats, prop_index, len(all_properties), console)

    # Active filters
    if conditions:
        table = Table(show_header=False, padding=(0, 1), box=None)
        table.add_column(style="cyan")
        table.add_column("right", style="green")
        table.add_column("right", style="dim")
        console.print(f"\n[bold]Active Filters ({logic_str}):[/bold]")
        for i, cond in enumerate(conditions, 1):
            table.add_row(f"{i}. {cond}", "", "")
        console.print(table)

    # Preview combined mask
    if conditions:
        mask, per_counts = engine.build_mask(conditions, logic=logic, keep=keep)
        filtered_count = int(sum(mask))
        kept_count = total_points - filtered_count

        pct_filtered = filtered_count / total_points * 100
        pct_kept = kept_count / total_points * 100
        status = Text.assemble(
            "\nFiltered: ",
            f"{filtered_count:,} ",
            f"({pct_filtered:.1f}%)  ",
            "|  Kept: ",
            f"{kept_count:,} ",
            f"({pct_kept:.1f}%)",
        )
        console.print(status)

        if per_counts:
            console.print("\n[dim]Per-condition matches:[/dim]")
            for cond, count in zip(conditions, per_counts):
                console.print(f"  {cond.property_name}: {count:,}")
    else:
        console.print(
            "\n[dim]No active filters. Press Enter to add a filter expression.[/dim]"
        )

    # Navigation
    nav = Text.assemble(
        f"\nProperty: {prop_index + 1}/{len(all_properties)} ({current_prop})  ",
        style="dim",
    )
    console.print(nav)

    # Key bindings
    keys_text = "[Enter] Add filter  [Esc] Remove last  [a/d] Navigate props  [w] Toggle AND/OR  [k] Toggle keep  [c] Clear  [s] Save  [q] Quit  [?] Help"
    console.print(f"\n[dim]{keys_text}[/dim]")


def _render_prop_stats(
    stats: PropertyStats, prop_index: int, total: int, console: Console
):
    """Render property statistics in a compact format."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("cyan")
    table.add_column("right", style="green")

    table.add_row("Property:", f"{stats.property_name} (derived)" if stats.property_name in DERIVED_PROPERTIES else stats.property_name)
    table.add_row("Min:", _format_val(stats.min_val))
    table.add_row("Max:", _format_val(stats.max_val))
    table.add_row("Mean:", _format_val(stats.mean))
    table.add_row("Median:", _format_val(stats.median))
    table.add_row("P5:", _format_val(stats.pct_5))
    table.add_row("P25:", _format_val(stats.q1))
    table.add_row("P75:", _format_val(stats.q3))
    table.add_row("P95:", _format_val(stats.pct_95))
    table.add_row("Std:", _format_val(stats.std))

    console.print(table)


def _print_filter_help(console: Console):
    """Print filter help information."""
    help_text = """
[bold]Filter Expressions:[/bold]

  Numeric:   opacity>0.1, scale_0<=0.5, x==0, z!=0
  Percentile: opacity<P5, scale_0>=P90, x>0P (any 0-100 rank)
  Range:     x~[-10,10], z!~[0,100]
  Pct Range: opacity~P[5,95], x!~P[10,90]

[bold]Keyboard Controls:[/bold]

  [cyan]Enter[/cyan]     - Add filter expression (line input)
  [cyan]Esc[/cyan]     - Remove last filter condition
  [cyan]a / ←[/cyan]   - Previous property
  [cyan]d / →[/cyan]   - Next property
  [cyan]w[/cyan]       - Toggle AND/OR logic
  [cyan]k[/cyan]       - Toggle keep/reject mode
  [cyan]c[/cyan]       - Clear all filters
  [cyan]s[/cyan]       - Save filtered output
  [cyan]q[/cyan]       - Quit without saving
  [cyan]?[/cyan]       - Show this help
"""
    console.print(Panel(help_text, title="[bold cyan]Filter Help[/bold cyan]"))


def _wait_enter():
    """Wait for user to press Enter."""
    _get_input("\n[dim]Press Enter to continue...[/dim]")


def _save_interactive(
    engine: FilterEngine,
    ply_file: str,
    total_points: int,
    conditions: List[FilterCondition],
    logic: str,
    keep: bool,
    output: Optional[str],
    console: Console,
) -> int:
    """Save filtered output in interactive mode."""
    import numpy as np
    import time
    from rich.progress import (
        Progress,
        SpinnerColumn,
        BarColumn,
        TextColumn,
        TimeRemainingColumn,
    )

    if not conditions:
        console.print("[yellow]No filters to apply.[/yellow]")
        return 0

    start_time = time.time()
    mask, _ = engine.build_mask(conditions, logic=logic, keep=keep)
    filtered_count = int(np.sum(mask))
    kept_count = total_points - filtered_count

    if output is None:
        input_path = Path(ply_file)
        output = str(input_path.parent / f"{input_path.stem}_filtered.ply")

    filter_comment = _build_filter_comment(conditions, logic, keep)
    console.print(f"[cyan]Output:[/cyan] {output}")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed:,}/{task.total:,})"),
        TimeRemainingColumn(),
    ) as progress:
        write_task = progress.add_task("Writing...", total=kept_count)
        kept = engine.write_filtered(
            mask,
            output,
            filter_comment,
            progress_callback=lambda done, total: progress.update(
                write_task, advance=1
            ),
        )

    elapsed = time.time() - start_time
    console.print("\n[green]Success![/green]")
    console.print(f"  Original: {total_points:,} points")
    console.print(
        f"  Filtered: {filtered_count:,} points ({filtered_count / total_points:.2%})"
    )
    console.print(f"  Kept: {kept:,} points ({kept / total_points:.2%})")
    console.print(f"  Time: {elapsed:.2f}s")
    console.print(f"  Output: {output}")
    return 0
