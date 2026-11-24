"""Import a 1.0.5 account ZIP into this launcher's account database.

Rules requested by the user:
- UID login: if the capture contains a UID, log in with it; otherwise use the UID
  the player typed and create that account row.
- A UID that already holds progress is a conflict and must be reported, never
  overwritten silently.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import zipfile
from contextlib import closing
from pathlib import Path, PurePosixPath

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import capture_import  # noqa: E402


def open_account_zip(path: Path):
    """Return (archive, prefix) where account packet JSON lives under <prefix>json/."""
    archive = zipfile.ZipFile(path)
    names = archive.namelist()
    if len(names) != len(set(names)):
        archive.close()
        raise ValueError("ZIP 内有重名文件，无法确认导入内容。")
    for name in names:
        parts = PurePosixPath(name)
        if parts.is_absolute() or ".." in parts.parts or "\\" in name:
            archive.close()
            raise ValueError("ZIP 含不安全路径。")
    for prefix in ("", "export/"):
        if any(n.startswith(f"{prefix}json/") for n in names):
            return archive, prefix
    archive.close()
    raise ValueError("这不是账号备份 ZIP：缺少 json/ 数据目录。")


def collect_entries(archive: zipfile.ZipFile, prefix: str) -> dict:
    import re

    entries: dict[str, list] = {}
    for item in archive.infolist():
        name = item.filename
        if not name.startswith(f"{prefix}json/") or not name.endswith(".json"):
            continue
        if "_s2c_" not in name:
            continue
        match = re.search(r"_s2c_\d+_([A-Za-z0-9_]+)\.json$", name)
        if not match:
            continue
        entries.setdefault(match.group(1), []).append(json.loads(archive.read(item)))
    return entries


def read_identity(path: Path) -> tuple[dict, dict]:
    """Read the captured main data and all decoded responses from an account ZIP."""
    archive, prefix = open_account_zip(path)
    try:
        entries = collect_entries(archive, prefix)
    finally:
        archive.close()

    main = entries.get("PlayerMainDataRsp", [])
    if not main:
        raise ValueError("备份里没有 PlayerMainDataRsp，无法确定账号数据。")
    uids = {int(value["player_id"]) for value in main if value.get("player_id")}
    if len(uids) > 1:
        raise ValueError("备份包含多个玩家 UID，请按账号分别备份后重试。")
    player = main[-1]
    if player.get("status") not in (1, "StatusCode_OK"):
        raise ValueError("PlayerMainDataRsp 状态异常，备份可能不完整。")
    return player, entries


def captured_uid(player: dict) -> int:
    """Display UID written by the game, falling back to the internal id."""
    return int(player.get("player_label") or player.get("player_id") or 0)


def existing_uids(database: Path) -> list[int]:
    if not database.is_file():
        return []
    with closing(sqlite3.connect(database, timeout=10)) as connection:
        return [row[0] for row in connection.execute("SELECT user_id FROM of_user ORDER BY user_id")]


def has_progress(database: Path, uid: int) -> bool:
    if not database.is_file():
        return False
    with closing(sqlite3.connect(database, timeout=10)) as connection:
        return connection.execute("SELECT 1 FROM of_game WHERE user_id=?", (uid,)).fetchone() is not None


def describe(database: Path, uid: int) -> str:
    with closing(sqlite3.connect(database, timeout=10)) as connection:
        row = connection.execute(
            "SELECT b.nick_name, b.level FROM of_game_basic b WHERE b.user_id=?", (uid,)
        ).fetchone()
    if not row:
        return f"UID {uid}"
    return f"UID {uid}（{row[0] or '未命名'}，等级 {row[1] or '?'}）"


def plan(path: Path, database: Path, login_uid: int | None) -> dict:
    """Decide which UID to use and whether it conflicts, without writing anything."""
    player, entries = read_identity(path)
    uid = captured_uid(player)
    source = "capture"
    if not uid:
        if not login_uid:
            raise ValueError("备份里没有 UID，请填写要创建的登录 UID。")
        uid = int(login_uid)
        source = "login"

    conflict = has_progress(database, uid)
    return {
        "uid": uid,
        "uidSource": source,
        "name": player.get("player_name", ""),
        "level": player.get("level", 1),
        "characters": len(player.get("characters", [])),
        "capturedMessages": sum(len(value) for value in entries.values()),
        "database": str(database),
        "conflict": conflict,
        "conflictWith": describe(database, uid) if conflict else "",
        "existingUids": existing_uids(database),
    }


def import_account(path: Path, database: Path, login_uid: int | None, replace: bool = False) -> dict:
    reviewed = plan(path, database, login_uid)
    if reviewed["conflict"] and not replace:
        raise ValueError(
            f"UID 冲突：{reviewed['conflictWith']} 已有存档。"
            "如需覆盖，请先备份该账号或选择其他 UID。"
        )

    uid = reviewed["uid"]
    player, entries = read_identity(path)

    # Reuse the existing importer by presenting a flat export/ ZIP it already understands.
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        flat = Path(directory) / "import.zip"
        archive, prefix = open_account_zip(path)
        try:
            with zipfile.ZipFile(flat, "w", zipfile.ZIP_DEFLATED) as out:
                for item in archive.infolist():
                    if item.filename.startswith(f"{prefix}json/") and "_s2c_" in item.filename:
                        out.writestr("export/" + item.filename[len(prefix):], archive.read(item))
        finally:
            archive.close()
        result = capture_import.import_capture(flat, database.parent.parent, uid, replace=replace)

    result.update(
        uid=uid,
        uidSource=reviewed["uidSource"],
        name=player.get("player_name", ""),
        level=player.get("level", 1),
        database=str(database),
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "import"])
    parser.add_argument("--file", type=Path, required=True, help="account_*.zip from the backup tool")
    parser.add_argument("--database", type=Path, required=True, help="profiles/<mode>/db/lolo.db")
    parser.add_argument("--uid", type=int, default=0, help="UID to create when the capture has none")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    database = args.database.resolve()
    try:
        if args.action == "plan":
            result = plan(args.file.resolve(), database, args.uid or None)
        else:
            result = import_account(args.file.resolve(), database, args.uid or None, args.replace)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, OSError, zipfile.BadZipFile, sqlite3.Error) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
