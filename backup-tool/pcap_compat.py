"""Preserve PktMon captures while correcting mislabelled link-layer frames.

Two kinds are corrected, each only when every packet on that interface agrees:
  * native Wi-Fi frames recorded with the Ethernet link type
  * bare IP packets recorded with the Ethernet link type (VPN/tunnel adapters)
"""

from pathlib import Path
import shutil
import struct
from tempfile import NamedTemporaryFile

LINKTYPE_ETHERNET = 1
LINKTYPE_RAW = 101
LINKTYPE_WIFI = 105


def _is_ipv4(packet: bytes) -> bool:
    """Bare IPv4 header: version 4, a sane IHL and a total length that fits."""
    if len(packet) < 20:
        return False
    if packet[0] >> 4 != 4:
        return False
    header_length = (packet[0] & 0x0F) * 4
    if header_length < 20 or header_length > len(packet):
        return False
    total = int.from_bytes(packet[2:4], "big")
    return header_length <= total <= len(packet)


def _is_ipv6(packet: bytes) -> bool:
    """Bare IPv6 header: version 6 and a payload length that fits the frame."""
    if len(packet) < 40:
        return False
    if packet[0] >> 4 != 6:
        return False
    payload = int.from_bytes(packet[4:6], "big")
    return payload == 0 or 40 + payload <= len(packet)


def _is_bare_ip(packet: bytes) -> bool:
    return _is_ipv4(packet) or _is_ipv6(packet)


def _is_wifi_data(packet: bytes) -> bool:
    if len(packet) < 32:
        return False
    control = int.from_bytes(packet[:2], "little")
    # PktMon may retain the protected flag after the driver decrypts the frame.
    # Require a plaintext LLC header below. Account for address 4 and QoS.
    if control & 0x000F != 0x0008:
        return False
    offset = 24 + (6 if control & 0x0300 == 0x0300 else 0)
    if control & 0x0080:
        offset += 2 + (4 if control & 0x8000 else 0)
    return (
        packet[offset:offset + 6] == b"\xaa\xaa\x03\x00\x00\x00"
        and packet[offset + 6:offset + 8] in (b"\x08\x00", b"\x86\xdd", b"\x08\x06")
    )


def prepare_capture(path: Path) -> Path:
    """Correct only Ethernet interfaces whose every packet is native Wi-Fi.

    Other captures pass through. Original bytes are retained; the derived file
    changes the link type (Ethernet 1 -> IEEE 802.11 105) and clears stale
    protection flags only where a plaintext LLC header has been verified.
    """
    interfaces = []
    section = []
    endian = "<"
    with path.open("rb") as source:
        while True:
            position = source.tell()
            header = source.read(12)
            if not header:
                break
            if len(header) != 12:
                return path
            if header[:4] == b"\x0a\x0d\x0d\x0a":
                if header[8:12] == b"\x4d\x3c\x2b\x1a":
                    endian = "<"
                elif header[8:12] == b"\x1a\x2b\x3c\x4d":
                    endian = ">"
                else:
                    return path
                section = []
            elif position == 0:
                return path  # Includes classic pcap files.
            kind, length = struct.unpack(endian + "II", header[:8])
            if length < 12 or length % 4 or length > 64 * 1024 * 1024:
                return path
            remainder = source.read(length - 12)
            block = header + remainder
            if len(block) != length or struct.unpack(endian + "I", block[-4:])[0] != length:
                return path
            if kind == 1:
                if length < 20:
                    return path
                interface = dict(offset=position + 8, endian=endian, count=0, flags=[],
                                 eligible=struct.unpack(endian + "H", block[8:10])[0] == 1,
                                 wifi=True, raw=True)
                section.append(interface)
                interfaces.append(interface)
            elif kind == 6:
                if length < 32:
                    return path
                index, _, _, captured, _ = struct.unpack(endian + "IIIII", block[8:28])
                if index >= len(section) or captured > length - 32:
                    return path
                interface = section[index]
                interface["count"] += 1
                packet = block[28:28 + captured]
                interface["wifi"] &= _is_wifi_data(packet)
                interface["raw"] &= _is_bare_ip(packet)
                if interface["wifi"] and packet[1] & 0x40:
                    interface["flags"].append((position + 29, packet[1] & ~0x40))
            elif kind in (2, 3):
                # Obsolete/simple packet blocks need separate validation.
                return path

    fixes = [item for item in interfaces if item["count"] and (item["wifi"] or item["raw"])]
    if not fixes:
        return path
    # Re-deriving a file that was already corrected would append the suffix again
    # (capture.link-fixed.link-fixed...). An already-corrected file is returned as is.
    if path.stem.endswith(".link-fixed"):
        return path
    corrected = path.with_name(path.stem + ".link-fixed.pcapng")
    if corrected.is_file() and corrected.stat().st_mtime >= path.stat().st_mtime:
        return corrected
    with NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as target:
        temporary = Path(target.name)
        try:
            with path.open("rb") as source:
                shutil.copyfileobj(source, target)
            for item in fixes:
                target.seek(item["offset"])
                target.write(struct.pack(item["endian"] + "H",
                                         LINKTYPE_WIFI if item["wifi"] else LINKTYPE_RAW))
                for offset, flag in item["flags"]:
                    target.seek(offset)
                    target.write(bytes([flag]))
        except BaseException:
            target.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(corrected)
    finally:
        temporary.unlink(missing_ok=True)
    kinds = []
    if any(item["wifi"] for item in fixes):
        kinds.append("Wi-Fi 帧被标为以太网")
    if any(item["raw"] and not item["wifi"] for item in fixes):
        kinds.append("隧道裸 IP 包被标为以太网")
    print(f"[兼容] 检测到{'、'.join(kinds)}，已生成修正副本：{corrected}")
    return corrected
