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
        """
        if self._destroyed:
            return None

        loop = getattr(self.app, "loop", None)
        if loop is None:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                return None

        try:
            task = loop.create_task(coro)
        except RuntimeError:
            return None
        try:
            task.set_name(f"{type(self).__name__}.{name}")
        except Exception:
            pass

        with self._destroy_lock:
            if self._destroyed:
                task.cancel()
                return None
            self._async_tasks.append(task)
        return task
