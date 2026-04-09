"""PLY file header parser"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
import struct


@dataclass
class PLYProperty:
    """Represents a PLY element property"""
    name: str
    data_type: str
    is_list: bool = False
    list_size_type: Optional[str] = None

    # Type mapping for struct
    TYPE_MAP: Dict[str, str] = field(default_factory=lambda: {
        'char': 'b',
        'uchar': 'B',
        'short': 'h',
        'ushort': 'H',
        'int': 'i',
        'uint': 'I',
        'float': 'f',
        'double': 'd',
        'int8': 'b',
        'uint8': 'B',
        'int16': 'h',
        'uint16': 'H',
        'int32': 'i',
        'uint32': 'I',
        'float32': 'f',
        'float64': 'd',
    }, repr=False, compare=False)

    TYPE_SIZE: Dict[str, int] = field(default_factory=lambda: {
        'char': 1,
        'uchar': 1,
        'short': 2,
        'ushort': 2,
        'int': 4,
        'uint': 4,
        'float': 4,
        'double': 8,
        'int8': 1,
        'uint8': 1,
        'int16': 2,
        'uint16': 2,
        'int32': 4,
        'uint32': 4,
        'float32': 4,
        'float64': 8,
    }, repr=False, compare=False)

    def struct_format(self) -> str:
        """Get struct format character"""
        return self.TYPE_MAP[self.data_type]

    def size(self) -> int:
        """Get size in bytes"""
        return self.TYPE_SIZE[self.data_type]


@dataclass
class PLYElementType:
    """Represents a PLY element type (e.g., vertex, face)"""
    name: str
    count: int
    properties: List[PLYProperty] = field(default_factory=list)

    def struct_format(self, endian: str = '<') -> str:
        """Get struct format string for this element"""
        fmt = endian
        for prop in self.properties:
            if prop.is_list:
                raise ValueError("List properties not supported in struct_format")
            fmt += prop.struct_format()
        return fmt

    def size(self) -> int:
        """Get size of one element in bytes"""
        return sum(p.size() for p in self.properties)


@dataclass
class PLYHeader:
    """Represents a complete PLY file header"""
    format: str  # 'ascii', 'binary_little_endian', or 'binary_big_endian'
    version: str
    elements: List[PLYElementType] = field(default_factory=list)
    comments: List[str] = field(default_factory=list)
    obj_info: List[str] = field(default_factory=list)
    header_size: int = 0

    def is_binary(self) -> bool:
        """Check if file is binary format"""
        return self.format.startswith('binary')

    def is_little_endian(self) -> bool:
        """Check if file uses little endian"""
        return self.format == 'binary_little_endian'

    def endian_char(self) -> str:
        """Get struct endian character"""
        return '<' if self.is_little_endian() else '>'

    def get_element(self, name: str) -> Optional[PLYElementType]:
        """Get element by name"""
        for elem in self.elements:
            if elem.name == name:
                return elem
        return None

    @classmethod
    def parse(cls, file_path: str) -> 'PLYHeader':
        """Parse PLY header from file"""
        header = cls(format='', version='1.0')
        header_bytes = []

        with open(file_path, 'rb') as f:
            in_header = True
            current_elem: Optional[PLYElementType] = None

            while in_header:
                # Read line bytes
                line_bytes = b''
                while True:
                    byte = f.read(1)
                    if not byte:
                        break
                    line_bytes += byte
                    if byte == b'\n':
                        break

                if not line_bytes:
                    break

                header_bytes.append(line_bytes)
                line = line_bytes.decode('ascii', errors='ignore').strip()

                if line == 'ply':
                    continue
                elif line == 'end_header':
                    in_header = False
                    break
                elif line.startswith('format '):
                    parts = line.split()
                    header.format = parts[1]
                    header.version = parts[2] if len(parts) > 2 else '1.0'
                elif line.startswith('comment '):
                    header.comments.append(line[8:].strip())
                elif line.startswith('obj_info '):
                    header.obj_info.append(line[9:].strip())
                elif line.startswith('element '):
                    parts = line.split()
                    if current_elem:
                        header.elements.append(current_elem)
                    current_elem = PLYElementType(
                        name=parts[1],
                        count=int(parts[2])
                    )
                elif line.startswith('property '):
                    if current_elem is None:
                        continue
                    parts = line.split()
                    if parts[1] == 'list':
                        # list property: property list size_type type name
                        prop = PLYProperty(
                            name=parts[4],
                            data_type=parts[3],
                            is_list=True,
                            list_size_type=parts[2]
                        )
                    else:
                        # simple property
                        prop = PLYProperty(
                            name=parts[2],
                            data_type=parts[1]
                        )
                    current_elem.properties.append(prop)

            if current_elem:
                header.elements.append(current_elem)

            header.header_size = sum(len(b) for b in header_bytes)

        return header

    def to_string(self) -> str:
        """Convert header back to string format"""
        lines = ['ply']
        lines.append(f'format {self.format} {self.version}')
        for comment in self.comments:
            lines.append(f'comment {comment}')
        for info in self.obj_info:
            lines.append(f'obj_info {info}')
        for elem in self.elements:
            lines.append(f'element {elem.name} {elem.count}')
            for prop in elem.properties:
                if prop.is_list:
                    lines.append(f'property list {prop.list_size_type} {prop.data_type} {prop.name}')
                else:
                    lines.append(f'property {prop.data_type} {prop.name}')
        lines.append('end_header')
        return '\n'.join(lines) + '\n'
