"""Selected placement CSV owned by Map Roundtrip, independent of UBT."""
import csv
import math
import os
import tempfile
import bpy
from .chunked import ChunkedOperator
from .constants import CSV_COLUMNS, ZONE_KEY
from .placement import normalize


class MRT_OT_ExportZoneCSV(ChunkedOperator, bpy.types.Operator):
    bl_idname = 'mrt.export_zone_csv'
    bl_label = 'Export Selected CSV'
    bl_description = '選択Meshを現在のゾーン名.csvへ出力し、正常終了時だけub_zoneを付けます。All Zonesでは個別ゾーンを選んでください'

    def work(self, context):
        p = context.scene.mrt_props
        zone = p.zone_choice
        if not zone or zone == 'ALL':
            raise ValueError('Choose one zone before exporting its CSV.')
        if any(c in zone for c in '/\\:*?"<>|\0'):
            raise ValueError('Zone name contains characters that cannot be used in a CSV filename.')
        objects = tuple(ob for ob in context.selected_objects if ob.type == 'MESH')
        if not objects:
            raise ValueError('No mesh objects selected.')
        if not p.zone_csv_dir:
            raise ValueError('CSV Output Folder is empty.')
        folder = bpy.path.abspath(p.zone_csv_dir)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, zone + '.csv')
        targets = set(objects)
        colnames = {}
        for collection in (*bpy.data.collections, *(s.collection for s in bpy.data.scenes)):
            for i, ob in enumerate(collection.objects):
                if ob in targets:
                    colnames.setdefault(ob, collection.name)
                if i % 512 == 0:
                    yield
            yield
        fd, temp = tempfile.mkstemp(dir=folder, prefix='.mrt-', suffix='.csv')
        previous_tags = []
        try:
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
                    self.progress('Exporting zone CSV', i, len(objects))
                    yield
            for ob in objects:
                if not ob.is_editable:
                    raise ValueError(f'Cannot tag read-only object: {ob.name}')
                previous_tags.append((ob, ZONE_KEY in ob, ob.get(ZONE_KEY)))
                ob[ZONE_KEY] = zone
                yield
            # No yielding between replacing the file and committing the tags.
            os.replace(temp, path)
        except BaseException:
            for ob, existed, value in previous_tags:
                if existed:
                    ob[ZONE_KEY] = value
                elif ZONE_KEY in ob:
                    del ob[ZONE_KEY]
                yield
            if os.path.exists(temp):
                os.remove(temp)
            raise
        p.zone_override = zone
        self.result = f'Exported {len(objects)} meshes to {path}'
