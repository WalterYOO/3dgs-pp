"""Spatial filling for 3DGS PLY files.

Fills source PLY points into a target region of a destination PLY file,
with relative offset alignment. Only source points that fall within the
target region after offset are included.
"""

from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from ..ply.header import PLYHeader
from ..ply.writer import PLYWriter, copy_header_for_partition
from .crop import build_aabb_mask, build_hexahedron_mask
from .stats import StatsAnalyzer


def _check_property_compatibility(
    header_a: PLYHeader, header_b: PLYHeader
) -> None:
    """Check that two PLY files have compatible vertex property schemas.

    Raises ValueError if properties differ.
    """
    elem_a = header_a.get_element("vertex")
    elem_b = header_b.get_element("vertex")
    if elem_a is None or elem_b is None:
        raise ValueError("Both files must have a 'vertex' element")

    props_a = [(p.name, p.data_type) for p in elem_a.properties if not p.is_list]
    props_b = [(p.name, p.data_type) for p in elem_b.properties if not p.is_list]

    if props_a != props_b:
        a_str = ", ".join(f"{n}:{t}" for n, t in props_a)
        b_str = ", ".join(f"{n}:{t}" for n, t in props_b)
        raise ValueError(
            f"Property mismatch between source and target PLY files:\n"
            f"  Target: {a_str}\n"
            f"  Source: {b_str}\n"
            "Both files must have identical vertex properties."
        )


def fill_ply(
    target_file: str,
    source_file: str,
    output: str,
    p1: Tuple[float, float, float],
    p2: Optional[Tuple[float, float, float]] = None,
    corners: Optional[List[Tuple[float, float, float]]] = None,
    offset: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    progress_callback=None,
) -> Tuple[int, int]:
    """Fill source PLY points into a target region of a destination PLY.

    Args:
        target_file: Path to target PLY file (destination).
        source_file: Path to source PLY file (points to fill).
        output: Path to output PLY file.
        p1: First point of target region (min corner for AABB mode).
        p2: Second point (max corner for AABB mode). If None, eight-point mode.
        corners: 8 corner points for hexahedron mode. Required if p2 is None.
        offset: (dx, dy, dz) offset applied to source points before region test.
        progress_callback: Optional callback(current, total) for progress.

    Returns:
        (target_count, added_count) - original point count and how many added.
    """
    # Parse both files
    target_analyzer = StatsAnalyzer(target_file)
    source_analyzer = StatsAnalyzer(source_file)

    target_total = target_analyzer.vertex_elem.count
    source_total = source_analyzer.vertex_elem.count

    # Check property compatibility
    _check_property_compatibility(target_analyzer.header, source_analyzer.header)

    # Read source coordinates and apply offset
    sx = source_analyzer.read_column("x") + offset[0]
    sy = source_analyzer.read_column("y") + offset[1]
    sz = source_analyzer.read_column("z") + offset[2]

    # Build mask for source points inside target region
    if p2 is not None:
        mask = build_aabb_mask(sx, sy, sz, p1, p2)
        region_desc = f"p1={p1} p2={p2}"
    else:
        if corners is None or len(corners) != 8:
            raise ValueError("Eight-point mode requires exactly 8 corner points")
        mask = build_hexahedron_mask(sx, sy, sz, corners)
        region_desc = f"corners={len(corners)}"

    source_keep_indices = np.where(mask)[0]
    added_count = len(source_keep_indices)
    total_out = target_total + added_count

    # Build output header
    new_header = copy_header_for_partition(target_analyzer.header, total_out)
    new_header.comments.append(
        f"fill source={Path(source_file).name} offset={offset} {region_desc}"
    )
    new_header.comments.append(
        f"fill added {added_count:,} of {source_total:,} source points"
    )

    # Read target data via memmap
    target_dtype = target_analyzer._get_struct_dtype()
    target_mmap = np.memmap(
        target_file,
        dtype=target_dtype,
        mode="r",
        offset=target_analyzer.header.header_size,
        shape=target_total,
    )

    # Read source data via memmap
    source_dtype = source_analyzer._get_struct_dtype()
    source_mmap = np.memmap(
        source_file,
        dtype=source_dtype,
        mode="r",
        offset=source_analyzer.header.header_size,
        shape=source_total,
    )

    prop_names = [p.name for p in target_analyzer.vertex_elem.properties]
    written = 0

    with PLYWriter(output) as writer:
        writer.write_header(new_header)

        # Write all target points first
        for i in range(target_total):
            row = target_mmap[i]
            data = {name: row[name] for name in prop_names}
            writer.write_element("vertex", data)
            written += 1
            if progress_callback:
                progress_callback(written, total_out)

        # Write qualifying source points
        for idx in source_keep_indices:
            row = source_mmap[idx]
            data = {name: row[name] for name in prop_names}
            data["x"] = float(row["x"]) + offset[0]
            data["y"] = float(row["y"]) + offset[1]
            data["z"] = float(row["z"]) + offset[2]
            writer.write_element("vertex", data)
            written += 1
            if progress_callback:
                progress_callback(written, total_out)

    del target_mmap, source_mmap
    return target_total, added_count