"""Cooperative, context-independent restriction engine. Every large traversal yields."""
import fnmatch
import re
import time
import bpy
from collections import deque
from dataclasses import dataclass, field
from .definitions import RESTRICTIONS, KEYS, SCOPE_FIELDS


class InvalidTarget(ValueError):
    pass


def identity(item):
    return item.as_pointer()


def matcher(pattern, mode, sensitive):
    if not pattern:
        return lambda name: True
    if mode == 'REGEX':
        try:
            regex = re.compile(pattern, 0 if sensitive else re.IGNORECASE)
        except re.error as exc:
            raise ValueError('Invalid regular expression: ' + str(exc)) from exc
        return lambda name: bool(regex.search(name))
    pattern = pattern if sensitive else pattern.casefold()
    if mode == 'WILDCARD':
        regex = re.compile(fnmatch.translate(pattern))
        match = lambda name: bool(regex.fullmatch(name))
    elif mode == 'EXACT':
        match = lambda name: name == pattern
    elif mode == 'STARTS':
        match = lambda name: name.startswith(pattern)
    elif mode == 'ENDS':
        match = lambda name: name.endswith(pattern)
    else:
        match = lambda name: pattern in name
    return lambda name: match(name if sensitive else name.casefold())


def name_filter(include, exclude, mode, sensitive):
    yes = matcher(include, mode, sensitive)
    no = matcher(exclude, mode, sensitive) if exclude else lambda name: False
    return lambda name: yes(name) and not no(name)


@dataclass
class Config:
    root: object
    view_layer: object
    modes: dict
    include_root: bool = True
    child_collections: bool = True
    objects: bool = True
    traversal: str = 'RECURSIVE'
    depth: int = 3
    use_filters: bool = False
    collection_include: str = ''
    collection_exclude: str = ''
    collection_match: str = 'CONTAINS'
    object_include: str = ''
    object_exclude: str = ''
    object_match: str = 'CONTAINS'
    case_sensitive: bool = False
    object_types: set = field(default_factory=set)
    branch_behavior: str = 'ITEM'

    @classmethod
    def from_settings(cls, settings, context, modes=None):
        layer = context.scene.view_layers.get(settings.view_layer) if settings.view_layer else context.view_layer
        if layer is None:
            raise InvalidTarget('The chosen View Layer no longer exists. Choose Current View Layer.')
        if settings.target is None:
            raise InvalidTarget('Choose a target collection first.')
        values = {key: getattr(settings, key) for key in SCOPE_FIELDS}
        values['object_types'] = set(values['object_types'])
        return cls(settings.target, layer, modes or {key: getattr(settings, key) for key in KEYS}, **values)

    def validate(self):
        try:
            if not self.root or not self.root.as_pointer() or not self.view_layer.as_pointer():
                raise InvalidTarget('The target or View Layer was removed.')
        except ReferenceError as exc:
            raise InvalidTarget('The target or View Layer was removed.') from exc
        if not self.use_filters:
            self.collection_test = self.object_test = lambda name: True
            return
        self.collection_test = name_filter(self.collection_include, self.collection_exclude, self.collection_match, self.case_sensitive)
        self.object_test = name_filter(self.object_include, self.object_exclude, self.object_match, self.case_sensitive)


@dataclass
class Stats:
    collections: int = 0
    object_links: int = 0
    objects: int = 0
    candidates: int = 0
    modified: int = 0
    writes: int = 0
    unchanged: int = 0
    readonly: int = 0
    missing: int = 0
    errors: int = 0
    scanned: int = 0
    phase: str = 'Preparing'
    duration: float = 0
    distributions: dict = field(default_factory=lambda: {k: [0, 0] for k in KEYS})
    messages: list = field(default_factory=list)
    timings: dict = field(default_factory=dict)

    def note(self, text):
        if text not in self.messages and len(self.messages) < 12:
            self.messages.append(text)


@dataclass
class Change:
    target: object
    prop: str
    old: bool
    new: bool
    view_layer: object = None

    def read(self):
        if self.prop == '@hide':
            if self.target.name not in self.view_layer.objects:
                raise InvalidTarget('Object is absent from the chosen View Layer')
            return self.target.hide_get(view_layer=self.view_layer)
        return getattr(self.target, self.prop)

    def set(self, value):
        if self.prop == '@hide':
            self.target.hide_set(value, view_layer=self.view_layer)
        else:
            setattr(self.target, self.prop, value)


def writable(target, prop):
    if prop == '@hide':
        return True  # A local View Layer flag, also valid for library-linked objects.
    return not target.is_property_readonly(prop)


def semantic(raw, definition):
    return not raw if definition.inverted else raw


def desired(raw, mode, definition):
    if mode == 'KEEP':
        return raw
    if mode == 'INVERT':
        return not raw
    positive = mode == 'ON'
    return not positive if definition.inverted else positive


class Journal(list):
    def __init__(self):
        super().__init__()
        self.hidden = []
        self.seen_hidden = set()
        self.seen_collections = set()

    def clear(self):
        super().clear()
        self.hidden.clear()
        self.seen_hidden.clear()
        self.seen_collections.clear()


def capture_hidden(change, journal, view_layer):
    # Exclude and global viewport changes rebuild Object bases. Blender can discard
    # unchanged temporary hide flags as a side effect; record those too for Cancel.
    target, prop = change.target, change.prop
    if prop not in {'exclude', 'hide_viewport'} or (prop == 'hide_viewport' and isinstance(target, bpy.types.LayerCollection)):
        return
    layers = [view_layer] if prop == 'exclude' else [layer for scene in bpy.data.scenes for layer in scene.view_layers]
    def capture(obj):
        for layer in layers:
            key = (identity(obj), identity(layer))
            if key in journal.seen_hidden:
                continue
            journal.seen_hidden.add(key)
            if obj.name in layer.objects and obj.hide_get(view_layer=layer):
                journal.hidden.append(Change(obj, '@hide', True, True, layer))
            yield None
    if isinstance(target, bpy.types.Object):
        yield from capture(target)
        return
    root = target.collection if isinstance(target, bpy.types.LayerCollection) else target
    queue = deque([root])
    layer_token = tuple(identity(layer) for layer in layers)
    while queue:
        collection = queue.popleft()
        token = (identity(collection), layer_token)
        if token in journal.seen_collections:
            yield None
            continue
        journal.seen_collections.add(token)
        for obj in collection.objects:
            yield from capture(obj)
            yield None
        for child in collection.children:
            queue.append(child)
            yield None
        yield None


class Job:
    def __init__(self, config, preview=False, detailed=False, count_all=False):
        config.validate()
        self.config = config
        self.preview = preview
        self.detailed = detailed
        self.count_all = count_all
        self.stats = Stats()
        self.journal = Journal()
        self.collections = []
        self.layers = {}
        self.deferred = []
        self.changed_items = set()
        self.done = False
        self.started = time.perf_counter()
        self._specs = {kind: tuple(sorted([(r, prop) for r in RESTRICTIONS for target_kind, prop in r.targets if target_kind == kind and (detailed or config.modes[r.key] != 'KEEP')], key=lambda pair: pair[1] != '@hide')) for kind in ('C', 'L', 'O')}

    def hierarchy(self):
        cfg = self.config
        limit = 1 if cfg.traversal == 'DIRECT' else cfg.depth if cfg.traversal == 'DEPTH' else None
        queue = deque([(cfg.root, 0)])
        visited = set()
        while queue:
            collection, depth = queue.popleft()
            key = identity(collection)
            if key in visited:
                yield None
                continue
            visited.add(key)
            match = not cfg.use_filters or cfg.collection_test(collection.name)
            self.stats.scanned += 1
            if match:
                affect = cfg.include_root if depth == 0 else cfg.child_collections
                self.collections.append((collection, affect))
                self.stats.collections += 1
            yield None
            if not match and cfg.use_filters and cfg.branch_behavior == 'BRANCH':
                continue
            if limit is None or depth < limit:
                for child in collection.children:
                    queue.append((child, depth + 1))
                    yield None

    def map_layers(self, warnings=True):
        cfg = self.config
        wanted = {identity(c) for c, _ in self.collections}
        stack = [(cfg.view_layer.layer_collection, False, False)]
        while stack:
            layer, inside, blocked = stack.pop()
            key = identity(layer.collection)
            is_root = layer.collection == cfg.root
            if key in wanted:
                self.layers.setdefault(key, []).append(layer)
            if warnings and is_root and blocked:
                self.stats.note('An ancestor outside the target blocks visibility/rendering; its restrictions were preserved.')
            child_blocked = blocked or (not inside and not is_root and bool(layer.exclude or layer.hide_viewport or layer.collection.hide_viewport or layer.collection.hide_render))
            for child in layer.children:
                stack.append((child, inside or is_root, child_blocked))
                yield None
            yield None

    def object_items(self):
        cfg = self.config
        visited = set()
        for collection, _affect in self.collections:
            for obj in collection.objects:
                self.stats.object_links += 1
                key = identity(obj)
                if key in visited:
                    yield None
                    continue
                visited.add(key)
                if cfg.use_filters:
                    if cfg.object_types and obj.type not in cfg.object_types:
                        yield None
                        continue
                    if not cfg.object_test(obj.name):
                        yield None
                        continue
                self.stats.objects += 1
                yield obj

    def specs(self, kind):
        return self._specs[kind]

    def inspect(self, kind, target):
        stats, cfg = self.stats, self.config
        stats.candidates += 1
        modified = False
        # Temporary object visibility must be set before disabling that object globally.
        specs = self.specs(kind)
        for definition, prop in specs:
            mode = cfg.modes[definition.key]
            change = Change(target, prop, False, False, cfg.view_layer if prop == '@hide' else None)
            try:
                raw = change.read()
                if self.detailed:
                    stats.distributions[definition.key][int(semantic(raw, definition))] += 1
                if mode == 'KEEP':
                    continue
                new = desired(raw, mode, definition)
                if new == raw:
                    stats.unchanged += 1
                    continue
                if not writable(target, prop):
                    stats.readonly += 1
                    continue
                change.old, change.new = raw, new
                if self.preview:
                    stats.writes += 1
                    modified = True
                elif kind in {'C', 'L'} and prop in {'exclude', 'hide_viewport'} and new:
                    yield from capture_hidden(change, self.journal, cfg.view_layer)
                    self.deferred.append(change)
                else:
                    yield from capture_hidden(change, self.journal, cfg.view_layer)
                    self.write(change)
            except InvalidTarget:
                stats.missing += 1
                stats.note('Some objects are absent from the View Layer. Their temporary visibility was skipped.')
            except (ReferenceError, AttributeError, RuntimeError, TypeError) as exc:
                stats.errors += 1
                stats.note(str(exc))
        if modified:
            stats.modified += 1

    def write(self, change):
        # Journal before mutation so an interrupted assignment remains recoverable.
        self.journal.append(change)
        try:
            change.set(change.new)
        except (ReferenceError, RuntimeError, TypeError, AttributeError):
            self.journal.pop()
            raise
        self.stats.writes += 1
        key = identity(change.target)
        if key not in self.changed_items:
            self.changed_items.add(key)
            self.stats.modified += 1

    def run(self):
        cfg, stats = self.config, self.stats
        if not self.preview and all(value == 'KEEP' for value in cfg.modes.values()):
            self.done = True
            return
        mark = time.perf_counter()
        yield from self.hierarchy()
        stats.timings['Hierarchy'] = time.perf_counter() - mark
        need_layers = (not self.preview or self.detailed) and bool(self.specs('L')) and any(affect for _, affect in self.collections)
        if need_layers:
            stats.phase = 'Mapping View Layer'
            mark = time.perf_counter()
            yield from self.map_layers()
            stats.timings['Layer mapping'] = time.perf_counter() - mark
        stats.phase = 'Collections'
        mark = time.perf_counter()
        for collection, affect in self.collections:
            if affect:
                if self.preview and not self.detailed:
                    stats.candidates += 1
                elif self.specs('C'):
                    yield from self.inspect('C', collection)
                if need_layers:
                    layers = self.layers.get(identity(collection), ())
                    if not layers:
                        stats.missing += 1
                    for layer in layers:
                        yield from self.inspect('L', layer)
                        yield None
            yield None
        stats.timings['Collection changes'] = time.perf_counter() - mark
        if not self.preview and any(c.prop in {'exclude', 'hide_viewport'} for c in self.journal):
            cfg.view_layer.update()  # One barrier before per-View-Layer Object visibility.
            yield None
        if cfg.objects and (self.count_all or self.specs('O')):
            stats.phase = 'Objects'
            mark = time.perf_counter()
            for obj in self.object_items():
                if obj is not None:
                    if self.preview and not self.detailed:
                        stats.candidates += 1
                    else:
                        yield from self.inspect('O', obj)
                yield None
            stats.timings['Object changes'] = time.perf_counter() - mark
        stats.phase = 'Finishing restrictions'
        for change in self.deferred:
            try:
                self.write(change)
            except (ReferenceError, RuntimeError, TypeError, AttributeError) as exc:
                stats.errors += 1
                stats.note(str(exc))
            yield None
        self.deferred.clear()
        stats.duration = time.perf_counter() - self.started
        self.done = True


def restore_changes(journal, stats=None):
    """Reverse write order: unblock collections, restore objects, then restore early flags."""
    for change in reversed(journal):
        try:
            change.set(change.old)
        except (ReferenceError, RuntimeError, TypeError, AttributeError) as exc:
            if stats is not None:
                stats.errors += 1
                stats.note('Restore: ' + str(exc))
        yield None

    for change in getattr(journal, 'hidden', ()):
        try:
            if change.target.name in change.view_layer.objects:
                change.set(True)
        except (ReferenceError, RuntimeError, TypeError, AttributeError) as exc:
            if stats is not None:
                stats.errors += 1
                stats.note('Restore hidden state: ' + str(exc))
        yield None


def snapshot_root(config):
    config.validate()
    job = Job(config)
    job.collections = [(config.root, True)]
    for _ in job.map_layers(False):
        yield None
    values, mixed = {}, []
    for definition in RESTRICTIONS:
        states = set()
        for kind, prop in definition.targets:
            targets = [config.root] if kind == 'C' else job.layers.get(identity(config.root), ()) if kind == 'L' else ()
            for target in targets:
                states.add(semantic(getattr(target, prop), definition))
                yield None
        if len(states) == 1:
            values[definition.key] = 'ON' if states.pop() else 'OFF'
        else:
            values[definition.key] = 'KEEP'
            mixed.append(definition.label)
    return values, mixed


def solo_changes(config, mode):
    """Isolate all occurrences of the root; preserve descendant Object flags."""
    config.validate()
    root_layer = config.view_layer.layer_collection
    nodes, parents, order = {}, {}, []
    stack = [(root_layer, None)]
    roots = []
    while stack:
        layer, parent = stack.pop()
        key = identity(layer)
        nodes[key], parents[key] = layer, parent
        order.append(key)
        if layer.collection == config.root:
            roots.append(key)
        for child in layer.children:
            stack.append((child, key))
            yield None
        yield None
    if not roots:
        raise InvalidTarget('Solo requires the target in the chosen View Layer.')
    ancestors, inside = set(), set()
    for key in roots:
        parent = key
        while parent is not None and parent not in ancestors:
            ancestors.add(parent)
            parent = parents[parent]
            yield None
    for key in order:  # Preorder, parents before children.
        if key in roots or parents[key] in inside:
            inside.add(key)
        yield None
    keep = ancestors | inside
    # Global Collection flags cannot distinguish occurrences; any retained occurrence wins.
    kept_collections = {identity(nodes[k].collection) for k in keep}
    seen = set()
    for key in order:
        layer = nodes[key]
        if layer == root_layer:
            continue
        parent = parents[key]
        path = key in ancestors
        outside_boundary = key not in keep and parent in keep
        if not path and not outside_boundary:
            yield None
            continue
        requests = []
        if mode in {'VISIBLE', 'BOTH'}:
            requests.append((layer, 'hide_viewport', outside_boundary))
            if path:
                requests.append((layer, 'exclude', False))
                requests.append((layer.collection, 'hide_viewport', False))
        if mode in {'VIEWPORT', 'BOTH'}:
            requests.append((layer.collection, 'hide_viewport', outside_boundary))
            if path:
                requests.extend([(layer, 'exclude', False), (layer, 'hide_viewport', False)])
        if mode in {'RENDER', 'BOTH'}:
            requests.append((layer.collection, 'hide_render', outside_boundary))
            if path:
                requests.append((layer, 'exclude', False))
        for target, prop, new in requests:
            token = (identity(target), prop)
            if token in seen:
                continue
            if target != layer and new and identity(target) in kept_collections:
                continue
            seen.add(token)
            raw = getattr(target, prop)
            if raw != new:
                yield Change(target, prop, raw, new)
        yield None

    # Objects linked directly to retained ancestors cannot be isolated by hiding
    # their Collection. Only these exceptions require Object-level changes.
    retained_collections = {identity(nodes[key].collection) for key in inside}
    seen_objects = set()
    for key in ancestors - inside:
        for obj in nodes[key].collection.objects:
            token = identity(obj)
            if token in seen_objects:
                yield None
                continue
            seen_objects.add(token)
            if any(identity(collection) in retained_collections for collection in obj.users_collection):
                yield None
                continue
            requests = []
            if mode in {'VISIBLE', 'BOTH'}:
                requests.append(('@hide', config.view_layer))
            if mode in {'VIEWPORT', 'BOTH'}:
                requests.append(('hide_viewport', None))
            if mode in {'RENDER', 'BOTH'}:
                requests.append(('hide_render', None))
            for prop, layer in requests:
                if prop == '@hide' and obj.name not in layer.objects:
                    continue
                change = Change(obj, prop, False, True, layer)
                raw = change.read()
                if not raw:
                    change.old = raw
                    yield change
            yield None
