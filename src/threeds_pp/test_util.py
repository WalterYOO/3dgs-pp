"""Test utility - generate sample 3DGS PLY files"""

import random
import math
from pathlib import Path
from typing import Tuple

from .ply.writer import PLYWriter, create_3dgs_header


def generate_sample_ply(output_path: str, num_points: int = 1000,
                        bounds: Tuple[Tuple[float, float, float], Tuple[float, float, float]] = None):
    """
    Generate a sample 3DGS PLY file for testing.

    Args:
        output_path: Output file path
        num_points: Number of points to generate
        bounds: ((min_x, min_y, min_z), (max_x, max_y, max_z))
    """
    if bounds is None:
        bounds = ((-5.0, -5.0, -5.0), (5.0, 5.0, 5.0))

    (min_x, min_y, min_z), (max_x, max_y, max_z) = bounds

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    header = create_3dgs_header(num_points, format='binary_little_endian')

    with PLYWriter(output_path) as writer:
        writer.write_header(header)

        for i in range(num_points):
            # Generate point in a spiral pattern for interesting distribution
            t = i / num_points * 20 * math.pi
            r = i / num_points * (max_x - min_x) / 2
            x = r * math.cos(t) + (min_x + max_x) / 2
            y = r * math.sin(t) + (min_y + max_y) / 2
            z = (i / num_points) * (max_z - min_z) + min_z

            # Generate random SH coefficients
            f_dc = [random.random() * 0.5 + 0.2 for _ in range(3)]
            f_rest = [random.random() * 0.1 - 0.05 for _ in range(45)]

            # Opacity
            opacity = random.random() * 0.8 + 0.2

            # Scale
            scale = [random.random() * 0.01 + 0.001 for _ in range(3)]

            # Rotation (normalized quaternion)
            rot = [random.random() * 2 - 1 for _ in range(4)]
            rot_len = math.sqrt(sum(r * r for r in rot))
            rot = [r / rot_len for r in rot]

            data = {
                'x': x, 'y': y, 'z': z,
                'f_dc_0': f_dc[0], 'f_dc_1': f_dc[1], 'f_dc_2': f_dc[2],
                **{f'f_rest_{i}': v for i, v in enumerate(f_rest)},
                'opacity': opacity,
                'scale_0': scale[0], 'scale_1': scale[1], 'scale_2': scale[2],
                'rot_0': rot[0], 'rot_1': rot[1], 'rot_2': rot[2], 'rot_3': rot[3],
            }

            writer.write_element('vertex', data)

    return output_path


if __name__ == '__main__':
    import sys
    out_file = sys.argv[1] if len(sys.argv) > 1 else 'test_data/sample.ply'
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 10000
    print(f"Generating {count} points to {out_file}...")
    generate_sample_ply(out_file, count)
    print("Done!")
