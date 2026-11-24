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
import zipfile
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
    """Pick an interpreter that can actually decode captures.

    runtime-python ships this launcher's own deps and has neither cramjam nor
    protobuf, so decoding with it fails after capture. Prefer the tool's own
    interpreter, which carries the decode stack.
    """
    candidates = (
        BASE / "backup-tool" / "tools" / "python" / "python.exe",
        BASE / "tools" / "python" / "python.exe",
        BASE / "runtime-python" / "python.exe",
    )
    for candidate in candidates:
        if candidate.is_file() and can_decode(candidate):
            return candidate
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return Path(sys.executable)


def can_decode(python: Path) -> bool:
    """True when this interpreter can import the modules parse_pcap.py needs."""
    try:
        result = subprocess.run(
            [str(python), "-B", "-c", "import cramjam, google.protobuf"],
            capture_output=True, timeout=60, creationflags=NO_WINDOW,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


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


def wait_capture_ready(process, ready_path: Path, timeout=40) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        code = process.poll()
        if code is not None:
            error_path = ready_path.parent / "capture-worker.stderr.log"
            detail = ""
            if error_path.is_file():
                lines = error_path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
                detail = next((line.strip() for line in lines if line.strip()), "")[:240]
            if detail:
                raise ValueError(f"抓包启动失败（{code}）：{detail}。公服未启动。")
            raise ValueError(f"抓包程序提前退出（{code}），公服未启动。请查看本次采集日志。")
        if ready_path.is_file():
            ready = json.loads(ready_path.read_text(encoding="utf-8-sig"))
            if ready.get("ready") and int(ready.get("pid", 0)) == process.pid:
                return ready
            raise ValueError("抓包程序返回无效就绪信号，公服未启动。")
        time.sleep(0.1)
    raise ValueError("等待抓包启动超时，公服未启动。请查看采集日志。")


def request_failed_start_stop(process, state):
    STOP_FLAG.parent.mkdir(parents=True, exist_ok=True)
    STOP_FLAG.touch()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        pass  # The script owns cleanup; do not kill it or stop another PktMon session.
    write_state(dict(state, active=process.poll() is None, phase="stopping", error="采集或公服启动失败，已发送停止信号"))


def start(launcher_path=None) -> dict:
    """Wait for actual capture readiness, then launch only the configured official EXE."""
    from official_launcher import validate_launcher, launch_official, clean_environment
    if read_state().get("active"):
        raise ValueError("已有采集正在进行，请先结束当前采集。")
    launcher = validate_launcher(launcher_path, BASE)
    world_state = RUNTIME / "world-state.json"
    if world_state.is_file() and json.loads(world_state.read_text(encoding="utf-8-sig")).get("Active"):
        raise ValueError("请先停止私服服务，再开始公服采集，避免流量混入私服。")
    report = preflight()
    if not report["ok"]:
        raise ValueError("无法开始采集：" + "；".join(report["problems"]))
    session = SESSIONS / dt.datetime.now().strftime("capture_%Y%m%d_%H%M%S_%f")
    session.mkdir(parents=True, exist_ok=True)
    STOP_FLAG.unlink(missing_ok=True)
    ready_path = session / "capture-ready.json"
    from official_launcher import steam_app_id, steam_install_dir, server_addresses
    server_ips = []
    if steam_app_id(launcher) is not None:
        # The Steam build assigns game ports at runtime, so capture its server
        # addresses instead of relying on the fixed Bilibili port list.
        server_ips = server_addresses(steam_install_dir(steam_app_id(launcher)))
    command = [
        "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", str(BASE / "backup-tool" / "capture.ps1"), "-Mode", "Account",
        "-OutDir", str(session), "-PythonExe", str(python_exe()),
        "-TSharkExe", str(tshark_exe()), "-StopFlag", str(STOP_FLAG),
        "-ReadyPath", str(ready_path),
    ]
    if server_ips:
        command += ["-ServerIps", ",".join(server_ips)]
    with (session / "capture-worker.stdout.log").open("ab") as out, (session / "capture-worker.stderr.log").open("ab") as err:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                   cwd=str(BASE / "backup-tool"), creationflags=NO_WINDOW,
                                   env=clean_environment())
    state = {"active": False, "phase": "starting", "startedAt": dt.datetime.now().isoformat(timespec="seconds"),
             "session": str(session), "pid": process.pid, "officialLauncherPath": str(launcher)}
    write_state(state)
    try:
        ready = wait_capture_ready(process, ready_path)
        state.update(active=True, phase="capturing", capturePath=ready.get("session", ""))
        write_state(state)
        official = launch_official(launcher, BASE)
    except (ValueError, OSError, subprocess.SubprocessError):
        request_failed_start_stop(process, state)
        raise
    state["officialPid"] = official.pid
    state["officialKind"] = official.kind
    write_state(state)
    log(f"抓包已就绪，公服启动器已打开 -> {launcher}")
    return {"session": str(session), "officialLauncherPath": str(launcher), "officialPid": official.pid,
            "officialKind": official.kind,
            "hint": "抓包已开始，公服启动器已打开。请正常登录并进入场景；若客户端已在运行，请退出后重新打开以采集登录响应。"}


def result_from_export(export: Path, session: Path):
    summary_path = export / "summary.json"
    if not summary_path.is_file():
        return None
    if not summary_path.resolve().is_relative_to(session.resolve()):
        raise ValueError("采集产物不能指向当前会话之外。")
    summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    if not isinstance(summary, dict) or "player_uids" not in summary or "total_packets" not in summary:
        return None
    name = summary.get("account_zip", "")
    account_zip = None
    if name:
        if not isinstance(name, str) or Path(name).name != name or "\\" in name or Path(name).drive:
            raise ValueError("账号ZIP产物路径不安全。")
        account_zip = export / name
        if not account_zip.is_file():
            return None
        if account_zip.resolve().parent != export.resolve():
            raise ValueError("账号ZIP不能链接到输出目录之外。")
        from capture_zip import inspect_account_zip
        inspect_account_zip(account_zip)
    return {"session": str(session), "export": str(export),
            "accountZip": str(account_zip) if account_zip else "", "playerUids": summary["player_uids"]}


def completed_result(session: Path):
    if not session.is_dir():
        return None
    summaries = sorted(session.rglob("summary.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in summaries:
        if path.parent.name.startswith("export"):
            result = result_from_export(path.parent, session)
            if result is not None:
                return result
    return None


def finalize_capture(result, recovered=False):
    final = dict(read_state(), **result)
    final.update(active=False, phase="complete", recovered=recovered,
                 stoppedAt=dt.datetime.now().isoformat(timespec="seconds"))
    final.pop("error", None)
    try:
        from capture_checklist import atomic_json, final_report
        atomic_json(Path(result["export"]) / "capture-checklist.json", final_report(result["export"]))
    except (OSError, ValueError, TypeError) as error:
        log("采集清单最终核对暂不可用：" + str(error))
    write_state(final)
    log("采集产物已确认，账号ZIP可另存交付。")
    return result


def recover() -> dict:
    """Recover completed outputs only; never signal or stop a running capture."""
    state = read_state()
    if state.get("active"):
        raise ValueError("当前采集仍在进行，请先由用户结束采集。")
    if not state.get("session"):
        raise ValueError("没有可恢复的采集会话。")
    session = Path(state["session"])
    if not session.resolve().is_relative_to(SESSIONS.resolve()):
        raise ValueError("采集会话路径不属于当前启动器。")
    result = completed_result(session)
    if result is None:
        raise ValueError("没有找到完整的已解码产物，原始文件已保留。")
    current = read_state()
    if current.get("active") or current.get("session") != state.get("session"):
        raise ValueError("采集会话已变化，未改写状态。")
    return finalize_capture(result, recovered=True)


def stop() -> dict:
    """Receive worker-completed outputs; only decode when no usable output exists."""
    state = read_state()
    if not state.get("session"):
        raise ValueError("当前没有采集会话或可恢复的完成产物。")
    session = Path(state["session"])
    if not session.resolve().is_relative_to(SESSIONS.resolve()):
        raise ValueError("采集会话路径不属于当前启动器。")
    if not state.get("active"):
        if state.get("session"):
            result = completed_result(session)
            if result is not None:
                return finalize_capture(result, recovered=True)
        raise ValueError("当前没有进行中的采集，也没有可恢复的完成产物。")

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
    write_state(dict(state, active=False, phase="decoding"))
    finished = completed_result(session)
    if finished is not None:
        return finalize_capture(finished)

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
    if export.exists() and any(export.iterdir()):
        export = etl_path.parent / ("export-recovery-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    decode = subprocess.run(
        [str(python_exe()), "-B", "-X", "utf8", str(BASE / "backup-tool" / "parse_pcap.py"),
         str(pcap_path), "--out", str(export)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=1800, creationflags=NO_WINDOW,
    )
    if decode.returncode != 0:
        raise ValueError("解码失败：" + (decode.stderr or decode.stdout or "").strip()[-400:])

    result = result_from_export(export, session)
    if result is None:
        raise ValueError("解码未生成完整产物；原始抓包及已有输出已保留。")
    return finalize_capture(result)


def status() -> dict:
    state = read_state()
    readiness = preflight()
    return {
        "active": bool(state.get("active")),
        "session": state.get("session", ""),
        "startedAt": state.get("startedAt", ""),
        "playerUids": state.get("playerUids", []),
        "accountZip": state.get("accountZip", ""),
        "ready": readiness["ok"],
        "problems": readiness["problems"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "stop", "status", "validate-launcher", "export-zip", "recover", "progress"])
    parser.add_argument("--launcher", type=Path)
    parser.add_argument("--file", type=Path)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "progress":
            from capture_checklist import progress
            result = progress(read_state())
        elif args.action == "export-zip":
            if args.file is None or args.destination is None:
                raise ValueError("请选择要交付的账号ZIP及保存位置。")
            from capture_zip import export_account_zip
            result = export_account_zip(args.file, args.destination)
        elif args.action == "validate-launcher":
            from official_launcher import validate_launcher, steam_app_id, steam_install_dir
            path = validate_launcher(args.launcher, BASE)
            app_id = steam_app_id(path)
            result = {"path": str(path)}
            if app_id is not None:
                install = steam_install_dir(app_id)
                result.update(kind="steam", appId=app_id,
                              install=str(install) if install else "")
        elif args.action == "start":
            result = start(args.launcher)
        else:
            result = {"stop": stop, "status": status, "recover": recover}[args.action]()
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
