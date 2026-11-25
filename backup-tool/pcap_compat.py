"""Preserve PktMon captures while correcting mislabelled link-layer frames.

Two kinds are corrected on LinkType=Ethernet interfaces, provided every
packet on that interface belongs to native Wi-Fi and/or bare IP (tunnel):
  * native Wi-Fi frames recorded with the Ethernet link type
  * bare IP packets recorded with the Ethernet link type (VPN/tunnel adapters)
"""

from pathlib import Path
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


def _classify_frame(packet: bytes) -> str:
    """Classify a packet captured on an Ethernet-labelled interface."""
    if _is_wifi_data(packet):
        return "wifi"
    if _is_bare_ip(packet):
        return "raw"
    return "other"


def _read_sections(path: Path) -> list[list[tuple[int, str, bytes]]] | None:
    """Parse PCAPNG blocks grouped by section; return None to pass through."""
    sections: list[list[tuple[int, str, bytes]]] = []
    current: list[tuple[int, str, bytes]] | None = None
    endian = "<"
    with path.open("rb") as source:
        while True:
            position = source.tell()
            header = source.read(12)
            if not header:
                break
            if len(header) != 12:
                return None
            if header[:4] == b"\x0a\x0d\x0d\x0a":
                if header[8:12] == b"\x4d\x3c\x2b\x1a":
                    endian = "<"
                elif header[8:12] == b"\x1a\x2b\x3c\x4d":
                    endian = ">"
                else:
                    return None
                current = []
                sections.append(current)
            elif position == 0 or current is None:
                return None  # Includes classic pcap files.
            kind, length = struct.unpack(endian + "II", header[:8])
            if length < 12 or length % 4 or length > 64 * 1024 * 1024:
                return None
            block = header + source.read(length - 12)
            if len(block) != length or struct.unpack(endian + "I", block[-4:])[0] != length:
                return None
            if kind == 1 and length < 20:
                return None
            if kind == 6:
                if length < 32:
                    return None
                captured = struct.unpack(endian + "I", block[20:24])[0]
                if captured > length - 32:
                    return None
            elif kind in (2, 3):
                # Obsolete/simple packet blocks need separate validation.
                return None
            current.append((kind, endian, block))
    return sections


def _process_section(blocks: list[tuple[int, str, bytes]]) -> tuple[list[bytes], bool, bool]:
    """Fix or split eligible Ethernet IDBs whose packets are strictly Wi-Fi and/or bare IP."""
    idbs: list[dict] = []
    epb_meta: dict[int, tuple[int, str]] = {}
    saw_epb_after_idb = False
    idb_after_epb = False

    for b_idx, (kind, endian, block) in enumerate(blocks):
        if kind == 1:
            if saw_epb_after_idb:
                idb_after_epb = True
            linktype, _, snaplen = struct.unpack(endian + "HHI", block[8:16])
            idbs.append({
                "b_idx": b_idx,
                "endian": endian,
                "linktype": linktype,
                "snaplen": snaplen,
                "eligible": linktype == LINKTYPE_ETHERNET,
                "counts": {"wifi": 0, "raw": 0, "other": 0},
            })
        elif kind == 6:
            saw_epb_after_idb = True
            iid, _, _, captured, _ = struct.unpack(endian + "IIIII", block[8:28])
            if iid >= len(idbs):
                continue
            info = idbs[iid]
            if info["eligible"]:
                cls = _classify_frame(block[28:28 + captured])
                info["counts"][cls] += 1
                epb_meta[b_idx] = (iid, cls)

    used_wifi = False
    used_raw = False
    primary_lt: dict[int, int] = {}
    remap_lt: dict[tuple[int, str], int] = {}
    appended_idbs: list[bytes] = []
    next_iid = len(idbs)
    last_idb_bidx = -1

    for iid, info in enumerate(idbs):
        last_idb_bidx = info["b_idx"]
        if not info["eligible"]:
            continue
        counts = info["counts"]
        wifi_n, raw_n, other_n = counts["wifi"], counts["raw"], counts["other"]
        # Match upstream's non-guessing rule: only fix when all packets on this IDB qualify.
        if other_n > 0 or (wifi_n == 0 and raw_n == 0):
            continue

        if wifi_n >= raw_n:
            primary_lt[iid] = LINKTYPE_WIFI
            used_wifi = True
            if raw_n > 0:
                remap_lt[(iid, "raw")] = next_iid
                appended_idbs.append(
                    struct.pack(info["endian"] + "IIHHII", 1, 20, LINKTYPE_RAW, 0, info["snaplen"], 20)
                )
                next_iid += 1
                used_raw = True
        else:
            primary_lt[iid] = LINKTYPE_RAW
            used_raw = True
            if wifi_n > 0:
                remap_lt[(iid, "wifi")] = next_iid
                appended_idbs.append(
                    struct.pack(info["endian"] + "IIHHII", 1, 20, LINKTYPE_WIFI, 0, info["snaplen"], 20)
                )
                next_iid += 1
                used_wifi = True

    if not used_wifi and not used_raw:
        return [b for _, _, b in blocks], False, False

    rebuilt_idb_map: dict[int, bytes] = {}
    for iid, info in enumerate(idbs):
        raw_block = blocks[info["b_idx"]][2]
        if iid in primary_lt and primary_lt[iid] != info["linktype"]:
            buf = bytearray(raw_block)
            struct.pack_into(info["endian"] + "H", buf, 8, primary_lt[iid])
            rebuilt_idb_map[info["b_idx"]] = bytes(buf)
        else:
            rebuilt_idb_map[info["b_idx"]] = raw_block

    out_blocks: list[bytes] = []
    skip_indices: set[int] = set()
    if idb_after_epb and appended_idbs:
        out_blocks.append(blocks[0][2])
        for info in idbs:
            out_blocks.append(rebuilt_idb_map[info["b_idx"]])
        out_blocks.extend(appended_idbs)
        skip_indices = {0} | {info["b_idx"] for info in idbs}

    for b_idx, (kind, endian, block) in enumerate(blocks):
        if b_idx in skip_indices:
            continue
        if b_idx in rebuilt_idb_map:
            out_blocks.append(rebuilt_idb_map[b_idx])
            if b_idx == last_idb_bidx and appended_idbs:
                out_blocks.extend(appended_idbs)
            continue
        if kind == 6 and b_idx in epb_meta:
            orig_iid, cls = epb_meta[b_idx]
            target_iid = remap_lt.get((orig_iid, cls), orig_iid)
            target_lt = (
                LINKTYPE_WIFI if cls == "wifi" else LINKTYPE_RAW
            ) if (orig_iid, cls) in remap_lt else primary_lt.get(orig_iid, LINKTYPE_ETHERNET)
            need_clear_prot = cls == "wifi" and target_lt == LINKTYPE_WIFI and (block[29] & 0x40) != 0
            if target_iid != orig_iid or need_clear_prot:
                buf = bytearray(block)
                if target_iid != orig_iid:
                    struct.pack_into(endian + "I", buf, 8, target_iid)
                if need_clear_prot:
                    buf[29] &= ~0x40
                out_blocks.append(bytes(buf))
                continue
        out_blocks.append(block)

    return out_blocks, used_wifi, used_raw


def prepare_capture(path: Path) -> Path:
    """Correct mislabelled Wi-Fi and bare-IP tunnel frames on LinkType=1 interfaces.

    Other captures pass through. Original bytes are retained; the derived file
    fixes or splits mislabelled LinkType=1 IDBs (Ethernet 1 -> 105 / 101) and clears
    stale protection flags only where a plaintext LLC header has been verified.
    """
    if path.stem.endswith(".link-fixed"):
        return path
    sections = _read_sections(path)
    if not sections:
        return path

    rebuilt_sections: list[bytes] = []
    any_wifi = False
    any_raw = False
    for sec in sections:
        sec_blocks, sec_wifi, sec_raw = _process_section(sec)
        rebuilt_sections.extend(sec_blocks)
        any_wifi |= sec_wifi
        any_raw |= sec_raw

    if not any_wifi and not any_raw:
        return path

    corrected = path.with_name(path.stem + ".link-fixed.pcapng")
    if corrected.is_file() and corrected.stat().st_mtime >= path.stat().st_mtime:
        return corrected
    with NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as target:
        temporary = Path(target.name)
        try:
            for block in rebuilt_sections:
                target.write(block)
        except BaseException:
            target.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(corrected)
    finally:
        temporary.unlink(missing_ok=True)
    kinds = []
    if any_wifi:
        kinds.append("Wi-Fi 帧被标为以太网")
    if any_raw:
        kinds.append("隧道裸 IP 包被标为以太网")
    print(f"[兼容] 检测到{'、'.join(kinds)}，已生成修正副本：{corrected}")
    return corrected
