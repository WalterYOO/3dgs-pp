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

# Regex for parsing filter expressions
_FILTER_RE = re.compile(
    r"^(?P<attr>[a-zA-Z_][a-zA-Z0-9_]*)"
    r"(?P<op>~P|!~P|>=P|<=P|>P|<P|>=|<=|==|!=|!~|~|>|<)"
    r"(?P<val>.+)$"
)

_RANGE_RE = re.compile(r"\[([-\d.]+),([-\d.]+)\]$")


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


class FilterEngine:
    """Core filtering engine: parse expressions, build masks, apply to PLY data."""

    def __init__(self, ply_file: str):
        if not Path(ply_file).exists():
            raise FileNotFoundError(f"PLY file not found: {ply_file}")
        self.analyzer = StatsAnalyzer(ply_file)
        self._stats_cache: Dict[str, PropertyStats] = {}

    def _get_stats(self, prop: str) -> PropertyStats:
        if prop not in self._stats_cache:
            self._stats_cache[prop] = self.analyzer.compute_stats(prop)
        return self._stats_cache[prop]

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

        # Collect unique properties and load columns
        needed_props = list(set(c.property_name for c in conditions))
        columns: Dict[str, np.ndarray] = {}
        for prop in needed_props:
            columns[prop] = self.analyzer.read_column(prop)

        # Compute stats for properties that need percentile lookups
        for prop in needed_props:
            if not self._needs_percentile(prop, conditions):
                continue
            if prop not in self._stats_cache:
                self._stats_cache[prop] = self.analyzer.compute_stats(prop)

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
