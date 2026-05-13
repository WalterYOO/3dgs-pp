"""Axis transform (swap/rotate) for 3DGS PLY files.

Transforms coordinates and quaternion imaginary parts via direct axis
permutation + sign flip - no matrix multiplication required.
"""

import re
from dataclasses import dataclass
from typing import Tuple

import numpy as np

from .stats import StatsAnalyzer
from ..ply.writer import copy_header_for_partition


@dataclass
class TransformPlan:
    """Planned axis transform.

    transform: tuple of 3 integers, each in {-3,-2,-1,1,2,3}.
        |v| indicates which old axis the new value comes from (1=x, 2=y, 3=z).
        sign indicates whether to negate.
        Example: (2, -1, 3) means new_x=old_y, new_y=-old_x, new_z=old_z.

    description: human-readable description of the transform.
    mirror: True if the transform is a mirror (det=-1), False for pure rotation.
        Mirror transforms conjugate the quaternion after permuting.
    """

    transform: Tuple[int, int, int]
    description: str
    mirror: bool = False


# Preset transforms: key -> (new_x, new_y, new_z)
# |v|: source axis (1=x, 2=y, 3=z), sign: negate or not
SWAP_TABLE = {
    "xy": (2, 1, 3),
    "nxy": (-2, -1, 3),
    "xz": (3, 2, 1),
    "nxz": (-3, 2, -1),
    "yz": (1, 3, 2),
    "nyz": (1, -3, -2),
}

ROT_TABLE = {
    "z90": (2, -1, 3),
    "z180": (-1, -2, 3),
    "z270": (-2, 1, 3),
    "y90": (3, 2, -1),
    "y180": (-1, 2, -3),
    "y270": (-3, 2, 1),
    "x90": (1, 3, -2),
    "x180": (1, -2, -3),
    "x270": (1, -3, 2),
}


def _is_valid_transform(values: Tuple[int, int, int]) -> bool:
    """Check if a tuple is a valid signed permutation of {1,2,3}."""
    return sorted(abs(v) for v in values) == [1, 2, 3]


def _fmt_axis(val: int) -> str:
    """Format a transform component as axis name, e.g. -y."""
    sign = "-" if val < 0 else ""
    return sign + "xyz"[abs(val) - 1]


def _fmt_description(t: Tuple[int, int, int]) -> str:
    """Format transform tuple as coordinate mapping, e.g. (x,y,z) -> (y, -x, z)."""
    parts = [_fmt_axis(v) for v in t]
    return f"(x,y,z) -> ({parts[0]}, {parts[1]}, {parts[2]})"


def get_transform(
    swap: str | None = None,
    inv: str | None = None,
    rot: str | None = None,
    transform_expr: str | None = None,
) -> TransformPlan:
    """Parse transform specification and return a TransformPlan.

    Exactly one of swap, inv, rot, or transform_expr must be provided.
    """
    count = sum(1 for v in (swap, inv, rot, transform_expr) if v is not None)
    if count != 1:
        raise ValueError(
            "Exactly one of --swap, --inv, --rot, or --transform must be specified"
        )

    if swap is not None:
        key = swap.lower().strip()
        if key not in SWAP_TABLE:
            raise ValueError(
                f"Invalid swap '{swap}'. Choose from: xy, nxy, xz, nxz, yz, nyz "
                f"('n' prefix = negative, e.g. nxy means -xy)"
            )
        t = SWAP_TABLE[key]
        display = key.replace("n", "-", 1) if key.startswith("n") else key
        return TransformPlan(
            transform=t,
            description=f"swap {display} ({_fmt_description(t)})",
            mirror=True,
        )

    if inv is not None:
        axis = inv.lower().strip()
        if axis not in ("x", "y", "z"):
            raise ValueError(f"Invalid inversion axis '{inv}'. Must be x, y, or z")
        idx = {"x": 0, "y": 1, "z": 2}[axis]
        t = list(range(1, 4))
        t[idx] = -t[idx]
        t = tuple(t)
        return TransformPlan(
            transform=t,
            description=f"inv {axis} ({_fmt_description(t)})",
            mirror=True,
        )

    if rot is not None:
        if isinstance(rot, (list, tuple)):
            parts = [str(p).lower().strip() for p in rot]
        else:
            parts = rot.lower().strip().split()
        if len(parts) != 2:
            raise ValueError("Rotation format: '<axis> <angle>', e.g. 'z 90'")
        axis, angle_str = parts
        if axis not in ("x", "y", "z"):
            raise ValueError(f"Invalid rotation axis '{axis}'. Must be x, y, or z")
        if angle_str not in ("90", "180", "270"):
            raise ValueError(
                f"Invalid rotation angle '{angle_str}'. Must be 90, 180, or 270"
            )
        key = f"{axis}{angle_str}"
        if key not in ROT_TABLE:
            raise ValueError(f"Invalid rotation '{rot}'")
        t = ROT_TABLE[key]
        return TransformPlan(
            transform=t,
            description=f"rot {axis} {angle_str} ({_fmt_description(t)})",
            mirror=False,
        )

    # Generic expression: "x->y,y->-x,z->z"
    expr = transform_expr.strip()
    mapping = {}
    for part in re.split(r",\s*", expr):
        m = re.match(r"^(x|y|z)\s*->\s*(-?)(x|y|z)$", part.strip())
        if not m:
            raise ValueError(
                f"Invalid transform expression part '{part}'. Use format like 'x->y,y->-x,z->z'"
            )
        dst = m.group(1)
        sign = -1 if m.group(2) == "-" else 1
        src = m.group(3)
        mapping[dst] = sign * {"x": 1, "y": 2, "z": 3}[src]

    t = (mapping["x"], mapping["y"], mapping["z"])
    if not _is_valid_transform(t):
        raise ValueError(
            f"Invalid transform '{expr}': must be a signed permutation of (x, y, z)"
        )

    # Determine if mirror: compute determinant of signed permutation matrix
    # det = sign(permutation) * (-1)^num_negatives
    perm = [abs(v) for v in t]
    inversions = sum(1 for i in range(3) for j in range(i + 1, 3) if perm[i] > perm[j])
    sign_perm = -1 if inversions % 2 else 1
    num_neg = sum(1 for v in t if v < 0)
    det = sign_perm * ((-1) ** num_neg)
    is_mirror = det < 0

    return TransformPlan(
        transform=t,
        description=f"transform {_fmt_description(t)}",
        mirror=is_mirror,
    )


def _apply_transform(arr: np.ndarray, t: Tuple[int, int, int]) -> np.ndarray:
    """Apply transform to a (N,3) array in-place. Returns the same array."""
    src = [abs(v) - 1 for v in t]
    signs = [v < 0 for v in t]
    new = np.empty_like(arr)
    new[:, 0] = -arr[:, src[0]] if signs[0] else arr[:, src[0]]
    new[:, 1] = -arr[:, src[1]] if signs[1] else arr[:, src[1]]
    new[:, 2] = -arr[:, src[2]] if signs[2] else arr[:, src[2]]
    arr[:] = new
    return arr


def _apply_transform_quat_imag(
    arr: np.ndarray, t: Tuple[int, int, int], mirror: bool
) -> np.ndarray:
    """Apply transform to quaternion imaginary part (N,3) in-place.

    For mirror transforms (det=-1), also conjugate: negate all imaginary parts
    after the coordinate transform to mirror the rotation direction.
    """
    _apply_transform(arr, t)
    if mirror:
        arr *= -1
    return arr


def _apply_transform_permute(arr: np.ndarray, t: Tuple[int, int, int]) -> np.ndarray:
    """Apply transform permutation only (no sign flip) to a (N,3) array in-place.

    Used for scale_0/1/2 which follow the same axis remapping but keep magnitudes.
    """
    src = [abs(v) - 1 for v in t]
    new = np.empty_like(arr)
    new[:, 0] = arr[:, src[0]]
    new[:, 1] = arr[:, src[1]]
    new[:, 2] = arr[:, src[2]]
    arr[:] = new
    return arr


def _is_identity(t: Tuple[int, int, int]) -> bool:
    return t == (1, 2, 3)


def _chunked_transform_binary(
    fpath_in: str,
    fpath_out: str,
    new_header,
    dtype,
    total: int,
    header_size: int,
    plan: TransformPlan,
    has_rot_props: bool,
    has_scale_props: bool,
    progress_callback=None,
):
    """Transform binary PLY data in ~64 MB chunks."""
    row_size = dtype.itemsize
    chunk = max(1, 64 * 1024 * 1024 // row_size)
    t = plan.transform

    skip = _is_identity(t) and not has_rot_props and not has_scale_props

    with open(fpath_in, "rb") as fin, open(fpath_out, "wb") as fout:
        fout.write(new_header.to_string().encode("ascii"))
        fin.seek(header_size)

        written = 0
        while written < total:
            to_read = min(chunk, total - written)
            if skip:
                raw = fin.read(to_read * row_size)
                fout.write(raw)
            else:
                block = np.fromfile(fin, dtype=dtype, count=to_read)
                actual = len(block)
                coords = np.stack([block["x"], block["y"], block["z"]], axis=-1)
                _apply_transform(coords, t)
                block["x"] = coords[:, 0]
                block["y"] = coords[:, 1]
                block["z"] = coords[:, 2]

                if has_rot_props:
                    quat_imag = np.stack(
                        [block["rot_1"], block["rot_2"], block["rot_3"]], axis=-1
                    )
                    _apply_transform_quat_imag(quat_imag, t, plan.mirror)
                    block["rot_1"] = quat_imag[:, 0]
                    block["rot_2"] = quat_imag[:, 1]
                    block["rot_3"] = quat_imag[:, 2]

                if has_scale_props:
                    scales = np.stack(
                        [block["scale_0"], block["scale_1"], block["scale_2"]], axis=-1
                    )
                    _apply_transform_permute(scales, t)
                    block["scale_0"] = scales[:, 0]
                    block["scale_1"] = scales[:, 1]
                    block["scale_2"] = scales[:, 2]

                fout.write(block.tobytes())
                del block

            written += actual
            if progress_callback:
                progress_callback(written, total)


def transform_ply(
    ply_file: str,
    plan: TransformPlan,
    output_path: str,
    progress_callback=None,
) -> int:
    """Apply axis transform to a PLY file.

    Returns the number of transformed points.
    """
    analyzer = StatsAnalyzer(ply_file)
    vertex_elem = analyzer.vertex_elem
    total = vertex_elem.count

    prop_names = [p.name for p in vertex_elem.properties]
    has_rot = all(f"rot_{i}" in prop_names for i in range(4))
    has_scale = all(f"scale_{i}" in prop_names for i in range(3))

    new_header = copy_header_for_partition(analyzer.header, total)
    new_header.comments.append(f"transform={plan.description}")
    t = plan.transform
    matrix_rows = []
    for v in t:
        row = [0, 0, 0]
        row[abs(v) - 1] = -1 if v < 0 else 1
        matrix_rows.append(row)
    new_header.comments.append(f"transform_matrix={matrix_rows}")

    dtype = analyzer._get_struct_dtype()
    is_binary = analyzer.header.format.startswith("binary")

    if is_binary:
        _chunked_transform_binary(
            fpath_in=analyzer.file_path,
            fpath_out=output_path,
            new_header=new_header,
            dtype=dtype,
            total=total,
            header_size=analyzer.header.header_size,
            plan=plan,
            has_rot_props=has_rot,
            has_scale_props=has_scale,
            progress_callback=progress_callback,
        )
    else:
        # ASCII: fall back to per-vertex writing
        ascii_mmap = np.memmap(
            analyzer.file_path,
            dtype=dtype,
            mode="r",
            offset=analyzer.header.header_size,
            shape=total,
        )
        from ..ply.writer import PLYWriter

        with PLYWriter(output_path) as writer:
            writer.write_header(new_header)
            for i in range(total):
                row = ascii_mmap[i]
                data_dict = {}
                for name in prop_names:
                    val = row[name]
                    # Apply transform to x, y, z
                    if name == "x":
                        src = abs(t[0]) - 1
                        sign = -1 if t[0] < 0 else 1
                        val = sign * [row["x"], row["y"], row["z"]][src]
                    elif name == "y":
                        src = abs(t[1]) - 1
                        sign = -1 if t[1] < 0 else 1
                        val = sign * [row["x"], row["y"], row["z"]][src]
                    elif name == "z":
                        src = abs(t[2]) - 1
                        sign = -1 if t[2] < 0 else 1
                        val = sign * [row["x"], row["y"], row["z"]][src]
                    # Apply transform to quaternion imaginary parts
                    elif name == "rot_1" and has_rot:
                        src = abs(t[0]) - 1
                        sign = -1 if t[0] < 0 else 1
                        q_val = sign * [row["rot_1"], row["rot_2"], row["rot_3"]][src]
                        val = -q_val if plan.mirror else q_val
                    elif name == "rot_2" and has_rot:
                        src = abs(t[1]) - 1
                        sign = -1 if t[1] < 0 else 1
                        q_val = sign * [row["rot_1"], row["rot_2"], row["rot_3"]][src]
                        val = -q_val if plan.mirror else q_val
                    elif name == "rot_3" and has_rot:
                        src = abs(t[2]) - 1
                        sign = -1 if t[2] < 0 else 1
                        q_val = sign * [row["rot_1"], row["rot_2"], row["rot_3"]][src]
                        val = -q_val if plan.mirror else q_val
                    # Apply permutation (no sign) to scale
                    elif name == "scale_0" and has_scale:
                        val = [row["scale_0"], row["scale_1"], row["scale_2"]][
                            abs(t[0]) - 1
                        ]
                    elif name == "scale_1" and has_scale:
                        val = [row["scale_0"], row["scale_1"], row["scale_2"]][
                            abs(t[1]) - 1
                        ]
                    elif name == "scale_2" and has_scale:
                        val = [row["scale_0"], row["scale_1"], row["scale_2"]][
                            abs(t[2]) - 1
                        ]
                    data_dict[name] = val
                writer.write_element("vertex", data_dict)
                if progress_callback:
                    progress_callback(i + 1, total)

        del ascii_mmap

    return total
