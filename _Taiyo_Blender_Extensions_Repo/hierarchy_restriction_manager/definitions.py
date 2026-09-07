"""Restriction semantics shared by the engine and UI (no scene access)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Restriction:
    key: str
    label: str
    icon: str
    targets: tuple
    inverted: bool = True
    layer_only: bool = False


RESTRICTIONS = (
    Restriction('included', 'Included', 'CHECKBOX_HLT', (('L', 'exclude'),), layer_only=True),
    Restriction('selectable', 'Selectable', 'RESTRICT_SELECT_OFF', (('C', 'hide_select'), ('O', 'hide_select'))),
    Restriction('visible', 'Visible', 'HIDE_OFF', (('L', 'hide_viewport'), ('O', '@hide')), layer_only=True),
    Restriction('viewport_enabled', 'Viewport Enabled', 'RESTRICT_VIEW_OFF', (('C', 'hide_viewport'), ('O', 'hide_viewport'))),
    Restriction('holdout', 'Holdout', 'HOLDOUT_ON', (('L', 'holdout'),), False, True),
    Restriction('indirect_only', 'Indirect Only', 'INDIRECT_ONLY_ON', (('L', 'indirect_only'),), False, True),
    Restriction('render_enabled', 'Render Enabled', 'RESTRICT_RENDER_OFF', (('C', 'hide_render'), ('O', 'hide_render'))),
)
KEYS = tuple(r.key for r in RESTRICTIONS)
BY_KEY = {r.key: r for r in RESTRICTIONS}
MODES = [('KEEP', 'Keep', 'Leave this restriction unchanged'), ('ON', 'On', 'Enable the named state'),
         ('OFF', 'Off', 'Disable the named state'), ('INVERT', 'Invert', 'Invert each item independently')]
QUICK = {
    'SHOW': ('Show Hierarchy', dict(included='ON', visible='ON', viewport_enabled='ON')),
    'HIDE': ('Hide in Viewport', dict(visible='OFF')),
    'UNLOCK': ('Unlock Selection', dict(selectable='ON')),
    'LOCK': ('Lock Selection', dict(selectable='OFF')),
    'RENDER_ON': ('Enable Render', dict(render_enabled='ON')),
    'RENDER_OFF': ('Disable Render', dict(render_enabled='OFF')),
}
PRESETS = {
    'ENABLE_ALL': ('Enable All', dict(included='ON', selectable='ON', visible='ON', viewport_enabled='ON', holdout='OFF', indirect_only='OFF', render_enabled='ON')),
    'DISABLE_ALL': ('Disable All', dict(included='OFF', selectable='OFF', visible='OFF', viewport_enabled='OFF', render_enabled='OFF')),
    'VIEWPORT_ONLY': ('Viewport Only', dict(included='ON', viewport_enabled='ON', visible='ON', render_enabled='OFF')),
    'RENDER_ONLY': ('Render Only', dict(included='ON', viewport_enabled='OFF', render_enabled='ON')),
    'LOCK': QUICK['LOCK'], 'HIDE': QUICK['HIDE'],
}
MATCH_MODES = [(v, label, '') for v, label in [('CONTAINS', 'Contains'), ('STARTS', 'Starts With'), ('ENDS', 'Ends With'),
    ('EXACT', 'Exact'), ('WILDCARD', 'Wildcard'), ('REGEX', 'Regex')]]
SCOPE_FIELDS = ('include_root', 'child_collections', 'objects', 'traversal', 'depth', 'use_filters',
    'collection_include', 'collection_exclude', 'collection_match', 'object_include', 'object_exclude',
    'object_match', 'case_sensitive', 'object_types', 'branch_behavior')


def modes_with(values):
    return {key: values.get(key, 'KEEP') for key in KEYS}
