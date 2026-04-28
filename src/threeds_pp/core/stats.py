"""Statistics analysis for PLY file properties"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy import stats as scipy_stats

from ..ply.header import PLYHeader


@dataclass(frozen=True)
class PropertyStats:
    """Computed statistics for a single PLY property."""
    property_name: str
    count: int
    min_val: float
    max_val: float
    mean: float
    std: float
    median: float
    q1: float
    q2: float
    q3: float
    pct_5: float
    pct_10: float
    pct_20: float
    pct_50: float
    pct_90: float
    pct_95: float
    skewness: float
    kurtosis: float


# Mapping from PLY type to numpy dtype string
PLY_TO_NUMPY_DTYPE = {
    'char': 'i1',
    'uchar': 'u1',
    'short': 'i2',
    'ushort': 'u2',
    'int': 'i4',
    'uint': 'u4',
    'float': 'f4',
    'double': 'f8',
    'int8': 'i1',
    'uint8': 'u1',
    'int16': 'i2',
    'uint16': 'u2',
    'int32': 'i4',
    'uint32': 'u4',
    'float32': 'f4',
    'float64': 'f8',
}


class StatsAnalyzer:
    """Compute statistics on PLY file properties using efficient column extraction."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.header = PLYHeader.parse(file_path)
        self.vertex_elem = self.header.get_element('vertex')
        if not self.vertex_elem:
            raise ValueError(f"No 'vertex' element found in {file_path}")

        # Build property index map: (prop_name, index, is_list)
        self._property_info = {}
        for idx, prop in enumerate(self.vertex_elem.properties):
            self._property_info[prop.name] = idx

    def get_numeric_properties(self) -> List[str]:
        """Return names of all numeric (non-list) properties on vertex element."""
        return [p.name for p in self.vertex_elem.properties if not p.is_list]

    def _get_struct_dtype(self) -> np.dtype:
        """Build a structured numpy dtype from the vertex element properties."""
        fields = []
        for prop in self.vertex_elem.properties:
            if prop.is_list:
                raise ValueError(
                    f"Cannot build structured dtype with list property: {prop.name}"
                )
            np_dtype = PLY_TO_NUMPY_DTYPE.get(prop.data_type)
            if np_dtype is None:
                raise ValueError(f"Unknown PLY data type: {prop.data_type}")

            endian = self.header.endian_char()
            fields.append((prop.name, endian + np_dtype))

        return np.dtype(fields)

    def read_column(self, property_name: str) -> np.ndarray:
        """
        Read an entire property column from disk as a numpy float64 array.

        Uses np.memmap for memory-efficient access to large files.
        """
        prop = None
        for p in self.vertex_elem.properties:
            if p.name == property_name:
                prop = p
                break

        if prop is None:
            raise ValueError(f"Property '{property_name}' not found")

        if prop.is_list:
            raise ValueError(f"Cannot extract list property: {property_name}")

        if self.header.is_binary():
            return self._read_binary_column(property_name)
        else:
            return self._read_ascii_column(property_name)

    def _read_binary_column(self, property_name: str) -> np.ndarray:
        """Read a column from a binary PLY file using memmap."""
        dtype = self._get_struct_dtype()
        count = self.vertex_elem.count

        mmap = np.memmap(
            self.file_path,
            dtype=dtype,
            mode='r',
            offset=self.header.header_size,
            shape=count
        )

        return mmap[property_name].astype(np.float64).copy()

    def _read_ascii_column(self, property_name: str) -> np.ndarray:
        """Read a column from an ASCII PLY file by iterating elements."""
        prop_idx = self._property_info[property_name]
        count = self.vertex_elem.count
        column = np.empty(count, dtype=np.float64)

        with open(self.file_path, 'r') as f:
            # Skip header
            for _ in range(self._count_header_lines()):
                f.readline()

            for i in range(count):
                line = f.readline()
                parts = line.split()
                column[i] = float(parts[prop_idx])

        return column

    def _count_header_lines(self) -> int:
        """Count the number of lines in the PLY header."""
        with open(self.file_path, 'r') as f:
            count = 0
            for line in f:
                count += 1
                if line.strip() == 'end_header':
                    break
            return count

    def compute_stats(self, property_name: str) -> PropertyStats:
        """
        Compute full statistics for a single property.

        Returns PropertyStats with all statistical measures.
        """
        column = self.read_column(property_name)
        n = len(column)

        if n == 0:
            raise ValueError(f"No data points for property: {property_name}")

        # Basic stats (O(n))
        min_val = float(np.min(column))
        max_val = float(np.max(column))
        mean_val = float(np.mean(column, dtype=np.float64))
        std_val = float(np.std(column, dtype=np.float64))

        # Percentiles via selection algorithm (no full sort needed)
        percentiles = np.percentile(
            column,
            [5, 10, 20, 25, 50, 75, 90, 95]
        )

        # Skewness and kurtosis
        skew = float(scipy_stats.skew(column, bias=False)) if n > 2 else 0.0
        kurt = float(scipy_stats.kurtosis(column, bias=False)) if n > 3 else 0.0

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

    def plot_distribution(
        self,
        property_name: str,
        chart_type: str = 'histogram',
        output_dir: str = '.',
        num_bins: int = 100,
        dpi: int = 300,
        figure_size: Tuple[int, int] = (1200, 700),
        subsample_max: int = 10_000_000,
    ) -> str:
        """
        Generate a distribution chart for a property and save as PNG.

        Returns the path to the saved file.
        """
        column = self.read_column(property_name)

        # Subsample if too large for chart rendering
        if len(column) > subsample_max:
            rng = np.random.default_rng(42)
            indices = rng.choice(len(column), subsample_max, replace=False)
            sample = column[indices]
        else:
            sample = column

        os.makedirs(output_dir, exist_ok=True)

        if chart_type == 'histogram':
            path = self._plot_histogram(sample, property_name, len(column),
                                        output_dir, num_bins, figure_size, dpi)
        elif chart_type == 'box':
            path = self._plot_box(sample, property_name, len(column),
                                  output_dir, figure_size, dpi)
        elif chart_type == 'violin':
            path = self._plot_violin(sample, property_name, len(column),
                                     output_dir, figure_size, dpi)
        else:
            raise ValueError(f"Unknown chart type: {chart_type}")

        return path

    def _plot_histogram(
        self, data: np.ndarray, prop_name: str, total_count: int,
        output_dir: str, num_bins: int, figure_size: Tuple[int, int], dpi: int
    ) -> str:
        """Generate histogram with KDE overlay."""
        fig, ax = plt.subplots(
            figsize=(figure_size[0] / dpi, figure_size[1] / dpi), dpi=dpi
        )
        fig.patch.set_facecolor('#1a1a2e')
        ax.set_facecolor('#16213e')

        counts, bins, patches = ax.hist(
            data, bins=num_bins, alpha=0.7,
            color='#0f3460', edgecolor='#e94560'
        )

        # KDE curve
        try:
            kde = scipy_stats.gaussian_kde(data)
            kde_points = np.linspace(bins[0], bins[-1], 200)
            kde_values = kde(kde_points)
            bin_width = bins[1] - bins[0]
            kde_values = kde_values * len(data) * bin_width
            ax.plot(kde_points, kde_values, color='#e94560', linewidth=2, label='KDE')
        except Exception:
            pass

        self._add_stat_annotation_lines(ax, data)

        ax.set_xlabel(prop_name, color='#e0e0e0', fontsize=13, labelpad=10)
        ax.set_ylabel('Frequency', color='#e0e0e0', fontsize=13, labelpad=10)
        ax.set_title(f'{prop_name} - {total_count:,} samples', color='#ffffff', fontsize=16, pad=16)
        ax.tick_params(colors='#e0e0e0', labelsize=11)
        ax.legend(loc='upper right', facecolor='#16213e', edgecolor='#0f3460',
                  labelcolor='#e0e0e0', fontsize=11, framealpha=0.8, handletextpad=0.6,
                  labelspacing=0.8, borderpad=0.8)
        ax.grid(True, alpha=0.3, color='#0f3460')

        output_path = os.path.join(output_dir, f"{prop_name}_distribution.png")
        fig.savefig(output_path, bbox_inches='tight', dpi=dpi)
        plt.close(fig)

        return output_path

    def _plot_box(
        self, data: np.ndarray, prop_name: str, total_count: int,
        output_dir: str, figure_size: Tuple[int, int], dpi: int
    ) -> str:
        """Generate horizontal box plot."""
        fig, ax = plt.subplots(
            figsize=(figure_size[0] / dpi, figure_size[1] / dpi), dpi=dpi
        )
        fig.patch.set_facecolor('#1a1a2e')
        ax.set_facecolor('#16213e')

        bp = ax.boxplot(data, patch_artist=True, vert=False)
        for patch in bp['boxes']:
            patch.set_facecolor('#0f3460')
            patch.set_edgecolor('#e94560')
        for item in ['whiskers', 'caps', 'medians']:
            for line in bp[item]:
                line.set_color('#e94560')

        # Annotate quartile values below the box
        q1, median, q3 = np.percentile(data, [25, 50, 75])
        # Use actual x-axis values for annotation placement
        annotations = [
            (q1, f'Q1: {q1:.4f}', -0.35),
            (median, f'Median: {median:.4f}', -0.18),
            (q3, f'Q3: {q3:.4f}', -0.05),
        ]
        for val, label, y_offset in annotations:
            ax.annotate(label, xy=(val, 1 + y_offset),
                        color='#e0e0e0', fontsize=11,
                        ha='center', va='top')

        # Expand x-axis to show whiskers fully
        x_min, x_max = float(np.min(data)), float(np.max(data))
        x_range = x_max - x_min
        ax.set_xlim(x_min - x_range * 0.05, x_max + x_range * 0.05)

        ax.set_xlabel(prop_name, color='#e0e0e0', fontsize=13, labelpad=10)
        ax.set_title(f'{prop_name} - {total_count:,} samples', color='#ffffff', fontsize=16, pad=16)
        ax.tick_params(colors='#e0e0e0', labelsize=11)
        ax.grid(True, alpha=0.3, color='#0f3460', axis='x')

        output_path = os.path.join(output_dir, f"{prop_name}_distribution.png")
        fig.savefig(output_path, bbox_inches='tight', dpi=dpi)
        plt.close(fig)

        return output_path

    def _plot_violin(
        self, data: np.ndarray, prop_name: str, total_count: int,
        output_dir: str, figure_size: Tuple[int, int], dpi: int
    ) -> str:
        """Generate violin plot with overlaid box markers."""
        fig, ax = plt.subplots(
            figsize=(figure_size[0] / dpi, figure_size[1] / dpi), dpi=dpi
        )
        fig.patch.set_facecolor('#1a1a2e')
        ax.set_facecolor('#16213e')

        parts = ax.violinplot(data, vert=False, showmeans=True, showmedians=True)
        for pc in parts['bodies']:
            pc.set_facecolor('#0f3460')
            pc.set_edgecolor('#e94560')
            pc.set_alpha(0.7)
        parts['cmeans'].set_color('red')
        parts['cmedians'].set_color('green')
        parts['cmins'].set_color('#e94560')
        parts['cmaxes'].set_color('#e94560')
        parts['cbars'].set_color('#e94560')

        ax.set_xlabel(prop_name, color='#e0e0e0', fontsize=13, labelpad=10)
        ax.set_title(f'{prop_name} - {total_count:,} samples', color='#ffffff', fontsize=16, pad=16)
        ax.tick_params(colors='#e0e0e0', labelsize=11)
        ax.grid(True, alpha=0.3, color='#0f3460', axis='x')

        output_path = os.path.join(output_dir, f"{prop_name}_distribution.png")
        fig.savefig(output_path, bbox_inches='tight', dpi=dpi)
        plt.close(fig)

        return output_path

    def _add_stat_annotation_lines(self, ax, data: np.ndarray):
        """Add mean/median/Q1/Q3 annotation lines to a plot."""
        mean_val = float(np.mean(data))
        median_val = float(np.median(data))
        q1, q3 = np.percentile(data, [25, 75])

        ax.axvline(mean_val, color='red', linestyle='--', linewidth=1, alpha=0.8, label=f'Mean: {mean_val:.4f}')
        ax.axvline(median_val, color='green', linestyle='-', linewidth=1, alpha=0.8, label=f'Median: {median_val:.4f}')
        ax.axvline(q1, color='blue', linestyle='-.', linewidth=1, alpha=0.8, label=f'Q1: {q1:.4f}')
        ax.axvline(q3, color='cyan', linestyle='-.', linewidth=1, alpha=0.8, label=f'Q3: {q3:.4f}')

    def plot_all_core(
        self,
        chart_type: str = 'histogram',
        output_dir: str = '.',
    ) -> List[str]:
        """
        Generate distribution charts for all core properties.

        Core properties: x, y, z, opacity, scale_0, scale_1, scale_2
        Returns list of output file paths.
        """
        core_properties = ['x', 'y', 'z', 'opacity', 'scale_0', 'scale_1', 'scale_2']
        available = [p for p in core_properties if p in self._property_info]
        results = []
        for prop in available:
            path = self.plot_distribution(prop, chart_type, output_dir)
            results.append(path)
        return results

    def save_stats_text(
        self,
        stats_obj: PropertyStats,
        output_dir: str = '.',
    ) -> str:
        """
        Save a PropertyStats object as a formatted text file.

        Returns the path to the saved file.
        """
        os.makedirs(output_dir, exist_ok=True)

        ply_path = Path(self.file_path)
        stem = ply_path.stem
        filename = f"{stem}_stats_{stats_obj.property_name}.txt"
        filepath = os.path.join(output_dir, filename)

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        fmt = "{:.6f}"

        lines = [
            "=" * 48,
            "3DGS Property Statistics Report",
            "=" * 48,
            f"File: {ply_path.name}",
            f"Property: {stats_obj.property_name}",
            f"Total Samples: {stats_obj.count:,}",
            f"Generated: {now}",
            "=" * 48,
            "",
            f"  {'Metric':<25} {'Value'}",
            f"  {'-' * 40}",
            f"  {'Min':<25} {fmt.format(stats_obj.min_val)}",
            f"  {'5% Percentile':<25} {fmt.format(stats_obj.pct_5)}",
            f"  {'10% Percentile':<25} {fmt.format(stats_obj.pct_10)}",
            f"  {'20% Percentile':<25} {fmt.format(stats_obj.pct_20)}",
            f"  {'Q1 (25%)':<25} {fmt.format(stats_obj.q1)}",
            f"  {'Median (50%)':<25} {fmt.format(stats_obj.median)}",
            f"  {'Q3 (75%)':<25} {fmt.format(stats_obj.q3)}",
            f"  {'90% Percentile':<25} {fmt.format(stats_obj.pct_90)}",
            f"  {'95% Percentile':<25} {fmt.format(stats_obj.pct_95)}",
            f"  {'Max':<25} {fmt.format(stats_obj.max_val)}",
            f"  {'Mean':<25} {fmt.format(stats_obj.mean)}",
            f"  {'Std':<25} {fmt.format(stats_obj.std)}",
            f"  {'Skewness':<25} {stats_obj.skewness:.4f}",
            f"  {'Kurtosis':<25} {stats_obj.kurtosis:.4f}",
            "",
            "=" * 48,
        ]

        with open(filepath, 'w') as f:
            f.write('\n'.join(lines) + '\n')

        return filepath


def save_comparison_text(
    properties: List[str],
    stats_list: List[PropertyStats],
    file_name: str,
    output_dir: str = '.',
) -> str:
    """
    Save a multi-property comparison table as a text file.

    Returns the path to the saved file.
    """
    os.makedirs(output_dir, exist_ok=True)

    stem = Path(file_name).stem
    filename = f"{stem}_stats_comparison.txt"
    filepath = os.path.join(output_dir, filename)

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    col_w = 14
    metric_w = 16

    header_line = f"{'Metric':<{metric_w}}" + ''.join(f"{p:>{col_w}}" for p in properties)
    sep = ' ' + '-' * (metric_w + col_w * len(properties))

    rows = [
        ('Min', lambda s: s.min_val),
        ('5%', lambda s: s.pct_5),
        ('25%', lambda s: s.q1),
        ('50%', lambda s: s.median),
        ('75%', lambda s: s.q3),
        ('95%', lambda s: s.pct_95),
        ('Max', lambda s: s.max_val),
        ('Mean', lambda s: s.mean),
        ('Std', lambda s: s.std),
    ]

    lines = [
        "=" * (metric_w + col_w * len(properties) + len(properties)),
        "3DGS Statistics Comparison",
        "=" * (metric_w + col_w * len(properties) + len(properties)),
        f"File: {file_name}",
        f"Generated: {now}",
        "",
        header_line,
        sep,
    ]

    for label, getter in rows:
        row = f"{label:<{metric_w}}"
        for s in stats_list:
            val = getter(s)
            row += f"{val:>{col_w}.6f}"
        lines.append(row)

    lines.append(sep)
    lines.append("")

    with open(filepath, 'w') as f:
        f.write('\n'.join(lines) + '\n')

    return filepath
