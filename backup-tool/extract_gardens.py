#!/usr/bin/env python3
"""
OverField (开放空间) 好友家园批量抓取解析与归档工具。

用法：
  1. 仅从抓包中提取所有拜访过的家园并按好友 UID 分别保存 (.bin + .json)：
     python extract_gardens.py <pcapng路径>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

from google.protobuf import json_format

SCRIPT_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "proto_gen"))

import net_pb2  # type: ignore  # noqa: E402
from parse_pcap import (  # type: ignore  # noqa: E402
    extract_tcp_stream_directions,
    list_tcp_streams,
    parse_game_stream,
)


def extract_gardens(pcap_path: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    known_names: Dict[int, str] = {}

    streams = list_tcp_streams(pcap_path)
    print(f"[信息] 发现 {len(streams)} 条 TCP 流，正在扫描家园场景包 (SceneDataNotice / 1016)...")

    # owner_uid -> (SceneGardenData bytes, SceneGardenData msg, meta dict)
    gardens: Dict[int, Tuple[bytes, net_pb2.SceneGardenData, dict]] = {}

    for sid in streams:
        _, _, b01, b10 = extract_tcp_stream_directions(pcap_path, sid)
        for payload in (b01, b10):
            if not payload:
                continue
            pkts, _ = parse_game_stream(payload)
            for pkt in pkts:
                if pkt["msg_id"] != 1016 or pkt["decompress_err"]:
                    continue
                sdn = net_pb2.SceneDataNotice()
                try:
                    sdn.ParseFromString(pkt["body"])
                except Exception:
                    continue

                data = sdn.data
                if data.scene_id != 9999:
                    continue

                gdata = data.scene_garden_data
                fcount = len(gdata.garden_furniture_info_map)
                if fcount == 0:
                    continue

                try:
                    owner_id = int(data.channel_id or data.channel_label)
                except (ValueError, TypeError):
                    continue
                if owner_id <= 0:
                    continue
                # 如果玩家刚好也在场景里，尝试从 players 补昵称
                for pl in data.players:
                    if pl.player_id and pl.player_name:
                        known_names.setdefault(int(pl.player_id), pl.player_name)

                # 同一好友如果进出多次，保留家具数最多/最新的一次
                prev = gardens.get(owner_id)
                if prev is None or fcount >= prev[2]["furniture_count"]:
                    gardens[owner_id] = (
                        gdata.SerializeToString(),
                        gdata,
                        {
                            "owner_uid": owner_id,
                            "owner_name": known_names.get(owner_id, "未知玩家"),
                            "scene_id": int(data.scene_id),
                            "furniture_count": fcount,
                            "likes_num": int(gdata.likes_num),
                            "access_player_num": int(gdata.access_player_num),
                        },
                    )

    if not gardens:
        print("\n[提示] 本次抓包未发现任何带家具数据的家园 (scene_id=9999)。")
        print("       请确认抓包期间确实进入了好友的家园场景。")
        (out_dir / "gardens_index.json").write_text("[]\n", encoding="utf-8")
        return

    index_list = []
    for owner_id, (raw_bytes, gdata, meta) in sorted(gardens.items()):
        safe_name = re.sub(r'[\\/:*?"<>|\s]+', "_", meta["owner_name"]).strip("_.")[:40] or "unknown"
        stem = f"garden_{owner_id}_{safe_name}_{meta['furniture_count']}items"

        # 1. 保存无损 SceneGardenData Protobuf 二进制
        bin_path = out_dir / f"{stem}.bin"
        bin_path.write_bytes(raw_bytes)

        # 2. 保存可读 JSON
        json_path = out_dir / f"{stem}.json"
        gdict = json_format.MessageToDict(
            gdata, preserving_proto_field_name=True, always_print_fields_with_no_presence=False
        )
        gdict["_meta"] = meta
        json_path.write_text(json.dumps(gdict, ensure_ascii=False, indent=2), encoding="utf-8")

        meta["bin_file"] = bin_path.name
        meta["json_file"] = json_path.name
        index_list.append(meta)

    (out_dir / "gardens_index.json").write_text(
        json.dumps(index_list, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n" + "=" * 60)
    print(f"好友家园提取完成！共保存 {len(gardens)} 个家园配置")
    print(f"保存目录: {out_dir}")
    print("=" * 60)
    for m in index_list:
        print(
            f"  - UID {m['owner_uid']} ({m['owner_name']}): "
            f"{m['furniture_count']} 件家具 | 点赞 {m['likes_num']} | 访客 {m['access_player_num']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="OverField 好友家园抓取与归档工具")
    parser.add_argument("pcap", type=Path, help="抓包生成的 .pcapng 文件路径")
    parser.add_argument("-o", "--out", type=Path, default=None, help="输出目录（默认在抓包同目录创建 gardens_<文件名>）")
    args = parser.parse_args()

    pcap_path = args.pcap.resolve()
    if not pcap_path.exists():
        print(f"[错误] 找不到文件: {pcap_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = (
        args.out.resolve()
        if args.out
        else pcap_path.parent / f"gardens_{pcap_path.stem}"
    )
    if args.out is None and out_dir.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        out_dir = out_dir.with_name(f"{out_dir.name}_{stamp}")
    if out_dir.exists() and (not out_dir.is_dir() or any(out_dir.iterdir())):
        parser.error("输出路径已存在且非空，请指定新的 --out 目录。")
    extract_gardens(pcap_path, out_dir)


if __name__ == "__main__":
    main()
