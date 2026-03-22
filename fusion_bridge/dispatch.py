"""Thread-safe callback relay for executing work on the Fusion main thread."""

import queue
import threading
import traceback

import adsk.core

from ..lib import fusionAddInUtils as futil

# ── Module state ──────────────────────────────────────────────────────────

_callback_impl = None
_pending = queue.Queue()
_callback_event = None
_scheduler_active = threading.Event()
_halt = threading.Event()
_run_lock = threading.Lock()

_deferred_messages = []
_msg_lock = threading.Lock()
_registered = False

CALLBACK_EVENT_ID = "FusionBridgeCallback"
_TICK_INTERVAL = 0.075
_KEEPALIVE_INTERVAL = 2.0
_BATCH_LIMIT = 8


# ── Fusion application accessor ──────────────────────────────────────────


def get_app():
    return adsk.core.Application.get()


# ── Thread-safe logging ──────────────────────────────────────────────────


def log(message: str, level=None):
    """Log immediately on the main thread, or defer for later flushing."""
    if threading.current_thread() is threading.main_thread():
        futil.log(message) if level is None else futil.log(message, level)
        return
    with _msg_lock:
        _deferred_messages.append((message, level))


def drain_logs():
    """Flush any log messages that were deferred from background threads."""
    with _msg_lock:
        if not _deferred_messages:
            return
        snapshot = list(_deferred_messages)
        _deferred_messages.clear()
    for text, lvl in snapshot:
        futil.log(text) if lvl is None else futil.log(text, lvl)


# ── Custom-event handler ─────────────────────────────────────────────────


class _BridgeEventHandler(adsk.core.CustomEventHandler):
    """Responds to the custom Fusion event by draining the work queue."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        del args
        _flush_pending()


# ── Recursive timer scheduler ────────────────────────────────────────────


def _schedule_tick():
    """Fire a single tick, then reschedule if still active."""
    if not _scheduler_active.is_set():
        return
    try:
        _fire_event_if_needed()
    except Exception as exc:
        log(f"Scheduler tick error: {exc}", adsk.core.LogLevels.ErrorLogLevel)
    if _scheduler_active.is_set():
        t = threading.Timer(_TICK_INTERVAL, _schedule_tick)
        t.daemon = True
        t.start()


_last_fire_time = 0.0


def _fire_event_if_needed():
    """Signal the main thread when there is queued work or a keepalive is due."""
    import time

    global _last_fire_time
    now = time.time()
    has_work = not _pending.empty()
    keepalive_due = (now - _last_fire_time) >= _KEEPALIVE_INTERVAL
    if has_work or keepalive_due:
        get_app().fireCustomEvent(CALLBACK_EVENT_ID)
        _last_fire_time = now


# ── Public dispatch API ──────────────────────────────────────────────────


def set_tool_handler(handler):
    global _callback_impl
    _callback_impl = handler


def dispatch_to_main_thread(call_data):
    """Submit *call_data* for execution on the Fusion main thread and block
    until the result is available.  If already on the main thread, execute
    directly."""
    if threading.current_thread() is threading.main_thread():
        if _callback_impl is None:
            raise RuntimeError("Tool implementation is not initialized")
        return _callback_impl(call_data)

    reply = queue.Queue(maxsize=1)
    envelope = {"payload": call_data, "reply": reply}
    _pending.put(envelope)

    try:
        get_app().fireCustomEvent(CALLBACK_EVENT_ID)
    except Exception as exc:
        _try_remove(envelope)
        log(
            f"Failed to fire main-thread event: {exc}",
            adsk.core.LogLevels.ErrorLogLevel,
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Error: RuntimeError: failed to schedule Fusion main-thread work ({exc})",
                }
            ],
            "isError": True,
        }

    return reply.get()


# ── Internal helpers ─────────────────────────────────────────────────────


def _try_remove(envelope):
    """Best-effort removal of an unprocessed envelope from the queue."""
    with _pending.mutex:
        try:
            _pending.queue.remove(envelope)
            return True
        except ValueError:
            return False


def _flush_pending():
    """Process up to *_BATCH_LIMIT* envelopes from the queue."""
    if not _run_lock.acquire(blocking=False):
        return
    try:
        drain_logs()
        processed = 0
        while processed < _BATCH_LIMIT:
            try:
                envelope = _pending.get_nowait()
            except queue.Empty:
                break

            payload = envelope["payload"]
            reply = envelope["reply"]
            try:
                if _callback_impl is None:
                    raise RuntimeError("Tool implementation is not initialized")
                result = _callback_impl(payload)
            except Exception as exc:
                tb = traceback.format_exc()
                log(
                    f"Main-thread work item failed: {exc}",
                    adsk.core.LogLevels.ErrorLogLevel,
                )
                log(tb, adsk.core.LogLevels.ErrorLogLevel)
                result = {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"Error: {type(exc).__name__}: {exc}\n"
                                "Call: _flush_pending()\n"
                                f"Traceback:\n{tb}"
                            ),
                        }
                    ],
                    "isError": True,
                }

            reply.put(result)
            processed += 1

        drain_logs()
    finally:
        _run_lock.release()


# ── Lifecycle ─────────────────────────────────────────────────────────────


def init_main_thread_dispatch():
    global _callback_event, _registered

    if _registered:
        raise RuntimeError("Main-thread dispatch is already initialized")

    _halt.clear()
    _scheduler_active.clear()
    _callback_event = get_app().registerCustomEvent(CALLBACK_EVENT_ID)
    handler = _BridgeEventHandler()
    _callback_event.add(handler)
    # Store handler on the event object to prevent GC
    _callback_event._bridge_handler = handler
    _registered = True

    _scheduler_active.set()
    _schedule_tick()


def stop_main_thread_dispatch():
    global _callback_event, _registered

    _halt.set()
    _scheduler_active.clear()

    if _callback_event and hasattr(_callback_event, "_bridge_handler"):
        try:
            _callback_event.remove(_callback_event._bridge_handler)
        except Exception as exc:
            log(
                f"Error removing event handler: {exc}",
                adsk.core.LogLevels.WarningLogLevel,
            )

    app = None
    try:
        app = get_app()
    except Exception:
        app = None

    if app and _registered and hasattr(app, "unregisterCustomEvent"):
        try:
            app.unregisterCustomEvent(CALLBACK_EVENT_ID)
        except Exception as exc:
            log(
                f"Error unregistering custom event: {exc}",
                adsk.core.LogLevels.WarningLogLevel,
            )

    _registered = False
    _callback_event = None


def get_shutdown_flag():
    return _halt
