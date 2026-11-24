"""Official-server capture: start/stop a capture session and store the result in the account DB.

The public server still requires the player's own channel login. This module only
records traffic and imports what the client actually received; it never injects a
local UID into the official client.
"""
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
RUNTIME = BASE / "runtime"
STATE = RUNTIME / "capture-state.json"
SESSIONS = RUNTIME / "capture-sessions"
LOG = RUNTIME / "capture.log"
STOP_FLAG = RUNTIME / "capture-stop.flag"

PACKETMON = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "PktMon.exe"
PORTS = [11001, 11002, 11003, 11004, 21001, 21002]
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def log(message: str) -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%H:%M:%S")
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"[{stamp}] {message}\n")


def write_state(payload: dict) -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_name(STATE.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(STATE)


def read_state() -> dict:
    if not STATE.is_file():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def python_exe() -> Path:
    bundled = BASE / "runtime-python" / "python.exe"
    return bundled if bundled.is_file() else Path(sys.executable)


def tshark_exe() -> Path:
    for candidate in (
        BASE / "backup-tool" / "tools" / "tshark" / "tshark.exe",
        BASE / "tools" / "tshark" / "tshark.exe",
    ):
        if candidate.is_file():
            return candidate
    found = shutil.which("tshark")
    return Path(found) if found else BASE / "tools" / "tshark" / "tshark.exe"


def is_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def powershell(script: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, creationflags=NO_WINDOW,
    )


def preflight() -> dict:
    problems = []
    if not (BASE / "backup-tool" / "capture.ps1").is_file():
        problems.append("缺少 backup-tool/capture.ps1")
    if not (BASE / "backup-tool" / "parse_pcap.py").is_file():
        problems.append("缺少 backup-tool/parse_pcap.py")
    if not python_exe().is_file():
        problems.append("缺少 Python 运行时")
    if not tshark_exe().is_file():
        problems.append("缺少 TShark")
    if not PACKETMON.is_file():
        problems.append("系统缺少 PktMon（需要 Windows 10 1809 及以上）")
    if not is_admin():
        problems.append("需要管理员权限才能采集公服流量")
    return {"ok": not problems, "problems": problems}


def start() -> dict:
    """Begin capturing official traffic; the player then logs in with their own account."""
    if read_state().get("active"):
        raise ValueError("已有采集正在进行，请先结束当前采集。")
    report = preflight()
    if not report["ok"]:
        raise ValueError("无法开始采集：" + "；".join(report["problems"]))

    session = SESSIONS / dt.datetime.now().strftime("capture_%Y%m%d_%H%M%S")
    session.mkdir(parents=True, exist_ok=True)
    STOP_FLAG.unlink(missing_ok=True)

    command = [
        "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", str(BASE / "backup-tool" / "capture.ps1"),
        "-Mode", "Account",
        "-OutDir", str(session),
        "-PythonExe", str(python_exe()),
        "-TSharkExe", str(tshark_exe()),
        "-StopFlag", str(STOP_FLAG),
    ]
    # capture.ps1 blocks on Read-Host until Enter arrives on stdin; keep the pipe open
    # and write the newline from stop().
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        cwd=str(BASE / "backup-tool"), creationflags=NO_WINDOW,
    )
    write_state({
        "active": True,
        "startedAt": dt.datetime.now().isoformat(timespec="seconds"),
        "session": str(session),
        "pid": process.pid,
    })
    log(f"开始采集公服流量 -> {session}")
    return {
        "session": str(session),
        "hint": "现在启动公服客户端，用你自己的渠道账号登录并进入游戏，逐项打开要保存的界面；完成后点「结束采集」。",
    }


def stop() -> dict:
    """Stop capturing, decode traffic, and report the captured account ZIP."""
    state = read_state()
    if not state.get("active"):
        raise ValueError("当前没有进行中的采集。")

    session = Path(state["session"])

    # 1) Cooperative stop: the script polls this flag, then runs its own finally block
    #    (stop PktMon, remove only its own filters, release the mutex) and decodes.
    #    Killing it instead would skip that cleanup and leave filters/mutex behind.
    STOP_FLAG.parent.mkdir(parents=True, exist_ok=True)
    STOP_FLAG.write_text(dt.datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
    log("已发送结束采集信号")

    pid = int(state.get("pid") or 0)
    waited = 0
    while pid and waited < 1800:
        check = powershell(
            f"$p = Get-Process -Id {pid} -ErrorAction SilentlyContinue; if ($p) {{ 'alive' }} else {{ 'gone' }}"
        )
        if (check.stdout or "").strip() != "alive":
            break
        time.sleep(2)
        waited += 2
    if pid and waited >= 1800:
        log("等待抓包脚本结束超时，改为强制结束")
        powershell(f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue")
    STOP_FLAG.unlink(missing_ok=True)

    etl = sorted(session.rglob("capture.etl")) if session.is_dir() else []
    if not etl:
        write_state({"active": False, "stoppedAt": dt.datetime.now().isoformat(timespec="seconds"),
                     "session": str(session), "error": "没有抓包文件"})
        raise ValueError("没有采集到抓包文件：请确认登录公服后确实进入了游戏场景。")

    etl_path = etl[0]
    pcap_path = etl_path.with_suffix(".pcapng")
    if not pcap_path.is_file():
        subprocess.run([str(PACKETMON), "etl2pcap", str(etl_path), "--out", str(pcap_path)],
                       capture_output=True, text=True, timeout=900, creationflags=NO_WINDOW)

    export = etl_path.parent / "export"
    decode = subprocess.run(
        [str(python_exe()), "-B", "-X", "utf8", str(BASE / "backup-tool" / "parse_pcap.py"),
         str(pcap_path), "--out", str(export)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=1800, creationflags=NO_WINDOW,
    )
    if decode.returncode != 0:
        raise ValueError("解码失败：" + (decode.stderr or decode.stdout or "").strip()[-400:])

    summary = {}
    if (export / "summary.json").is_file():
        summary = json.loads((export / "summary.json").read_text(encoding="utf-8"))

    account_zip = export / summary["account_zip"] if summary.get("account_zip") else None
    if account_zip is not None and not account_zip.is_file():
        account_zip = None

    result = {
        "session": str(session),
        "export": str(export),
        "accountZip": str(account_zip) if account_zip else "",
        "playerUids": summary.get("player_uids", []),
    }
    write_state(dict(result, active=False,
                     stoppedAt=dt.datetime.now().isoformat(timespec="seconds")))
    log(f"采集结束 UID={result['playerUids']} 产物={result['accountZip'] or '无'}")
    return result


def status() -> dict:
    state = read_state()
    return {
        "active": bool(state.get("active")),
        "session": state.get("session", ""),
        "startedAt": state.get("startedAt", ""),
        "playerUids": state.get("playerUids", []),
        "accountZip": state.get("accountZip", ""),
        "ready": preflight()["ok"],
        "problems": preflight()["problems"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "stop", "status"])
    args = parser.parse_args()
    try:
        result = {"start": start, "stop": stop, "status": status}[args.action]()
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
