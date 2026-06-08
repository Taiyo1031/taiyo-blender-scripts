import time


MAX_SECONDS_PER_TICK = 0.012
TIMER_INTERVAL = 0.02


def begin_operation(settings, name, total=0, message="Processing..."):
    settings.is_running = True
    settings.cancel_requested = False
    settings.operation_name = name
    settings.operation_message = message
    settings.processed_count = 0
    settings.total_count = max(0, int(total))
    settings.progress_percent = 0.0


def update_operation(settings, processed=None, total=None, message=None):
    if processed is not None:
        settings.processed_count = max(0, int(processed))
    if total is not None:
        settings.total_count = max(0, int(total))
    if settings.total_count:
        settings.progress_percent = min(100.0, settings.processed_count / settings.total_count * 100.0)
    else:
        settings.progress_percent = 0.0
    if message is not None:
        settings.operation_message = message


def finish_operation(settings, message):
    settings.is_running = False
    settings.cancel_requested = False
    settings.operation_message = message
    if settings.total_count:
        settings.progress_percent = 100.0


def cancel_operation(settings, message):
    settings.is_running = False
    settings.cancel_requested = False
    settings.operation_message = message


def time_budget_exceeded(start_time):
    return time.perf_counter() - start_time >= MAX_SECONDS_PER_TICK


def redraw_view3d(context):
    screen = getattr(context, "screen", None)
    if not screen:
        return
    for area in screen.areas:
        if area.type == "VIEW_3D":
            area.tag_redraw()
