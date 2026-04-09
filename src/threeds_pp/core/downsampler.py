"""Downsampling algorithms for 3DGS point clouds"""

import random
from typing import List, Iterator, Callable, Optional, Dict, Any
from dataclasses import dataclass
import math

from ..ply import LazyPLYReader


@dataclass
class DownsampleResult:
    """Result of downsampling operation"""
    selected_indices: List[int]
    original_count: int
    target_count: int
    actual_count: int
    method: str


class Downsampler:
    """Downsampler for 3DGS point clouds"""

    def __init__(self, reader: LazyPLYReader):
        self.reader = reader
        self.vertex_elem = reader.header.get_element('vertex')
        if not self.vertex_elem:
            raise ValueError("No 'vertex' element found in PLY file")
        self.total_count = self.vertex_elem.count

    def calculate_target_count(self, ratio: Optional[float] = None,
                                 count: Optional[int] = None) -> int:
        """
        Calculate target count from ratio or count.

        Args:
            ratio: Retention ratio (0 < ratio <= 1)
            count: Target count

        Returns:
            Target count
        """
        if ratio is not None:
            if ratio <= 0 or ratio > 1:
                raise ValueError(f"Ratio must be between 0 and 1, got {ratio}")
            target = max(1, int(self.total_count * ratio))
        elif count is not None:
            if count <= 0:
                raise ValueError(f"Count must be positive, got {count}")
            target = min(count, self.total_count)
        else:
            raise ValueError("Either ratio or count must be specified")
        return target

    def uniform_sample(self, target_count: int) -> DownsampleResult:
        """
        Uniform sampling by index.

        Args:
            target_count: Number of points to retain

        Returns:
            DownsampleResult with selected indices
        """
        if target_count >= self.total_count:
            return DownsampleResult(
                selected_indices=list(range(self.total_count)),
                original_count=self.total_count,
                target_count=target_count,
                actual_count=self.total_count,
                method='uniform'
            )

        step = self.total_count / target_count
        selected = [int(i * step) for i in range(target_count)]

        # Ensure no duplicates
        selected = sorted(list(set(selected)))

        return DownsampleResult(
            selected_indices=selected,
            original_count=self.total_count,
            target_count=target_count,
            actual_count=len(selected),
            method='uniform'
        )

    def opacity_sample(self, target_count: int) -> DownsampleResult:
        """
        Sampling based on opacity (importance sampling).

        Args:
            target_count: Number of points to retain

        Returns:
            DownsampleResult with selected indices
        """
        if target_count >= self.total_count:
            return DownsampleResult(
                selected_indices=list(range(self.total_count)),
                original_count=self.total_count,
                target_count=target_count,
                actual_count=self.total_count,
                method='opacity'
            )

        # First pass: collect opacities
        opacities = []
        for i in range(self.total_count):
            elem = self.reader.get_element(i, 'vertex')
            opacities.append((i, elem.opacity))

        # Sort by opacity descending
        opacities.sort(key=lambda x: x[1], reverse=True)

        # Select top N
        selected = [idx for idx, _ in opacities[:target_count]]
        selected.sort()

        return DownsampleResult(
            selected_indices=selected,
            original_count=self.total_count,
            target_count=target_count,
            actual_count=len(selected),
            method='opacity'
        )

    def random_sample(self, target_count: int, seed: Optional[int] = None) -> DownsampleResult:
        """
        Random sampling.

        Args:
            target_count: Number of points to retain
            seed: Random seed for reproducibility

        Returns:
            DownsampleResult with selected indices
        """
        if target_count >= self.total_count:
            return DownsampleResult(
                selected_indices=list(range(self.total_count)),
                original_count=self.total_count,
                target_count=target_count,
                actual_count=self.total_count,
                method='random'
            )

        if seed is not None:
            random.seed(seed)

        # Use reservoir sampling for efficiency
        selected = list(range(min(target_count, self.total_count)))

        for i in range(target_count, self.total_count):
            j = random.randint(0, i)
            if j < target_count:
                selected[j] = i

        selected.sort()

        return DownsampleResult(
            selected_indices=selected,
            original_count=self.total_count,
            target_count=target_count,
            actual_count=len(selected),
            method='random'
        )

    def voxel_sample(self, target_count: int) -> DownsampleResult:
        """
        Voxel-based sampling.

        Args:
            target_count: Number of points to retain (approximate)

        Returns:
            DownsampleResult with selected indices
        """
        if target_count >= self.total_count:
            return DownsampleResult(
                selected_indices=list(range(self.total_count)),
                original_count=self.total_count,
                target_count=target_count,
                actual_count=self.total_count,
                method='voxel'
            )

        # Get bounds
        (min_x, min_y, min_z), (max_x, max_y, max_z) = self.reader.get_bounds('vertex')

        # Calculate voxel size to get approximately target_count voxels
        volume = (max_x - min_x) * (max_y - min_y) * (max_z - min_z)
        if volume <= 0:
            # Fallback to uniform sampling if volume is zero
            return self.uniform_sample(target_count)

        # Calculate voxel dimensions
        voxels_per_dim = math.pow(target_count, 1/3)
        voxel_size_x = (max_x - min_x) / voxels_per_dim
        voxel_size_y = (max_y - min_y) / voxels_per_dim
        voxel_size_z = (max_z - min_z) / voxels_per_dim

        # First pass: assign points to voxels and track best in each voxel
        voxels: Dict[tuple, tuple] = {}  # (vx, vy, vz) -> (opacity, index)

        for i in range(self.total_count):
            elem = self.reader.get_element(i, 'vertex')
            x, y, z = elem.x, elem.y, elem.z
            opacity = elem.opacity

            # Calculate voxel coordinates
            vx = int((x - min_x) / voxel_size_x) if voxel_size_x > 0 else 0
            vy = int((y - min_y) / voxel_size_y) if voxel_size_y > 0 else 0
            vz = int((z - min_z) / voxel_size_z) if voxel_size_z > 0 else 0

            voxel_key = (vx, vy, vz)

            # Keep the point with highest opacity in each voxel
            if voxel_key not in voxels or opacity > voxels[voxel_key][0]:
                voxels[voxel_key] = (opacity, i)

        # Collect selected indices
        selected = [idx for (_, idx) in voxels.values()]
        selected.sort()

        return DownsampleResult(
            selected_indices=selected,
            original_count=self.total_count,
            target_count=target_count,
            actual_count=len(selected),
            method='voxel'
        )

    def sample(self, method: str = 'uniform',
               ratio: Optional[float] = None,
               count: Optional[int] = None,
               seed: Optional[int] = None) -> DownsampleResult:
        """
        Run downsampling with specified method.

        Args:
            method: Sampling method ('uniform', 'opacity', 'random', 'voxel')
            ratio: Retention ratio
            count: Target count
            seed: Random seed (for random method)

        Returns:
            DownsampleResult
        """
        target_count = self.calculate_target_count(ratio, count)

        if method == 'uniform':
            return self.uniform_sample(target_count)
        elif method == 'opacity':
            return self.opacity_sample(target_count)
        elif method == 'random':
            return self.random_sample(target_count, seed)
        elif method == 'voxel':
            return self.voxel_sample(target_count)
        else:
            raise ValueError(f"Unknown sampling method: {method}")

    def iter_selected(self, result: DownsampleResult) -> Iterator[Dict[str, Any]]:
        """
        Iterate over selected elements.

        Args:
            result: DownsampleResult from sample()

        Yields:
            Element data as dictionary
        """
        prop_names = self.reader.get_property_names('vertex')
        for idx in result.selected_indices:
            elem = self.reader.get_element(idx, 'vertex')
            yield {name: elem[name] for name in prop_names}
