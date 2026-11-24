"""Validate a decoded capture and import supported player fields without replacing other UIDs."""
from __future__ import annotations
import argparse
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import zipfile
from contextlib import closing
from profile_manager import snapshot, write_json

BASE = Path(__file__).resolve().parent
SCHEMA = json.loads((BASE / 'model_schema.json').read_text(encoding='utf-8'))
ENUMS = SCHEMA['enums']


def normalize(value): return re.sub('[^a-z0-9]', '', value.lower())


def model(kind, data):
    if data is None: return None
    if kind.startswith('*'): return model(kind[1:], data)
    if kind.startswith('[]'):
        return [model(kind[2:], value) for value in data]
    if kind.startswith('map['):
        nested = kind.split(']', 1)[1]
        return {str(key): model(nested, value) for key, value in data.items()}
    if kind in SCHEMA['models'] and isinstance(data, dict):
        normalized = {normalize(key): value for key, value in data.items()}
        result = {}
        for field in SCHEMA['models'][kind]:
            if 'embedded' in field:
                result.update(model(field['embedded'], data)); continue
            lookup = normalize(field['key'])
            if lookup in normalized: result[field['key']] = model(field['type'], normalized[lookup])
        return result
    if kind.startswith(('uint', 'int', 'proto.')):
        if isinstance(data, str) and data in ENUMS: return ENUMS[data]
        return int(data)
    if kind == 'RandomPropertys': return [model('RandomProperty', value) for value in data]
    if isinstance(data, dict):
        return {key: model('', value) for key, value in data.items()}
    if isinstance(data, list): return [model('', value) for value in data]
    return ENUMS.get(data, data) if isinstance(data, str) else data


def read_capture(path):
    entries = {}
    with zipfile.ZipFile(path) as archive:
        if sum(item.file_size for item in archive.infolist()) > 512 * 1024 * 1024:
            raise ValueError('Capture is too large.')
        for item in archive.infolist():
            parts = PurePosixPath(item.filename)
            if parts.is_absolute() or '..' in parts.parts or '\\' in item.filename:
                raise ValueError('Archive contains an unsafe path.')
            if item.filename.startswith(('export/json/', 'json/')) and '_s2c_' in item.filename and item.filename.endswith('.json'):
                match = re.search(r'_s2c_\d+_([A-Za-z0-9_]+)\.json$', item.filename)
                if match:
                    entries.setdefault(match.group(1), []).append(json.loads(archive.read(item)))
    main = entries.get('PlayerMainDataRsp', [])
    if len({int(value['player_id']) for value in main}) != 1:
        raise ValueError('Capture must contain one unambiguous PlayerMainDataRsp UID.')
    player = main[-1]
    if player.get('status') not in (1, 'StatusCode_OK'):
        raise ValueError('PlayerMainDataRsp was not successful.')
    return player, entries


def inspect(path):
    player, entries = read_capture(path)
    return {'uid': int(player.get('player_label') or player['player_id']), 'internalId': int(player['player_id']), 'name': player.get('player_name', ''), 'level': player.get('level', 1),
            'characters': len(player.get('characters', [])), 'quests': len(player.get('quest_detail', {}).get('quests', [])),
            'capturedMessages': sum(len(value) for value in entries.values()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def schema_database(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as origin, closing(sqlite3.connect(target)) as database, database:
        for (sql,) in origin.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            database.execute(sql)
        for (sql,) in origin.execute("SELECT sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"):
            database.execute(sql)


def ensure_uid(database, uid):
    if not 1 <= uid <= 4294967295: raise ValueError('UID must be a nonzero uint32.')
    with closing(sqlite3.connect(database, timeout=10)) as connection, connection:
        row = connection.execute('SELECT sdk_uid FROM of_user WHERE user_id=?', (uid,)).fetchone()
        if row: return int(row[0])
        if connection.execute('SELECT 1 FROM of_user WHERE sdk_uid=?', (uid,)).fetchone():
            raise ValueError('This UID conflicts with an existing account mapping.')
        connection.execute('INSERT INTO of_user(user_id,sdk_uid,ban) VALUES(?,?,0)', (uid, uid))
        return uid


def build_player(main, entries):
    character_map = {}
    for captured in main.get('characters', []):
        data = dict(captured, item_id=captured['character_id'], num=1, item_type='EBagItemTag_Card', pack_type=0)
        data['characterAppearance'] = captured.get('appearance', captured.get('character_appearance', {'badge': 5000}))
        data['characterSkillList'] = {str(value['skill_id']): value for value in captured.get('skill_list', captured.get('skills', captured.get('character_skill_list', [])))}
        data['equipmentPresets'] = {}
        for preset in captured.get('equipment_presets', []):
            data['equipmentPresets'][str(preset.get('preset_index', 0))] = {
                'presetIndex': preset.get('preset_index', 0), 'weaponInstanceId': preset.get('weapon', 0),
                'armors': {str(ENUMS.get(value.get('equip_type', ''), value.get('equip_type', 0))): {'equipType': value.get('equip_type', 0), 'instanceId': value.get('armor_id', 0)} for value in preset.get('armors', [])},
                'posters': {str(ENUMS.get(value.get('poster_index', ''), value.get('poster_index', 0))): {'posterIndex': value.get('poster_index', 0), 'instanceId': value.get('poster_id', 0)} for value in preset.get('posters', [])}}
        data['outfitPresets'] = {str(value.get('preset_index', 0)): value for value in captured.get('outfit_presets', [])}
        character_map[str(captured['character_id'])] = model('CharacterInfo', data)
    items = {name: {} for name in ('itemBaseInfo','itemWeaponMap','itemArmorMap','itemPosterMap','itemFashionMap','itemInscriptionMap','itemPetInfoMap','itemHeadMap','furnitureItemMap')}
    for packet in entries.get('PackNotice', []):
        for detail in packet.get('items', []):
            item = detail.get('main_item', {})
            base = item.get('base_item')
            if base:
                data = dict(base, item_type=item.get('item_tag', 0), pack_type=detail.get('pack_type', 0))
                items['itemBaseInfo'][str(base['item_id'])] = model('ItemBaseInfo', data)
            fashion = item.get('outfit')
            if fashion:
                data = dict(fashion, item_id=item['item_id'], outfit_id=fashion.get('outfit_id', item['item_id']), item_type=item.get('item_tag', 0), num=1)
                data['dyeSchemes'] = {str(value.get('scheme_index', 0)): value for value in fashion.get('dye_schemes', [])}
                items['itemFashionMap'][str(data['outfit_id'])] = model('ItemFashionInfo', data)
    greatest = 0
    for packet_kind, collection, target, kind, id_key, tag in [
        ('GetWeaponRsp','weapons','itemWeaponMap','ItemWeaponInfo','weapon_id','EBagItemTag_Weapon'),
        ('GetArmorRsp','armors','itemArmorMap','ItemArmorInfo','armor_id','EBagItemTag_Armor'),
        ('GetPosterRsp','posters','itemPosterMap','ItemPosterInfo','poster_id','EBagItemTag_Poster'),
    ]:
        for packet in entries.get(packet_kind, []):
            for captured in packet.get(collection, []):
                greatest = max(greatest, int(captured['instance_id']))
                data = dict(captured, item_id=captured[id_key], item_type=tag, num=1, pack_type=0)
                items[target][str(captured['instance_id'])] = model(kind, data)
    items['instanceIndex'] = greatest + 1
    # PackNotice includes gathering tools and inscriptions that equipment-list
    # responses omit. Preserve these variants and their original inventory tags.
    variants=[('weapon','itemWeaponMap','ItemWeaponInfo','weapon_id'),('armor','itemArmorMap','ItemArmorInfo','armor_id'),('poster','itemPosterMap','ItemPosterInfo','poster_id'),('inscription','itemInscriptionMap','ItemInscriptionInfo','inscription_id')]
    for pack in entries.get('PackNotice',[]):
        for detail in pack.get('items',[]):
            main_item=detail.get('main_item',{})
            for source,target,kind,id_key in variants:
                value=main_item.get(source)
                if not value:continue
                key=int(value.get('instance_id',value[id_key]))
                if 'instance_id' in value:greatest=max(greatest,key)
                data=dict(value,item_id=main_item.get('item_id',value[id_key]),item_type=main_item.get('item_tag',0),pack_type=detail.get('pack_type',0),num=1)
                merged=dict(items[target].get(str(key),{}));merged.update(model(kind,data));items[target][str(key)]=merged
    items['instanceIndex']=greatest+1
    team = main.get('team', {})
    return {'instanceIndex': greatest + 1, 'character': {'characterMap': character_map, 'placedCharacters': main.get('placed_characters', [])},
            'item': items, 'team': {'TeamInfo': {'Char1': team.get('char1', 101001), 'Char2': team.get('char2', 0), 'Char3': team.get('char3', 0)}},
            'scene': {'worldLevel': main.get('world_level', 0), 'cur_pet_instance_id': main.get('pet_instance_id', 0)}}


def import_capture(path, profile, expected_uid, replace=False):
    main, entries = read_capture(path)
    uid = int(main.get('player_label') or main['player_id'])
    if expected_uid and uid != expected_uid: raise ValueError('Capture UID differs from selected UID.')
    database = profile / 'db/lolo.db'
    if not database.exists(): raise ValueError('Prepare this profile before importing.')
    with closing(sqlite3.connect(database)) as connection:
        existing = connection.execute('SELECT 1 FROM of_game WHERE user_id=?', (uid,)).fetchone()
    if existing and not replace: raise ValueError('UID already has progress. Export or confirm a backup before replacing it.')
    backup = profile / 'backups' / f'before-import-{dt.datetime.now():%Y%m%d-%H%M%S-%f}.db'
    snapshot(database, backup)
    player = build_player(main, entries)
    payload = gzip.compress(json.dumps(player, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    created = dt.datetime.fromtimestamp(int(main.get('create_time', 0)), dt.timezone.utc).isoformat()
    with closing(sqlite3.connect(database, timeout=10)) as connection, connection:
        mapping = connection.execute('SELECT sdk_uid FROM of_user WHERE user_id=?', (uid,)).fetchone()
        if not mapping:
            if connection.execute('SELECT 1 FROM of_user WHERE sdk_uid=?', (uid,)).fetchone(): raise ValueError('UID mapping conflicts with another account.')
            connection.execute('INSERT INTO of_user(user_id,sdk_uid,ban) VALUES(?,?,0)', (uid,uid))
        connection.execute('INSERT INTO of_game(user_id,created_at,updated_at,bin_data) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET updated_at=excluded.updated_at,bin_data=excluded.bin_data', (uid,created,now,payload))
        values = {'user_id':uid,'nick_name':main.get('player_name',f'UID {uid}'),'level':main.get('level',1),'exp':main.get('exp',0),'head':main.get('head',41101),'sex':ENUMS.get(main.get('sex'),main.get('sex',0)), 'phone_background':main.get('phone_background',8000),'sign':main.get('sign',''),'created_at':created,'updated_at':now,'birthday':main.get('birthday',''),'is_hide_birthday':main.get('is_hide_birthday',False),'avatar_frame':main.get('appearance',{}).get('avatar_frame',0),'pendant':main.get('appearance',{}).get('pendant',0),'character_id':main.get('team',{}).get('char1',101001),'hide_value':main.get('hide_value',0)}
        columns = {row[1] for row in connection.execute('PRAGMA table_info(of_game_basic)')}
        values = {key:value for key,value in values.items() if key in columns}
        names=list(values)
        update=','.join(f'{key}=excluded.{key}' for key in names if key!='user_id')
        connection.execute(f'INSERT INTO of_game_basic({",".join(names)}) VALUES({",".join("?" for _ in names)}) ON CONFLICT(user_id) DO UPDATE SET {update}', list(values.values()))
    directory = profile / 'accounts' / str(uid)
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / 'main-data.json', main)
    write_json(directory / 'captured-responses.json', entries)
    result = inspect(path)
    result.update(database=str(database), backup=str(backup), restored=['basic','characters','equipment presets','outfits','team','inventory','weapons','armor','posters','inscriptions','gathering tools','world level'],
                  preservedOnly=['quest state','activities','other modules not persisted by this Lolo version'])
    write_json(directory / 'import-report.json', result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['inspect','import','uid','accounts'])
    parser.add_argument('--file',type=Path)
    parser.add_argument('--profile',type=Path)
    parser.add_argument('--uid',type=int,default=0)
    parser.add_argument('--replace',action='store_true')
    args=parser.parse_args()
    if args.action=='inspect':result=inspect(args.file)
    elif args.action=='import':result=import_capture(args.file,args.profile,args.uid,args.replace)
    elif args.action=='uid':result={'uid':args.uid,'sdkUid':ensure_uid(args.profile/'db/lolo.db',args.uid)}
    else:
        database=args.profile/'db/lolo.db'
        result=[]
        if database.exists():
            with closing(sqlite3.connect(database)) as connection:
                result=[{'uid':row[0],'name':row[1] or f'UID {row[0]}','level':row[2] or 1} for row in connection.execute('SELECT u.user_id,b.nick_name,b.level FROM of_user u LEFT JOIN of_game_basic b ON u.user_id=b.user_id ORDER BY u.user_id')]
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
