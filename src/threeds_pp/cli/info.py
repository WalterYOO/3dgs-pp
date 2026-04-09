"""Info command - display PLY file metadata"""

from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from ..ply import LazyPLYReader


def format_size(num: float, suffix: str = "B") -> str:
    """Format file size in human readable format"""
    for unit in ["", "K", "M", "G", "T"]:
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f} P{suffix}"


def run_info(ply_file: str):
    """Run info command"""
    console = Console()

    if not Path(ply_file).exists():
        console.print(f"[red]Error:[/red] File not found: {ply_file}")
        return 1

    try:
        with LazyPLYReader(ply_file) as reader:
            header = reader.header

            # Display file info
            file_size = Path(ply_file).stat().st_size

            console.print()
            console.print(Panel(f"[bold cyan]{Path(ply_file).name}[/bold cyan]",
                              subtitle=format_size(file_size)))

            # Header info
            console.print()
            console.print("[bold]Header:[/bold]")
            console.print(f"  Format: {header.format}")
            console.print(f"  Version: {header.version}")

            if header.comments:
                console.print("  Comments:")
                for comment in header.comments:
                    console.print(f"    - {comment}")

            # Elements table
            console.print()
            console.print("[bold]Elements:[/bold]")

            for elem in header.elements:
                elem_table = Table(title=f"\n[bold]{elem.name}[/bold] (count: {elem.count:,})",
                                  show_header=True, header_style="magenta")
                elem_table.add_column("#", style="dim", width=4)
                elem_table.add_column("Property", style="cyan")
                elem_table.add_column("Type", style="green")

                for idx, prop in enumerate(elem.properties):
                    type_str = prop.data_type
                    if prop.is_list:
                        type_str = f"list[{prop.list_size_type}] {type_str}"
                    elem_table.add_row(str(idx + 1), prop.name, type_str)

                console.print(elem_table)

            # Bounds info for vertex element
            vertex_elem = header.get_element('vertex')
            if vertex_elem and 'x' in [p.name for p in vertex_elem.properties]:
                console.print()
                console.print("[bold]Calculating bounds...[/bold]", end="\r")
                try:
                    (min_x, min_y, min_z), (max_x, max_y, max_z) = reader.get_bounds('vertex')

                    bounds_table = Table(title="\n[bold]Bounding Box[/bold]", show_header=True, header_style="magenta")
                    bounds_table.add_column("Axis", style="cyan")
                    bounds_table.add_column("Min", style="green")
                    bounds_table.add_column("Max", style="green")
                    bounds_table.add_column("Size", style="yellow")

                    bounds_table.add_row("X", f"{min_x:.6f}", f"{max_x:.6f}", f"{max_x - min_x:.6f}")
                    bounds_table.add_row("Y", f"{min_y:.6f}", f"{max_y:.6f}", f"{max_y - min_y:.6f}")
                    bounds_table.add_row("Z", f"{min_z:.6f}", f"{max_z:.6f}", f"{max_z - min_z:.6f}")

                    console.print(bounds_table)
                except Exception as e:
                    console.print(f"[yellow]Warning:[/yellow] Could not calculate bounds: {e}")

            console.print()

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        return 1

    return 0
