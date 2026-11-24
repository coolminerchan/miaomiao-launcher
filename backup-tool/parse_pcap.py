#!/usr/bin/env python3
"""
OverField (开放空间) 官服 TCP 抓包无损解包与玩家数据完整性核对工具。

功能：
1. 调用 tshark 对 pcapng 中的所有 TCP 流进行精确重组（自动处理乱序、重传与分片），
   按双向独立字节流（c2s / s2c）拆包。
2. 解析游戏协议帧：[2字节 BigEndian header_len][PacketHead][Body (flag==1 时 Raw Snappy 解压)]。
3. 合并加载 Lolo/protocol/cmdid.csv 与 of-ps/network/msg_id.py 的消息名映射。
4. 双份落盘：
   - raw/*.bin  : 导出的 Protobuf 二进制。
   - json/*.json: 基于 net_pb2 解码出的可读 JSON。
   - 已知登录请求跳过，登录响应去除日志令牌。
5. 生成 summary.json 与终端核对清单，明确提示哪些关键玩家数据包已抓到 / 尚未抓到。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import struct
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cramjam
from google.protobuf import json_format

SCRIPT_DIR = Path(__file__).resolve().parent
PROTO_DIR = SCRIPT_DIR / "proto_gen"
TSHARK = os.environ.get("OVERFIELD_TSHARK") or str(SCRIPT_DIR / "tools" / "tshark" / "tshark.exe")
sys.path.insert(0, str(PROTO_DIR))

import net_pb2  # type: ignore  # noqa: E402

HEADER_STRUCT = struct.Struct(">H")
GAME_PORTS = {"11001", "11002", "11003", "11004", "21001", "21002"}
LOGIN_REQUEST_IDS = {1001, 1003, 2201}

# 关键玩家数据核对项：(显示名, 匹配的消息名关键字列表)
CHECKLIST_GROUPS: List[Tuple[str, List[str]]] = [
    ("登录响应 (UID/基础信息)", ["PlayerLoginRsp"]),
    ("主数据 (等级/角色/任务/外观)", ["PlayerMainDataRsp"]),
    ("背包与物品推送", ["PackNotice", "GetAllCharacterEquipRsp"]),
    ("武器与护甲", ["GetWeaponRsp", "GetArmorRsp"]),
    ("宠物本体列表", ["GetPetRsp"]),
    ("花园信息", ["GetGardenInfoRsp"]),
    ("邮件列表", ["GetMailsRsp"]),
    ("抽卡记录/卡池", ["GachaRecordRsp", "GachaListRsp"]),
    ("成就与图鉴", ["GetAchieveGroupListRsp", "ManualListRsp", "GetCharacterAchievementListRsp"]),
    ("探索与收集 (月亮/收藏/宝箱)", ["GetCollectItemIdsRsp", "GetCollectMoonInfoRsp", "ExploreInitRsp"]),
    ("好友列表", ["FriendRsp", "FriendListRsp"]),
    ("档案/头像/海报/生活技能", ["GetArchiveInfoRsp", "UnlockHeadListRsp", "GetPosterRsp", "GetLifeInfoRsp"]),
]


def load_cmd_map() -> Dict[int, str]:
    """合并加载 Lolo 的 cmdid.csv 和 of-ps 的 msg_id.py。"""
    id_to_name: Dict[int, str] = {}

    ofps_msg_id = PROTO_DIR / "msg_id.txt"
    if ofps_msg_id.exists():
        pattern = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=\s*(\d+)\s*$")
        for line in ofps_msg_id.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = pattern.match(line)
            if m:
                id_to_name[int(m.group(2))] = m.group(1)

    lolo_csv = PROTO_DIR / "cmdid.csv"
    if lolo_csv.exists():
        with lolo_csv.open("r", encoding="utf-8", errors="ignore", newline="") as f:
            for row in csv.reader(f):
                if len(row) >= 2 and row[1].strip().isdigit():
                    id_to_name[int(row[1].strip())] = row[0].strip()

    return id_to_name


def list_tcp_streams(pcap_path: Path) -> List[int]:
    """使用 tshark 列出 pcapng 中所有的 TCP stream ID。"""
    cmd = [TSHARK, "-n", "-r", str(pcap_path), "-T", "fields", "-e", "tcp.stream", "-Y", "tcp"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"tshark 读取 pcap 失败: {res.stderr.strip()}")
    streams = sorted({int(x.strip()) for x in res.stdout.splitlines() if x.strip().isdigit()})
    return streams


def extract_tcp_stream_directions(pcap_path: Path, stream_id: int) -> Tuple[str, str, bytes, bytes]:
    """
    通过 tshark -z follow,tcp,raw,<id> 精确提取重组后的双向字节流。
    返回 (node0_addr, node1_addr, node0_to_node1_bytes, node1_to_node0_bytes)。
    """
    cmd = [TSHARK, "-n", "-r", str(pcap_path), "-q", "-z", f"follow,tcp,raw,{stream_id}"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"tshark 重组流 {stream_id} 失败: {res.stderr.strip()}")

    node0 = ""
    node1 = ""
    dir0_chunks: List[bytes] = []
    dir1_chunks: List[bytes] = []

    in_body = False
    for raw_line in res.stdout.splitlines():
        line = raw_line.rstrip("\r\n")
        if line.startswith("Node 0: "):
            node0 = line[len("Node 0: "):].strip()
            continue
        if line.startswith("Node 1: "):
            node1 = line[len("Node 1: "):].strip()
            in_body = True
            continue
        if not in_body:
            continue
        if line.startswith("===="):
            break
        if not line:
            continue
        # tshark follow,tcp,raw 约定：无前导制表符为 Node0 -> Node1，带前导 '\t' 为 Node1 -> Node0
        is_from_node1 = line.startswith("\t")
        hex_str = line.strip()
        if not re.fullmatch(r"[0-9a-fA-F]+", hex_str) or len(hex_str) % 2 != 0:
            continue
        chunk = bytes.fromhex(hex_str)
        if is_from_node1:
            dir1_chunks.append(chunk)
        else:
            dir0_chunks.append(chunk)

    return node0, node1, b"".join(dir0_chunks), b"".join(dir1_chunks)


def parse_game_stream(data: bytes) -> Tuple[List[dict], int]:
    """
    解析单方向的游戏 TCP 字节流。
    返回 (packet_list, remaining_bytes_count)。
    """
    packets: List[dict] = []
    pos = 0
    total = len(data)

    while pos + 2 <= total:
        head_len = HEADER_STRUCT.unpack_from(data, pos)[0]
        if head_len == 0 or head_len > 4096:
            break
        hend = pos + 2 + head_len
        if hend > total:
            break

        head = net_pb2.PacketHead()
        try:
            head.ParseFromString(data[pos + 2 : hend])
        except Exception:
            break

        if head.msg_id <= 0 or head.body_len > 32 * 1024 * 1024:
            break

        pend = hend + head.body_len
        if pend > total:
            break

        raw_body = data[hend:pend]
        decompress_err: Optional[str] = None
        body = raw_body
        if head.flag == 1:
            try:
                body = bytes(cramjam.snappy.decompress_raw(raw_body))
            except Exception as e:
                decompress_err = str(e)

        packets.append(
            {
                "msg_id": int(head.msg_id),
                "seq_id": int(head.seq_id),
                "packet_id": int(head.packet_id),
                "flag": int(head.flag),
                "body_len": int(head.body_len),
                "body": body,
                "decompress_err": decompress_err,
            }
        )
        pos = pend

    return packets, total - pos


def decode_proto_body(msg_name: str, body: bytes) -> Tuple[Optional[dict], Optional[str]]:
    """尝试使用 net_pb2 解码消息体为 dict。"""
    msg_cls = getattr(net_pb2, msg_name, None)
    if msg_cls is None:
        return None, "proto_class_not_found"
    try:
        msg = msg_cls()
        msg.ParseFromString(body)
        data_dict = json_format.MessageToDict(
            msg, preserving_proto_field_name=True, always_print_fields_with_no_presence=False
        )
        return data_dict, None
    except Exception as e:
        return None, str(e)


def analyze_pcap(pcap_path: Path, out_dir: Path) -> None:
    cmd_map = load_cmd_map()
    raw_dir = out_dir / "raw"
    json_dir = out_dir / "json"
    raw_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)

    streams = list_tcp_streams(pcap_path)
    print(f"[信息] 发现 {len(streams)} 条 TCP 流，开始精确重组与解包...")

    global_seq = 0
    omitted_login_requests = 0
    sanitized_login_responses = 0
    msg_names_seen: Counter = Counter()
    unknown_ids: Counter = Counter()
    decode_errors: List[dict] = []
    player_highlights: dict = {}
    stream_summaries: List[dict] = []

    for sid in streams:
        node0, node1, b01, b10 = extract_tcp_stream_directions(pcap_path, sid)
        if not b01 and not b10:
            continue

        # 判断哪个方向是 s2c（通常服务端端口是 11003 / 21001 等，或非内网 IP）
        p0 = node0.rsplit(":", 1)[-1] if ":" in node0 else ""
        p1 = node1.rsplit(":", 1)[-1] if ":" in node1 else ""
        if p1 in GAME_PORTS:
            directions = [("c2s", b01), ("s2c", b10)]
        elif p0 in GAME_PORTS:
            directions = [("s2c", b01), ("c2s", b10)]
        else:
            directions = [("d0to1", b01), ("d1to0", b10)]

        stream_pkt_total = 0
        for dir_label, payload in directions:
            if not payload:
                continue
            pkts, _ = parse_game_stream(payload)
            if not pkts:
                continue
            stream_pkt_total += len(pkts)

            for pkt in pkts:
                global_seq += 1
                msg_id = pkt["msg_id"]
                msg_name = cmd_map.get(msg_id, f"Unknown_{msg_id}")
                msg_names_seen[msg_name] += 1
                if msg_id in LOGIN_REQUEST_IDS:
                    omitted_login_requests += 1
                    continue
                if msg_id not in cmd_map:
                    unknown_ids[msg_id] += 1

                safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", msg_name)
                stem = f"{global_seq:05d}_s{sid}_{dir_label}_{msg_id}_{safe_name}"

                body = pkt["body"]
                if pkt["decompress_err"]:
                    decode_errors.append({"seq": global_seq, "msg": msg_name, "err": pkt["decompress_err"]})
                    if msg_id != 1004:
                        (raw_dir / f"{stem}.bin").write_bytes(body)
                    continue

                if msg_id == 1004:
                    try:
                        login = net_pb2.PlayerLoginRsp.FromString(body)
                    except Exception as exc:
                        decode_errors.append({"seq": global_seq, "msg": msg_name, "err": str(exc)})
                        continue
                    if login.client_log_server_token:
                        login.ClearField("client_log_server_token")
                        body = login.SerializeToString()
                        sanitized_login_responses += 1

                (raw_dir / f"{stem}.bin").write_bytes(body)
                decoded, err = decode_proto_body(msg_name, body)
                if decoded is not None:
                    (json_dir / f"{stem}.json").write_text(
                        json.dumps(decoded, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    # 提取核心玩家摘要
                    if msg_name == "PlayerMainDataRsp":
                        player_highlights["player_id"] = decoded.get("player_id")
                        player_highlights["player_name"] = decoded.get("player_name")
                        player_highlights["level"] = decoded.get("level")
                        player_highlights["world_level"] = decoded.get("world_level")
                        player_highlights["character_count"] = len(decoded.get("characters", []))
                        qd = decoded.get("quest_detail", {})
                        player_highlights["quest_count"] = len(qd.get("quests", []))
                        player_highlights["chapter_count"] = len(qd.get("chapters", []))
                    elif msg_name == "PackNotice":
                        items = decoded.get("items", []) or decoded.get("item_details", [])
                        player_highlights["pack_notice_count"] = player_highlights.get("pack_notice_count", 0) + 1
                        player_highlights["pack_items_seen"] = player_highlights.get("pack_items_seen", 0) + len(items)
                else:
                    decode_errors.append({"seq": global_seq, "msg_id": msg_id, "msg": msg_name, "err": err})

        if stream_pkt_total > 0:
            stream_summaries.append(
                {"stream_id": sid, "node0": node0, "node1": node1, "packets": stream_pkt_total}
            )

    summary = {
        "pcap_file": str(pcap_path),
        "total_packets": global_seq,
        "game_streams": stream_summaries,
        "player_highlights": player_highlights,
        "message_counts": dict(msg_names_seen.most_common()),
        "unknown_msg_ids": dict(unknown_ids),
        "decode_fallback_count": len(decode_errors),
        "omitted_login_requests": omitted_login_requests,
        "sanitized_login_responses": sanitized_login_responses,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n" + "=" * 60)
    print(f"解包完成！共解析出 {global_seq} 个游戏协议包")
    print(f"输出目录: {out_dir}")
    print("=" * 60)

    if player_highlights:
        print("\n【核心账号信息已捕获】")
        for k, v in player_highlights.items():
            print(f"  - {k}: {v}")
    else:
        print("\n[注意] 尚未抓到 PlayerMainDataRsp (1006)！请确认抓包期间是否重新登录了游戏。")

    if global_seq == 0:
        print("[注意] 未识别到游戏协议包。请确认在抓包开始后重新登录并进入官服场景。")

    print("\n【关键玩家数据核对清单】")
    for label, targets in CHECKLIST_GROUPS:
        hit = {t: msg_names_seen[t] for t in targets if msg_names_seen[t] > 0}
        if hit:
            detail = ", ".join(f"{k} x{v}" for k, v in hit.items())
            print(f"  [OK] {label}: {detail}")
        else:
            print(f"  [--] {label}: 未捕获（可进入对应界面触发）")

    if unknown_ids:
        print(f"\n[提示] 发现 {len(unknown_ids)} 种新版本消息 ID（原始 .bin 已无损保留）: {dict(unknown_ids)}")
    print("")


def main() -> None:
    parser = argparse.ArgumentParser(description="OverField 抓包解包与玩家数据核对工具")
    parser.add_argument("pcap", type=Path, help="输入的 .pcapng 或 .pcap 文件路径")
    parser.add_argument("-o", "--out", type=Path, default=None, help="输出目录（默认在 pcap 同目录创建 parsed_<名>）")
    args = parser.parse_args()

    pcap_path = args.pcap.resolve()
    if not pcap_path.exists():
        print(f"[错误] 找不到文件: {pcap_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = args.out.resolve() if args.out else pcap_path.parent / f"parsed_{pcap_path.stem}"
    if args.out is None and out_dir.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        out_dir = out_dir.with_name(f"{out_dir.name}_{stamp}")
    if out_dir.exists() and (not out_dir.is_dir() or any(out_dir.iterdir())):
        parser.error("输出路径已存在且非空，请指定新的 --out 目录。")
    analyze_pcap(pcap_path, out_dir)


if __name__ == "__main__":
    main()
