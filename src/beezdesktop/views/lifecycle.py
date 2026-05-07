"""
View lifecycle helpers shared by every BeezDesktop view.

Why this exists
---------------
Every Toga view spawns background work (HTTP calls, fastembed warm-up,
blockchain polling). When the user navigates away, that background work
keeps running and tries to mutate Toga widgets that have been removed
from the tree. On GTK that produces either a silent UI freeze or a
cascade of `RuntimeError: dictionary changed size during iteration`
inside the asyncio loop, which is exactly the "Wallet/Blockchain/Files
stop loading after visiting Smart/Knowledge" symptom from the
production audit (D-04, D-05).

`ViewLifecycle` gives every view three guarantees:

1. ``self._destroyed`` is set to ``True`` by ``app._clear_content`` the
   moment the view leaves the screen.
2. Background callbacks scheduled via ``self.safe_ui_call(fn, ...)`` are
   silently dropped after destruction, so they never touch a dead
   widget.
3. ``asyncio.Task`` instances created via
   ``self.spawn_task(coro, name=...)`` are cancelled on destruction.
4. ``threading.Thread`` workers created via
   ``self.spawn_worker(target, name=...)`` are tracked, marked daemon,
   and will exit naturally on their next ``safe_ui_call`` because the
   callback is a no-op.

Importing this module has no side effects beyond the standard library.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Callable, List, Optional


logger = logging.getLogger("beezdesktop.lifecycle")


class ViewLifecycle:
    """Mixin that gives a view a controlled background-work lifecycle.

    Subclasses must call ``ViewLifecycle.__init__(self, app)`` from their
    own ``__init__``. They should then use ``self.spawn_worker``,
    ``self.spawn_task`` and ``self.safe_ui_call`` instead of raw
    ``threading.Thread`` / ``asyncio.create_task`` /
    ``app.loop.call_soon_threadsafe``.
    """

    def __init__(self, app: Any) -> None:
        self.app = app
        self._destroyed: bool = False
        self._workers: List[threading.Thread] = []
        self._async_tasks: List[asyncio.Task] = []
        self._destroy_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle hooks - called by app._clear_content / _switch_view
    # ------------------------------------------------------------------

    def destroy(self) -> None:
        """Mark the view as destroyed and cancel its async tasks.

        Safe to call multiple times. Background threads are not killed
        (Python cannot kill threads); they just become no-ops on their
        next ``safe_ui_call`` because the view is destroyed.
        """
        with self._destroy_lock:
            if self._destroyed:
                return
            self._destroyed = True
            tasks = list(self._async_tasks)
            workers = list(self._workers)
            self._async_tasks.clear()
            self._workers.clear()

        for task in tasks:
            try:
                if not task.done():
                    task.cancel()
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("destroy: task cancel failed: %s", exc)

        live_workers = sum(1 for t in workers if t.is_alive())
        if live_workers:
            logger.debug(
                "destroy: %s background workers still alive (will no-op on completion)",
                live_workers,
            )

    # ------------------------------------------------------------------
    # Public helpers used by view code
    # ------------------------------------------------------------------

    def safe_ui_call(self, fn: Callable, *args: Any, **kwargs: Any) -> bool:
        """Schedule ``fn(*args, **kwargs)`` on the Toga event loop.

        Returns True if the callback was scheduled, False if the view
        was already destroyed.

        The wrapper guards against widget mutation after destruction:
        even if Toga keeps the loop alive, the callback exits early
        without touching anything.
        """
        if self._destroyed:
            return False

        loop = getattr(self.app, "loop", None)
        if loop is None:  # pragma: no cover - Toga always sets loop
            return False

        def _guarded() -> None:
            if self._destroyed:
                return
            try:
                fn(*args, **kwargs)
            except Exception as exc:
                logger.error(
                    "[%s] safe_ui_call exception in %s: %s",
                    type(self).__name__,
                    getattr(fn, "__name__", repr(fn)),
                    exc,
                )

        try:
            loop.call_soon_threadsafe(_guarded)
            return True
        except RuntimeError:
            # Loop is closed - app is shutting down
            return False

    def spawn_worker(
        self,
        target: Callable,
        name: str = "worker",
        args: tuple = (),
        kwargs: Optional[dict] = None,
    ) -> Optional[threading.Thread]:
        """Start a daemon thread and register it for cleanup tracking.

        Returns the started thread, or None if the view is already
        destroyed.
        """
        if self._destroyed:
            return None

        kwargs = kwargs or {}
        thread_name = f"{type(self).__name__}.{name}"

        def _runner() -> None:
            try:
                target(*args, **kwargs)
            except Exception as exc:
                logger.error("[%s] worker %s crashed: %s", type(self).__name__, name, exc)

        thread = threading.Thread(target=_runner, name=thread_name, daemon=True)
        with self._destroy_lock:
            if self._destroyed:
                return None
            self._workers.append(thread)
        thread.start()
        return thread

    def spawn_task(self, coro, name: str = "task") -> Optional[asyncio.Task]:
        """Create an asyncio.Task tracked by this view.

        Returns the Task, or None if the view is destroyed or the loop
        is unavailable.

        NOTE: this depends on the asyncio loop actually scheduling the
        task. Under gbulb (Toga's GTK loop) we have observed B-17 where
        the loop becomes biased toward GTK events after a heavy event
        burst (e.g. file upload + dialog dismissal) and newly created
        tasks sit in the queue without ever running, even though
        ``loop.call_soon_threadsafe`` callbacks still fire.

        For "fetch data on view build" patterns prefer ``self.bg_load``
        which uses a thread and is therefore independent of the loop's
        scheduling state. ``spawn_task`` is still the right tool for
        coroutines that need to ``await`` Toga dialogs or for handler
        wrappers; we just instrument it so future regressions are
        visible in the log.
        """
        if self._destroyed:
            try:
                coro.close()
            except Exception:
                pass
            return None

        loop = getattr(self.app, "loop", None)
        if loop is None:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                logger.error(
                    "[%s] spawn_task(%s): no event loop available",
                    type(self).__name__, name,
                )
                try:
                    coro.close()
                except Exception:
                    pass
                return None

        try:
            task = loop.create_task(coro)
        except RuntimeError as exc:
            logger.error(
                "[%s] spawn_task(%s): create_task raised %s",
                type(self).__name__, name, exc,
            )
            try:
                coro.close()
            except Exception:
                pass
            return None
        try:
            task.set_name(f"{type(self).__name__}.{name}")
        except Exception:
            pass

        # B-17 watchdog: warn if the task is created but never starts
        # running on the loop within a reasonable window. This is a
        # diagnostic only - it does not retry or reschedule, but next
        # time the user reports "data stopped loading" the log will
        # explicitly say so.
        view_name = type(self).__name__
        task_label = f"{view_name}.{name}"

        def _on_done(t: asyncio.Task) -> None:
            if t.cancelled():
                logger.debug(
                    "[lifecycle] task %s cancelled (view destroyed?)", task_label
                )
                return
            exc = t.exception() if not t.cancelled() else None
            if exc is not None:
                logger.error(
                    "[lifecycle] task %s raised: %r", task_label, exc,
                )

        task.add_done_callback(_on_done)

        async def _watchdog() -> None:
            # Give the loop generous time to start it. 3s is enormous
            # for a healthy gbulb loop; if we exceed it the loop is
            # almost certainly being starved by GTK events.
            await asyncio.sleep(3.0)
            if not task.done() and not task.cancelled():
                # The task is still pending. It was created but never
                # ran. This is the B-17 fingerprint.
                logger.warning(
                    "[lifecycle] B-17: task %s still PENDING after 3s "
                    "(loop starvation?). Use self.bg_load() instead.",
                    task_label,
                )

        try:
            wd = loop.create_task(_watchdog())
            wd.add_done_callback(lambda _t: None)
        except Exception:
            pass

        with self._destroy_lock:
            if self._destroyed:
                task.cancel()
                return None
            self._async_tasks.append(task)
        return task

    def bg_load(
        self,
        work_fn: Callable,
        ui_fn: Optional[Callable] = None,
        *,
        error_ui_fn: Optional[Callable] = None,
        name: str = "bg_load",
    ) -> Optional[threading.Thread]:
        """Run ``work_fn()`` in a background thread, then deliver the
        result to ``ui_fn(result)`` on the Toga UI thread.

        This is the B-17 hardened replacement for the common pattern::

            self.spawn_task(self._load_xxx(), name="load_xxx")

        where ``_load_xxx`` was an ``async def`` that immediately awaited
        ``loop.run_in_executor(None, sync_call)``.

        Why a thread instead of an asyncio.Task?
            After a burst of GTK activity (file upload + dialog +
            navigation), gbulb has been observed to leave newly created
            asyncio tasks PENDING indefinitely while still serving
            ``call_soon_threadsafe`` callbacks. A plain daemon thread is
            independent of the loop's scheduling state and always runs.

        Parameters
        ----------
        work_fn:
            Synchronous callable executed in the background thread. Must
            be safe to call from a non-loop thread.
        ui_fn:
            Optional callable invoked on the UI thread with the result
            of ``work_fn()``. Skipped if the view has been destroyed by
            the time the work finishes.
        error_ui_fn:
            Optional callable invoked on the UI thread with the
            exception when ``work_fn()`` raises. Skipped on destroy.
        name:
            Logical name used in logs and worker thread name.
        """
        if self._destroyed:
            return None

        view = self
        view_name = type(self).__name__

        def runner() -> None:
            try:
                result = work_fn()
            except Exception as exc:
                logger.error(
                    "[%s] bg_load %s failed: %s",
                    view_name, name, exc,
                )
                if error_ui_fn is not None:
                    view.safe_ui_call(error_ui_fn, exc)
                return

            if ui_fn is not None:
                view.safe_ui_call(ui_fn, result)

        return self.spawn_worker(runner, name=name)

    def wrap_handler(self, async_handler: Callable, name: str = "handler") -> Callable:
        """Wrap an async ``on_press`` handler so it is tracked + cancelled on destroy.

        Usage in build():
            primary_button("Send", self.wrap_handler(self._on_send, "send"))

        The returned function is sync and returns immediately so Toga
        does not try to ``await`` it (which would put the task back on
        Toga's untracked pool). The actual coroutine runs via
        ``self.spawn_task``, so destroy() can cancel it.
        """
        view = self

        def _sync_press(widget):
            async def _runner():
                try:
                    await async_handler(widget)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error(
                        "[%s] handler %s raised: %s",
                        type(view).__name__, name, exc,
                    )

            view.spawn_task(_runner(), name=name)

        _sync_press.__name__ = f"wrap_handler({name})"
        return _sync_press

    def is_destroyed(self) -> bool:
        """Tiny helper for views that want to bail mid-await."""
        return self._destroyed
