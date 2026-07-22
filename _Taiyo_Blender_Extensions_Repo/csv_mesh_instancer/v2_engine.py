"""Stable-ID state and read-only change preview for CSV Mesh Instancer v2."""

import base64
import json
import math
import os
import time
import zlib

import bpy
from mathutils import Euler


SCHEMA_VERSION = 2
OUTPUT_MANAGED_KEY = "csvmi_output_managed"
OUTPUT_SCHEMA_KEY = "csvmi_schema_version"
OUTPUT_STATE_TEXT_KEY = "csvmi_state_text"
OBJECT_ID_KEY = "csvmi_id"
OBJECT_SCHEMA_KEY = "csvmi_schema_version"
STATE_TEXT_PREFIX = ".CSVMI_State_"
STATE_TEXT_LINE_LENGTH = 65536
ROW_NAME = 0
ROW_ID = 1
ROW_LINE = 2
ROW_TX = 3
ROW_TY = 4
ROW_TZ = 5
ROW_RX = 6
ROW_RY = 7
ROW_RZ = 8
ROW_SX = 9
ROW_SY = 10
ROW_SZ = 11
ROW_EXTRA = 12
LOCATION_SCALE_TOLERANCE = 1.0e-5
ROTATION_TOLERANCE_RADIANS = 1.0e-4


STATUS_LABELS = {
    "NEW": "New",
    "CSV_CHANGED": "CSV Changed",
    "BLENDER_EDITED": "Blender Edited",
    "CONFLICT": "Conflict",
    "MESH_CHANGED": "Mesh Changed",
    "CSV_DELETED": "CSV Deleted",
    "BLENDER_DELETED": "Blender Deleted",
    "DELETED": "Deleted",
    "FILTERED_OUT": "Filtered Out",
    "MISSING_SOURCE": "Missing Source",
}


class PreviewData:
    __slots__ = (
        "changes",
        "summary",
        "state",
        "output",
        "resolved",
        "cache",
        "selected_names",
        "created_at",
        "filtered_indices",
    )

    def __init__(self, changes, summary, state, output, resolved, cache, selected_names):
        self.changes = changes
        self.summary = summary
        self.state = state
        self.output = output
        self.resolved = resolved
        self.cache = cache
        self.selected_names = selected_names
        self.created_at = time.perf_counter()
        self.filtered_indices = list(range(len(changes)))


def row_transform(row):
    return tuple(float(row[index]) for index in range(ROW_TX, ROW_SZ + 1))


def object_transform(obj):
    rotation = obj.rotation_euler
    return (
        float(obj.location.x),
        float(obj.location.y),
        float(obj.location.z),
        float(rotation.x),
        float(rotation.y),
        float(rotation.z),
        float(obj.scale.x),
        float(obj.scale.y),
        float(obj.scale.z),
    )


def transform_equal(left, right):
    if left is None or right is None or len(left) != 9 or len(right) != 9:
        return False
    for index in (0, 1, 2, 6, 7, 8):
        if abs(float(left[index]) - float(right[index])) > LOCATION_SCALE_TOLERANCE:
            return False
    # Blender stores Euler components as float32. Comparing their quaternion
    # conversion first can magnify harmless storage noise near 180 degrees.
    # Preserve the quaternion test for alternate Euler representations, but
    # accept a direct wrapped-component match at the same fixed tolerance.
    if all(
        abs((float(left[index]) - float(right[index]) + math.pi) % (2.0 * math.pi) - math.pi)
        <= ROTATION_TOLERANCE_RADIANS
        for index in (3, 4, 5)
    ):
        return True
    left_q = Euler(tuple(float(value) for value in left[3:6]), 'XYZ').to_quaternion()
    right_q = Euler(tuple(float(value) for value in right[3:6]), 'XYZ').to_quaternion()
    dot = min(1.0, max(-1.0, abs(left_q.dot(right_q))))
    return 2.0 * math.acos(dot) <= ROTATION_TOLERANCE_RADIANS


def row_attributes(cache, row):
    return {
        name: row[ROW_EXTRA][index]
        for index, name in enumerate(cache.extra_columns)
    }


def selected_row_properties(cache, row, selected_names):
    attributes = row_attributes(cache, row)
    return {name: attributes[name] for name in selected_names if attributes.get(name) is not None}


def current_object_properties(obj, names):
    return {name: obj[name] for name in names if name in obj}


def object_preview_signature(obj, transform=None):
    if obj is None or obj.name not in bpy.data.objects:
        return None
    managed_names = ()
    raw_names = obj.get("csvmi_custom_property_keys", "")
    if isinstance(raw_names, str) and raw_names:
        try:
            managed_names = tuple(json.loads(raw_names))
        except (TypeError, ValueError):
            managed_names = ()
    properties = tuple(
        sorted((name, repr(obj[name])) for name in managed_names if isinstance(name, str) and name in obj)
    )
    return (
        obj.name,
        obj.type,
        obj.data.name if obj.data else "",
        tuple(round(value, 9) for value in (transform or object_transform(obj))),
        properties,
    )


def _iter_collection_tree(root):
    if root is None:
        return
    stack = [root]
    seen = set()
    while stack:
        collection = stack.pop()
        pointer = collection.as_pointer()
        if pointer in seen:
            continue
        seen.add(pointer)
        yield collection
        stack.extend(reversed(collection.children[:]))


def managed_scene_index(output):
    result = {}
    transforms = {}
    if output is None:
        return result, transforms
    collections = tuple(_iter_collection_tree(output))
    seen_pointers = set()
    for collection in collections:
        count = len(collection.objects)
        locations = [0.0] * (count * 3)
        rotations = [0.0] * (count * 3)
        scales = [0.0] * (count * 3)
        if count:
            collection.objects.foreach_get("location", locations)
            collection.objects.foreach_get("rotation_euler", rotations)
            collection.objects.foreach_get("scale", scales)
        for index, obj in enumerate(collection.objects):
            pointer = obj.as_pointer()
            if pointer in seen_pointers:
                continue
            seen_pointers.add(pointer)
            if OBJECT_ID_KEY not in obj:
                raise ValueError(
                    f"The v2 output contains an unmanaged Object: {obj.name}. "
                    "Move it outside the managed Collection before Preview."
                )
            identity = str(obj[OBJECT_ID_KEY])
            if identity in result:
                raise ValueError(f"The v2 output contains duplicate Object ID {identity!r}.")
            result[identity] = obj
            offset = index * 3
            transforms[identity] = (
                locations[offset], locations[offset + 1], locations[offset + 2],
                rotations[offset], rotations[offset + 1], rotations[offset + 2],
                scales[offset], scales[offset + 1], scales[offset + 2],
            )
    return result, transforms


def managed_objects_by_id(output, state=None):
    return managed_scene_index(output)[0]


def encode_state(state):
    payload = json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b85encode(zlib.compress(payload, 1)).decode("ascii")


class StateTextWriter:
    """Incrementally encode a large ID registry, then atomically swap its Text."""

    def __init__(self, output, state):
        self.output = output
        self.state = state
        self.state["schema"] = SCHEMA_VERSION
        self.records = list(self.state.get("records", {}).items())
        self.index = 0
        self.compressor = zlib.compressobj(1)
        self.compressed_remainder = b""
        self.encoded_parts = []
        self.finished_encoding = False
        self.committed = False
        metadata = {key: value for key, value in self.state.items() if key != "records"}
        metadata_json = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
        separator = "," if len(metadata) else ""
        self._feed((metadata_json[:-1] + separator + '"records":{').encode("utf-8"))

    @property
    def total(self):
        return len(self.records)

    def _feed(self, payload):
        compressed = self.compressor.compress(payload)
        if not compressed:
            return
        combined = self.compressed_remainder + compressed
        complete_length = len(combined) - (len(combined) % 4)
        if complete_length:
            self.encoded_parts.append(
                base64.b85encode(combined[:complete_length]).decode("ascii")
            )
        self.compressed_remainder = combined[complete_length:]

    def step(self, budget_seconds):
        if self.finished_encoding:
            return True
        deadline = time.perf_counter() + max(0.0001, budget_seconds)
        did_work = False
        while self.index < len(self.records) and (not did_work or time.perf_counter() < deadline):
            did_work = True
            identity, record = self.records[self.index]
            prefix = b"," if self.index else b""
            fragment = (
                json.dumps(str(identity), ensure_ascii=False, separators=(",", ":"))
                + ":"
                + json.dumps(record, ensure_ascii=False, separators=(",", ":"))
            ).encode("utf-8")
            self._feed(prefix + fragment)
            self.index += 1
        if self.index >= len(self.records):
            self._feed(b"}}")
            tail = self.compressed_remainder + self.compressor.flush()
            self.compressed_remainder = b""
            if tail:
                self.encoded_parts.append(base64.b85encode(tail).decode("ascii"))
            self.finished_encoding = True
        return self.finished_encoding

    def commit(self):
        if not self.finished_encoding:
            raise RuntimeError("The stable ID registry is not fully encoded.")
        encoded = "".join(self.encoded_parts)
        stored = "\n".join(
            encoded[index:index + STATE_TEXT_LINE_LENGTH]
            for index in range(0, len(encoded), STATE_TEXT_LINE_LENGTH)
        )
        text_name = f"{STATE_TEXT_PREFIX}{self.output.name}_{time.time_ns()}"
        new_text = bpy.data.texts.new(text_name)
        try:
            new_text.from_string(stored)
            old_name = self.output.get(OUTPUT_STATE_TEXT_KEY, "")
            self.output[OUTPUT_MANAGED_KEY] = True
            self.output[OUTPUT_SCHEMA_KEY] = SCHEMA_VERSION
            self.output[OUTPUT_STATE_TEXT_KEY] = new_text.name
            old_text = bpy.data.texts.get(old_name) if isinstance(old_name, str) else None
            if old_text is not None and old_text != new_text:
                bpy.data.texts.remove(old_text)
            self.committed = True
            return new_text
        except Exception:
            if new_text.name in bpy.data.texts:
                bpy.data.texts.remove(new_text)
            raise


def decode_state(text):
    try:
        compact = "".join(text.split())
        payload = zlib.decompress(base64.b85decode(compact.encode("ascii")))
        state = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"The CSV Mesh Instancer state is corrupted: {exc}") from exc
    if not isinstance(state, dict) or int(state.get("schema", 0)) != SCHEMA_VERSION:
        raise ValueError("The output state schema is not supported by CSV Mesh Instancer v2.")
    if not isinstance(state.get("records"), dict):
        raise ValueError("The output state has no valid ID registry.")
    return state


def read_output_state(output, identity_column=None):
    if output is None:
        return {
            "schema": SCHEMA_VERSION,
            "id_column": identity_column or "id",
            "records": {},
        }
    if not bool(output.get(OUTPUT_MANAGED_KEY, False)):
        raise ValueError(
            "A same-named regular Collection already exists. Choose another output name or remove it."
        )
    if int(output.get(OUTPUT_SCHEMA_KEY, 0)) != SCHEMA_VERSION:
        raise ValueError(
            "This Collection was not created by CSV Mesh Instancer v2. "
            "Delete it or choose another output name; v1 output migration is not supported."
        )
    text_name = output.get(OUTPUT_STATE_TEXT_KEY, "")
    text = bpy.data.texts.get(text_name) if isinstance(text_name, str) else None
    if text is None:
        raise ValueError("The v2 output state Text datablock is missing.")
    state = decode_state(text.as_string())
    if identity_column and state.get("id_column") != identity_column:
        raise ValueError(
            f"This output uses identity column {state.get('id_column')!r}; "
            f"the loaded CSV uses {identity_column!r}."
        )
    return state


def write_output_state(output, state):
    writer = StateTextWriter(output, state)
    while not writer.step(3600.0):
        pass
    return writer.commit()


def remove_output_state(output):
    if output is None:
        return
    text_name = output.get(OUTPUT_STATE_TEXT_KEY, "")
    text = bpy.data.texts.get(text_name) if isinstance(text_name, str) else None
    if text is not None:
        bpy.data.texts.remove(text)
    if OUTPUT_STATE_TEXT_KEY in output:
        del output[OUTPUT_STATE_TEXT_KEY]


def selected_filter_rules(props):
    rules = []
    for rule in props.attribute_filters:
        if not rule.enabled or not rule.attribute:
            continue
        selected = {item.value for item in rule.values if item.selected}
        if rule.manual_values.strip():
            selected.update(part.strip() for part in rule.manual_values.split(",") if part.strip())
        rules.append((rule.attribute, selected))
    return tuple(rules)


def attributes_match_filters(attributes, rules):
    if not rules:
        return True
    for attribute, accepted in rules:
        value = attributes.get(attribute)
        key = "" if value is None else str(value)
        if not accepted or key not in accepted:
            return False
    return True


def _domain_kind(csv_changed, blender_changed, has_override=False):
    if csv_changed and (blender_changed or has_override):
        return "CONFLICT"
    if csv_changed:
        return "CSV"
    if blender_changed:
        return "BLENDER"
    return ""


def _status_for(change):
    if change["object_kind"]:
        return change["object_kind"]
    kinds = (change["transform_kind"], change["mesh_kind"], change["props_kind"])
    if "CONFLICT" in kinds:
        return "CONFLICT"
    if change.get("missing_source"):
        return "MISSING_SOURCE"
    if change.get("attribute_changed") or change.get("collection_changed"):
        return "CSV_CHANGED"
    if change["mesh_kind"]:
        return "MESH_CHANGED"
    if "CSV" in kinds:
        return "CSV_CHANGED"
    if "BLENDER" in kinds:
        return "BLENDER_EDITED"
    return ""


def _change_search_blob(change):
    old = change.get("old") or {}
    fields = [
        change["identity"],
        change["zone"],
        change["objname"],
        STATUS_LABELS.get(change["status"], change["status"]),
        old.get("objname", ""),
        old.get("source_mesh", ""),
        change.get("new_source_mesh", ""),
    ]
    fields.extend(change.get("changed_properties", ()))
    return "\x1f".join(str(field).casefold() for field in fields if field is not None)


def _base_change(identity, row, old, obj, source, attributes, selected_props, zone):
    return {
        "identity": identity,
        "row": row,
        "old": old,
        "obj": obj,
        "source": source,
        "attributes": attributes,
        "selected_props": selected_props,
        "zone": zone,
        "objname": row[ROW_NAME] if row is not None else (old or {}).get("objname", ""),
        "new_source_mesh": source.data.name if source is not None else "",
        "transform_kind": "",
        "mesh_kind": "",
        "props_kind": "",
        "object_kind": "",
        "transform_decision": "NONE",
        "mesh_decision": "NONE",
        "props_decision": "NONE",
        "object_decision": "NONE",
        "changed_properties": (),
        "attribute_changed": False,
        "collection_changed": False,
        "missing_source": row is not None and source is None,
        "filtered": False,
        "status": "",
        "search_blob": "",
        "object_signature": None,
    }


def build_preview(cache, output, resolved, props, selected_names):
    profile_enabled = os.environ.get("CSVMI_PROFILE") == "1"
    profile_started = time.perf_counter()
    state = read_output_state(output, cache.identity_column)
    state_done = time.perf_counter()
    previous = state["records"]
    objects, current_transforms = managed_scene_index(output)
    index_done = time.perf_counter()
    rules = selected_filter_rules(props)
    initial = output is None
    changes = []
    summary = {key: 0 for key in STATUS_LABELS}

    for identity in set(cache.rows_by_id) | set(previous):
        row = cache.rows_by_id.get(identity)
        old = previous.get(identity)
        obj = objects.get(identity)
        attributes = row_attributes(cache, row) if row is not None else dict((old or {}).get("attrs", {}))
        selected_props = (
            selected_row_properties(cache, row, selected_names) if row is not None else {}
        )
        zone_value = attributes.get(props.split_attribute, "") if props.split_attribute else ""
        zone = "" if zone_value is None else str(zone_value)
        source = resolved.get(row[ROW_NAME]) if row is not None else None
        change = _base_change(identity, row, old, obj, source, attributes, selected_props, zone)
        in_scope = initial or attributes_match_filters(attributes, rules)

        if old is None:
            change["object_kind"] = "NEW"
            change["object_decision"] = "SKIP" if source is None else "CREATE"
        elif bool(old.get("skipped", False)):
            if row is None:
                continue
            unchanged_skip = (
                row[ROW_NAME] == old.get("objname")
                and transform_equal(row_transform(row), old.get("csv_transform"))
                and attributes == old.get("attrs", {})
            )
            if unchanged_skip:
                continue
            change["object_kind"] = "NEW"
            change["object_decision"] = "SKIP" if source is None else "CREATE"
        elif bool(old.get("deleted", False)):
            if row is not None:
                change["object_kind"] = "DELETED"
                change["object_decision"] = "KEEP_DELETED"
            else:
                continue
        elif row is None:
            change["object_kind"] = "CSV_DELETED"
            change["object_decision"] = "MOVE_DELETED"
        elif obj is None:
            change["object_kind"] = "BLENDER_DELETED"
            change["object_decision"] = "KEEP_DELETED"
        else:
            old_attributes = dict(old.get("attrs", {}))
            changed_attributes = {
                name
                for name in set(old_attributes) | set(attributes)
                if old_attributes.get(name) != attributes.get(name)
            }
            change["attribute_changed"] = bool(changed_attributes)
            if props.split_by_attribute and props.split_attribute in changed_attributes:
                change["collection_changed"] = True
            new_transform = row_transform(row)
            old_transform = old.get("csv_transform")
            transform_override = old.get("transform_override")
            expected_transform = transform_override or old_transform
            csv_transform_changed = not transform_equal(new_transform, old_transform)
            current_transform = current_transforms.get(identity) or object_transform(obj)
            blender_transform_changed = not transform_equal(current_transform, expected_transform)
            change["transform_kind"] = _domain_kind(
                csv_transform_changed,
                blender_transform_changed,
                transform_override is not None and csv_transform_changed,
            )
            if change["transform_kind"] == "CSV":
                change["transform_decision"] = "APPLY"
            elif change["transform_kind"]:
                change["transform_decision"] = "KEEP"

            new_mesh = change["new_source_mesh"]
            old_mesh = old.get("source_mesh", "")
            mesh_override = old.get("mesh_override")
            current_mesh = obj.data.name if obj.type == 'MESH' and obj.data else ""
            expected_mesh = mesh_override or old_mesh
            csv_mesh_changed = row[ROW_NAME] != old.get("objname") or new_mesh != old_mesh
            blender_mesh_changed = current_mesh != expected_mesh
            change["mesh_kind"] = _domain_kind(
                csv_mesh_changed,
                blender_mesh_changed,
                mesh_override is not None and csv_mesh_changed,
            )
            if change["mesh_kind"] == "CSV" and source is not None:
                change["mesh_decision"] = "RELINK"
            elif change["mesh_kind"]:
                change["mesh_decision"] = "KEEP"

            old_props = dict(old.get("csv_props", {}))
            props_override = old.get("props_override")
            expected_props = dict(props_override) if props_override is not None else old_props
            prop_names = set(old_props) | set(expected_props) | set(selected_props)
            current_props = current_object_properties(obj, prop_names)
            csv_props_changed = selected_props != old_props
            blender_props_changed = current_props != expected_props
            change["props_kind"] = _domain_kind(
                csv_props_changed,
                blender_props_changed,
                props_override is not None and csv_props_changed,
            )
            change["changed_properties"] = tuple(
                sorted(
                    set(changed_attributes) | {
                    name
                    for name in set(old_props) | set(selected_props) | set(current_props)
                    if old_props.get(name) != selected_props.get(name)
                    or current_props.get(name) != expected_props.get(name)
                    }
                )
            )
            if change["props_kind"] == "CSV":
                change["props_decision"] = "APPLY"
            elif change["props_kind"]:
                change["props_decision"] = "KEEP"

        change["status"] = _status_for(change)
        if not change["status"]:
            continue
        change["object_signature"] = object_preview_signature(
            obj, current_transforms.get(identity)
        )
        if not in_scope:
            change["filtered"] = True
            change["status"] = "FILTERED_OUT"
            change["transform_decision"] = "NONE"
            change["mesh_decision"] = "NONE"
            change["props_decision"] = "NONE"
            change["object_decision"] = "NONE"
        change["search_blob"] = _change_search_blob(change)
        summary[change["status"]] = summary.get(change["status"], 0) + 1
        changes.append(change)

    changes.sort(key=lambda item: (item["status"], item["zone"], item["objname"], item["identity"]))
    if profile_enabled:
        finished = time.perf_counter()
        print(
            f"[CSVMI PREVIEW PROFILE] state={state_done - profile_started:.3f}s "
            f"index={index_done - state_done:.3f}s compare={finished - index_done:.3f}s",
            flush=True,
        )
    return PreviewData(changes, summary, state, output, resolved, cache, tuple(selected_names))


def state_record_from_row(cache, row, source_mesh, selected_props):
    return {
        "csv_transform": list(row_transform(row)),
        "objname": row[ROW_NAME],
        "attrs": row_attributes(cache, row),
        "csv_props": dict(selected_props),
        "source_mesh": source_mesh,
        "transform_override": None,
        "mesh_override": None,
        "props_override": None,
        "deleted": False,
        "skipped": False,
        "object_name": "",
    }
