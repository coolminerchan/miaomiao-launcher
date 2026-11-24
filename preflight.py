"""Read-only local readiness check. Never launches services or lists account IDs."""
from pathlib import Path
from contextlib import closing
import argparse
import json
import sqlite3
import sys

BASE = Path(__file__).resolve().parent
FILES = ['OverFieldLauncher.exe','LocalUidSDK.dll','launcher.ico','World-Control.ps1','Lan-Firewall.ps1','profile_manager.py','capture_import.py','room_gateway.py','model_schema.json','proto_fields.json','service_runner.py','make_junction.ps1','repair_version.py']

def check(root=None, mode='host'):
    failures=[]
    warnings=[]
    if sys.version_info < (3,12):
        failures.append('Use Python 3.12 or later; supported launcher environment is Python 3.12 x64.')
    for name in FILES:
        if not (BASE/name).is_file(): failures.append('Missing launcher file: '+name)
    server=root/'LoloServer' if root and (root/'LoloServer/Lolo.exe').is_file() else BASE/'server-kit'
    for name in ['Lolo.exe','config.json','db/lolo.db']:
        if not (server/name).is_file(): failures.append('Missing service component: '+name)
    for name in ['data','Resource']:
        path=server/name
        if not path.is_dir() or not any(path.iterdir()): failures.append('Missing or empty service resources: '+name)
    config=server/'config.json'
    if config.is_file():
        try:
            document=json.loads(config.read_text(encoding='utf-8-sig'))
            for key in ['HttpNet','GateWay','LogServer','DB']:
                if not isinstance(document.get(key),dict): failures.append('Missing config section: '+key)
        except (ValueError,OSError): failures.append('Cannot parse service config.json.')
    database=server/'db/lolo.db'
    if database.is_file():
        try:
            with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True)) as connection:
                tables={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                for table in ['of_user','of_game','of_game_basic']:
                    if table not in tables: failures.append('Missing database table: '+table)
                    elif connection.execute('SELECT EXISTS(SELECT 1 FROM "'+table+'" LIMIT 1)').fetchone()[0]:
                        warnings.append('Template contains account/progress rows; public builds ignore those rows. Never distribute this database.')
                        break
        except sqlite3.Error: failures.append('Cannot read template database schema.')
    if mode=='solo':
        client=root/'OverField Game' if root and (root/'OverField Game/launcher.exe').is_file() else root
        if not client or not (client/'launcher.exe').is_file() or not (client/'launcher_Data').is_dir():
            failures.append('Solo mode requires a compatible local PC game client selected with --game-root.')
    warnings.append('Local UID login is not ownership authentication. Do not expose a personal-save host to untrusted players.')
    return {'ready':not failures,'missing':failures,'warnings':list(dict.fromkeys(warnings)),'scope':'Files/schema only; no game startup, networking, authentication or protocol compatibility test.'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-root',type=Path)
    parser.add_argument('--mode',choices=['solo','host'],default='host')
    args=parser.parse_args()
    result=check(args.game_root,args.mode)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['ready'] else 2

if __name__=='__main__':
    sys.exit(main())
