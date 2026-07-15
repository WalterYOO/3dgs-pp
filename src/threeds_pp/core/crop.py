"""Spatial cropping for 3DGS PLY files.

Supports two-point (axis-aligned bounding box) and eight-point (convex hexahedron)
region specification, with optional invert (keep outside) mode.
"""

from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from ..ply.header import PLYHeader
from ..ply.writer import PLYWriter, copy_header_for_partition
from .stats import StatsAnalyzer


def _parse_point(s: str) -> Tuple[float, float, float]:
    """Parse a comma-separated point string 'x,y,z' into floats."""
    parts = s.split(",")
    if len(parts) != 3:
        raise ValueError(f"Invalid point format: '{s}'. Expected 'x,y,z'")
    return float(parts[0]), float(parts[1]), float(parts[2])


def build_aabb_mask(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    p1: Tuple[float, float, float],
    p2: Tuple[float, float, float],
) -> np.ndarray:
    """Build boolean mask for points inside an axis-aligned bounding box.

    Args:
        x: X coordinates.
        y: Y coordinates.
        z: Z coordinates.
        p1: Minimum corner (min_x, min_y, min_z).
        p2: Maximum corner (max_x, max_y, max_z).

    Returns:
        Boolean array, True for points inside the AABB.
    """
    min_x, min_y, min_z = p1
    max_x, max_y, max_z = p2
    return (
        (x >= min_x) & (x <= max_x)
        & (y >= min_y) & (y <= max_y)
        & (z >= min_z) & (z <= max_z)
    )


def build_hexahedron_mask(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    corners: List[Tuple[float, float, float]],
) -> np.ndarray:
    """Build boolean mask for points inside a convex hexahedron.

    Uses scipy.spatial.ConvexHull to compute the face equations of the
    convex hull of the 8 corner points. A point is inside iff it lies on
    the same side of all faces (within numerical tolerance).

    Args:
        x: X coordinates.
        y: Y coordinates.
        z: Z coordinates.
        corners: 8 corner points defining the convex hexahedron.

    Returns:
        Boolean array, True for points inside the hexahedron.
    """
    from scipy.spatial import ConvexHull

    hull = ConvexHull(np.array(corners))
    # hull.equations: (n_faces, 4) [A, B, C, D] where A*x + B*y + C*z + D = 0
    # For a point inside: A*x + B*y + C*z + D <= 0 for all faces
    pts = np.stack([x, y, z], axis=-1)  # (N, 3)
    # (N, 3) @ (n_faces, 3).T + (n_faces,) -> (N, n_faces)
    dists = pts @ hull.equations[:, :3].T + hull.equations[:, 3]
    return np.all(dists <= 1e-10, axis=1)


def crop_ply(
    ply_file: str,
    output: str,
    p1: Tuple[float, float, float],
    p2: Optional[Tuple[float, float, float]] = None,
    corners: Optional[List[Tuple[float, float, float]]] = None,
    outside: bool = False,
    progress_callback=None,
) -> int:
    """Crop points from a PLY file based on spatial region.

    Args:
        ply_file: Path to input PLY file.
        output: Path to output PLY file.
        p1: First point (min corner for AABB mode).
        p2: Second point (max corner for AABB mode). If None, eight-point mode.
        corners: 8 corner points for hexahedron mode. Required if p2 is None.
        outside: If True, keep points outside the region (default: keep inside).
        progress_callback: Optional callback(current, total) for progress.

    Returns:
        Number of kept points.
    """
    analyzer = StatsAnalyzer(ply_file)
    total = analyzer.vertex_elem.count

    # Read coordinates
    x = analyzer.read_column("x")
    y = analyzer.read_column("y")
    z = analyzer.read_column("z")

    # Build mask
    if p2 is not None:
        mask = build_aabb_mask(x, y, z, p1, p2)
        region_desc = f"p1={p1} p2={p2}"
    else:
        if corners is None or len(corners) != 8:
            raise ValueError("Eight-point mode requires exactly 8 corner points")
        mask = build_hexahedron_mask(x, y, z, corners)
        region_desc = f"corners={len(corners)}"

    if outside:
        mask = ~mask

    keep_indices = np.where(mask)[0]
    kept_count = len(keep_indices)
    removed = total - kept_count

    # Build header
    new_header = copy_header_for_partition(analyzer.header, kept_count)
    mode_str = "outside" if outside else "inside"
    new_header.comments.append(f"crop mode={mode_str} {region_desc}")
    new_header.comments.append(
        f"crop kept {kept_count:,} of {total:,} points"
    )

    # Write output
    dtype = analyzer._get_struct_dtype()
    mmap = np.memmap(
        analyzer.file_path,
        dtype=dtype,
        mode="r",
        offset=analyzer.header.header_size,
        shape=total,
    )
    prop_names = [p.name for p in analyzer.vertex_elem.properties]

    with PLYWriter(output) as writer:
        writer.write_header(new_header)
        for i, idx in enumerate(keep_indices):
            row = mmap[idx]
            data = {name: row[name] for name in prop_names}
            writer.write_element("vertex", data)
            if progress_callback:
                progress_callback(i + 1, kept_count)

    del mmap
    return kept_count