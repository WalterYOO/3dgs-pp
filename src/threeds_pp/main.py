"""3DGS Point Cloud Processing Tool - Main CLI entry point"""

import argparse
import sys
from pathlib import Path

from .cli.info import run_info
from .cli.view import run_view
from .cli.split import run_split
from .cli.downsample import run_downsample


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="3DGS Point Cloud Processing Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show file information
  3dgs-pp info scene.ply

  # View point cloud interactively
  3dgs-pp view scene.ply
  3dgs-pp view --page-size 50 --full scene.ply

  # Split into blocks
  3dgs-pp split "2*3*2" scene.ply
  3dgs-pp split --output-dir ./blocks "4*4*4" scene.ply

  # Downsample (retain 50%%)
  3dgs-pp downsample --ratio 0.5 scene.ply

  # Downsample (retain 10000 points)
  3dgs-pp downsample --count 10000 scene.ply

  # Downsample with specific method
  3dgs-pp downsample --ratio 0.3 --method opacity --output scene_small.ply scene.ply
        """
    )

    subparsers = parser.add_subparsers(title="Commands", dest="command", help="Available commands")

    # Info command
    info_parser = subparsers.add_parser("info", help="Display PLY file information")
    info_parser.add_argument("ply_file", help="Path to PLY file")

    # View command
    view_parser = subparsers.add_parser("view", help="View PLY file interactively")
    view_parser.add_argument("ply_file", help="Path to PLY file")
    view_parser.add_argument("--page-size", type=int, default=20,
                           help="Number of records per page (default: 20)")
    view_parser.add_argument("--full", action="store_true",
                           help="Show all properties by default")

    # Split command
    split_parser = subparsers.add_parser("split", help="Split PLY file into spatial blocks")
    split_parser.add_argument("split_spec", help="Split specification, e.g., '2*3*2' or '2x3x2'")
    split_parser.add_argument("ply_file", help="Path to PLY file")
    split_parser.add_argument("--output-dir", "-o", help="Output directory (default: same as input file)")

    # Downsample command
    downsample_parser = subparsers.add_parser("downsample", help="Downsample 3DGS PLY file")
    downsample_parser.add_argument("ply_file", help="Path to PLY file")
    group = downsample_parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ratio", type=float, help="Retention ratio (0 < ratio <= 1, e.g., 0.5 for 50%%)")
    group.add_argument("--count", type=int, help="Number of points to retain")
    downsample_parser.add_argument("--method", default="uniform",
                                   choices=["uniform", "opacity", "random", "voxel"],
                                   help="Sampling method (default: uniform)")
    downsample_parser.add_argument("--output", "-o", help="Output file path")
    downsample_parser.add_argument("--seed", type=int, help="Random seed (for random method)")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "info":
        return run_info(args.ply_file)
    elif args.command == "view":
        return run_view(args.ply_file, page_size=args.page_size, show_full=args.full)
    elif args.command == "split":
        return run_split(args.ply_file, args.split_spec, output_dir=args.output_dir)
    elif args.command == "downsample":
        return run_downsample(
            args.ply_file,
            ratio=args.ratio,
            count=args.count,
            method=args.method,
            output=args.output,
            seed=args.seed
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
