"""Time-budgeted modal tasks. Rollbacks also yield to the UI."""
import time
import bpy

_RUNNING = None


class Cancelled(Exception):
    pass


class ChunkedOperator:
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return _RUNNING is None and context.mode == 'OBJECT' and not context.scene.mrt_props.running

    def invoke(self, context, event):
        return self.start(context, bool(context.window))

    def execute(self, context):
        return self.start(context, False)

    def start(self, context, modal):
        global _RUNNING
        if _RUNNING is not None:
            self.report({'WARNING'}, 'A Map Roundtrip task is already running.')
            return {'CANCELLED'}
        _RUNNING = self
        self._timer = None
        self._started = time.perf_counter()
        self._last_draw = 0
        self._items_per_tick = 128
        self.max_tick = 0.0
        self._cancelling = False
        self._error = ''
        self._work = self.work(context)
        self._done = self._total = 0
        self._phase = 'Starting'
        context.scene.mrt_props.running = True
        context.scene.mrt_props.cancel_requested = False
        context.window_manager.progress_begin(0, 100)
        if modal:
            self._timer = context.window_manager.event_timer_add(.01, window=context.window)
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        while True:
            result = self.tick(context)
            if result is not None:
                return result

    def progress(self, phase, done, total):
        self._phase, self._done, self._total = phase, done, total

    def request_cancel(self):
        if not self._cancelling:
            self._cancelling = True
            self._error = 'Cancelled.'
            # Throw into the suspended generator so its transaction can roll back.
            try:
                self._work.throw(Cancelled('Cancelled.'))
            except StopIteration:
                return True
            except Exception as exc:
                if not self._error.startswith('Rolled back'):
                    self._error = str(exc)
                return True
        return False

    def modal(self, context, event):
        if event.type == 'ESC' or context.scene.mrt_props.cancel_requested:
            context.scene.mrt_props.cancel_requested = False
            if self.request_cancel():
                return self.finish(context)
        if event.type == 'TIMER':
            return self.tick(context) or {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'}

    def tick(self, context):
        started = time.perf_counter()
        count = 0
        try:
            while count < self._items_per_tick:
                next(self._work)
                count += 1
                if time.perf_counter() - started >= .3:
                    break
        except StopIteration:
            self.max_tick = max(self.max_tick, time.perf_counter() - started)
            return self.finish(context)
        except Exception as exc:
            if not self._error.startswith('Rolled back'):
                self._error = str(exc)
            return self.finish(context)
        elapsed = max(time.perf_counter() - started, 1e-6)
        self.max_tick = max(self.max_tick, elapsed)
        self._items_per_tick = max(1, min(8192, int(max(1, count) * .3 / elapsed)))
        now = time.perf_counter()
        if now - self._last_draw >= .18:
            self._last_draw = now
            fraction = self._done / max(1, self._total)
            seconds = now - self._started
            eta = seconds * (self._total - self._done) / self._done if self._done else 0
            text = f'{self._phase}: {self._done}/{self._total} | Remaining ~{eta:.0f}s | ESC cancels'
            p = context.scene.mrt_props
            p.status, p.progress = text, fraction
            context.window_manager.progress_update(fraction * 100)
            context.workspace.status_text_set(text)
            if context.area:
                context.area.tag_redraw()
        return None

    def finish(self, context):
        global _RUNNING
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        self._work.close()
        context.window_manager.progress_end()
        context.workspace.status_text_set(None)
        p = context.scene.mrt_props
        p.running = False
        p.max_tick = self.max_tick
        elapsed = time.perf_counter() - self._started
        p.status = (self._error or getattr(self, 'result', 'Completed')) + f' ({elapsed:.3f} s; max tick {self.max_tick:.3f} s)'
        p.progress = 0 if self._error else 1
        _RUNNING = None
        if context.area:
            context.area.tag_redraw()
        level = 'WARNING' if self._cancelling else 'ERROR'
        self.report({level} if self._error else {'INFO'}, p.status)
        return {'CANCELLED'} if self._error else {'FINISHED'}
