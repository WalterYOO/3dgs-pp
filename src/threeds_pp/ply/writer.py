"""PLY file writer"""

import struct
from typing import List, Dict, Any, Optional, Iterator
from pathlib import Path

from .header import PLYHeader, PLYElementType, PLYProperty


class PLYWriter:
    """Write PLY files"""

    def __init__(self, file_path: str, header: Optional[PLYHeader] = None):
        self.file_path = file_path
        self.header = header
        self._file: Optional[Any] = None
        self._written_count: Dict[str, int] = {}

    def open(self):
        """Open file for writing"""
        Path(self.file_path).parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.file_path, 'wb')

    def close(self):
        """Close file"""
        if self._file is not None:
            self._file.close()
            self._file = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def write_header(self, header: PLYHeader):
        """Write header to file"""
        if self._file is None:
            raise RuntimeError("File not open")
        self.header = header
        header_str = header.to_string()
        self._file.write(header_str.encode('ascii'))
        for elem in header.elements:
            self._written_count[elem.name] = 0

    def write_element(self, element_name: str, data: Dict[str, Any]):
        """Write a single element"""
        if self._file is None:
            raise RuntimeError("File not open")
        if self.header is None:
            raise RuntimeError("Header not written")

        elem = self.header.get_element(element_name)
        if elem is None:
            raise ValueError(f"Element '{element_name}' not found in header")

        if self.header.is_binary():
            self._write_element_binary(elem, data)
        else:
            self._write_element_ascii(elem, data)

        self._written_count[element_name] += 1

    def _write_element_binary(self, elem: PLYElementType, data: Dict[str, Any]):
        """Write element in binary format"""
        endian = self.header.endian_char()

        for prop in elem.properties:
            value = data.get(prop.name)
            if value is None:
                raise ValueError(f"Property '{prop.name}' missing for element '{elem.name}'")

            if prop.is_list:
                # Write list size
                size_fmt = endian + PLYProperty.TYPE_MAP[prop.list_size_type]
                self._file.write(struct.pack(size_fmt, len(value)))
                # Write list data
                data_fmt = endian + PLYProperty.TYPE_MAP[prop.data_type] * len(value)
                self._file.write(struct.pack(data_fmt, *value))
            else:
                fmt = endian + prop.struct_format()
                self._file.write(struct.pack(fmt, value))

    def _write_element_ascii(self, elem: PLYElementType, data: Dict[str, Any]):
        """Write element in ASCII format"""
        parts = []
        for prop in elem.properties:
            value = data.get(prop.name)
            if value is None:
                raise ValueError(f"Property '{prop.name}' missing for element '{elem.name}'")

            if prop.is_list:
                parts.append(str(len(value)))
                parts.extend(str(v) for v in value)
            else:
                if prop.data_type in ['float', 'double', 'float32', 'float64']:
                    parts.append(f"{value:.10g}")
                else:
                    parts.append(str(value))

        line = ' '.join(parts) + '\n'
        self._file.write(line.encode('ascii'))

    def write_elements(self, element_name: str, data_list: List[Dict[str, Any]]):
        """Write multiple elements"""
        for data in data_list:
            self.write_element(element_name, data)

    def write_element_iterator(self, element_name: str, iterator: Iterator[Dict[str, Any]],
                               total: Optional[int] = None):
        """Write elements from an iterator"""
        for data in iterator:
            self.write_element(element_name, data)


def create_3dgs_header(vertex_count: int, format: str = 'binary_little_endian') -> PLYHeader:
    """Create a standard 3DGS PLY header"""
    header = PLYHeader(format=format, version='1.0')

    # Create vertex element with all standard 3DGS properties
    vertex = PLYElementType(name='vertex', count=vertex_count)

    # Position
    vertex.properties.append(PLYProperty(name='x', data_type='float'))
    vertex.properties.append(PLYProperty(name='y', data_type='float'))
    vertex.properties.append(PLYProperty(name='z', data_type='float'))

    # Spherical harmonics DC component
    vertex.properties.append(PLYProperty(name='f_dc_0', data_type='float'))
    vertex.properties.append(PLYProperty(name='f_dc_1', data_type='float'))
    vertex.properties.append(PLYProperty(name='f_dc_2', data_type='float'))

    # Spherical harmonics remaining components (45)
    for i in range(45):
        vertex.properties.append(PLYProperty(name=f'f_rest_{i}', data_type='float'))

    # Opacity
    vertex.properties.append(PLYProperty(name='opacity', data_type='float'))

    # Scale
    vertex.properties.append(PLYProperty(name='scale_0', data_type='float'))
    vertex.properties.append(PLYProperty(name='scale_1', data_type='float'))
    vertex.properties.append(PLYProperty(name='scale_2', data_type='float'))

    # Rotation (quaternion)
    vertex.properties.append(PLYProperty(name='rot_0', data_type='float'))
    vertex.properties.append(PLYProperty(name='rot_1', data_type='float'))
    vertex.properties.append(PLYProperty(name='rot_2', data_type='float'))
    vertex.properties.append(PLYProperty(name='rot_3', data_type='float'))

    header.elements.append(vertex)
    return header


def copy_header_for_partition(original_header: PLYHeader, vertex_count: int) -> PLYHeader:
    """Copy header with new vertex count for partitioned output"""
    import copy
    new_header = copy.deepcopy(original_header)
    vertex_elem = new_header.get_element('vertex')
    if vertex_elem:
        vertex_elem.count = vertex_count
    return new_header
