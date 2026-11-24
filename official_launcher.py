"""Official-only executable validation and launch, independent of private gameRoot.
No local SDK injection, client preparation, dispatch redirection or UID arguments.
"""
import hashlib
import os
import subprocess
from pathlib import Path


def validate_launcher(value, base=None):
    if not value or not str(value).strip():
        raise ValueError('请先设置公服启动器路径；该路径与私服游戏目录独立。')
    path = Path(value).expanduser()
    if not path.is_absolute() or path.suffix.lower() != '.exe' or not path.is_file():
        raise ValueError('请选择已存在的公服启动器或原版客户端 EXE。')
    path = path.resolve()
    base = Path(base or Path(__file__).resolve().parent).resolve()
    private = base / 'profiles'
    if path == private or private in path.parents:
        raise ValueError('公服路径不能指向启动器 profiles 内的私服副本。')
    if path.name.lower() in ('overfieldlauncher.exe', 'lolo.exe'):
        raise ValueError('请选择原版公服启动器，不要选择私服启动器或服务端。')
    for parent in path.parents:
        if (parent / 'client-ready.json').is_file():
            raise ValueError('该目录是已准备的私服客户端副本，不能用于公服采集。')
    sdk = path.parent / 'launcher_Data/Plugins/x86_64/PCGameSDK.dll'
    local = base / 'LocalUidSDK.dll'
    if sdk.is_file() and local.is_file() and sdk.stat().st_size == local.stat().st_size:
        if hashlib.sha256(sdk.read_bytes()).digest() == hashlib.sha256(local.read_bytes()).digest():
            raise ValueError('这个客户端已经替换本地UID SDK，请选择未修改的公服客户端。')
    return path


def clean_environment(environ=None):
    return {k: v for k, v in (os.environ if environ is None else environ).items()
            if not k.upper().startswith('LOLO_')}


def launch_official(value, base=None):
    path = validate_launcher(value, base)
    # Visible direct process launch, never service_runner or a shell command string.
    return subprocess.Popen([str(path)], cwd=str(path.parent), env=clean_environment(),
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, creationflags=0)
