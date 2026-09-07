import json
import time
import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator
from . import engine, state, presets
from .definitions import KEYS, QUICK, PRESETS, modes_with


class Session:
    """Own all work, journals and modal cleanup, including interrupted operations."""
    def __init__(self, context, action, confirmed=False):
        self.scene = context.scene
        self.settings = context.scene.hrm_settings
        if action not in set(QUICK) | {'APPLY', 'REFRESH', 'COPY', 'MATCH', 'SOLO', 'RESTORE'}:
            raise ValueError('Unknown HRM operation')
        self.action = action
        self.confirmed = confirmed
        self.waiting = False
        self.cancel_requested = False
        self.canceling = False
        self.finished = False
        self.failed = False
        self.timer = None
        self.wm = context.window_manager
        self.window = context.window
        self.area = context.area
        self.stats = engine.Stats()
        self.journal = engine.Journal()
        self.job = None
        self.started = time.perf_counter()
        prefs = state.preferences(context)
        self.performance = prefs.performance
        self.confirm_large = prefs.confirm_large
        self.threshold = prefs.threshold
        self.interval = prefs.progress_interval
        self.debug = prefs.debug
        if action == 'RESTORE':
            layer = context.scene.view_layers.get(self.settings.view_layer) if self.settings.view_layer else context.view_layer
            if layer is None:
                raise engine.InvalidTarget('The chosen View Layer no longer exists.')
            self.config = engine.Config(context.scene.collection, layer, modes_with({}))
        else:
            self.config = engine.Config.from_settings(self.settings, context,
                modes_with(QUICK[action][1]) if action in QUICK else None)
        if action in {'SOLO', 'RESTORE', 'COPY', 'MATCH'}:
            self.config.use_filters = False
        self.solo_mode = self.settings.solo_mode
        self.config.validate()
        self.key = state.solo_key(self.scene, self.config.view_layer)
        self.generator = self.work()

    def confirmation(self, count=None):
        if not self.confirm_large or self.confirmed or (count is not None and count <= self.threshold):
            return
        self.waiting = True
        self.stats.phase = f'Confirm {count:,} candidate items' if count is not None else 'Confirm Fast Apply (size not counted)'
        if bpy.app.background:
            raise ValueError('Large operation requires confirmed=True in background mode.')
        while not self.confirmed and not self.cancel_requested:
            yield None
        self.waiting = False

    def work(self):
        cfg = self.config
        if self.action == 'COPY' or self.action == 'MATCH':
            values, mixed = yield from engine.snapshot_root(cfg)
            if self.action == 'COPY':
                state.CLIPBOARD = {'values': values, 'source': cfg.root.name, 'mixed': mixed}
                self.settings.message = 'Copied root restrictions.'
            else:
                for key, value in values.items():
                    setattr(self.settings, key, value)
                self.settings.include_root = False
                self.settings.show_restrictions = True
                self.settings.message = 'Root states loaded. Press Apply.'
            if mixed:
                self.settings.message += ' Kept unavailable/mixed: ' + ', '.join(mixed)
            return
        if self.action == 'REFRESH':
            job = engine.Job(cfg, preview=True, detailed=self.settings.statistics_detail == 'DETAILED', count_all=True)
            self.job, self.stats = job, job.stats
            yield from job.run()
            state.PREVIEWS[state.scene_key(self.scene)] = (job.stats, job.detailed)
            self.settings.dirty = False
            self.settings.message = 'Statistics refreshed. States describe stored flags, not inherited visibility.'
            return
        if self.action in {'SOLO', 'RESTORE'}:
            prior = state.SOLOS.get(self.key, [])
            if self.action == 'RESTORE' and not prior:
                raise ValueError('No Solo snapshot exists for this Scene and View Layer.')
            # Preview the size without changing existing Solo; actual Solo is rebuilt after restoring it.
            if self.action == 'SOLO':
                count = 0
                for item in engine.solo_changes(cfg, self.solo_mode):
                    if item is not None:
                        count += 1
                    yield None
                yield from self.confirmation(count + len(prior))
            self.job = engine.Job(cfg)
            self.stats = self.job.stats
            self.journal = self.job.journal
            self.stats.phase = 'Restoring previous Solo'
            for old in reversed(prior):
                try:
                    current = old.read()
                    if current != old.old:
                        change = engine.Change(old.target, old.prop, current, old.old, old.view_layer)
                        yield from engine.capture_hidden(change, self.journal, cfg.view_layer)
                        self.job.write(change)
                except (ReferenceError, RuntimeError, TypeError, AttributeError, engine.InvalidTarget) as exc:
                    self.stats.errors += 1
                    self.stats.note(str(exc))
                yield None
            for hidden in getattr(prior, 'hidden', ()):
                try:
                    current = hidden.read()
                    if not current:
                        self.job.write(engine.Change(hidden.target, '@hide', False, True, hidden.view_layer))
                except (ReferenceError, RuntimeError, engine.InvalidTarget) as exc:
                    self.stats.errors += 1
                    self.stats.note(str(exc))
                yield None
            snapshot = engine.Journal()
            if self.action == 'SOLO':
                self.stats.phase = 'Isolating hierarchy'
                for change in engine.solo_changes(cfg, self.solo_mode):
                    if change is not None:
                        try:
                            if engine.writable(change.target, change.prop):
                                yield from engine.capture_hidden(change, snapshot, cfg.view_layer)
                                yield from engine.capture_hidden(change, self.journal, cfg.view_layer)
                                self.job.write(change)
                                snapshot.append(change)
                            else:
                                self.stats.readonly += 1
                        except (ReferenceError, RuntimeError, AttributeError, TypeError) as exc:
                            self.stats.errors += 1
                            self.stats.note(str(exc))
                    yield None
                snapshot.seen_hidden.clear()
                snapshot.seen_collections.clear()
                state.SOLOS[self.key] = snapshot
            else:
                state.SOLOS.pop(self.key, None)
            return
        if all(value == 'KEEP' for value in cfg.modes.values()):
            self.settings.message = 'No restriction changes requested.'
            return
        if self.performance == 'FAST':
            yield from self.confirmation()
        else:
            preview = engine.Job(cfg, preview=True, detailed=self.performance == 'DETAILED')
            self.job, self.stats = preview, preview.stats
            yield from preview.run()
            yield from self.confirmation(preview.stats.candidates)
        # Never trust preview target lists after confirmation.
        cfg.validate()
        self.job = engine.Job(cfg)
        self.stats = self.job.stats
        self.journal = self.job.journal
        yield from self.job.run()

    def start_rollback(self, error=None):
        if self.canceling:
            return
        self.canceling = True
        self.waiting = False
        self.failed = error is not None
        if error:
            self.stats.errors += 1
            self.stats.note(str(error))
        self.stats.phase = 'Restoring changes — please wait'
        self.generator.close()
        self.generator = engine.restore_changes(self.journal, self.stats)

    def step(self, budget=0.008):
        if self.cancel_requested and not self.canceling:
            self.start_rollback()
        until = time.perf_counter() + budget
        iterations = 0
        while time.perf_counter() < until and iterations < self.interval:
            try:
                next(self.generator)
            except StopIteration:
                self.finished = True
                self.finish()
                return
            except Exception as exc:
                self.start_rollback(exc)
            iterations += 1
            if self.waiting:
                break

    def finish(self):
        self.stats.duration = time.perf_counter() - self.started
        if self.canceling:
            self.settings.message = ('Stopped: ' + self.stats.messages[0]) if self.failed and self.stats.messages else 'Canceled. Previous values restored.' if not self.stats.errors else 'Stopped. Check restore errors in Last Operation.'
        elif self.action not in {'COPY', 'MATCH', 'REFRESH'}:
            self.settings.message = f'{self.stats.modified:,} items / {self.stats.writes:,} properties changed in {self.stats.duration:.2f}s'
            self.settings.dirty = True
        state.LAST[state.scene_key(self.scene)] = self.stats
        if self.debug:
            print('HRM', self.action, self.stats.timings, self.settings.message)
        self.cleanup()

    def cleanup(self):
        if self.timer:
            self.wm.event_timer_remove(self.timer)
            self.timer = None
        if self.window:
            self.window.cursor_modal_restore()
        if state.ACTIVE is self:
            state.ACTIVE = None
        self.journal.clear()
        if self.job:
            self.job.collections.clear()
            self.job.layers.clear()
            self.job.changed_items.clear()
        self.redraw()

    def abort_now(self):
        # Unregister/file load cannot keep a timer running. Restore synchronously first.
        self.generator.close()
        self.finished = True
        self.canceling = True
        for _ in engine.restore_changes(self.journal, self.stats):
            pass
        self.cleanup()

    def redraw(self):
        if self.window:
            for area in self.window.screen.areas:
                if area.type in {'VIEW_3D', 'OUTLINER'}:
                    area.tag_redraw()

    def panel_event(self, event):
        if self.area and self.area.type == 'VIEW_3D':
            return any(region.type == 'UI' and region.x <= event.mouse_x < region.x + region.width
                       and region.y <= event.mouse_y < region.y + region.height for region in self.area.regions)
        return False


class HRM_OT_run(Operator):
    bl_idname = 'hrm.run'
    bl_label = 'Apply to Hierarchy'
    bl_description = 'Apply to the current target, scope and filters; large changes require confirmation'
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}
    action: StringProperty(default='APPLY', options={'SKIP_SAVE'})
    confirmed: BoolProperty(default=False, options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return context.scene is not None and state.ACTIVE is None

    def invoke(self, context, event):
        return self.execute(context)

    def execute(self, context):
        if context.mode != 'OBJECT' and self.action not in {'COPY', 'MATCH', 'REFRESH'}:
            self.report({'WARNING'}, 'Use Object Mode to apply restrictions with reliable Undo. The mode was not changed.')
            return {'CANCELLED'}
        try:
            self.session = Session(context, self.action, self.confirmed)
        except (ValueError, ReferenceError) as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        state.ACTIVE = self.session
        if bpy.app.background:
            while not self.session.finished:
                self.session.step(0.05)
            return {'CANCELLED'} if self.session.canceling else {'FINISHED'}
        self.session.timer = context.window_manager.event_timer_add(0.02, window=context.window)
        context.window_manager.modal_handler_add(self)
        self._last_redraw = 0
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        session = self.session
        if session.finished:
            return {'CANCELLED'} if session.canceling else {'FINISHED'}
        if event.type == 'ESC' and event.value == 'PRESS':
            session.cancel_requested = True
        if event.type == 'TIMER':
            session.step()
            now = time.monotonic()
            if now - self._last_redraw >= 0.1 or session.finished:
                session.redraw()
                self._last_redraw = now
            if session.finished:
                if session.stats.errors:
                    self.report({'WARNING'}, session.settings.message)
                return {'CANCELLED'} if session.canceling else {'FINISHED'}
        # Only this sidebar's disabled controls + Confirm/Cancel remain interactive.
        if event.type in {'LEFTMOUSE', 'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and session.panel_event(event):
            return {'PASS_THROUGH'}
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'TRACKPADPAN', 'TRACKPADZOOM'}:
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        if getattr(self, 'session', None):
            self.session.abort_now()


class HRM_OT_control(Operator):
    bl_idname = 'hrm.control'
    bl_label = 'Confirm / Cancel HRM'
    action: StringProperty(default='CANCEL')

    def execute(self, context):
        if state.ACTIVE:
            if self.action == 'CONFIRM':
                state.ACTIVE.confirmed = True
            else:
                state.ACTIVE.cancel_requested = True
        return {'FINISHED'}


class HRM_OT_target(Operator):
    bl_idname = 'hrm.target'
    bl_label = 'Choose HRM Target'
    bl_description = 'Set the target without changing any restrictions'
    action: StringProperty(default='ACTIVE')
    name: StringProperty()
    library: StringProperty()

    def execute(self, context):
        if state.ACTIVE:
            return {'CANCELLED'}
        settings = context.scene.hrm_settings
        if self.action == 'FAVORITE':
            if settings.target:
                for i, item in enumerate(settings.favorites):
                    if item.collection == settings.target:
                        settings.favorites.remove(i)
                        return {'FINISHED'}
                settings.favorites.add().collection = settings.target
            return {'FINISHED'}
        if self.action == 'NAMED':
            collection = bpy.data.collections.get((self.name, self.library or None))
        elif self.action == 'OBJECT':
            obj = context.active_object
            if obj is None:
                self.report({'WARNING'}, 'Select an object first.')
                return {'CANCELLED'}
            collections = tuple(obj.users_collection)
            if len(collections) > 1:
                def draw(menu, ctx):
                    for collection in collections:
                        op = menu.layout.operator('hrm.target', text=collection.name, icon='OUTLINER_COLLECTION')
                        op.action, op.name = 'NAMED', collection.name
                        op.library = collection.library.filepath if collection.library else ''
                context.window_manager.popup_menu(draw, title='Choose Object Collection')
                return {'FINISHED'}
            collection = collections[0] if collections else None
        else:
            selected = getattr(context, 'selected_ids', ()) if context.area and context.area.type == 'OUTLINER' else ()
            collections = [item for item in selected if isinstance(item, bpy.types.Collection)]
            if len(collections) > 1:
                self.report({'WARNING'}, 'Select a single Collection in the Outliner.')
                return {'CANCELLED'}
            collection = collections[0] if collections else context.view_layer.active_layer_collection.collection
        if collection is None:
            self.report({'WARNING'}, 'No Collection could be resolved.')
            return {'CANCELLED'}
        settings.target = collection
        return {'FINISHED'}


class HRM_OT_settings(Operator):
    bl_idname = 'hrm.settings'
    bl_label = 'Prepare Restriction Settings'
    bl_description = 'Only update the controls; press Apply to change the hierarchy'
    action: StringProperty(default='RESET')
    name: StringProperty()

    def execute(self, context):
        if state.ACTIVE:
            return {'CANCELLED'}
        settings = context.scene.hrm_settings
        try:
            if self.action in PRESETS or self.action == 'RESET':
                values = modes_with(PRESETS[self.action][1] if self.action in PRESETS else {})
                for key, value in values.items():
                    setattr(settings, key, value)
                settings.show_restrictions = True
                settings.message = 'Settings prepared. Press Apply.'
            elif self.action == 'PASTE':
                if not state.CLIPBOARD:
                    raise ValueError('Copy restrictions first.')
                for key, value in state.CLIPBOARD['values'].items():
                    setattr(settings, key, value)
                settings.show_restrictions = True
                settings.message = 'Clipboard pasted into settings. Press Apply.'
            elif self.action in {'SAVE', 'LOAD', 'DELETE'}:
                name = (self.name or settings.preset_name).strip()
                if not name:
                    raise ValueError('Enter a preset name.')
                values = presets.read()
                if self.action == 'SAVE':
                    values[name] = presets.capture(settings)
                    presets.write(values)
                    settings.message = f'Saved preset: {name}'
                elif self.action == 'DELETE':
                    values.pop(name, None)
                    presets.write(values)
                    settings.message = f'Deleted preset: {name}'
                else:
                    if name not in values:
                        raise ValueError('Preset not found. Use Browse Presets.')
                    settings.message = presets.apply(settings, values[name])
                    settings.preset_name = name
            elif self.action == 'BROWSE':
                names = sorted(presets.read())
                def draw(menu, ctx):
                    if not names:
                        menu.layout.label(text='No saved presets')
                    for name in names:
                        op = menu.layout.operator('hrm.settings', text=name)
                        op.action, op.name = 'LOAD', name
                context.window_manager.popup_menu(draw, title='Load Preset to Settings')
            elif self.action == 'CURRENT_LAYER':
                settings.view_layer = ''
            elif self.action == 'COPY_REPORT':
                stats = state.LAST.get(state.scene_key(context.scene))
                if stats:
                    context.window_manager.clipboard = json.dumps(vars(stats), ensure_ascii=False, indent=2)
        except (ValueError, OSError, TypeError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


def outliner_menu(self, context):
    self.layout.separator()
    op = self.layout.operator('hrm.target', text='Set as HRM Target', icon='OUTLINER_COLLECTION')
    op.action = 'ACTIVE'


CLASSES = (HRM_OT_run, HRM_OT_control, HRM_OT_target, HRM_OT_settings)
