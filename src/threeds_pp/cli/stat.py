"""Stat command - statistics viewer for PLY file properties"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Optional

from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.panel import Panel

from ..core.stats import StatsAnalyzer, PropertyStats, save_comparison_text


CORE_PROPERTIES = ['x', 'y', 'z', 'opacity', 'scale_0', 'scale_1', 'scale_2']


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

            if ch == '\x1b':
                ch2 = sys.stdin.read(1)
                if ch2 == '[':
                    ch3 = sys.stdin.read(1)
                    if ch3 == 'A':
                        return 'k'
                    elif ch3 == 'B':
                        return 'j'
                    elif ch3 == 'H':
                        return 'g'
                    elif ch3 == 'F':
                        return 'G'
                    elif ch3 == 'D':
                        return 'a'
                    elif ch3 == 'C':
                        return 'd'
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except Exception:
        return ''


def _get_input(prompt: str) -> str:
    """Get input from user (fallback for non-tty)."""
    Console().print(prompt, end="")
    return input().strip()


def _format_val(value: float, decimals: int = 6) -> str:
    """Format a float value."""
    return f"{value:.{decimals}f}"


def _render_detail_view(
    stats: PropertyStats,
    total_points: int,
    current_prop: str,
    prop_index: int,
    total_props: int,
    console: Console,
):
    """Render single-attribute detail stats table."""
    table = Table(
        title=f"\n[bold cyan]Property:[/bold cyan] {current_prop}  "
              f"[bold]Samples:[/bold] {total_points:,}",
        show_header=True,
        header_style="magenta",
    )
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    rows = [
        ("Min", stats.min_val),
        ("5% Percentile", stats.pct_5),
        ("10% Percentile", stats.pct_10),
        ("20% Percentile", stats.pct_20),
        ("Q1 (25%)", stats.q1),
        ("Median (50%)", stats.median),
        ("Q3 (75%)", stats.q3),
        ("90% Percentile", stats.pct_90),
        ("95% Percentile", stats.pct_95),
        ("Max", stats.max_val),
        ("Mean", stats.mean),
        ("Std", stats.std),
        ("Skewness", stats.skewness),
        ("Kurtosis", stats.kurtosis),
    ]

    for label, val in rows:
        table.add_row(label, _format_val(val))

    console.print(table)

    # Status bar
    status = Text.assemble(
        ("Property: ", "dim"),
        (f"{prop_index + 1}/{total_props} ({current_prop})", "cyan"),
        ("  ", "dim"),
        ("[detail]", "yellow"),
    )
    console.print(status)
    console.print()


def _render_comparison_view(
    properties: List[str],
    stats_list: List[PropertyStats],
    current_prop: str,
    prop_index: int,
    total_props: int,
    console: Console,
):
    """Render multi-attribute comparison table."""
    table = Table(
        title="\n[bold cyan]Multi-Property Comparison[/bold cyan]",
        show_header=True,
        header_style="magenta",
    )
    table.add_column("Metric", style="cyan")
    for prop in properties:
        table.add_column(prop, style="green")

    rows = [
        ("Min", lambda s: s.min_val),
        ("5%", lambda s: s.pct_5),
        ("25%", lambda s: s.q1),
        ("50%", lambda s: s.median),
        ("75%", lambda s: s.q3),
        ("95%", lambda s: s.pct_95),
        ("Max", lambda s: s.max_val),
        ("Mean", lambda s: s.mean),
        ("Std", lambda s: s.std),
    ]

    for label, getter in rows:
        row = [label]
        for s in stats_list:
            row.append(_format_val(getter(s)))
        table.add_row(*row)

    console.print(table)

    status = Text.assemble(
        ("Property: ", "dim"),
        (f"{prop_index + 1}/{total_props} ({current_prop})", "cyan"),
        ("  ", "dim"),
        ("[comparison]", "yellow"),
    )
    console.print(status)
    console.print()


def _print_help(console: Console):
    """Print help information."""
    help_text = """
[bold]Keyboard Controls:[/bold]

  [cyan]a / ←[/cyan]     - Previous property
  [cyan]d / →[/cyan]     - Next property
  [cyan]s[/cyan]        - Toggle detail / comparison mode
  [cyan]f[/cyan]        - Full comparison (all properties)
  [cyan]o[/cyan]        - Save current stats to file
  [cyan]p[/cyan]        - Plot current property distribution
  [cyan]P[/cyan]        - Plot all core properties
  [cyan]q[/cyan]        - Quit
  [cyan]?[/cyan]        - Show this help
"""
    console.print(Panel(help_text, title="[bold cyan]Help[/bold cyan]"))


def _print_save_confirmation(console: Console, path: str):
    """Print save confirmation."""
    console.print(f"[green]Saved:[/green] {path}")


def _print_plot_confirmation(console: Console, path: str):
    """Print plot confirmation."""
    console.print(f"[green]Chart saved:[/green] {path}")


def _default_output_dir(ply_file: str) -> str:
    """Get default output directory for charts and saved stats."""
    stem = Path(ply_file).stem
    return os.path.join(os.path.dirname(ply_file) or '.', f"{stem}_stats_plots")


def run_stat(
    ply_file: str,
    attr: Optional[str] = None,
    show_all: bool = False,
    plot: bool = False,
    output_dir: Optional[str] = None,
    chart_type: str = 'histogram',
) -> int:
    """
    Run the stat command.

    Modes:
    - --plot only: Generate charts and exit (non-interactive)
    - --all only: Show multi-attribute comparison and exit
    - Default: Interactive statistics viewer
    """
    console = Console()

    try:
        if not Path(ply_file).exists():
            console.print(f"[red]Error:[/red] File not found: {ply_file}")
            return 1

        analyzer = StatsAnalyzer(ply_file)
        all_properties = analyzer.get_numeric_properties()

        if not all_properties:
            console.print("[red]Error:[/red] No numeric properties found")
            return 1

        if output_dir is None:
            output_dir = _default_output_dir(ply_file)

        # Determine default property
        default_attr = attr if attr in all_properties else all_properties[0]

        # Non-interactive: plot mode
        if plot and not show_all:
            props_to_plot = [default_attr]
            with console.status(f"[cyan]Generating chart for {default_attr}...[/cyan]"):
                path = analyzer.plot_distribution(default_attr, chart_type, output_dir)
            console.print(f"[green]Chart saved:[/green] {path}")
            return 0

        # Non-interactive: plot all mode
        if plot and show_all:
            core_avail = [p for p in CORE_PROPERTIES if p in all_properties]
            if not core_avail:
                core_avail = all_properties
            with console.status("[cyan]Generating charts for all core properties...[/cyan]"):
                paths = analyzer.plot_all_core(chart_type, output_dir)
            for p in paths:
                console.print(f"[green]Chart saved:[/green] {p}")
            return 0

        # Non-interactive: show all comparison
        if show_all:
            core_avail = [p for p in CORE_PROPERTIES if p in all_properties]
            if not core_avail:
                core_avail = all_properties[:6]

            stats_list = []
            for prop in core_avail:
                with console.status(f"[cyan]Computing stats for {prop}...[/cyan]"):
                    stats_obj = analyzer.compute_stats(prop)
                stats_list.append(stats_obj)

            _render_comparison_view(core_avail, stats_list,
                                    core_avail[0], 0, len(all_properties), console)
            return 0

        # Interactive mode
        _run_interactive(analyzer, console, all_properties, default_attr,
                         output_dir, chart_type)

    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


def _run_interactive(
    analyzer: StatsAnalyzer,
    console: Console,
    all_properties: List[str],
    default_attr: str,
    output_dir: str,
    chart_type: str,
):
    """Interactive statistics viewer with keyboard shortcuts."""
    prop_index = all_properties.index(default_attr)
    current_property = all_properties[prop_index]
    display_mode = 'detail'  # 'detail' | 'comparison' | 'full'
    stats_cache: Dict[str, PropertyStats] = {}

    # Core properties for comparison mode
    core_props = [p for p in CORE_PROPERTIES if p in all_properties]
    if not core_props:
        core_props = all_properties[:6]

    total_points = analyzer.vertex_elem.count

    while True:
        console.print("\033c", end="")

        if display_mode == 'detail':
            if current_property not in stats_cache:
                stats_obj = analyzer.compute_stats(current_property)
                stats_cache[current_property] = stats_obj
            else:
                stats_obj = stats_cache[current_property]

            _render_detail_view(stats_obj, total_points, current_property,
                                prop_index, len(all_properties), console)

        else:
            # Comparison or full comparison mode
            if display_mode == 'full':
                props_to_show = all_properties
            else:
                props_to_show = core_props

            # Compute stats for all shown properties
            for p in props_to_show:
                if p not in stats_cache:
                    stats_cache[p] = analyzer.compute_stats(p)

            stats_list = [stats_cache[p] for p in props_to_show]
            _render_comparison_view(props_to_show, stats_list, current_property,
                                    prop_index, len(all_properties), console)

        # Get key input
        ch = _get_key()
        if not ch:
            ch = _get_input("\n[dim]Command (? for help): [/dim]")
            if ch:
                ch = ch[0].lower()

        # Process command
        if ch == 'q':
            break
        elif ch == '?':
            _print_help(console)
            _get_input("\n[dim]Press Enter to continue...[/dim]")
        elif ch in ('a',):
            prop_index = max(0, prop_index - 1)
            current_property = all_properties[prop_index]
        elif ch in ('d',):
            prop_index = min(len(all_properties) - 1, prop_index + 1)
            current_property = all_properties[prop_index]
        elif ch == 's':
            if display_mode == 'detail':
                display_mode = 'comparison'
            else:
                display_mode = 'detail'
        elif ch == 'f':
            display_mode = 'full'
        elif ch == 'o':
            _handle_save(stats_cache, current_property, display_mode,
                         core_props, all_properties, output_dir, console, analyzer)
            _get_input("\n[dim]Press Enter to continue...[/dim]")
        elif ch == 'p':
            _handle_plot(analyzer, current_property, chart_type, output_dir, console)
            _get_input("\n[dim]Press Enter to continue...[/dim]")
        elif ch == 'P':
            _handle_plot_all(analyzer, core_props, chart_type, output_dir, console)
            _get_input("\n[dim]Press Enter to continue...[/dim]")


def _handle_save(
    stats_cache: Dict[str, PropertyStats],
    current_property: str,
    display_mode: str,
    core_props: List[str],
    all_properties: List[str],
    output_dir: str,
    console: Console,
    analyzer: StatsAnalyzer,
):
    """Handle 'o' keypress - save current stats to text file."""
    if display_mode == 'detail':
        stats_obj = stats_cache.get(current_property)
        if stats_obj:
            path = analyzer.save_stats_text(stats_obj, output_dir)
            _print_save_confirmation(console, path)
        else:
            console.print("[yellow]No stats to save. Switch to the property first.[/yellow]")
    else:
        # Save comparison table
        if display_mode == 'full':
            props_to_show = all_properties
        else:
            props_to_show = core_props

        stats_list = [stats_cache[p] for p in props_to_show if p in stats_cache]
        if stats_list:
            path = save_comparison_text(props_to_show[:len(stats_list)], stats_list,
                                        analyzer.file_path, output_dir)
            _print_save_confirmation(console, path)
        else:
            console.print("[yellow]No stats to save.[/yellow]")


def _handle_plot(
    analyzer: StatsAnalyzer,
    property_name: str,
    chart_type: str,
    output_dir: str,
    console: Console,
):
    """Handle 'p' keypress - plot current property distribution."""
    try:
        path = analyzer.plot_distribution(property_name, chart_type, output_dir)
        _print_plot_confirmation(console, path)
    except Exception as e:
        console.print(f"[red]Chart error:[/red] {e}")


def _handle_plot_all(
    analyzer: StatsAnalyzer,
    core_props: List[str],
    chart_type: str,
    output_dir: str,
    console: Console,
):
    """Handle 'P' keypress - plot all core properties."""
    try:
        paths = analyzer.plot_all_core(chart_type, output_dir)
        for p in paths:
            _print_plot_confirmation(console, p)
    except Exception as e:
        console.print(f"[red]Chart error:[/red] {e}")
