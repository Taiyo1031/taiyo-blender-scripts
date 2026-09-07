"""Portable configuration presets, separate from restriction-state snapshots."""
import json
import os
from pathlib import Path
import bpy
from .definitions import KEYS, SCOPE_FIELDS


FIELDS = KEYS + SCOPE_FIELDS


def path():
    folder = bpy.utils.extension_path_user(__package__, path='presets', create=True) if __package__.startswith('bl_ext.') else bpy.utils.user_resource('CONFIG', path='hierarchy_restriction_manager', create=True)
    return Path(folder) / 'presets.json'


def read():
    file = path()
    if not file.exists():
        return {}
    value = json.loads(file.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or value.get('version') != 1 or not isinstance(value.get('presets'), dict):
        raise ValueError('Unsupported preset file format')
    return value['presets']


def write(values):
    file = path()
    temp = file.with_suffix('.tmp')
    temp.write_text(json.dumps({'version': 1, 'presets': values}, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, file)


def capture(settings):
    values = {name: getattr(settings, name) for name in FIELDS}
    values['object_types'] = sorted(values['object_types'])
    if settings.preset_include_target and settings.target:
        collection = settings.target
        values['target'] = {'file': bpy.data.filepath, 'name': collection.name,
                            'library': collection.library.filepath if collection.library else ''}
    return values


def apply(settings, values):
    if not isinstance(values, dict):
        raise ValueError('Invalid preset')
    # Validate against RNA in advance so a malformed preset cannot partly update settings.
    clean = {}
    for name in FIELDS:
        if name not in values:
            continue
        value = values[name]
        prop = settings.bl_rna.properties[name]
        if prop.type == 'ENUM':
            valid = {item.identifier for item in prop.enum_items}
            if prop.is_enum_flag:
                if not isinstance(value, list) or not set(value) <= valid:
                    raise ValueError(f'Invalid preset value: {name}')
                value = set(value)
            elif value not in valid:
                raise ValueError(f'Invalid preset value: {name}')
        elif prop.type == 'BOOLEAN' and not isinstance(value, bool):
            raise ValueError(f'Invalid Boolean: {name}')
        elif prop.type == 'STRING' and not isinstance(value, str):
            raise ValueError(f'Invalid text: {name}')
        elif prop.type == 'INT' and (type(value) is not int or not prop.hard_min <= value <= prop.hard_max):
            raise ValueError(f'Invalid number: {name}')
        clean[name] = value
    target = values.get('target')
    if target is not None and (not isinstance(target, dict) or not all(isinstance(target.get(k), str) for k in ('file', 'name', 'library'))):
        raise ValueError('Invalid target reference')
    for name, value in clean.items():
        setattr(settings, name, value)
    if target is not None:
        settings.target = None
        if target['file'] == bpy.data.filepath:
            collection = bpy.data.collections.get((target['name'], target['library'] or None))
            settings.target = collection
        if settings.target is None:
            return 'Preset loaded. Saved target is unavailable; choose a Collection.'
    return 'Preset loaded into settings. Press Apply to change the hierarchy.'
