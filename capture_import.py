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


PLACEHOLDER = re.compile(r'^(field_\d+|_bytes|unknown_field.*)$')


def is_placeholder(value):
    """A dict carrying only protobuf fallback fields means the message was not decoded."""
    if not isinstance(value, dict) or not value: return False
    return all(isinstance(key, str) and PLACEHOLDER.match(key) for key in value)


def placeholder_hits(value, budget=None):
    """Count fallback field names anywhere in a decoded payload."""
    if budget is None: budget = [20000]
    if budget[0] <= 0: return 0
    budget[0] -= 1
    if isinstance(value, dict):
        total = sum(1 for key in value if isinstance(key, str) and PLACEHOLDER.match(key))
        return total + sum(placeholder_hits(item, budget) for item in value.values())
    if isinstance(value, list):
        return sum(placeholder_hits(item, budget) for item in value[:50])
    return 0


def as_list(value):
    """Accept a list, a single object, a protobuf map or nothing."""
    if value is None: return []
    if isinstance(value, list): return value
    if isinstance(value, dict):
        if is_placeholder(value): return []
        if value and all(isinstance(item, dict) for item in value.values()): return list(value.values())
        return [value]
    return []


def as_mapping(value):
    """Accept a protobuf map or a one-element list; return a plain dict."""
    if isinstance(value, dict): return value
    values = as_list(value)
    return values[0] if len(values) == 1 and isinstance(values[0], dict) else {}


def as_int(value, default=0):
    if isinstance(value, bool): return int(value)
    if isinstance(value, int): return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit(): return int(stripped)
        return ENUMS.get(stripped, default)
    return default


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
    if kind == 'bool':
        # The server stores these as real JSON booleans; a number fails GPB
        # deserialization with "mismatch type bool with number at index ...".
        if isinstance(data, bool): return data
        if isinstance(data, (int, float)): return bool(data)
        if isinstance(data, str):
            lowered = data.strip().lower()
            if lowered in ('true', '1'): return True
            if lowered in ('false', '0', ''): return False
            if lowered in ENUMS: return bool(ENUMS[lowered])
        return bool(data)
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


def capture_quality(main, entries):
    """Report how much of the capture actually decoded into named fields."""
    report = {'placeholderFields': placeholder_hits(main), 'characters': 0,
              'characterPlaceholderFields': 0, 'equipmentResponses': 0, 'inventoryItems': 0}
    characters = as_list(main.get('characters'))
    report['characters'] = len(characters)
    for captured in characters:
        if not isinstance(captured, dict): continue
        report['characterPlaceholderFields'] += placeholder_hits(captured.get('character_appearance')) if 'character_appearance' in captured else 0
        report['characterPlaceholderFields'] += placeholder_hits(captured.get('appearance')) if 'appearance' in captured else 0
        report['characterPlaceholderFields'] += sum(placeholder_hits(preset) for preset in as_list(captured.get('equipment_presets'))[:10])
    for kind, collection in (('GetWeaponRsp','weapons'),('GetArmorRsp','armors'),('GetPosterRsp','posters')):
        for packet in entries.get(kind, []):
            report['equipmentResponses'] += len(as_list((packet or {}).get(collection)))
    for packet in entries.get('PackNotice', []):
        for detail in as_list((packet or {}).get('items')):
            item = (detail or {}).get('main_item') if isinstance(detail, dict) else None
            if isinstance(item, dict) and any(item.get(key) for key in ('base_item','weapon','armor','poster','outfit','inscription')): report['inventoryItems'] += 1
    report['incomplete'] = bool(report['placeholderFields'] or report['characterPlaceholderFields'])
    report['equipmentListsMissing'] = report['equipmentResponses'] == 0
    return report


def build_player(main, entries, report=None):
    report = report if report is not None else {}
    skipped = report.setdefault('skippedEntries', 0)
    from schema_restore import restore_capture
    report['schemaRestore'] = restore_capture(main, entries)
    character_map = {}
    for captured in as_list(main.get('characters')):
        if not isinstance(captured, dict) or 'character_id' not in captured:
            skipped += 1; continue
        data = dict(captured, item_id=captured['character_id'], num=1, item_type='EBagItemTag_Card', pack_type=0)
        appearance = captured.get('appearance')
        if not isinstance(appearance, dict) or is_placeholder(appearance):
            appearance = captured.get('character_appearance')
        data['characterAppearance'] = appearance if isinstance(appearance, dict) and not is_placeholder(appearance) else {'badge': 5000}
        skills = captured.get('skill_list', captured.get('skills', captured.get('character_skill_list')))
        data['characterSkillList'] = {str(as_int(value.get('skill_id'))): value for value in as_list(skills) if isinstance(value, dict) and 'skill_id' in value}
        data['equipmentPresets'] = {}
        for index, preset in enumerate(as_list(captured.get('equipment_presets'))):
            if not isinstance(preset, dict): skipped += 1; continue
            armors = {}
            for value in as_list(preset.get('armors')):
                if not isinstance(value, dict) or is_placeholder(value): skipped += 1; continue
                instance = as_int(value.get('armor_id'))
                if instance <= 0: skipped += 1; continue  # empty slot, not real equipment
                armors[str(as_int(value.get('equip_type')))] = {'equipType': as_int(value.get('equip_type')), 'instanceId': instance}
            posters = {}
            for value in as_list(preset.get('posters')):
                if not isinstance(value, dict) or is_placeholder(value): skipped += 1; continue
                instance = as_int(value.get('poster_id'))
                if instance <= 0: skipped += 1; continue
                posters[str(as_int(value.get('poster_index')))] = {'posterIndex': as_int(value.get('poster_index')), 'instanceId': instance}
            data['equipmentPresets'][str(index)] = {
                'presetIndex': as_int(preset.get('preset_index'), index), 'weaponInstanceId': as_int(preset.get('weapon')),
                'armors': armors, 'posters': posters}
        outfits = {}
        for value in as_list(captured.get('outfit_presets')):
            if isinstance(value, dict): outfits[str(as_int(value.get('preset_index'), len(outfits)))] = value
        data['outfitPresets'] = outfits
        character_map[str(captured['character_id'])] = model('CharacterInfo', data)
    items = {name: {} for name in ('itemBaseInfo','itemWeaponMap','itemArmorMap','itemPosterMap','itemFashionMap','itemInscriptionMap','itemPetInfoMap','itemHeadMap','furnitureItemMap')}
    for packet in entries.get('PackNotice', []):
        for detail in as_list((packet or {}).get('items')):
            if not isinstance(detail, dict): skipped += 1; continue
            item = detail.get('main_item')
            if not isinstance(item, dict): skipped += 1; continue
            base = item.get('base_item')
            if isinstance(base, dict) and 'item_id' in base:
                data = dict(base, item_type=as_int(item.get('item_tag')), pack_type=as_int(detail.get('pack_type')))
                items['itemBaseInfo'][str(base['item_id'])] = model('ItemBaseInfo', data)
            fashion = item.get('outfit')
            if isinstance(fashion, dict) and not is_placeholder(fashion):
                data = dict(fashion, item_id=item.get('item_id'), outfit_id=as_int(fashion.get('outfit_id'), as_int(item.get('item_id'))), item_type=as_int(item.get('item_tag')), num=1)
                schemes = {}
                raw_schemes = fashion.get('dye_schemes')
                if isinstance(raw_schemes, dict) and not is_placeholder(raw_schemes) and not all(isinstance(v, dict) for v in raw_schemes.values()):
                    skipped += 1
                for value in as_list(raw_schemes):
                    if isinstance(value, dict): schemes[str(as_int(value.get('scheme_index'), len(schemes)))] = value
                    else: skipped += 1
                data['dyeSchemes'] = schemes
                items['itemFashionMap'][str(data['outfit_id'])] = model('ItemFashionInfo', data)
                # Fashion entries often carry no base_item block, yet the wardrobe
                # lists only what exists in itemBaseInfo. Register the owned outfit
                # there too, otherwise the fashion map is present but unreachable.
                base_id = str(as_int(item.get('item_id'), as_int(data['outfit_id'])))
                if base_id not in items['itemBaseInfo']:
                    items['itemBaseInfo'][base_id] = model('ItemBaseInfo', {
                        'item_id': as_int(base_id), 'num': 1,
                        'item_type': as_int(item.get('item_tag')), 'pack_type': as_int(detail.get('pack_type'))})
    greatest = 0
    for packet_kind, collection, target, kind, id_key, tag in [
        ('GetWeaponRsp','weapons','itemWeaponMap','ItemWeaponInfo','weapon_id','EBagItemTag_Weapon'),
        ('GetArmorRsp','armors','itemArmorMap','ItemArmorInfo','armor_id','EBagItemTag_Armor'),
        ('GetPosterRsp','posters','itemPosterMap','ItemPosterInfo','poster_id','EBagItemTag_Poster'),
    ]:
        for packet in entries.get(packet_kind, []):
            for captured in as_list((packet or {}).get(collection)):
                if not isinstance(captured, dict) or 'instance_id' not in captured or id_key not in captured:
                    skipped += 1; continue
                greatest = max(greatest, as_int(captured['instance_id']))
                data = dict(captured, item_id=captured[id_key], item_type=tag, num=1, pack_type=0)
                items[target][str(captured['instance_id'])] = model(kind, data)
    items['instanceIndex'] = greatest + 1
    # PackNotice includes gathering tools and inscriptions that equipment-list
    # responses omit. Preserve these variants and their original inventory tags.
    variants=[('weapon','itemWeaponMap','ItemWeaponInfo','weapon_id'),('armor','itemArmorMap','ItemArmorInfo','armor_id'),('poster','itemPosterMap','ItemPosterInfo','poster_id'),('inscription','itemInscriptionMap','ItemInscriptionInfo','inscription_id')]
    for pack in entries.get('PackNotice',[]):
        for detail in as_list((pack or {}).get('items')):
            if not isinstance(detail, dict): continue
            main_item=detail.get('main_item')
            if not isinstance(main_item, dict): continue
            for source,target,kind,id_key in variants:
                value=main_item.get(source)
                if not isinstance(value, dict) or is_placeholder(value): continue
                if 'instance_id' not in value and id_key not in value: continue
                key=as_int(value.get('instance_id'), as_int(value.get(id_key)))
                if 'instance_id' in value:greatest=max(greatest,key)
                data=dict(value,item_id=main_item.get('item_id',value.get(id_key)),item_type=as_int(main_item.get('item_tag')),pack_type=as_int(detail.get('pack_type')),num=1)
                merged=dict(items[target].get(str(key),{}));merged.update(model(kind,data));items[target][str(key)]=merged
    items['instanceIndex']=greatest+1
    team = as_mapping(main.get('team'))
    return {'instanceIndex': greatest + 1, 'character': {'characterMap': character_map, 'placedCharacters': main.get('placed_characters', [])},
            'item': items, 'team': {'TeamInfo': {'Char1': as_int(team.get('char1'), 101001), 'Char2': as_int(team.get('char2')), 'Char3': as_int(team.get('char3'))}},
            'scene': {'worldLevel': as_int(main.get('world_level')), 'cur_pet_instance_id': as_int(main.get('pet_instance_id'))}}


def import_capture(path, profile, expected_uid, replace=False, allow_incomplete=False):
    main, entries = read_capture(path)
    uid = int(main.get('player_label') or main['player_id'])
    if expected_uid and uid != expected_uid: raise ValueError('Capture UID differs from selected UID.')
    database = profile / 'db/lolo.db'
    if not database.exists(): raise ValueError('Prepare this profile before importing.')
    with closing(sqlite3.connect(database)) as connection:
        existing = connection.execute('SELECT 1 FROM of_game WHERE user_id=?', (uid,)).fetchone()
    if existing and not replace: raise ValueError('UID already has progress. Export or confirm a backup before replacing it.')
    quality = capture_quality(main, entries)
    if quality['incomplete'] and not allow_incomplete:
        raise ValueError('这个包的解码不完整：' + str(quality['placeholderFields'] + quality['characterPlaceholderFields'])
                         + ' 个字段是未命名占位符，装备响应 ' + str(quality['equipmentResponses'])
                         + ' 条。导入会得到外观与装备为空的角色。请用本启动器自带的公服采集重新导出，或确认后允许不完整导入。')
    backup = profile / 'backups' / f'before-import-{dt.datetime.now():%Y%m%d-%H%M%S-%f}.db'
    snapshot(database, backup)
    player = build_player(main, entries, quality)
    payload = gzip.compress(json.dumps(player, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    created = dt.datetime.fromtimestamp(as_int(main.get('create_time')), dt.timezone.utc).isoformat()
    appearance = main.get('appearance')
    appearance = appearance if isinstance(appearance, dict) and not is_placeholder(appearance) else {}
    team = as_mapping(main.get('team'))
    with closing(sqlite3.connect(database, timeout=10)) as connection, connection:
        mapping = connection.execute('SELECT sdk_uid FROM of_user WHERE user_id=?', (uid,)).fetchone()
        if not mapping:
            if connection.execute('SELECT 1 FROM of_user WHERE sdk_uid=?', (uid,)).fetchone(): raise ValueError('UID mapping conflicts with another account.')
            connection.execute('INSERT INTO of_user(user_id,sdk_uid,ban) VALUES(?,?,0)', (uid,uid))
        connection.execute('INSERT INTO of_game(user_id,created_at,updated_at,bin_data) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET updated_at=excluded.updated_at,bin_data=excluded.bin_data', (uid,created,now,payload))
        values = {'user_id':uid,'nick_name':main.get('player_name',f'UID {uid}'),'level':main.get('level',1),'exp':main.get('exp',0),'head':main.get('head',41101),'sex':ENUMS.get(main.get('sex'),main.get('sex',0)), 'phone_background':main.get('phone_background',8000),'sign':main.get('sign',''),'created_at':created,'updated_at':now,'birthday':main.get('birthday',''),'is_hide_birthday':main.get('is_hide_birthday',False),'avatar_frame':as_int(appearance.get('avatar_frame')),'pendant':as_int(appearance.get('pendant')),'character_id':as_int(team.get('char1'),101001),'hide_value':main.get('hide_value',0)}
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
    result.update(database=str(database), backup=str(backup), quality=quality,
                  restored=['basic','characters','equipment presets','outfits','team','inventory','weapons','armor','posters','inscriptions','gathering tools','world level'],
                  preservedOnly=['quest state','activities','other modules not persisted by this Lolo version'])
    if quality['skippedEntries']: result['skippedEntries'] = quality['skippedEntries']
    write_json(directory / 'import-report.json', result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['inspect','import','uid','accounts'])
    parser.add_argument('--file',type=Path)
    parser.add_argument('--profile',type=Path)
    parser.add_argument('--uid',type=int,default=0)
    parser.add_argument('--replace',action='store_true')
    parser.add_argument('--allow-incomplete',action='store_true')
    args=parser.parse_args()
    if args.action=='inspect':result=inspect(args.file)
    elif args.action=='import':result=import_capture(args.file,args.profile,args.uid,args.replace,args.allow_incomplete)
    elif args.action=='uid':result={'uid':args.uid,'sdkUid':ensure_uid(args.profile/'db/lolo.db',args.uid)}
    else:
        database=args.profile/'db/lolo.db'
        result=[]
        if database.exists():
            with closing(sqlite3.connect(database)) as connection:
                result=[{'uid':row[0],'name':row[1] or f'UID {row[0]}','level':row[2] or 1} for row in connection.execute('SELECT u.user_id,b.nick_name,b.level FROM of_user u LEFT JOIN of_game_basic b ON u.user_id=b.user_id ORDER BY u.user_id')]
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
