"""Bounding box calculation"""

from dataclasses import dataclass
from typing import Tuple, Optional


@dataclass
class Bounds:
    """3D axis-aligned bounding box"""
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    def __init__(self, min_coords: Optional[Tuple[float, float, float]] = None,
                 max_coords: Optional[Tuple[float, float, float]] = None):
        if min_coords is None:
            self.min_x = self.min_y = self.min_z = float('inf')
        else:
            self.min_x, self.min_y, self.min_z = min_coords
        if max_coords is None:
            self.max_x = self.max_y = self.max_z = float('-inf')
        else:
            self.max_x, self.max_y, self.max_z = max_coords

    @property
    def min_coords(self) -> Tuple[float, float, float]:
        return (self.min_x, self.min_y, self.min_z)

    @property
    def max_coords(self) -> Tuple[float, float, float]:
        return (self.max_x, self.max_y, self.max_z)

    @property
    def size_x(self) -> float:
        return self.max_x - self.min_x

    @property
    def size_y(self) -> float:
        return self.max_y - self.min_y

    @property
    def size_z(self) -> float:
        return self.max_z - self.min_z

    @property
    def center(self) -> Tuple[float, float, float]:
        return (
            (self.min_x + self.max_x) / 2,
            (self.min_y + self.max_y) / 2,
            (self.min_z + self.max_z) / 2
        )

    def expand(self, x: float, y: float, z: float):
        """Expand bounds to include a point"""
        if x < self.min_x:
            self.min_x = x
        if x > self.max_x:
            self.max_x = x
        if y < self.min_y:
            self.min_y = y
        if y > self.max_y:
            self.max_y = y
        if z < self.min_z:
            self.min_z = z
        if z > self.max_z:
            self.max_z = z

    def expand_by_bounds(self, other: 'Bounds'):
        """Expand bounds to include another bounds"""
        if other.min_x < self.min_x:
            self.min_x = other.min_x
        if other.max_x > self.max_x:
            self.max_x = other.max_x
        if other.min_y < self.min_y:
            self.min_y = other.min_y
        if other.max_y > self.max_y:
            self.max_y = other.max_y
        if other.min_z < self.min_z:
            self.min_z = other.min_z
        if other.max_z > self.max_z:
            self.max_z = other.max_z

    def contains(self, x: float, y: float, z: float, epsilon: float = 1e-10) -> bool:
        """Check if a point is within bounds (inclusive on min, exclusive on max)"""
        return (self.min_x - epsilon <= x < self.max_x + epsilon and
                self.min_y - epsilon <= y < self.max_y + epsilon and
                self.min_z - epsilon <= z < self.max_z + epsilon)

    def is_valid(self) -> bool:
        """Check if bounds are valid (min <= max)"""
        return (self.min_x <= self.max_x and
                self.min_y <= self.max_y and
                self.min_z <= self.max_z)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'min_x': self.min_x,
            'min_y': self.min_y,
            'min_z': self.min_z,
            'max_x': self.max_x,
            'max_y': self.max_y,
            'max_z': self.max_z,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Bounds':
        """Create from dictionary"""
        return cls(
            min_coords=(d['min_x'], d['min_y'], d['min_z']),
            max_coords=(d['max_x'], d['max_y'], d['max_z'])
        )

    def __repr__(self) -> str:
        return f"Bounds(({self.min_x:.4f}, {self.min_y:.4f}, {self.min_z:.4f}), ({self.max_x:.4f}, {self.max_y:.4f}, {self.max_z:.4f}))"
