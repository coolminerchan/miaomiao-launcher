"""Restore protobuf fallback names (field_N) in already-decoded capture JSON.

The export in hand carries named fields where the schema matched, but keeps
field_N where decoding fell back to raw wire parsing. Only names proven by the
bundled schema are restored; everything else stays untouched and reported.
"""
from __future__ import annotations

import re

FALLBACK = re.compile(r'^field_(\d+)$')

# field number -> name, taken from the bundled net_pb2 descriptors.
SCHEMAS = {
    'weapon': {1:'weapon_id',2:'instance_id',3:'attack',4:'damage_balance',5:'critical_ratio',6:'random_property',
               7:'wearer_id',8:'level',9:'strength_level',10:'strength_exp',11:'star',12:'inscription1',
               13:'durability',14:'property_index',15:'is_lock'},
    'armor': {1:'armor_id',2:'instance_id',3:'main_property_type',4:'main_property_val',5:'random_property',
              6:'wearer_id',7:'level',8:'strength_level',9:'strength_exp',10:'property_index',15:'is_lock'},
    'poster': {1:'poster_id',2:'instance_id',3:'wearer_id',4:'star'},
    'armorInfo': {1:'equip_type',2:'armor_id'},
    'posterInfo': {1:'poster_index',2:'poster_id'},
    'outfit': {1:'outfit_id',2:'dye_schemes'},
    'dyeScheme': {1:'scheme_index',2:'colors',3:'is_un_lock'},
    'posColor': {1:'pos',2:'red',3:'green',4:'blue'},
}


def restore(value, schema):
    """Rename field_N using one schema; unresolved entries are counted, not dropped."""
    table = SCHEMAS[schema]
    restored = {}
    unresolved = 0
    for key, item in value.items():
        match = FALLBACK.match(key) if isinstance(key, str) else None
        if match:
            name = table.get(int(match.group(1)))
            if name is None:
                unresolved += 1
                continue
            restored[name] = item
        else:
            restored[key] = item
    return restored, unresolved


def restore_item(main_item):
    """Restore the equipment variant nested in a PackNotice item."""
    result = dict(main_item)
    total = 0
    for source, schema in (('weapon','weapon'), ('armor','armor'), ('poster','poster'),
                           ('outfit','outfit')):
        nested = result.get(source)
        if not isinstance(nested, dict):
            continue
        cleaned, unresolved = restore(nested, schema)
        total += unresolved
        if source == 'outfit' and isinstance(cleaned.get('dye_schemes'), dict):
            cleaned['dye_schemes'], extra = restore(cleaned['dye_schemes'], 'dyeScheme')
            total += extra
        result[source] = cleaned
    return result, total


def restore_capture(main, entries):
    """Apply restoration to a whole capture and report what remains unresolved."""
    unresolved = 0
    for packet in entries.get('PackNotice', []):
        for detail in packet.get('items', []) or []:
            if not isinstance(detail, dict):
                continue
            item = detail.get('main_item')
            if isinstance(item, dict):
                detail['main_item'], count = restore_item(item)
                unresolved += count
    for packet in entries.get('PackNotice', []):
        for detail in packet.get('items', []) or []:
            for extra in detail.get('extras', []) or []:
                if isinstance(extra, dict):
                    _, count = restore_item(extra)
                    unresolved += count
    for packet in entries.get('PlayerMainDataRsp', []):
        for character in packet.get('characters', []) or []:
            if not isinstance(character, dict):
                continue
            for preset in character.get('equipment_presets', []) or []:
                if not isinstance(preset, dict):
                    continue
                for key, schema in (('armors','armorInfo'), ('posters','posterInfo')):
                    values = preset.get(key)
                    if isinstance(values, list):
                        renamed = []
                        for value in values:
                            if isinstance(value, dict):
                                value, count = restore(value, schema)
                                unresolved += count
                            renamed.append(value)
                        preset[key] = renamed
            for preset in character.get('outfit_presets', []) or []:
                if isinstance(preset, dict):
                    for key in [k for k in list(preset) if FALLBACK.match(str(k))]:
                        preset.pop(key, None); unresolved += 1
    return {'restoredUnresolved': unresolved}
