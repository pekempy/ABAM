"""
Low-level byte-order helpers shared by the Xbox 360 texture codec.
"""


def byte_swap_16(data: bytes) -> bytes:
    """Swap every adjacent byte pair (8-in-16 endian swap).

    Xbox 360 texture memory (including BC1/BC3 payloads) is stored as
    byte-swapped 16-bit words -- the reference DLL's swap-mode 0x20001, applied
    uniformly across the whole buffer.
    """
    swapped = bytearray(data)
    swapped[0::2] = data[1::2]
    swapped[1::2] = data[0::2]
    return bytes(swapped)
