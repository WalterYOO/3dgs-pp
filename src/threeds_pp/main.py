"""3DGS Point Cloud Processing Tool - Main CLI entry point"""

import argparse
import sys

from .cli.info import run_info
from .cli.view import run_view
from .cli.split import run_split
from .cli.downsample import run_downsample
from .cli.stat import run_stat
from .cli.filter import run_filter
from .cli.translate import run_translate
from .cli.transform import run_transform
from .cli.crop import run_crop
from .cli.fill import run_fill


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

  # Filter by property values
  3dgs-pp filter --filter "opacity<P5" scene.ply
  3dgs-pp filter --filter "opacity>0.1" --filter "scale_0<P10" scene.ply
  3dgs-pp filter --and --filter "opacity<0.01" --filter "z>100" scene.ply
  3dgs-pp filter --keep --filter "opacity>P5" scene.ply
  3dgs-pp filter -i scene.ply

  # Downsample (retain 50%%)
  3dgs-pp downsample --ratio 0.5 scene.ply

  # Downsample (retain 10000 points)
  3dgs-pp downsample --count 10000 scene.ply

  # Downsample with specific method
  3dgs-pp downsample --ratio 0.3 --method opacity --output scene_small.ply scene.ply

  # Translate coordinates
  3dgs-pp translate --x 10 --y -5 scene.ply
  3dgs-pp translate --all mean scene.ply
  3dgs-pp translate --x mean --y median --z center scene.ply

  # Axis transform (swap/invert/rotate)
  3dgs-pp transform --swap xy scene.ply
  3dgs-pp transform --inv x scene.ply
  3dgs-pp transform --rot z 90 scene.ply
  3dgs-pp transform --transform "x->y,y->-x,z->z" scene.ply

  # Crop by spatial region (two-point AABB)
  3dgs-pp crop --p1 -10,-5,0 --p2 10,5,20 scene.ply

  # Crop by spatial region (eight-point hexahedron)
  3dgs-pp crop --p1 0,0,0 --p2 10,0,0 --p3 10,10,0 --p4 0,10,0 --p5 2,2,20 --p6 8,2,20 --p7 8,8,20 --p8 2,8,20 scene.ply

  # Crop outside region
  3dgs-pp crop --p1 -10,-5,0 --p2 10,5,20 --outside scene.ply

  # Fill source PLY into target region
  3dgs-pp fill --source source.ply --p1 -10,-5,0 --p2 10,5,20 target.ply

  # Fill with offset
  3dgs-pp fill --source source.ply --p1 -10,-5,0 --p2 10,5,20 --offset 5,0,0 target.ply
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
                                   choices=["uniform", "opacity", "random", "voxel", "merge"],
                                   help="Sampling method (default: uniform)")
    downsample_parser.add_argument("--output", "-o", help="Output file path")
    downsample_parser.add_argument("--seed", type=int, help="Random seed (for random method)")

    # Stat command
    stat_parser = subparsers.add_parser("stat", help="Statistics overview of PLY properties")
    stat_parser.add_argument("ply_file", help="Path to PLY file")
    stat_parser.add_argument("--attr", default=None, help="Default property to view (default: first numeric)")
    stat_parser.add_argument("--all", action="store_true", help="Show all properties comparison and exit")
    stat_parser.add_argument("--plot", action="store_true", help="Generate distribution chart(s) and exit")
    stat_parser.add_argument("--output-dir", "-o", default=None, help="Output directory for charts and saved stats")
    stat_parser.add_argument("--type", default="histogram", choices=["histogram", "box", "violin"],
                             help="Chart type (default: histogram)")

    # Filter command
    filter_parser = subparsers.add_parser("filter", help="Filter Gaussian ellipsoids based on conditions")
    filter_parser.add_argument("ply_file", help="Path to PLY file")
    filter_parser.add_argument("--filter", "-f", action="append", metavar="EXPR",
                               help="Filter expression, e.g. 'opacity<0.1' (repeatable)")
    filter_parser.add_argument("--and", dest="and_logic", action="store_true",
                               help="Use AND logic for combining conditions")
    filter_parser.add_argument("--keep", action="store_true",
                               help="Invert: keep matching, discard others")
    filter_parser.add_argument("--output", "-o", help="Output file path")
    filter_parser.add_argument("--interactive", "-i", action="store_true",
                               help="Enter interactive filter mode")

    # Translate command
    translate_parser = subparsers.add_parser("translate", help="Translate PLY coordinates")
    translate_parser.add_argument("ply_file", help="Path to PLY file")
    trans_group = translate_parser.add_mutually_exclusive_group()
    trans_group.add_argument("--all", dest="all_val", help="Apply same translation to all axes (value, mean, median, center, P<N>)")
    translate_parser.add_argument("--x", help="X axis translation (value, mean, median, center, P<N>)")
    translate_parser.add_argument("--y", help="Y axis translation (value, mean, median, center, P<N>)")
    translate_parser.add_argument("--z", help="Z axis translation (value, mean, median, center, P<N>)")
    translate_parser.add_argument("--output", "-o", help="Output file path")
    translate_parser.add_argument("--interactive", "-i", action="store_true",
                                  help="Enter interactive translate mode")

    # Transform command
    transform_parser = subparsers.add_parser("transform", help="Transform PLY axes (swap/rotate)")
    transform_parser.add_argument("ply_file", help="Path to PLY file")
    trans_group = transform_parser.add_mutually_exclusive_group()
    trans_group.add_argument("--swap", help="Axis swap (mirror): xy, nxy, xz, nxz, yz, nyz ('n' = negative)")
    trans_group.add_argument("--inv", choices=["x", "y", "z"],
                             help="Axis inversion (mirror): x, y, or z")
    trans_group.add_argument("--rot", nargs=2, metavar=("AXIS", "ANGLE"),
                             help="Rotation: AXIS=x/y/z, ANGLE=90/180/270")
    trans_group.add_argument("--transform", help="Generic expression, e.g. x->y,y->-x,z->z")
    transform_parser.add_argument("--output", "-o", help="Output file path")
    transform_parser.add_argument("--interactive", "-i", action="store_true",
                                  help="Enter interactive transform mode")

    # Crop command
    crop_parser = subparsers.add_parser("crop", help="Crop points by spatial region")
    crop_parser.add_argument("ply_file", help="Path to PLY file")
    crop_parser.add_argument("--p1", required=True, help="Point 1 as 'x,y,z' (min corner for AABB, or vertex 1 for hexahedron)")
    crop_parser.add_argument("--p2", help="Point 2 as 'x,y,z' (max corner for AABB, or vertex 2 for hexahedron)")
    crop_parser.add_argument("--p3", help="Point 3 as 'x,y,z' (hexahedron mode)")
    crop_parser.add_argument("--p4", help="Point 4 as 'x,y,z' (hexahedron mode)")
    crop_parser.add_argument("--p5", help="Point 5 as 'x,y,z' (hexahedron mode)")
    crop_parser.add_argument("--p6", help="Point 6 as 'x,y,z' (hexahedron mode)")
    crop_parser.add_argument("--p7", help="Point 7 as 'x,y,z' (hexahedron mode)")
    crop_parser.add_argument("--p8", help="Point 8 as 'x,y,z' (hexahedron mode)")
    crop_parser.add_argument("--outside", action="store_true",
                             help="Keep points outside the region (default: keep inside)")
    crop_parser.add_argument("--output", "-o", help="Output file path")

    # Fill command
    fill_parser = subparsers.add_parser("fill", help="Fill source PLY points into target region")
    fill_parser.add_argument("target_file", help="Path to target PLY file")
    fill_parser.add_argument("--source", required=True, help="Path to source PLY file")
    fill_parser.add_argument("--p1", required=True, help="Point 1 as 'x,y,z' (min corner for AABB, or vertex 1 for hexahedron)")
    fill_parser.add_argument("--p2", help="Point 2 as 'x,y,z' (max corner for AABB, or vertex 2 for hexahedron)")
    fill_parser.add_argument("--p3", help="Point 3 as 'x,y,z' (hexahedron mode)")
    fill_parser.add_argument("--p4", help="Point 4 as 'x,y,z' (hexahedron mode)")
    fill_parser.add_argument("--p5", help="Point 5 as 'x,y,z' (hexahedron mode)")
    fill_parser.add_argument("--p6", help="Point 6 as 'x,y,z' (hexahedron mode)")
    fill_parser.add_argument("--p7", help="Point 7 as 'x,y,z' (hexahedron mode)")
    fill_parser.add_argument("--p8", help="Point 8 as 'x,y,z' (hexahedron mode)")
    fill_parser.add_argument("--offset", default="0,0,0",
                             help="Offset applied to source points as 'dx,dy,dz' (default: 0,0,0)")
    fill_parser.add_argument("--output", "-o", help="Output file path")

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
    elif args.command == "filter":
        return run_filter(
            args.ply_file,
            filters=args.filter or [],
            and_logic=args.and_logic,
            keep=args.keep,
            output=args.output,
            interactive=args.interactive,
        )
    elif args.command == "stat":
        return run_stat(
            args.ply_file,
            attr=args.attr,
            show_all=args.all,
            plot=args.plot,
            output_dir=args.output_dir,
            chart_type=args.type,
        )
    elif args.command == "translate":
        return run_translate(
            args.ply_file,
            x=args.x,
            y=args.y,
            z=args.z,
            all_val=args.all_val,
            output=args.output,
            interactive=args.interactive,
        )
    elif args.command == "transform":
        return run_transform(
            args.ply_file,
            swap=args.swap,
            inv=args.inv,
            rot=args.rot,
            transform_expr=args.transform,
            output=args.output,
            interactive=args.interactive,
        )
    elif args.command == "crop":
        return run_crop(
            args.ply_file,
            p1=args.p1,
            p2=args.p2,
            p3=args.p3,
            p4=args.p4,
            p5=args.p5,
            p6=args.p6,
            p7=args.p7,
            p8=args.p8,
            outside=args.outside,
            output=args.output,
        )
    elif args.command == "fill":
        return run_fill(
            args.target_file,
            source_file=args.source,
            p1=args.p1,
            p2=args.p2,
            p3=args.p3,
            p4=args.p4,
            p5=args.p5,
            p6=args.p6,
            p7=args.p7,
            p8=args.p8,
            offset=args.offset,
            output=args.output,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
