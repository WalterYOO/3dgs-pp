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
    merged_data: Optional[List[Dict[str, Any]]] = None  # For merge method


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

    @staticmethod
    def _quat_to_rotmat(w: float, x: float, y: float, z: float) -> tuple:
        """
        Convert quaternion (w, x, y, z) to 3x3 rotation matrix.
        Returns flat 9-tuple (row-major): (m00, m01, m02, m10, m11, m12, m20, m21, m22)
        """
        xx = x * x
        yy = y * y
        zz = z * z
        xy = x * y
        xz = x * z
        yz = y * z
        wx = w * x
        wy = w * y
        wz = w * z

        m00 = 1 - 2 * (yy + zz)
        m01 = 2 * (xy - wz)
        m02 = 2 * (xz + wy)
        m10 = 2 * (xy + wz)
        m11 = 1 - 2 * (xx + zz)
        m12 = 2 * (yz - wx)
        m20 = 2 * (xz - wy)
        m21 = 2 * (yz + wx)
        m22 = 1 - 2 * (xx + yy)
        return (m00, m01, m02, m10, m11, m12, m20, m21, m22)

    @staticmethod
    def _rotmat_to_quat(m: tuple) -> tuple:
        """
        Convert 3x3 rotation matrix (flat 9-tuple) to quaternion (w, x, y, z).
        Uses trace method for numerical stability.
        """
        m00, m01, m02, m10, m11, m12, m20, m21, m22 = m
        tr = m00 + m11 + m22

        if tr > 0:
            s = math.sqrt(tr + 1.0) * 2
            w = 0.25 * s
            x = (m21 - m12) / s
            y = (m02 - m20) / s
            z = (m10 - m01) / s
        elif m00 > m11 and m00 > m22:
            s = math.sqrt(1.0 + m00 - m11 - m22) * 2
            w = (m21 - m12) / s
            x = 0.25 * s
            y = (m01 + m10) / s
            z = (m02 + m20) / s
        elif m11 > m22:
            s = math.sqrt(1.0 + m11 - m00 - m22) * 2
            w = (m02 - m20) / s
            x = (m01 + m10) / s
            y = 0.25 * s
            z = (m12 + m21) / s
        else:
            s = math.sqrt(1.0 + m22 - m00 - m11) * 2
            w = (m10 - m01) / s
            x = (m02 + m20) / s
            y = (m12 + m21) / s
            z = 0.25 * s

        # Normalize
        norm = math.sqrt(w * w + x * x + y * y + z * z)
        if norm > 1e-10:
            w /= norm
            x /= norm
            y /= norm
            z /= norm
        return (w, x, y, z)

    @staticmethod
    def _mat3_mul(a: tuple, b: tuple) -> tuple:
        """Multiply two 3x3 matrices (flat 9-tuples, row-major)."""
        return (
            a[0] * b[0] + a[1] * b[3] + a[2] * b[6],
            a[0] * b[1] + a[1] * b[4] + a[2] * b[7],
            a[0] * b[2] + a[1] * b[5] + a[2] * b[8],
            a[3] * b[0] + a[4] * b[3] + a[5] * b[6],
            a[3] * b[1] + a[4] * b[4] + a[5] * b[7],
            a[3] * b[2] + a[4] * b[5] + a[5] * b[8],
            a[6] * b[0] + a[7] * b[3] + a[8] * b[6],
            a[6] * b[1] + a[7] * b[4] + a[8] * b[7],
            a[6] * b[2] + a[7] * b[5] + a[8] * b[8],
        )

    @staticmethod
    def _mat3_transpose(a: tuple) -> tuple:
        """Transpose a 3x3 matrix (flat 9-tuple, row-major)."""
        return (a[0], a[3], a[6], a[1], a[4], a[7], a[2], a[5], a[8])

    @staticmethod
    def _mat3_scale(a: tuple, s: float) -> tuple:
        """Scale a 3x3 matrix by scalar."""
        return tuple(v * s for v in a)

    @staticmethod
    def _mat3_add(a: tuple, b: tuple) -> tuple:
        """Add two 3x3 matrices."""
        return tuple(va + vb for va, vb in zip(a, b))

    @staticmethod
    def _symmetric_eigendecompose(m: tuple) -> tuple:
        """
        Eigendecomposition of a 3x3 symmetric matrix via Jacobi iteration.
        m: 9-tuple (row-major)
        Returns: (eigenvalues tuple of 3, eigenvectors 9-tuple row-major)
        Eigenvectors rows correspond to eigenvalues in order.
        """
        # Work with list
        a = list(m)
        # Accumulator for eigenvectors (starts as identity)
        v = [1, 0, 0, 0, 1, 0, 0, 0, 1]

        for iteration in range(60):
            # Find largest off-diagonal
            max_val = max(abs(a[1]), abs(a[2]), abs(a[5]))
            if max_val < 1e-20:
                break

            # Choose p,q based on which off-diagonal is largest
            if max_val == abs(a[1]):
                p, q = 0, 1
            elif max_val == abs(a[2]):
                p, q = 0, 2
            else:
                p, q = 1, 2

            pp = p * 3 + p
            qq = q * 3 + q
            pq = p * 3 + q

            # Rotation angle
            if abs(a[qq] - a[pp]) < 1e-30:
                theta = math.pi / 4
            else:
                theta = 0.5 * math.atan2(2 * a[pq], a[pp] - a[qq])

            c = math.cos(theta)
            s = math.sin(theta)

            # Update matrix: J^T * A * J
            new_a = list(a)
            new_a[pp] = c*c*a[pp] + 2*s*c*a[pq] + s*s*a[qq]
            new_a[qq] = s*s*a[pp] - 2*s*c*a[pq] + c*c*a[qq]
            new_a[pq] = 0.0
            new_a[q*3+p] = 0.0

            # Update other rows/columns
            r = 3 - p - q  # the third index
            rp = r * 3 + p
            rq = r * 3 + q
            new_a[rp] = c*a[rp] + s*a[rq]
            new_a[rq] = -s*a[rp] + c*a[rq]
            new_a[p*3+r] = new_a[rp]
            new_a[q*3+r] = new_a[rq]

            a = new_a

            # Accumulate eigenvectors: V = V * J
            new_v = list(v)
            for i in range(3):
                ip = i * 3 + p
                iq = i * 3 + q
                new_v[ip] = c*v[ip] + s*v[iq]
                new_v[iq] = -s*v[ip] + c*v[iq]
            v = new_v

        eigenvalues = (a[0], a[4], a[8])
        return (eigenvalues, tuple(v))

    def _merge_gaussians(self, cluster: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Merge a cluster of Gaussian ellipsoids into one.

        Uses covariance matrix fusion for scale+rotation so the merged Gaussian
        covers the full space originally occupied by all Gaussians together.

        Args:
            cluster: List of Gaussian element dictionaries

        Returns:
            Merged Gaussian element dictionary
        """
        if len(cluster) == 1:
            return cluster[0].copy()

        n = len(cluster)

        # Calculate weights based on opacity * volume
        weights = []
        total_weight = 0.0

        for elem in cluster:
            opacity = elem['opacity']
            opacity_activated = 1.0 / (1.0 + math.exp(-opacity))
            sx = math.exp(elem['scale_0'])
            sy = math.exp(elem['scale_1'])
            sz = math.exp(elem['scale_2'])
            volume = sx * sy * sz
            weight = opacity_activated * volume
            weights.append(weight)
            total_weight += weight

        if total_weight > 1e-10:
            weights = [w / total_weight for w in weights]
        else:
            weights = [1.0 / n for _ in range(n)]

        merged = {}

        # --- Weighted average for position ---
        mu = [0.0, 0.0, 0.0]
        for prop in ['x', 'y', 'z']:
            mu[ord(prop) - ord('x')] = sum(w * elem[prop] for w, elem in zip(weights, cluster))

        merged['x'], merged['y'], merged['z'] = mu

        # --- Weighted average for spherical harmonics ---
        for prop in cluster[0].keys():
            if prop.startswith('f_dc_') or prop.startswith('f_rest_'):
                merged[prop] = sum(w * elem[prop] for w, elem in zip(weights, cluster))

        # --- Opacity: weighted sum in logit space ---
        merged['opacity'] = sum(w * elem['opacity'] for w, elem in zip(weights, cluster))

        # --- Covariance fusion for scale + rotation ---
        # Σ_merged = Σ w_i * (Σ_i + (μ_i - μ_merged)(μ_i - μ_merged)^T)
        fused_cov = [0.0] * 9  # 3x3 flat row-major

        for w, elem in zip(weights, cluster):
            # Rotation matrix from quaternion
            quat = (elem['rot_0'], elem['rot_1'], elem['rot_2'], elem['rot_3'])
            r = self._quat_to_rotmat(*quat)

            # Diagonal of exp(scale)^2
            sx = math.exp(elem['scale_0']) ** 2
            sy = math.exp(elem['scale_1']) ** 2
            sz = math.exp(elem['scale_2']) ** 2
            d = (sx, 0, 0,
                 0, sy, 0,
                 0, 0, sz)

            # Σ_i = R * D * R^T
            rd = self._mat3_mul(r, d)
            sigma_i = self._mat3_mul(rd, self._mat3_transpose(r))

            # Outer product of displacement: (μ_i - μ_merged)(μ_i - μ_merged)^T
            dx = elem['x'] - mu[0]
            dy = elem['y'] - mu[1]
            dz = elem['z'] - mu[2]
            outer = (dx * dx, dx * dy, dx * dz,
                     dy * dx, dy * dy, dy * dz,
                     dz * dx, dz * dy, dz * dz)

            # w * (σ + outer)
            fused_cov = list(self._mat3_add(
                fused_cov,
                self._mat3_scale(self._mat3_add(sigma_i, outer), w)
            ))

        # Ensure symmetry (numerical safety)
        fused_cov[1], fused_cov[3] = (fused_cov[1] + fused_cov[3]) * 0.5, (fused_cov[1] + fused_cov[3]) * 0.5
        fused_cov[2], fused_cov[6] = (fused_cov[2] + fused_cov[6]) * 0.5, (fused_cov[2] + fused_cov[6]) * 0.5
        fused_cov[5], fused_cov[7] = (fused_cov[5] + fused_cov[7]) * 0.5, (fused_cov[5] + fused_cov[7]) * 0.5

        # Eigendecompose: Σ = V * Λ * V^T
        eigenvalues, eigenvectors = self._symmetric_eigendecompose(tuple(fused_cov))

        # Extract scale from eigenvalues (log of sqrt)
        # eigenvalues are in row-major diagonal order of V*Λ*V^T
        scales = []
        for ev in eigenvalues:
            s = max(ev, 1e-10)
            scales.append(math.log(math.sqrt(s)))

        # Clamp very large scales
        for i in range(3):
            scales[i] = max(scales[i], -10.0)

        merged['scale_0'] = scales[0]
        merged['scale_1'] = scales[1]
        merged['scale_2'] = scales[2]

        # Extract rotation from eigenvectors
        # eigenvectors is 9-tuple row-major, each row is an eigenvector
        # corresponding to eigenvalues[0], [1], [2]
        # Build rotation matrix from eigenvectors (rows → columns for proper R)
        ev0 = (eigenvectors[0], eigenvectors[1], eigenvectors[2])
        ev1 = (eigenvectors[3], eigenvectors[4], eigenvectors[5])
        ev2 = (eigenvectors[6], eigenvectors[7], eigenvectors[8])

        # Build rotation matrix (eigenvectors as rows), then convert to quaternion
        # The eigenvector matrix V from Jacobi is orthogonal: V * V^T = I
        # R = V (eigenvectors as rows)
        # We need to ensure det(R) = 1 (not a reflection)
        det = (ev0[0] * (ev1[1] * ev2[2] - ev1[2] * ev2[1])
              - ev0[1] * (ev1[0] * ev2[2] - ev1[2] * ev2[0])
              + ev0[2] * (ev1[0] * ev2[1] - ev1[1] * ev2[0]))

        if det < 0:
            # Flip last eigenvector to fix reflection
            ev2 = (-ev2[0], -ev2[1], -ev2[2])
            eigenvectors = (ev0[0], ev0[1], ev0[2],
                            ev1[0], ev1[1], ev1[2],
                            ev2[0], ev2[1], ev2[2])

        # Convert rotation matrix to quaternion
        merged_quat = self._rotmat_to_quat(eigenvectors)
        merged['rot_0'], merged['rot_1'], merged['rot_2'], merged['rot_3'] = merged_quat

        return merged

    def merge_sample(self, target_count: int) -> DownsampleResult:
        """
        Gaussian merging sampling - merge nearby Gaussians instead of just selecting.

        Args:
            target_count: Target number of Gaussians

        Returns:
            DownsampleResult with merged_data populated
        """
        if target_count >= self.total_count:
            # Return all data without merging
            all_data = []
            for i in range(self.total_count):
                elem = self.reader.get_element(i, 'vertex')
                all_data.append({name: elem[name] for name in self.reader.get_property_names('vertex')})
            return DownsampleResult(
                selected_indices=list(range(self.total_count)),
                original_count=self.total_count,
                target_count=target_count,
                actual_count=self.total_count,
                method='merge',
                merged_data=all_data
            )

        # Get bounds
        (min_x, min_y, min_z), (max_x, max_y, max_z) = self.reader.get_bounds('vertex')

        # Calculate voxel grid dimensions to get approximately target_count
        volume = (max_x - min_x) * (max_y - min_y) * (max_z - min_z)
        if volume <= 0:
            # Fallback if volume is zero
            all_data = []
            for i in range(self.total_count):
                elem = self.reader.get_element(i, 'vertex')
                all_data.append({name: elem[name] for name in self.reader.get_property_names('vertex')})
            return DownsampleResult(
                selected_indices=list(range(min(target_count, self.total_count))),
                original_count=self.total_count,
                target_count=target_count,
                actual_count=min(target_count, self.total_count),
                method='merge',
                merged_data=all_data[:target_count]
            )

        # Calculate voxel size - aim for slightly more voxels to give flexibility
        voxels_per_dim = math.pow(target_count * 1.5, 1/3)
        voxel_size_x = (max_x - min_x) / voxels_per_dim
        voxel_size_y = (max_y - min_y) / voxels_per_dim
        voxel_size_z = (max_z - min_z) / voxels_per_dim

        # First pass: assign points to voxels
        voxels: Dict[tuple, List[Dict[str, Any]]] = {}

        for i in range(self.total_count):
            elem = self.reader.get_element(i, 'vertex')
            x, y, z = elem.x, elem.y, elem.z

            # Calculate voxel coordinates
            vx = int((x - min_x) / voxel_size_x) if voxel_size_x > 0 else 0
            vy = int((y - min_y) / voxel_size_y) if voxel_size_y > 0 else 0
            vz = int((z - min_z) / voxel_size_z) if voxel_size_z > 0 else 0

            voxel_key = (vx, vy, vz)

            # Store element data
            prop_names = self.reader.get_property_names('vertex')
            elem_data = {name: elem[name] for name in prop_names}

            if voxel_key not in voxels:
                voxels[voxel_key] = []
            voxels[voxel_key].append(elem_data)

        # If we have too many voxels, merge adjacent ones
        # For simplicity, we'll just use the voxels we have and merge within each
        merged_list = []

        # Sort voxel keys by center position for consistent ordering
        def voxel_center(key):
            vx, vy, vz = key
            cx = min_x + (vx + 0.5) * voxel_size_x
            cy = min_y + (vy + 0.5) * voxel_size_y
            cz = min_z + (vz + 0.5) * voxel_size_z
            return (cx, cy, cz)

        sorted_voxels = sorted(voxels.items(), key=lambda item: voxel_center(item[0]))

        # Merge each voxel's cluster
        for voxel_key, cluster in sorted_voxels:
            if cluster:
                merged = self._merge_gaussians(cluster)
                merged_list.append(merged)

        # If we still have too many points, we can merge further or subsample
        if len(merged_list) > target_count * 2:
            # Recursively merge the merged list
            # For simplicity, we'll just take every Nth for now
            step = len(merged_list) / target_count
            final_list = [merged_list[int(i * step)] for i in range(target_count)]
        elif len(merged_list) > target_count:
            # Just take the first target_count
            final_list = merged_list[:target_count]
        else:
            final_list = merged_list

        return DownsampleResult(
            selected_indices=[],  # Not used for merge
            original_count=self.total_count,
            target_count=target_count,
            actual_count=len(final_list),
            method='merge',
            merged_data=final_list
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
        elif method == 'merge':
            return self.merge_sample(target_count)
        else:
            raise ValueError(f"Unknown sampling method: {method}")

    def iter_selected(self, result: DownsampleResult) -> Iterator[Dict[str, Any]]:
        """
        Iterate over selected or merged elements.

        Args:
            result: DownsampleResult from sample()

        Yields:
            Element data as dictionary
        """
        if result.method == 'merge' and result.merged_data is not None:
            for data in result.merged_data:
                yield data
        else:
            prop_names = self.reader.get_property_names('vertex')
            for idx in result.selected_indices:
                elem = self.reader.get_element(idx, 'vertex')
                yield {name: elem[name] for name in prop_names}
