"""Coordinate translation for 3DGS PLY files"""

import re
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

from .stats import StatsAnalyzer
from ..ply.writer import PLYWriter, copy_header_for_partition


@dataclass
class TranslatePlan:
    """Planned translation with resolved offsets per axis"""
    x_offset: float = 0.0
    y_offset: float = 0.0
    z_offset: float = 0.0
    x_spec: str = "0"
    y_spec: str = "0"
    z_spec: str = "0"


# Keywords that are not raw numbers
STAT_KEYWORDS = {"min", "max", "mean", "median", "center"}


def _is_stat_keyword(spec: str) -> bool:
    """Check if a spec string is a stat keyword (min/max/mean/median/center/P<N>)"""
    lower = spec.lower().strip()
    if lower in STAT_KEYWORDS:
        return True
    return bool(re.match(r'^p\d+$', lower))


def _resolve_offset(analyzer: StatsAnalyzer, axis: str, spec: str) -> Tuple[float, str]:
    """Resolve a spec string to a concrete offset value for the given axis.

    Returns (offset, human_readable_description).
    The actual coordinate transformation is:  coord' = coord + offset
    so for centering (subtract mean), offset = -mean.
    """
    lower = spec.lower().strip()

    if lower in ("min", "max", "mean", "median", "center"):
        col = analyzer.read_column(axis)
        if lower == "min":
            val = float(np.min(col))
        elif lower == "max":
            val = float(np.max(col))
        elif lower == "mean":
            val = float(np.mean(col))
        elif lower == "median":
            val = float(np.median(col))
        else:  # center = (min + max) / 2
            val = float((np.min(col) + np.max(col)) / 2)
        return -val, f"{lower}({val:.6f})"

    m = re.match(r'^p(\d+)$', lower)
    if m:
        pct = int(m.group(1))
        col = analyzer.read_column(axis)
        val = float(np.percentile(col, pct))
        return -val, f"P{pct}({val:.6f})"

    # Raw number
    val = float(spec)
    return val, str(val)


def parse_translate_spec(
    x: Optional[str] = None,
    y: Optional[str] = None,
    z: Optional[str] = None,
    all_val: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse and validate translate arguments.

    Returns (x_spec, y_spec, z_spec) or raises on conflict.
    """
    if all_val is not None and (x is not None or y is not None or z is not None):
        raise ValueError("--all is mutually exclusive with --x/--y/--z")

    if all_val is not None:
        return all_val, all_val, all_val

    return x, y, z


def compute_plan(
    analyzer: StatsAnalyzer,
    x_spec: Optional[str],
    y_spec: Optional[str],
    z_spec: Optional[str],
) -> TranslatePlan:
    """Compute translation offsets from spec strings."""
    plan = TranslatePlan()

    for axis, spec in [("x", x_spec), ("y", y_spec), ("z", z_spec)]:
        if spec is None:
            offset = 0.0
            desc = "0"
        elif _is_stat_keyword(spec):
            offset, desc = _resolve_offset(analyzer, axis, spec)
        else:
            offset, desc = float(spec), spec

        setattr(plan, f"{axis}_offset", offset)
        setattr(plan, f"{axis}_spec", desc)

    return plan


def translate_ply(
    ply_file: str,
    plan: TranslatePlan,
    output_path: str,
    progress_callback=None,
) -> int:
    """Translate coordinates in a PLY file and write to output.

    Uses memmap for efficient reading. Returns the number of translated points.
    """
    analyzer = StatsAnalyzer(ply_file)
    vertex_elem = analyzer.vertex_elem
    total = vertex_elem.count

    new_header = copy_header_for_partition(analyzer.header, total)
    # Add translation comments
    for axis in ("x", "y", "z"):
        comment = f"translate_{axis}={getattr(plan, f'{axis}_spec')}"
        new_header.comments.append(comment)

    # Build structured dtype and memmap
    dtype = analyzer._get_struct_dtype()
    mmap = np.memmap(
        analyzer.file_path,
        dtype=dtype,
        mode="r",
        offset=analyzer.header.header_size,
        shape=total,
    )

    # Property names in order
    prop_names = [p.name for p in vertex_elem.properties]

    with PLYWriter(output_path) as writer:
        writer.write_header(new_header)

        for i in range(total):
            row = mmap[i]
            data = {}
            for name in prop_names:
                val = row[name]
                if name == "x":
                    val = val + plan.x_offset
                elif name == "y":
                    val = val + plan.y_offset
                elif name == "z":
                    val = val + plan.z_offset
                data[name] = val
            writer.write_element("vertex", data)
            if progress_callback:
                progress_callback(i + 1, total)

    del mmap
    return total
