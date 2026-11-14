"""Pieces shared by every panel: which zone is being worked on, and collection fields that show the collection color."""
import time
import bpy
from .journal import STATE_AFTER, STATE_BEFORE, map_state

_CHOICE = {}  # scene pointer -> (time, zone); a display cache: reading the zone enum scans every empty (16 ms in a 65k-object scene)
_TTL = 0.3


def invalidate_choice(_self=None, _context=None):
    """Called when the Zone list changes, so the panel headers show the new zone at once."""
    _CHOICE.clear()


def shown_zone(p):
    """The selected zone ('ALL', '' or a name) for display only. Logic must read p.zone_choice itself."""
    key = p.id_data.as_pointer()
    now = time.monotonic()
    hit = _CHOICE.get(key)
    if hit is None or now - hit[0] > _TTL:
        hit = (now, p.zone_choice)
        _CHOICE[key] = hit
    return hit[1]


STATE_TEXT = {'': ('Map: original (not imported yet)', 'MESH_GRID'),
              STATE_AFTER: ('Map: the imported CSV is shown', 'CHECKMARK'),
              STATE_BEFORE: ('Map: the ORIGINAL is shown (imported objects are stashed)', 'ERROR')}


def draw_zone_banner(layout, context, doing='', with_name=True):
    """Top lines of a panel: the zone, what state its map is in, and what this panel does with it.

    `doing` may use {zone}."""
    p = context.scene.mrt_props
    zone = shown_zone(p)
    col = layout.box().column(align=True)
    if zone in ('', 'ALL'):
        if with_name:
            col.label(text='Zone: All Zones' if zone == 'ALL' else 'Zone: (none yet)', icon='PIVOT_BOUNDBOX')
        if doing:
            col.label(text=doing.replace('{zone}', 'the zone'))
        return zone
    if with_name:
        col.label(text=f'Zone: {zone}', icon='PIVOT_BOUNDBOX')
    state = map_state(zone)
    text, icon = STATE_TEXT[state]
    row = col.row()
    row.alert = state == STATE_BEFORE
    row.label(text=text, icon=icon)
    if doing:
        col.label(text=doing.replace('{zone}', zone))
    return zone


def collection_icon(collection):
    """The icon of a collection with its color tag (the plain collection icon when it has none)."""
    tag = getattr(collection, 'color_tag', 'NONE') if collection is not None else 'NONE'
    return f'COLLECTION_{tag}' if tag and tag != 'NONE' else 'OUTLINER_COLLECTION'


def collection_prop(layout, owner, name):
    """A collection field that shows the color of the chosen collection."""
    layout.prop(owner, name, icon=collection_icon(getattr(owner, name)))
