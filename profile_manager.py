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

MODES = {'solo': (18080, 18100, 18200), 'host': (19080, 19100, 19200)}


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


def prepare(root, base, mode, host):
    http, gate, log = MODES[mode]
    address = '127.0.0.1' if mode == 'solo' else lan_ip(host)
    profile = base / mode
    profile.mkdir(parents=True, exist_ok=True)
    (profile / 'logs').mkdir(exist_ok=True)
    result = {'mode': mode, 'profile': str(profile), 'host': address, 'http': http, 'gateway': gate, 'log': log, 'imported': False}
    server = root / 'LoloServer'
    if not (server/'Lolo.exe').exists():server=Path(__file__).with_name('server-kit')
    if not (server / 'Lolo.exe').is_file():
        raise FileNotFoundError('LoloServer/Lolo.exe is missing.')
    data = profile / 'data'
    if not data.exists():
        shutil.copytree(server / 'data', data)
    resources = profile / 'Resource'
    if not resources.exists():
        shutil.copytree(server / 'Resource', resources)
    executable = profile / 'server/Lolo.exe'
    executable.parent.mkdir(exist_ok=True)
    if not executable.exists(): shutil.copy2(server / 'Lolo.exe', executable)
    # Repair only this profile's version map; original installation is read-only.
    import repair_version
    original_client = root/'OverField Game' if (root/'OverField Game/launcher.exe').exists() else root
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
    original = root / 'OverField Game' if (root/'OverField Game/launcher.exe').exists() else root
    target = base / mode / 'client'
    if (target / 'client-ready.json').exists():
        shutil.copy2(Path(__file__).with_name('LocalUidSDK.dll'),target/'launcher_Data/Plugins/x86_64/PCGameSDK.dll')
        return {'client': str(target / 'launcher.exe')}
    target.mkdir(parents=True, exist_ok=True)
    def junction(destination, source):
        if destination.exists(): return
        result = subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(Path(__file__).with_name('make_junction.ps1')),'-Destination',str(destination),'-Source',str(source)], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode: raise OSError('Could not link immutable client assets: ' + str(source))
    for entry in original.iterdir():
        destination = target / entry.name
        if entry.is_file():
            if not destination.exists(): shutil.copy2(entry,destination)
        elif entry.name != 'launcher_Data': junction(destination,entry)
    data = target / 'launcher_Data'
    data.mkdir(exist_ok=True)
    for entry in (original / 'launcher_Data').iterdir():
        destination = data / entry.name
        if entry.is_file(): shutil.copy2(entry,destination)
        elif entry.name == 'Plugins':
            if not destination.exists(): shutil.copytree(entry,destination)
        elif entry.name == 'StreamingAssets':
            destination.mkdir(exist_ok=True)
            for child in entry.iterdir():
                if child.is_file(): shutil.copy2(child,destination/child.name)
                else: junction(destination/child.name,child)
        else: junction(destination,entry)
    shutil.copy2(Path(__file__).with_name('LocalUidSDK.dll'),data/'Plugins/x86_64/PCGameSDK.dll')
    write_json(target/'client-ready.json',{'source':str(original),'localUidSdk':True})
    return {'client':str(target/'launcher.exe')}


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
    args = parser.parse_args()
    if args.action == 'prepare':
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
