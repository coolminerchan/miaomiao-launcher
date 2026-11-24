"""Map the installed OverField build to its locally installed resource manifest."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import shutil

DEFAULT_ROOT = pathlib.Path.cwd()
STAMP = re.compile(r"\d{4}(?:-\d{2}){5}")


def read_version(path: pathlib.Path) -> str:
    value = path.read_text(encoding="utf-8-sig").strip()
    if not STAMP.fullmatch(value):
        raise ValueError(f"Unexpected version in {path}: {value!r}")
    return value


def repair(root: pathlib.Path, apply: bool) -> dict:
    client = root / "OverField Game" / "launcher_Data"
    program = read_version(client / "StreamingAssets/yoo/DefaultPackage/PackageManifest_DefaultPackage.version")
    resource = read_version(client / "yoo/DefaultPackage/ManifestFiles/PackageManifest_DefaultPackage.version")
    target = root / "LoloServer/data/ClientVersion.json"
    data = json.loads(target.read_text(encoding="utf-8-sig"))
    mapping = data["VersionMap"]
    desired = f"{program}_{resource}"
    result = {"file": str(target), "program": program, "resource": resource,
              "previous": mapping.get(program), "desired": desired, "applied": False}
    if apply and mapping.get(program) != desired:
        backup = root / "LoloServer/backup" / f"ClientVersion-{dt.datetime.now():%Y%m%d-%H%M%S-%f}.json"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup)
        mapping[program] = desired
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(target)
        result.update(applied=True, backup=str(backup))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=DEFAULT_ROOT)
    parser.add_argument("--apply", action="store_true", help="Back up and update the version map")
    args = parser.parse_args()
    print(json.dumps(repair(args.root, args.apply), ensure_ascii=False, indent=2))
