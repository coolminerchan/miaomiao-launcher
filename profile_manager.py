"""Independent local/LAN server configuration and consistent SQLite snapshots."""
from __future__ import annotations
import argparse
import datetime as dt
import ipaddress
import json
from pathlib import Path
import shutil
import sqlite3
from urllib.request import ProxyHandler, build_opener
import re
import subprocess
from contextlib import closing

MODES = {'solo': (18080, 18100, 18200), 'host': (19080, 19100, 19200), 'steam': (20080, 20100, 20200)}

# Each profile owns a disjoint port block, so the national and the international
# worlds can run side by side on one machine without negotiating a free port.
# The room gateway admin port sits 220 above the HTTP port (18300/19300/20300).

# Client language enum values must be verified against the actual client.
# A voice-language enum is not evidence for the UI-language numbering.
# Launcher UI language is selected at build time, independently of this setting.
LANGUAGE_DEFAULT = {}

# Channels whose client assets differ; the Steam build keeps its own copy so the
# two editions never share a writable install.
CHANNEL_SOURCES = {'steam': 'steam'}


def lan_ip(value):
    ip = ipaddress.IPv4Address(value.strip())
    if not any(ip in ipaddress.IPv4Network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')):
        raise ValueError('A private LAN IPv4 address is required.')
    return str(ip)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def snapshot(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + '.tmp')
    with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)) as origin:
        with closing(sqlite3.connect(temporary)) as target:
            origin.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('SQLite snapshot validation failed.')
    temporary.replace(destination)


def locate(roots):
    """Find the client launcher and LoloServer, tolerating one extra nesting level.

    Players pick different folders: the install root, the folder holding
    'OverField Game', or the game folder itself. Accept all of them instead of
    failing with 'Game client not found'.
    """
    client = server = None
    for base in roots:
        if base is None:
            continue
        try:
            candidates = [base] + [p for p in base.iterdir() if p.is_dir()]
        except OSError:
            continue
        for folder in candidates:
            if client is None:
                if (folder / 'OverField Game' / 'launcher.exe').is_file():
                    client = folder / 'OverField Game'
                elif (folder / 'launcher.exe').is_file():
                    client = folder
            if server is None:
                if (folder / 'LoloServer' / 'Lolo.exe').is_file():
                    server = folder / 'LoloServer'
                elif (folder / 'Lolo.exe').is_file() and (folder / 'config.json').is_file():
                    server = folder
        if client is not None and server is not None:
            break
    return client, server


def apply_language(resources, language):
    """Pin the client UI language inside this profile's own resource copy.

    The value lives in InitConfigAsset.json. Rewriting only this profile's file
    keeps the shipped server-kit template untouched, so one installation can run
    a Chinese and an English world at the same time.
    """
    path = Path(resources) / 'Config' / 'InitConfigAsset.json'
    if not path.is_file():
        return None
    document = json.loads(path.read_text(encoding='utf-8-sig'))
    changed = 0
    for section in document.values():
        if isinstance(section, dict) and 'ForeceLaguageType' in section:
            if section['ForeceLaguageType'] != language:
                section['ForeceLaguageType'] = language
                changed += 1
    if changed:
        write_json(path, document)
    return {'path': str(path), 'language': language, 'sections': changed}


def prepare(root, base, mode, host):
    http, gate, log = MODES[mode]
    address = lan_ip(host) if mode == 'host' else '127.0.0.1'
    profile = base / mode
    profile.mkdir(parents=True, exist_ok=True)
    (profile / 'logs').mkdir(exist_ok=True)
    result = {'mode': mode, 'profile': str(profile), 'host': address, 'http': http, 'gateway': gate, 'log': log, 'imported': False}
    located_client, located_server = locate([root, Path(__file__).resolve().parent])
    server = located_server or (root / 'LoloServer')
    if not (server / 'Lolo.exe').is_file():
        server = Path(__file__).with_name('server-kit')
    if not (server / 'Lolo.exe').is_file():
        raise FileNotFoundError('LoloServer/Lolo.exe is missing. Put the server files next to the launcher or select the folder that contains LoloServer.')
    data = profile / 'data'
    if not data.exists():
        shutil.copytree(server / 'data', data)
    resources = profile / 'Resource'
    if not resources.exists():
        shutil.copytree(server / 'Resource', resources)
    language = LANGUAGE_DEFAULT.get(mode)
    if language is not None:
        result['language'] = apply_language(resources, language)
    executable = profile / 'server/Lolo.exe'
    executable.parent.mkdir(exist_ok=True)
    if not executable.exists(): shutil.copy2(server / 'Lolo.exe', executable)
    # Repair only this profile's version map; original installation is read-only.
    import repair_version
    original_client = located_client or root
    client = original_client/'launcher_Data'
    if (client/'StreamingAssets/yoo/DefaultPackage/PackageManifest_DefaultPackage.version').exists():
        program = repair_version.read_version(client / 'StreamingAssets/yoo/DefaultPackage/PackageManifest_DefaultPackage.version')
        resource = repair_version.read_version(client / 'yoo/DefaultPackage/ManifestFiles/PackageManifest_DefaultPackage.version')
        mapping = json.loads((data / 'ClientVersion.json').read_text(encoding='utf-8-sig'))
        mapping['VersionMap'][program] = program + '_' + resource
        write_json(data / 'ClientVersion.json', mapping)
    database = profile / 'db/lolo.db'
    database.parent.mkdir(exist_ok=True)
    metadata = profile / 'profile.json'
    # Public builds never inherit accounts from an installation/template database.
    # Keep an existing private profile unchanged; import player progress only explicitly.
    if not database.exists():
        from capture_import import schema_database
        schema_database(server / 'db/lolo.db', database)
    if not metadata.exists():
        write_json(metadata, {'mode': mode, 'createdAt': dt.datetime.now().isoformat(), 'schemaOnly': True})
    config = json.loads((server / 'config.json').read_text(encoding='utf-8-sig'))
    config['Resources'] = {'ResourcePath': str(resources), 'DataPath': str(data)}
    config['HttpNet'].update(InnerIp=address, InnerPort=str(http), Tls=False, HttpsPort=str(http + 3), CertPath=str(data / 'cert.pem'), KeyPath=str(data / 'key.pem'))
    config['GateWay'].update(OuterIp=address, OuterPort=gate, OuterAddr=f'127.0.0.1:{gate+1}', CheckToken=False, CheckUrl=f'http://{address}:{http}/gucooing/lolo/checkSdkToken')
    config['LogServer'].update(OuterIp=address, OuterPort=log, OuterAddr=f'{address}:{log}')
    config['DB'].update(dbType='sqlite', dsn=str(database) + '?_pragma=busy_timeout(10000)&_pragma=journal_mode(WAL)&_pragma=synchronous(NORMAL)', readDsn=[])
    write_json(profile / 'config.json', config)
    result['config'] = str(profile / 'config.json')
    result['database'] = str(database)
    result['executable'] = str(executable)
    return result


def prepare_client(root, base, mode):
    original, _ = locate([root])
    if original is None:
        raise FileNotFoundError('Game client not found. Select the folder that contains OverField Game or launcher.exe.')
    from client_identity import classify, fingerprint, cache_matches, assert_private_destination
    target = base / mode / 'client'
    assert_private_destination(original, target)
    channel = classify(original)
    source_identity = fingerprint(original)
    if cache_matches(original, target / 'client-ready.json'):
        if channel == 'pcgamesdk':
            shutil.copy2(Path(__file__).with_name('LocalUidSDK.dll'),target/'launcher_Data/Plugins/x86_64/PCGameSDK.dll')
        return {'client': str(target / 'launcher.exe'), 'adapter': channel}
    if target.exists():
        # Preserve old client copies rather than delete through resource junctions.
        # Account DB lives outside client and is never moved or reset here.
        backups = base / mode / 'backups'
        backups.mkdir(parents=True, exist_ok=True)
        target.rename(backups / ('client-before-source-change-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')))
    target.mkdir(parents=True, exist_ok=True)
    def junction(destination, source):
        if destination.exists(): return
        result = subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(Path(__file__).with_name('make_junction.ps1')),'-Destination',str(destination),'-Source',str(source)], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode: raise OSError('Could not link immutable client assets: ' + str(source))
    for entry in original.iterdir():
        destination = target / entry.name
        if entry.is_file():
            if not destination.exists(): shutil.copy2(entry,destination)
        elif entry.name != 'launcher_Data':
            # Never share writable channel account/cache directories with official client.
            shutil.copytree(entry, destination, ignore=shutil.ignore_patterns('cache','Cache','*.log','*_log.txt','Cookies*'))
    data = target / 'launcher_Data'
    data.mkdir(exist_ok=True)
    for entry in (original / 'launcher_Data').iterdir():
        destination = data / entry.name
        if entry.is_file(): shutil.copy2(entry,destination)
        elif entry.name == 'Quicksdk':
            # QuickSDK only writes diagnostics here; do not copy official token logs.
            destination.mkdir(exist_ok=True)
        elif entry.name == 'Plugins':
            if not destination.exists(): shutil.copytree(entry,destination,ignore=shutil.ignore_patterns('cache','Cache','*.log','*_log.txt','logs','Cookies*'))
        elif entry.name == 'StreamingAssets':
            destination.mkdir(exist_ok=True)
            for child in entry.iterdir():
                if child.is_file(): shutil.copy2(child,destination/child.name)
                else: junction(destination/child.name,child)
        else: junction(destination,entry)
    if channel == 'pcgamesdk':
        shutil.copy2(Path(__file__).with_name('LocalUidSDK.dll'),data/'Plugins/x86_64/PCGameSDK.dll')
    write_json(target/'client-ready.json',{'source':str(original),'fingerprint':source_identity['identity'],'adapter':channel,'localUidSdk':channel=='pcgamesdk'})
    return {'client':str(target/'launcher.exe'),'adapter':channel}


def previous_route(settings):
    enabled = settings.get('ProxyEnable', {}).get('Value') == 1
    server = settings.get('ProxyServer', {}).get('Value') or ''
    auto = settings.get('AutoConfigURL', {}).get('Value') or ''
    if auto:
        with build_opener(ProxyHandler({})).open(auto, timeout=6) as response:
            old = response.read(2_000_000).decode('utf-8-sig')
        if not re.search(r'function\s+FindProxyForURL\s*\(', old):
            raise ValueError('The existing PAC script does not contain FindProxyForURL.')
        old = re.sub(r'\bFindProxyForURL\b', 'LoloPreviousProxyForURL', old)
        return old, 'LoloPreviousProxyForURL(url, host)'
    if not enabled or not server:
        return '', '"DIRECT"'
    entries = {}
    if '=' in server:
        for entry in server.split(';'):
            if '=' in entry:
                protocol, value = entry.split('=', 1)
                entries[protocol.lower()] = value
    else:
        entries = {'http': server, 'https': server}
    lines = ['function LoloPreviousProxyForURL(url, host) {']
    override = settings.get('ProxyOverride', {}).get('Value') or ''
    for item in override.split(';'):
        if not item or item == '<-loopback>':
            continue
        if item == '<local>':
            lines.append('if (isPlainHostName(host)) return "DIRECT";')
        else:
            lines.append('if (shExpMatch(host, ' + json.dumps(item) + ')) return "DIRECT";')
    for protocol, value in entries.items():
        if protocol in ('http', 'https', 'ftp'):
            lines.append('if (url.indexOf(' + json.dumps(protocol + ':') + ') === 0) return ' + json.dumps('PROXY ' + value) + ';')
    lines.append('return "DIRECT"; }')
    return '\n'.join(lines), 'LoloPreviousProxyForURL(url, host)'


def pac_text(settings, proxy_port):
    old, fallback = previous_route(settings)
    return old + '\nfunction FindProxyForURL(url, host) {\n' + r'''
host = host.toLowerCase().replace(/\.$/, "");
var domain = /^(?:sdkapi[^.]*|dsp-[^.]*|api-callback[^.]*)\.inutan\.com$/.test(host);
var fallbackIp = (host === "14.103.225.205" || host === "14.103.224.57") && /^http:\/\/[^/]+:18881\/dispatch\//.test(url);
''' + f'if (domain || fallbackIp) return "PROXY 127.0.0.1:{proxy_port}";\nreturn {fallback};\n}}\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'pac', 'backup', 'client'])
    parser.add_argument('--root', type=Path)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--mode', choices=MODES, default='solo')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--before', type=Path)
    parser.add_argument('--proxy-port', type=int, default=18890)
    # Explicit language wins over the per-mode default, so a user can run an
    # English world on either channel.
    parser.add_argument('--language', type=int, choices=[1, 2, 3, 4, 5])
    args = parser.parse_args()
    if args.action == 'prepare':
        if args.language is not None:
            LANGUAGE_DEFAULT[args.mode] = args.language
        result = prepare(args.root, args.base, args.mode, args.host)
    elif args.action == 'client':
        result = prepare_client(args.root,args.base,args.mode)
    elif args.action == 'pac':
        settings = json.loads(args.before.read_text(encoding='utf-8-sig'))
        target = args.base / args.mode / 'game.pac'
        target.write_text(pac_text(settings, args.proxy_port), encoding='utf-8')
        result = {'pac': str(target)}
    else:
        database = args.base / args.mode / 'db/lolo.db'
        target = args.base / args.mode / 'backups' / f'lolo-{dt.datetime.now():%Y%m%d-%H%M%S-%f}.db'
        snapshot(database, target)
        result = {'backup': str(target)}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
