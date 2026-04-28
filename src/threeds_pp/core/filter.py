"""Filter engine for filtering Gaussian ellipsoids from PLY files."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..ply import PLYWriter
from ..ply.writer import copy_header_for_partition
from .stats import StatsAnalyzer, PropertyStats

# Known percentile attribute mappings for fast lookup
_PCT_ATTR_MAP = {
    5: "pct_5",
    10: "pct_10",
    20: "pct_20",
    25: "q1",
    50: "median",
    75: "q3",
    90: "pct_90",
    95: "pct_95",
}

# Derived (indirect) property names computed from scale_0/1/2
DERIVED_PROPERTIES = [
    "volume",
    "longest_axis",
    "shortest_axis",
    "sphericity",
    "disceness",
    "rodness",
]

# Regex for parsing filter expressions
_FILTER_RE = re.compile(
    r"^(?P<attr>[a-zA-Z_][a-zA-Z0-9_]*)"
    r"(?P<op>~P|!~P|>=P|<=P|>P|<P|>=|<=|==|!=|!~|~|>|<)"
    r"(?P<val>.+)$"
)

_RANGE_RE = re.compile(r"\[([-\d.]+),([-\d.]+)\]$")


def compute_derived_properties(
    scale_0: np.ndarray,
    scale_1: np.ndarray,
    scale_2: np.ndarray,
    props: List[str],
) -> Dict[str, np.ndarray]:
    """Compute derived (indirect) property arrays from scale values.

    The scale_* values in 3DGS PLY are log-scales. Actual half-axis lengths
    are exp(scale_0), exp(scale_1), exp(scale_2). We sort them to l1<=l2<=l3
    for shape-ratio calculations.
    """
    result: Dict[str, np.ndarray] = {}

    l0 = np.exp(scale_0)
    l1 = np.exp(scale_1)
    l2 = np.exp(scale_2)

    if "sphericity" in props or "disceness" in props or "rodness" in props:
        sorted_axes = np.stack([l0, l1, l2], axis=-1)
        np.sort(sorted_axes, axis=-1)

    if "volume" in props:
        result["volume"] = l0 * l1 * l2
    if "longest_axis" in props:
        result["longest_axis"] = np.maximum(l0, np.maximum(l1, l2))
    if "shortest_axis" in props:
        result["shortest_axis"] = np.minimum(l0, np.minimum(l1, l2))
    if "sphericity" in props:
        result["sphericity"] = np.divide(
            sorted_axes[..., 0], sorted_axes[..., 2],
            out=np.zeros_like(sorted_axes[..., 0]),
            where=sorted_axes[..., 2] > 0,
        )
    if "disceness" in props:
        result["disceness"] = np.divide(
            sorted_axes[..., 0], sorted_axes[..., 1],
            out=np.zeros_like(sorted_axes[..., 0]),
            where=sorted_axes[..., 1] > 0,
        )
    if "rodness" in props:
        result["rodness"] = np.divide(
            sorted_axes[..., 1], sorted_axes[..., 2],
            out=np.zeros_like(sorted_axes[..., 1]),
            where=sorted_axes[..., 2] > 0,
        )

    return result


@dataclass(frozen=True)
class FilterCondition:
    """Parsed representation of a single filter expression."""

    property_name: str
    operator: str
    value: float = 0.0
    pct_rank: float = 0.0
    range_low: float = 0.0
    range_high: float = 0.0
    pct_low: float = 0.0
    pct_high: float = 0.0

    def __str__(self) -> str:
        op = self.operator
        if op in (">", ">=", "<", "<=", "==", "!="):
            return f"{self.property_name}{op}{self.value}"
        elif op in (">P", ">=P", "<P", "<=P"):
            return f"{self.property_name}{op}{int(self.pct_rank)}"
        elif op in ("~", "!~"):
            return f"{self.property_name}{op}[{self.range_low},{self.range_high}]"
        elif op in ("~P", "!~P"):
            return f"{self.property_name}{op}[{int(self.pct_low)},{int(self.pct_high)}]"
        return f"{self.property_name}{op}"


def parse_filter_expression(expr: str) -> FilterCondition:
    """Parse a filter expression string into a FilterCondition.

    Supported formats:
        attr>value      (e.g. "opacity>0.1")
        attr>=value, attr<value, attr<=value, attr==value, attr!=value
        attr>Pn         (e.g. "opacity<P5")
        attr>=Pn, attr<Pn, attr<=Pn
        attr~[low,high] (e.g. "x~[-10,10]")
        attr!~[low,high]
        attr~P[lo,hi]   (e.g. "opacity~P[5,95]")
        attr!~P[lo,hi]

    Raises:
        ValueError: If the expression cannot be parsed.
    """
    match = _FILTER_RE.match(expr.strip())
    if not match:
        raise ValueError(
            f"Invalid filter expression: '{expr}'. "
            f"Expected format: property<op>value, e.g. 'opacity<0.1' or 'x<P5'"
        )

    attr = match.group("attr")
    op = match.group("op")
    val_str = match.group("val").strip()

    if op in (">", ">=", "<", "<=", "==", "!="):
        try:
            value = float(val_str)
        except ValueError:
            raise ValueError(f"Invalid numeric value '{val_str}' for operator '{op}'")
        return FilterCondition(property_name=attr, operator=op, value=value)

    elif op in (">P", ">=P", "<P", "<=P"):
        try:
            pct_rank = float(val_str)
        except ValueError:
            raise ValueError(f"Invalid percentile rank '{val_str}' for operator '{op}'")
        if not (0 <= pct_rank <= 100):
            raise ValueError(
                f"Percentile rank must be between 0 and 100, got {pct_rank}"
            )
        return FilterCondition(property_name=attr, operator=op, pct_rank=pct_rank)

    elif op in ("~", "!~"):
        m = _RANGE_RE.match(val_str)
        if not m:
            raise ValueError(
                f"Invalid range value '{val_str}' for operator '{op}'. "
                f"Expected format: [low,high], e.g. '[-10,10]'"
            )
        range_low = float(m.group(1))
        range_high = float(m.group(2))
        return FilterCondition(
            property_name=attr,
            operator=op,
            range_low=range_low,
            range_high=range_high,
        )

    elif op in ("~P", "!~P"):
        m = _RANGE_RE.match(val_str)
        if not m:
            raise ValueError(
                f"Invalid percentile range '{val_str}' for operator '{op}'. "
                f"Expected format: P[low,high], e.g. 'P[5,95]'"
            )
        pct_low = float(m.group(1))
        pct_high = float(m.group(2))
        if not (0 <= pct_low <= 100 and 0 <= pct_high <= 100):
            raise ValueError("Percentile ranks must be between 0 and 100")
        return FilterCondition(
            property_name=attr,
            operator=op,
            pct_low=pct_low,
            pct_high=pct_high,
        )

    raise ValueError(f"Unsupported operator: {op}")


def _resolve_percentile(
    rank: float, column: np.ndarray, stats: Optional[PropertyStats]
) -> float:
    """Resolve a percentile rank to an actual value from column or cached stats."""
    if stats is not None:
        int_rank = int(round(rank))
        attr_name = _PCT_ATTR_MAP.get(int_rank)
        if attr_name:
            return getattr(stats, attr_name)
    return float(np.percentile(column, [rank])[0])


def evaluate_condition(
    column: np.ndarray,
    cond: FilterCondition,
    stats: Optional[PropertyStats] = None,
) -> np.ndarray:
    """Evaluate a single condition against a column.

    Returns a boolean array where True means the point matches the condition (will be filtered out).
    """
    op = cond.operator

    if op == ">":
        return column > cond.value
    elif op == ">=":
        return column >= cond.value
    elif op == "<":
        return column < cond.value
    elif op == "<=":
        return column <= cond.value
    elif op == "==":
        return column == cond.value
    elif op == "!=":
        return column != cond.value

    elif op == ">P":
        threshold = _resolve_percentile(cond.pct_rank, column, stats)
        return column > threshold
    elif op == ">=P":
        threshold = _resolve_percentile(cond.pct_rank, column, stats)
        return column >= threshold
    elif op == "<P":
        threshold = _resolve_percentile(cond.pct_rank, column, stats)
        return column < threshold
    elif op == "<=P":
        threshold = _resolve_percentile(cond.pct_rank, column, stats)
        return column <= threshold

    elif op == "~":
        return (column >= cond.range_low) & (column <= cond.range_high)
    elif op == "!~":
        return ~((column >= cond.range_low) & (column <= cond.range_high))

    elif op == "~P":
        lo = _resolve_percentile(cond.pct_low, column, stats)
        hi = _resolve_percentile(cond.pct_high, column, stats)
        return (column >= lo) & (column <= hi)
    elif op == "!~P":
        lo = _resolve_percentile(cond.pct_low, column, stats)
        hi = _resolve_percentile(cond.pct_high, column, stats)
        return ~((column >= lo) & (column <= hi))

    raise ValueError(f"Unknown operator: {op}")


def _build_filter_comment(
    conditions: List[FilterCondition],
    logic: str,
    keep: bool,
) -> str:
    """Build a comment string for the PLY header."""
    logic_str = "AND" if logic == "and" else "OR"
    keep_str = " keep" if keep else ""
    sep = " & " if logic == "and" else " | "
    parts = [str(c) for c in conditions]
    return f"logic={logic_str}{keep_str}: {sep.join(parts)}"


def _compute_stats_from_array(
    property_name: str,
    column: np.ndarray,
) -> PropertyStats:
    """Compute PropertyStats from a numpy array (used for derived properties)."""
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
        property_name=property_name,
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
        pct_50=float(percentiles[4]),
        pct_90=float(percentiles[6]),
        pct_95=float(percentiles[7]),
        skewness=skew,
        kurtosis=kurt,
    )


class FilterEngine:
    """Core filtering engine: parse expressions, build masks, apply to PLY data."""

    def __init__(self, ply_file: str):
        if not Path(ply_file).exists():
            raise FileNotFoundError(f"PLY file not found: {ply_file}")
        self.analyzer = StatsAnalyzer(ply_file)
        self._stats_cache: Dict[str, PropertyStats] = {}
        self._derived_cache: Dict[str, np.ndarray] = {}

    def get_all_properties(self) -> List[str]:
        """Return all available properties including derived ones."""
        return self.analyzer.get_numeric_properties() + list(DERIVED_PROPERTIES)

    def _get_stats(self, prop: str) -> PropertyStats:
        """Get stats for a property, computing derived ones on-demand."""
        if prop not in self._stats_cache:
            if prop in DERIVED_PROPERTIES:
                col = self._get_derived_column(prop)
                self._stats_cache[prop] = _compute_stats_from_array(prop, col)
            else:
                self._stats_cache[prop] = self.analyzer.compute_stats(prop)
        return self._stats_cache[prop]

    def _get_derived_column(self, prop: str) -> np.ndarray:
        """Get or compute a single derived property column (cached)."""
        if prop not in self._derived_cache:
            scale_0 = self.analyzer.read_column("scale_0")
            scale_1 = self.analyzer.read_column("scale_1")
            scale_2 = self.analyzer.read_column("scale_2")
            # Batch-compute all needed derived props that aren't already cached
            missing = [p for p in DERIVED_PROPERTIES
                       if p not in self._derived_cache
                       and p == prop]
            if missing:
                computed = compute_derived_properties(
                    scale_0, scale_1, scale_2, missing
                )
                self._derived_cache.update(computed)
        return self._derived_cache[prop]

    def _get_derived_columns_batch(
        self, derived_needed: List[str]
    ) -> Dict[str, np.ndarray]:
        """Compute all needed derived columns in one pass."""
        if not derived_needed:
            return {}
        missing = [p for p in derived_needed if p not in self._derived_cache]
        if missing:
            scale_0 = self.analyzer.read_column("scale_0")
            scale_1 = self.analyzer.read_column("scale_1")
            scale_2 = self.analyzer.read_column("scale_2")
            computed = compute_derived_properties(scale_0, scale_1, scale_2, missing)
            self._derived_cache.update(computed)
        return {p: self._derived_cache[p] for p in derived_needed}

    def build_mask(
        self,
        conditions: List[FilterCondition],
        logic: str = "or",
        keep: bool = False,
    ) -> Tuple[np.ndarray, List[int]]:
        """Build boolean mask (True = remove) and per-condition match counts.

        Args:
            conditions: Parsed filter conditions.
            logic: 'or' (any matches) or 'and' (all must match).
            keep: If True, invert the mask (keep matching, discard others).

        Returns:
            (mask, per_condition_counts) - mask is True for points to remove.
        """
        if not conditions:
            total = self.analyzer.vertex_elem.count
            return np.zeros(total, dtype=bool), []

        # Collect unique properties needed
        needed_props = list(set(c.property_name for c in conditions))
        native_props = [p for p in needed_props if p not in DERIVED_PROPERTIES]
        derived_props = [p for p in needed_props if p in DERIVED_PROPERTIES]

        columns: Dict[str, np.ndarray] = {}
        for prop in native_props:
            columns[prop] = self.analyzer.read_column(prop)
        columns.update(self._get_derived_columns_batch(derived_props))

        # Compute stats for properties that need percentile lookups
        for prop in needed_props:
            if not self._needs_percentile(prop, conditions):
                continue
            if prop not in self._stats_cache:
                self._get_stats(prop)

        # Evaluate each condition
        masks = []
        counts = []
        for cond in conditions:
            col = columns[cond.property_name]
            stats = self._stats_cache.get(cond.property_name)
            mask = evaluate_condition(col, cond, stats)
            masks.append(mask)
            counts.append(int(np.sum(mask)))

        # Combine
        if logic == "and":
            combined = np.logical_and.reduce(masks)
        else:
            combined = np.zeros_like(masks[0], dtype=bool)
            for m in masks:
                combined |= m

        if keep:
            combined = ~combined

        return combined, counts

    def _needs_percentile(self, prop: str, conditions: List[FilterCondition]) -> bool:
        """Check if any condition for this property needs percentile resolution."""
        pct_ops = {">P", ">=P", "<P", "<=P", "~P", "!~P"}
        return any(
            c.property_name == prop and c.operator in pct_ops for c in conditions
        )

    def write_filtered(
        self,
        mask: np.ndarray,
        output_path: str,
        filter_comment: str,
        progress_callback=None,
    ) -> int:
        """Write filtered PLY file, returning kept count.

        Args:
            mask: Boolean array, True = remove.
            output_path: Output file path.
            filter_comment: Comment string for PLY header.
            progress_callback: Optional callback(current, total) for progress tracking.
        """
        keep_indices = np.where(~mask)[0]
        kept_count = len(keep_indices)
        total = self.analyzer.vertex_elem.count
        removed = total - kept_count

        # Copy header with new count
        new_header = copy_header_for_partition(self.analyzer.header, kept_count)
        new_header.comments.append(f"filter: {filter_comment}")
        new_header.comments.append(
            f"filter removed {removed:,} points, kept {kept_count:,} of {total:,}"
        )

        # Use structured memmap for efficient reading
        dtype = self.analyzer._get_struct_dtype()
        mmap = np.memmap(
            self.analyzer.file_path,
            dtype=dtype,
            mode="r",
            offset=self.analyzer.header.header_size,
            shape=total,
        )
        prop_names = [p.name for p in self.analyzer.vertex_elem.properties]

        with PLYWriter(output_path) as writer:
            writer.write_header(new_header)
            for i, idx in enumerate(keep_indices):
                row = mmap[idx]
                data = {name: row[name] for name in prop_names}
                writer.write_element("vertex", data)
                if progress_callback:
                    progress_callback(i + 1, kept_count)

        del mmap
        return kept_count
