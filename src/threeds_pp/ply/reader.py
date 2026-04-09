"""Lazy PLY file reader"""

import struct
import os
from typing import List, Dict, Any, Optional, Tuple, Iterator
from dataclasses import dataclass

from .header import PLYHeader, PLYElementType


@dataclass
class ElementData:
    """Data for a single element"""
    properties: Dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.properties[key]

    def __getattr__(self, key: str) -> Any:
        if key in self.properties:
            return self.properties[key]
        raise AttributeError(f"'ElementData' object has no attribute '{key}'")

    def get(self, key: str, default: Any = None) -> Any:
        return self.properties.get(key, default)


class LazyPLYReader:
    """
    Lazy-loading PLY file reader.
    Only loads data when requested, making it suitable for large files.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.header = PLYHeader.parse(file_path)
        self._file: Optional[Any] = None
        self._element_offsets: Dict[str, int] = {}
        self._calculate_offsets()

    def _calculate_offsets(self):
        """Calculate byte offsets for each element type"""
        offset = self.header.header_size
        for elem in self.header.elements:
            self._element_offsets[elem.name] = offset
            if elem.properties and all(not p.is_list for p in elem.properties):
                offset += elem.count * elem.size()
            else:
                # For list properties or unknown sizes, we can't pre-calculate
                # Just set to None and we'll scan when needed
                pass

    def open(self):
        """Open the file for reading"""
        if self._file is None:
            self._file = open(self.file_path, 'rb')

    def close(self):
        """Close the file"""
        if self._file is not None:
            self._file.close()
            self._file = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_element_count(self, element_name: str = 'vertex') -> int:
        """Get the number of elements of a given type"""
        elem = self.header.get_element(element_name)
        return elem.count if elem else 0

    def _read_element_binary(self, elem: PLYElementType, index: int) -> ElementData:
        """Read a single element from binary file"""
        if self._file is None:
            raise RuntimeError("File not open. Call open() first or use 'with' statement.")

        if elem.name in self._element_offsets:
            offset = self._element_offsets[elem.name] + index * elem.size()
            self._file.seek(offset)
        else:
            # Need to scan from start of element
            self._file.seek(self._element_offsets[elem.name])
            for _ in range(index):
                self._skip_element(elem)

        # Read the element
        endian = self.header.endian_char()
        props = {}

        for prop in elem.properties:
            if prop.is_list:
                # Read list size
                size_fmt = endian + PLYProperty.TYPE_MAP[prop.list_size_type]
                size = struct.unpack(size_fmt, self._file.read(struct.calcsize(size_fmt)))[0]
                # Read list data
                data_fmt = endian + PLYProperty.TYPE_MAP[prop.data_type] * size
                data = struct.unpack(data_fmt, self._file.read(struct.calcsize(data_fmt)))
                props[prop.name] = list(data)
            else:
                fmt = endian + prop.struct_format()
                value = struct.unpack(fmt, self._file.read(struct.calcsize(fmt)))[0]
                props[prop.name] = value

        return ElementData(props)

    def _skip_element(self, elem: PLYElementType):
        """Skip over one element"""
        for prop in elem.properties:
            if prop.is_list:
                size_fmt = self.header.endian_char() + PLYProperty.TYPE_MAP[prop.list_size_type]
                size = struct.unpack(size_fmt, self._file.read(struct.calcsize(size_fmt)))[0]
                data_size = size * PLYProperty.TYPE_SIZE[prop.data_type]
                self._file.read(data_size)
            else:
                self._file.read(prop.size())

    def _read_element_ascii(self, elem: PLYElementType, index: int) -> ElementData:
        """Read a single element from ASCII file"""
        if self._file is None:
            raise RuntimeError("File not open. Call open() first or use 'with' statement.")

        # Seek to header end
        self._file.seek(self.header.header_size)

        # Skip elements before the one we want
        for current_elem in self.header.elements:
            if current_elem.name == elem.name:
                break
            for _ in range(current_elem.count):
                self._file.readline()

        # Skip to the desired index
        for _ in range(index):
            self._file.readline()

        # Read the line
        line = self._file.readline().decode('ascii').strip()
        parts = line.split()

        props = {}
        part_idx = 0

        for prop in elem.properties:
            if prop.is_list:
                size = int(parts[part_idx])
                part_idx += 1
                data = []
                for _ in range(size):
                    if prop.data_type in ['float', 'double', 'float32', 'float64']:
                        data.append(float(parts[part_idx]))
                    else:
                        data.append(int(parts[part_idx]))
                    part_idx += 1
                props[prop.name] = data
            else:
                if prop.data_type in ['float', 'double', 'float32', 'float64']:
                    props[prop.name] = float(parts[part_idx])
                else:
                    props[prop.name] = int(parts[part_idx])
                part_idx += 1

        return ElementData(props)

    def get_element(self, index: int, element_name: str = 'vertex') -> ElementData:
        """Get a single element by index"""
        elem = self.header.get_element(element_name)
        if elem is None:
            raise ValueError(f"Element '{element_name}' not found")
        if index < 0 or index >= elem.count:
            raise IndexError(f"Index {index} out of range for element '{element_name}' (count: {elem.count})")

        if self.header.is_binary():
            return self._read_element_binary(elem, index)
        else:
            return self._read_element_ascii(elem, index)

    def iter_elements(self, element_name: str = 'vertex',
                      start: int = 0, end: Optional[int] = None) -> Iterator[ElementData]:
        """
        Iterate over elements in a range.

        Args:
            element_name: Name of element to iterate
            start: Start index (inclusive)
            end: End index (exclusive), None means until end
        """
        elem = self.header.get_element(element_name)
        if elem is None:
            raise ValueError(f"Element '{element_name}' not found")

        if end is None:
            end = elem.count

        start = max(0, start)
        end = min(elem.count, end)

        for i in range(start, end):
            yield self.get_element(i, element_name)

    def get_property_names(self, element_name: str = 'vertex') -> List[str]:
        """Get list of property names for an element"""
        elem = self.header.get_element(element_name)
        if elem is None:
            return []
        return [p.name for p in elem.properties]

    def get_bounds(self, element_name: str = 'vertex',
                   coord_props: Tuple[str, str, str] = ('x', 'y', 'z')) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
        """
        Calculate bounding box of point cloud.

        Returns:
            ((min_x, min_y, min_z), (max_x, max_y, max_z))
        """
        elem = self.header.get_element(element_name)
        if elem is None:
            raise ValueError(f"Element '{element_name}' not found")

        # Check that coordinate properties exist
        prop_names = self.get_property_names(element_name)
        for coord in coord_props:
            if coord not in prop_names:
                raise ValueError(f"Coordinate property '{coord}' not found")

        min_coords = [float('inf')] * 3
        max_coords = [float('-inf')] * 3

        # For large files, we sample to estimate bounds
        # If file is small (< 1M points), read all
        sample_step = max(1, elem.count // 100000) if elem.count > 1000000 else 1

        for i in range(0, elem.count, sample_step):
            elem_data = self.get_element(i, element_name)
            coords = [elem_data[coord_props[0]], elem_data[coord_props[1]], elem_data[coord_props[2]]]
            for j in range(3):
                if coords[j] < min_coords[j]:
                    min_coords[j] = coords[j]
                if coords[j] > max_coords[j]:
                    max_coords[j] = coords[j]

        return (tuple(min_coords), tuple(max_coords))
