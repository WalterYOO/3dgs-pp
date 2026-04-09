"""View command - interactive terminal viewer for PLY files"""

import sys
import math
from typing import Optional, List, Tuple
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.panel import Panel

from ..ply import LazyPLYReader


# Core properties to show by default
CORE_PROPERTIES = ['x', 'y', 'z', 'opacity']
# All properties
ALL_PROPERTIES = [
    'x', 'y', 'z',
    'f_dc_0', 'f_dc_1', 'f_dc_2',
    *[f'f_rest_{i}' for i in range(45)],
    'opacity',
    'scale_0', 'scale_1', 'scale_2',
    'rot_0', 'rot_1', 'rot_2', 'rot_3'
]


def format_value(value, decimals: int = 6) -> str:
    """Format a numeric value"""
    if isinstance(value, float):
        return f"{value:.{decimals}f}"
    return str(value)


def print_help():
    """Print help information"""
    help_text = """
[bold]Keyboard Controls:[/bold]

  [cyan]j / ↓[/cyan]     - Next page
  [cyan]k / ↑[/cyan]     - Previous page
  [cyan]g / Home[/cyan]  - Go to first page
  [cyan]G / End[/cyan]   - Go to last page
  [cyan]: / N[/cyan]    - Go to page number N
  [cyan]/ search[/cyan] - Search for value
  [cyan]e[/cyan]        - Toggle full properties
  [cyan]q[/cyan]        - Quit
  [cyan]?[/cyan]        - Show this help
"""
    console = Console()
    console.print(Panel(help_text, title="[bold cyan]Help[/bold cyan]"))


def get_input(prompt: str) -> str:
    """Get input from user"""
    Console().print(prompt, end="")
    return input()


def run_view(ply_file: str, page_size: int = 20, show_full: bool = False):
    """Run view command"""
    console = Console()

    try:
        with LazyPLYReader(ply_file) as reader:
            vertex_elem = reader.header.get_element('vertex')
            if not vertex_elem:
                console.print("[red]Error:[/red] No 'vertex' element found in PLY file")
                return 1

            total_points = vertex_elem.count
            total_pages = (total_points + page_size - 1) // page_size
            current_page = 0
            show_full_props = show_full
            search_query: Optional[str] = None

            prop_names = reader.get_property_names('vertex')

            while True:
                # Clear screen (simple approach)
                console.print("\033c", end="")

                # Determine which properties to show
                display_props = []
                if show_full_props:
                    # Show all properties in order
                    for p in prop_names:
                        display_props.append(p)
                else:
                    # Show only core properties
                    for p in CORE_PROPERTIES:
                        if p in prop_names:
                            display_props.append(p)

                # Calculate range
                start_idx = current_page * page_size
                end_idx = min(start_idx + page_size, total_points)

                # Create table
                table = Table(title=f"\n[bold cyan]{ply_file}[/bold cyan]", show_header=True, header_style="magenta")
                table.add_column("Index", style="dim", width=8)

                for prop in display_props:
                    table.add_column(prop, style="green")

                # Load and display data
                for idx in range(start_idx, end_idx):
                    elem = reader.get_element(idx, 'vertex')
                    row = [str(idx)]
                    for prop in display_props:
                        row.append(format_value(elem.get(prop, 'N/A')))
                    table.add_row(*row)

                console.print(table)

                # Status line
                status = Text.assemble(
                    ("Page ", "dim"),
                    (f"{current_page + 1}", "cyan"),
                    ("/", "dim"),
                    (f"{total_pages}", "cyan"),
                    ("  (Records ", "dim"),
                    (f"{start_idx}", "green"),
                    ("-", "dim"),
                    (f"{end_idx - 1}", "green"),
                    (" / ", "dim"),
                    (f"{total_points:,}", "green"),
                    (")", "dim"),
                )
                if show_full_props:
                    status.append("  [full mode]", "yellow")
                if search_query:
                    status.append(f"  [search: {search_query}]", "magenta")

                console.print(status)
                console.print()

                # Get input
                try:
                    import tty
                    import termios

                    fd = sys.stdin.fileno()
                    old_settings = termios.tcgetattr(fd)
                    try:
                        tty.setraw(sys.stdin.fileno())
                        ch = sys.stdin.read(1)

                        # Handle escape sequences
                        if ch == '\x1b':
                            ch2 = sys.stdin.read(1)
                            if ch2 == '[':
                                ch3 = sys.stdin.read(1)
                                if ch3 == 'A':  # Up arrow
                                    ch = 'k'
                                elif ch3 == 'B':  # Down arrow
                                    ch = 'j'
                                elif ch3 == 'H':  # Home
                                    ch = 'g'
                                elif ch3 == 'F':  # End
                                    ch = 'G'
                    finally:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                except:
                    # Fallback for non-tty environments
                    ch = get_input("\n[dim]Command (? for help): [/dim]").strip() or '?'
                    if ch:
                        ch = ch[0]

                # Process command
                if ch == 'q':
                    break
                elif ch == '?':
                    print_help()
                    get_input("\n[dim]Press Enter to continue...[/dim]")
                elif ch == 'j':
                    if current_page < total_pages - 1:
                        current_page += 1
                elif ch == 'k':
                    if current_page > 0:
                        current_page -= 1
                elif ch == 'g':
                    current_page = 0
                elif ch == 'G':
                    current_page = total_pages - 1
                elif ch == 'e':
                    show_full_props = not show_full_props
                elif ch == ':':
                    try:
                        page_str = get_input("\n[dim]Go to page: [/dim]")
                        page_num = int(page_str) - 1
                        if 0 <= page_num < total_pages:
                            current_page = page_num
                    except ValueError:
                        pass
                elif ch == '/':
                    search_query = get_input("\n[dim]Search: [/dim]")
                    # Simple search - scan for value
                    if search_query:
                        found = False
                        for idx in range(total_points):
                            elem = reader.get_element(idx, 'vertex')
                            for p in display_props:
                                val_str = str(elem.get(p, ''))
                                if search_query.lower() in val_str.lower():
                                    current_page = idx // page_size
                                    found = True
                                    break
                            if found:
                                break
                        if not found:
                            get_input(f"\n[yellow]'{search_query}' not found[/yellow] - [dim]Press Enter...[/dim]")
                    else:
                        search_query = None

    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0
