"""Coordinate translation for 3DGS PLY files"""

import re
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

from .stats import PropertyStats, StatsAnalyzer
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


def _load_axes(analyzer: StatsAnalyzer) -> dict[str, np.ndarray]:
    """Load x, y, z columns in a single memmap + copy, avoiding repeated disk reads."""
    dtype = analyzer._get_struct_dtype()
    mm = np.memmap(
        analyzer.file_path,
        dtype=dtype,
        mode="r",
        offset=analyzer.header.header_size,
        shape=analyzer.vertex_elem.count,
    )
    result = {axis: mm[axis].copy() for axis in ("x", "y", "z")}
    del mm
    return result


def _compute_stats_from_array(column: np.ndarray, name: str) -> PropertyStats:
    """Compute PropertyStats from a numpy array (avoids repeated disk reads)."""
    try:
        from scipy import stats as scipy_stats
    except ImportError:
        scipy_stats = None

    n = len(column)
    min_val = float(np.min(column))
    max_val = float(np.max(column))
    mean_val = float(np.mean(column, dtype=np.float64))
    std_val = float(np.std(column, dtype=np.float64))

    percentiles = np.percentile(column, [5, 10, 20, 25, 50, 75, 90, 95])

    if n > 2 and scipy_stats is not None:
        skew = float(scipy_stats.skew(column, bias=False))
        kurt = float(scipy_stats.kurtosis(column, bias=False)) if n > 3 else 0.0
    else:
        skew = 0.0
        kurt = 0.0

    return PropertyStats(
        property_name=name,
        count=n,
        min_val=min_val,
        max_val=max_val,
        mean=mean_val,
        std=std_val,
        median=float(percentiles[4]),
        q1=float(percentiles[3]),
        q2=float(percentiles[4]),
        q3=float(percentiles[5]),
        pct_5=float(percentiles[0]),
        pct_10=float(percentiles[1]),
        pct_20=float(percentiles[2]),
        pct_90=float(percentiles[6]),
        pct_95=float(percentiles[7]),
        skewness=skew,
        kurtosis=kurt,
    )


def _resolve_offset_from_array(
    column: np.ndarray, axis: str, spec: str
) -> Tuple[float, str]:
    """Resolve a spec string to an offset using an in-memory column array."""
    lower = spec.lower().strip()

    if lower in ("min", "max", "mean", "median", "center"):
        if lower == "min":
            val = float(np.min(column))
        elif lower == "max":
            val = float(np.max(column))
        elif lower == "mean":
            val = float(np.mean(column))
        elif lower == "median":
            val = float(np.median(column))
        else:  # center
            val = float((np.min(column) + np.max(column)) / 2)
        return -val, f"{lower}({val:.6f})"

    m = re.match(r"^p(\d+)$", lower)
    if m:
        pct = int(m.group(1))
        val = float(np.percentile(column, pct))
        return -val, f"P{pct}({val:.6f})"

    # Raw number
    val = float(spec)
    return val, str(val)


def _chunked_translate_binary(
    fpath_in: str,
    fpath_out: str,
    new_header,
    dtype,
    total: int,
    header_size: int,
    plan: TranslatePlan,
    progress_callback=None,
):
    """Translate binary PLY data in fixed-size chunks to bound memory usage.

    Each chunk is ~64 MB, keeping peak memory well under 128 MB regardless
    of input file size.
    """
    row_size = dtype.itemsize  # bytes per vertex row
    chunk = max(1, 64 * 1024 * 1024 // row_size)  # ~64 MB per chunk

    has_offset = plan.x_offset != 0 or plan.y_offset != 0 or plan.z_offset != 0

    with open(fpath_in, "rb") as fin, open(fpath_out, "wb") as fout:
        fout.write(new_header.to_string().encode("ascii"))
        fin.seek(header_size)

        written = 0
        while written < total:
            to_read = min(chunk, total - written)
            if has_offset:
                block = np.fromfile(fin, dtype=dtype, count=to_read)
                block["x"] += plan.x_offset
                block["y"] += plan.y_offset
                block["z"] += plan.z_offset
                fout.write(block.tobytes())
                del block
            else:
                raw = fin.read(to_read * row_size)
                fout.write(raw)

            written += to_read
            if progress_callback:
                progress_callback(written, total)


def translate_ply(
    ply_file: str,
    plan: TranslatePlan,
    output_path: str,
    progress_callback=None,
) -> int:
    """Translate coordinates in a PLY file and write to output.

    For binary PLY files, processes the data in ~64 MB chunks so memory usage
    stays bounded regardless of file size. Returns the number of translated points.
    """
    analyzer = StatsAnalyzer(ply_file)
    vertex_elem = analyzer.vertex_elem
    total = vertex_elem.count

    new_header = copy_header_for_partition(analyzer.header, total)
    # Add translation comments
    for axis in ("x", "y", "z"):
        comment = f"translate_{axis}={getattr(plan, f'{axis}_spec')}"
        new_header.comments.append(comment)

    dtype = analyzer._get_struct_dtype()
    prop_names = [p.name for p in vertex_elem.properties]
    is_binary = analyzer.header.format.startswith("binary")

    if is_binary:
        _chunked_translate_binary(
            fpath_in=analyzer.file_path,
            fpath_out=output_path,
            new_header=new_header,
            dtype=dtype,
            total=total,
            header_size=analyzer.header.header_size,
            plan=plan,
            progress_callback=progress_callback,
        )

    else:
        # ASCII format: fall back to per-vertex writing
        ascii_mmap = np.memmap(
            analyzer.file_path,
            dtype=dtype,
            mode="r",
            offset=analyzer.header.header_size,
            shape=total,
        )

        with PLYWriter(output_path) as writer:
            writer.write_header(new_header)
            for i in range(total):
                row = ascii_mmap[i]
                data_dict = {}
                for name in prop_names:
                    val = row[name]
                    if name == "x":
                        val = val + plan.x_offset
                    elif name == "y":
                        val = val + plan.y_offset
                    elif name == "z":
                        val = val + plan.z_offset
                    data_dict[name] = val
                writer.write_element("vertex", data_dict)
                if progress_callback:
                    progress_callback(i + 1, total)

        del ascii_mmap

    return total
