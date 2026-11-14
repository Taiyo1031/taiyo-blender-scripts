"""Zone placement CSV owned by Map Roundtrip, independent of UBT.

Exports the meshes inside the chosen zone (or every zone), regardless of selection.
"""
import csv
import math
import os
import tempfile
import bpy
from .chunked import ChunkedOperator
from .constants import CSV_COLUMNS, CSV_ID_KEY, ZONE_KEY
from .placement import build_parent_index, collection_colname, normalize
from .zones import zone_members

INVALID_FILENAME_CHARS = '/\\:*?"<>|\0'


class MRT_OT_ExportZoneCSV(ChunkedOperator, bpy.types.Operator):
    bl_idname = 'mrt.export_zone_csv'
    bl_label = 'Export Zone CSV'
    bl_description = 'Zoneで選んだゾーンの範囲内のMeshをゾーン名.csvへ出力します。選択は不要です。All Zonesではゾーンごとに別ファイルを出力します。正常終了時だけub_zoneを付けます'

    def work(self, context):
        p = context.scene.mrt_props
        choice = p.zone_choice
        if not choice:
            raise ValueError('Choose a zone before exporting its CSV.')
        if not p.zone_csv_dir:
            raise ValueError('CSV Output Folder is empty.')
        self.progress('Finding meshes in zones', 0, 1)
        groups, overlap = yield from zone_members(context, choice)
        groups = {name: objects for name, objects in groups.items() if objects}
        if not groups:
            raise ValueError('No mesh objects inside any zone.' if choice == 'ALL' else 'No mesh objects inside the zone.')
        for name in groups:
            if any(c in name for c in INVALID_FILENAME_CHARS):
                raise ValueError('Zone name contains characters that cannot be used in a CSV filename.')
        folder = bpy.path.abspath(p.zone_csv_dir)
        os.makedirs(folder, exist_ok=True)
        targets = {ob for objects in groups.values() for ob in objects}
        owners = {}
        for collection in (*bpy.data.collections, *(s.collection for s in bpy.data.scenes)):
            for i, ob in enumerate(collection.objects):
                if ob in targets:
                    owners.setdefault(ob, collection)
                if i % 512 == 0:
                    yield
            yield
        # colname = the collection path below the Map collection, so Replace Zone can rebuild the hierarchy.
        parents, roots = build_parent_index(p.map_coll)
        by_collection = {}
        colnames = {}
        for i, (ob, collection) in enumerate(owners.items()):
            if collection not in by_collection:
                by_collection[collection] = collection_colname(collection, p.map_coll, parents, roots)
            colnames[ob] = by_collection[collection]
            if i % 4096 == 0:
                yield
        total = len(targets)
        done = 0
        temps = []  # (temporary path, final path)
        previous_tags = []
        csv_ids = {}
        try:
            for name, objects in groups.items():
                fd, temp = tempfile.mkstemp(dir=folder, prefix='.mrt-', suffix='.csv')
                temps.append((temp, os.path.join(folder, name + '.csv')))
                with os.fdopen(fd, 'w', newline='', encoding='utf-8') as stream:
                    writer = csv.writer(stream)
                    writer.writerow(CSV_COLUMNS)
                    for i, ob in enumerate(objects, 1):
                        matrix = ob.matrix_world
                        location = matrix.to_translation()
                        rotation = matrix.to_euler('XYZ')
                        scale = matrix.to_scale()
                        writer.writerow([i, *(round(v, 6) for v in location),
                                         *(round(math.degrees(v), 6) for v in rotation),
                                         *(round(v, 6) for v in scale),
                                         normalize(ob.name, p.name_mode), colnames.get(ob, '')])
                        csv_ids[ob] = i
                        done += 1
                        self.progress('Exporting zone CSV', done, total)
                        yield
            for name, objects in groups.items():
                for ob in objects:
                    if not ob.is_editable:
                        raise ValueError(f'Cannot tag read-only object: {ob.name}')
                    previous_tags.append((ob, ZONE_KEY in ob, ob.get(ZONE_KEY), CSV_ID_KEY in ob, ob.get(CSV_ID_KEY)))
                    ob[ZONE_KEY] = name
                    ob[CSV_ID_KEY] = csv_ids[ob]
                    yield
            # No yielding between replacing the files and committing the tags.
            for temp, final in temps:
                os.replace(temp, final)
        except BaseException:
            for ob, existed, value, csv_existed, csv_value in previous_tags:
                if existed:
                    ob[ZONE_KEY] = value
                elif ZONE_KEY in ob:
                    del ob[ZONE_KEY]
                if csv_existed:
                    ob[CSV_ID_KEY] = csv_value
                elif CSV_ID_KEY in ob:
                    del ob[CSV_ID_KEY]
                yield
            for temp, _final in temps:
                if os.path.exists(temp):
                    os.remove(temp)
            raise
        if len(groups) == 1:
            name, objects = next(iter(groups.items()))
            note = f'; {overlap} meshes also inside an earlier zone were left to that zone' if overlap else ''
            self.result = f'Exported {len(objects)} meshes to {os.path.join(folder, name + ".csv")}{note}'
        else:
            detail = ' / '.join(f'{name} {len(objects)}' for name, objects in groups.items())
            note = f'; {overlap} meshes inside several zones went to the first one' if overlap else ''
            self.result = f'Exported {total} meshes in {len(groups)} zones to {folder} ({detail}){note}'
