"""
Aurora Asset File Binary Parser & Writer
Handles reading, creating, and modifying Aurora .asset (RXEA) and legacy FSD .assets files.
"""

import struct
from enum import IntEnum
from typing import Dict, List, Optional, Tuple

class AssetType(IntEnum):
    ICON = 0
    BANNER = 1
    BOXART = 2
    SLOT = 3
    BACKGROUND = 4
    SCREENSHOT_START = 5
    SCREENSHOT_1 = 5
    SCREENSHOT_2 = 6
    SCREENSHOT_3 = 7
    SCREENSHOT_4 = 8
    SCREENSHOT_5 = 9
    SCREENSHOT_6 = 10
    SCREENSHOT_7 = 11
    SCREENSHOT_8 = 12
    SCREENSHOT_9 = 13
    SCREENSHOT_10 = 14
    SCREENSHOT_11 = 15
    SCREENSHOT_12 = 16
    SCREENSHOT_13 = 17
    SCREENSHOT_14 = 18
    SCREENSHOT_15 = 19
    SCREENSHOT_16 = 20
    SCREENSHOT_17 = 21
    SCREENSHOT_18 = 22
    SCREENSHOT_19 = 23
    SCREENSHOT_20 = 24
    SCREENSHOT_END = 24
    MAX_ENTRIES = 25

MAGIC_RXEA = 0x52584541  # 'RXEA' in Big-Endian
HEADER_SIZE = 20  # 12 header + 8 entry table meta
ENTRY_SIZE = 64   # 12 offset/size/ext + 52 texture header
TOTAL_ENTRIES = 26
ENTRY_TABLE_SIZE = TOTAL_ENTRIES * ENTRY_SIZE  # 1664 bytes
HEADER_TABLE_SIZE = HEADER_SIZE + ENTRY_TABLE_SIZE  # 1684 bytes
ALIGNMENT = 2048

class AssetEntry:
    def __init__(self, offset: int = 0, size: int = 0, ext_info: int = 0,
                 texture_header: Optional[bytes] = None, video_data: Optional[bytes] = None):
        self.offset = offset
        self.size = size
        self.ext_info = ext_info
        self.texture_header = texture_header if texture_header and len(texture_header) == 52 else bytes(52)
        self.video_data = video_data if video_data else b""
        self.image_bytes: Optional[bytes] = None  # Decoded RGBA image bytes
        self.width: int = 0
        self.height: int = 0

class AuroraAssetFile:
    """Parser and generator for Aurora .asset files."""

    def __init__(self, raw_bytes: Optional[bytes] = None):
        self.magic = MAGIC_RXEA
        self.version = 1
        self.data_size = 0
        self.flags = 0
        self.screenshot_count = 0
        self.entries: List[AssetEntry] = [AssetEntry() for _ in range(TOTAL_ENTRIES)]

        if raw_bytes:
            self._parse(raw_bytes)

    def _parse(self, raw_bytes: bytes):
        if len(raw_bytes) < ALIGNMENT:
            raise ValueError("Invalid asset file size! File is too small.")

        # Read Header (Big Endian)
        magic, version, data_size = struct.unpack(">III", raw_bytes[0:12])
        if magic != MAGIC_RXEA:
            raise ValueError(f"Invalid magic: {hex(magic)}, expected {hex(MAGIC_RXEA)}")
        if version != 1:
            raise ValueError(f"Unsupported asset version: {version}")

        self.magic = magic
        self.version = version
        self.data_size = data_size

        # Read Entry Table Metadata
        self.flags, self.screenshot_count = struct.unpack(">II", raw_bytes[12:20])

        # Read 26 Entries
        offset_table = 20
        for i in range(TOTAL_ENTRIES):
            entry_bytes = raw_bytes[offset_table : offset_table + ENTRY_SIZE]
            off, size, ext = struct.unpack(">III", entry_bytes[0:12])
            tex_header = entry_bytes[12:64]
            self.entries[i].offset = off
            self.entries[i].size = size
            self.entries[i].ext_info = ext
            self.entries[i].texture_header = tex_header
            offset_table += ENTRY_SIZE

        # Calculate Data Offset (aligned to 2048 bytes)
        data_offset = HEADER_TABLE_SIZE + (ALIGNMENT - (HEADER_TABLE_SIZE % ALIGNMENT))

        # Extract Video/Texture payloads
        curr_offset = data_offset
        for i in range(TOTAL_ENTRIES):
            entry = self.entries[i]
            if entry.size > 0:
                entry.video_data = raw_bytes[curr_offset : curr_offset + entry.size]
                curr_offset += entry.size

    def pack(self) -> bytes:
        """Serializes the Aurora asset back into binary bytes."""
        payload = bytearray()
        offset = 0
        self.data_size = 0
        self.flags = 0
        self.screenshot_count = 0

        # Calculate offsets and size
        for i, entry in enumerate(self.entries):
            if entry.video_data and len(entry.video_data) > 0:
                entry.size = len(entry.video_data)
                entry.offset = offset
                offset += entry.size
                self.data_size += entry.size
                self.flags |= (1 << i)
                if AssetType.SCREENSHOT_START <= i <= AssetType.SCREENSHOT_END:
                    self.screenshot_count += 1
            else:
                entry.size = 0
                entry.offset = 0

        # Header bytes
        header_bytes = struct.pack(">III", self.magic, self.version, self.data_size)
        table_meta = struct.pack(">II", self.flags, self.screenshot_count)

        entries_bytes = bytearray()
        for entry in self.entries:
            entries_bytes.extend(struct.pack(">III", entry.offset, entry.size, entry.ext_info))
            entries_bytes.extend(entry.texture_header[:52].ljust(52, b"\x00"))

        header_and_table = header_bytes + table_meta + entries_bytes
        padding_size = ALIGNMENT - (len(header_and_table) % ALIGNMENT)
        if padding_size == ALIGNMENT:
            padding_size = 0
        padding = b"\x00" * padding_size

        payload_bytes = bytearray()
        for entry in self.entries:
            if entry.size > 0:
                payload_bytes.extend(entry.video_data)

        return bytes(header_and_table + padding + payload_bytes)

    def set_entry_data(self, asset_type: int, texture_header: bytes, video_data: bytes, width: int = 0, height: int = 0):
        """Sets texture header and video payload for a given entry index."""
        if 0 <= asset_type < TOTAL_ENTRIES:
            entry = self.entries[asset_type]
            entry.texture_header = texture_header[:52].ljust(52, b"\x00")
            entry.video_data = video_data
            entry.size = len(video_data)
            entry.width = width
            entry.height = height

    def remove_entry(self, asset_type: int):
        """Clears an entry."""
        if 0 <= asset_type < TOTAL_ENTRIES:
            self.entries[asset_type] = AssetEntry()

    def get_summary(self) -> Dict:
        """Returns JSON-serializable summary of stored assets."""
        return {
            "has_icon": self.entries[AssetType.ICON].size > 0,
            "has_banner": self.entries[AssetType.BANNER].size > 0,
            "has_boxart": self.entries[AssetType.BOXART].size > 0,
            "has_background": self.entries[AssetType.BACKGROUND].size > 0,
            "screenshot_count": self.screenshot_count,
            "data_size": self.data_size,
        }
