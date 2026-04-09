"""Spatial partitioning for point clouds"""

from typing import List, Tuple, Dict, Any, Optional, Iterator
from dataclasses import dataclass
import json
from pathlib import Path

from .bounds import Bounds


@dataclass
class BlockInfo:
    """Information about a single partition block"""
    index_i: int
    index_j: int
    index_k: int
    bounds: Bounds
    point_count: int = 0
    filename: str = ""

    def to_dict(self) -> dict:
        return {
            'index': [self.index_i, self.index_j, self.index_k],
            'bounds': self.bounds.to_dict(),
            'point_count': self.point_count,
            'filename': self.filename
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'BlockInfo':
        return cls(
            index_i=d['index'][0],
            index_j=d['index'][1],
            index_k=d['index'][2],
            bounds=Bounds.from_dict(d['bounds']),
            point_count=d['point_count'],
            filename=d['filename']
        )


@dataclass
class PartitionInfo:
    """Information about a complete partitioning"""
    original_file: str
    total_points: int
    splits: Tuple[int, int, int]
    global_bounds: Bounds
    blocks: List[BlockInfo]

    def to_dict(self) -> dict:
        return {
            'original_file': self.original_file,
            'total_points': self.total_points,
            'splits': list(self.splits),
            'global_bounds': self.global_bounds.to_dict(),
            'blocks': [b.to_dict() for b in self.blocks]
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'PartitionInfo':
        return cls(
            original_file=d['original_file'],
            total_points=d['total_points'],
            splits=tuple(d['splits']),
            global_bounds=Bounds.from_dict(d['global_bounds']),
            blocks=[BlockInfo.from_dict(b) for b in d['blocks']]
        )

    def save(self, filepath: str):
        """Save partition info to JSON file"""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, filepath: str) -> 'PartitionInfo':
        """Load partition info from JSON file"""
        with open(filepath, 'r') as f:
            return cls.from_dict(json.load(f))


class Partitioner:
    """Spatial partitioner for 3D point clouds"""

    def __init__(self, bounds: Bounds, splits: Tuple[int, int, int]):
        """
        Initialize partitioner.

        Args:
            bounds: Global bounding box
            splits: (nx, ny, nz) - number of splits in each dimension
        """
        self.global_bounds = bounds
        self.splits = splits
        self.nx, self.ny, self.nz = splits
        self.blocks: List[List[List[BlockInfo]]] = []
        self._setup_blocks()

    def _setup_blocks(self):
        """Create block grid"""
        dx = self.global_bounds.size_x / self.nx if self.nx > 0 else 0
        dy = self.global_bounds.size_y / self.ny if self.ny > 0 else 0
        dz = self.global_bounds.size_z / self.nz if self.nz > 0 else 0

        self.blocks = []
        for i in range(self.nx):
            yz_blocks = []
            for j in range(self.ny):
                z_blocks = []
                for k in range(self.nz):
                    min_x = self.global_bounds.min_x + i * dx
                    max_x = self.global_bounds.min_x + (i + 1) * dx if i < self.nx - 1 else self.global_bounds.max_x
                    min_y = self.global_bounds.min_y + j * dy
                    max_y = self.global_bounds.min_y + (j + 1) * dy if j < self.ny - 1 else self.global_bounds.max_y
                    min_z = self.global_bounds.min_z + k * dz
                    max_z = self.global_bounds.min_z + (k + 1) * dz if k < self.nz - 1 else self.global_bounds.max_z

                    block = BlockInfo(
                        index_i=i,
                        index_j=j,
                        index_k=k,
                        bounds=Bounds(
                            min_coords=(min_x, min_y, min_z),
                            max_coords=(max_x, max_y, max_z)
                        )
                    )
                    z_blocks.append(block)
                yz_blocks.append(z_blocks)
            self.blocks.append(yz_blocks)

    def get_block_index(self, x: float, y: float, z: float) -> Optional[Tuple[int, int, int]]:
        """
        Get block index for a point.

        Returns:
            (i, j, k) or None if point is outside bounds
        """
        if not self.global_bounds.contains(x, y, z):
            return None

        # Add small epsilon to handle precision issues at boundaries
        eps = 1e-12
        x_clamped = max(self.global_bounds.min_x, min(self.global_bounds.max_x - eps, x))
        y_clamped = max(self.global_bounds.min_y, min(self.global_bounds.max_y - eps, y))
        z_clamped = max(self.global_bounds.min_z, min(self.global_bounds.max_z - eps, z))

        i = int((x_clamped - self.global_bounds.min_x) / self.global_bounds.size_x * self.nx)
        j = int((y_clamped - self.global_bounds.min_y) / self.global_bounds.size_y * self.ny)
        k = int((z_clamped - self.global_bounds.min_z) / self.global_bounds.size_z * self.nz)

        # Clamp to valid range
        i = max(0, min(self.nx - 1, i))
        j = max(0, min(self.ny - 1, j))
        k = max(0, min(self.nz - 1, k))

        return (i, j, k)

    def get_block(self, i: int, j: int, k: int) -> Optional[BlockInfo]:
        """Get block by index"""
        if 0 <= i < self.nx and 0 <= j < self.ny and 0 <= k < self.nz:
            return self.blocks[i][j][k]
        return None

    def iter_blocks(self) -> Iterator[BlockInfo]:
        """Iterate over all blocks"""
        for i in range(self.nx):
            for j in range(self.ny):
                for k in range(self.nz):
                    yield self.blocks[i][j][k]

    def create_partition_info(self, original_file: str, total_points: int) -> PartitionInfo:
        """Create partition info object"""
        blocks = list(self.iter_blocks())
        return PartitionInfo(
            original_file=original_file,
            total_points=total_points,
            splits=self.splits,
            global_bounds=self.global_bounds,
            blocks=blocks
        )


def parse_split_spec(spec: str) -> Tuple[int, int, int]:
    """
    Parse split specification string.

    Args:
        spec: Format like "2*3*2" or "2x3x2"

    Returns:
        (nx, ny, nz) tuple
    """
    spec = spec.replace('x', '*')
    parts = spec.split('*')
    if len(parts) != 3:
        raise ValueError(f"Invalid split spec: {spec}, expected format like '2*3*2'")
    try:
        nx = int(parts[0])
        ny = int(parts[1])
        nz = int(parts[2])
        if nx <= 0 or ny <= 0 or nz <= 0:
            raise ValueError("Split counts must be positive integers")
        return (nx, ny, nz)
    except ValueError as e:
        raise ValueError(f"Invalid split spec: {spec}") from e


def generate_block_filename(base_name: str, i: int, j: int, k: int) -> str:
    """Generate filename for a block"""
    return f"{base_name}_block_{i}_{j}_{k}.ply"
