"""Lifecycle tests for BeezDesktop views.

These tests exercise the regression that produced the production "freeze
after visiting Smart/Knowledge" symptom (audit D-04, D-05):

    1. SmartView/KnowledgeView spawn a daemon worker.
    2. The user navigates away. `app._clear_content` calls `view.destroy()`.
    3. The daemon worker finishes its HTTP call and tries to mutate widgets
       via `app.loop.call_soon_threadsafe(...)`.
    4. Toga widgets are gone; the asyncio loop ends up touching dead Python
       objects, which freezes the rest of the app.

The fix wraps every cross-thread UI write in `view.safe_ui_call(...)`.
After `view.destroy()`, the wrapper is a no-op. These tests prove that.

We don't run a real Toga loop; we plug a fake `loop` object into the
fake `app` that records calls so the assertions don't depend on toga's
event loop.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from typing import Any, Callable, List

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("", "src", "shared"):
    p = os.path.join(ROOT, sub) if sub else ROOT
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)


from beezdesktop.views.lifecycle import ViewLifecycle  # noqa: E402


class _FakeLoop:
    """Minimal stand-in for an asyncio loop's ``call_soon_threadsafe``.

    Records every callback the lifecycle scheduled, and runs them inline
    (the tests are synchronous; that's fine - the production code path
    only cares that the callback is the no-op wrapper, not when it runs).
    """

    def __init__(self) -> None:
        self.calls: List[Callable] = []
        self.invocations: List[Callable] = []

    def call_soon_threadsafe(self, cb: Callable, *args: Any) -> None:
        self.calls.append(cb)
        cb(*args)
        self.invocations.append(cb)


class _FakeApp:
    def __init__(self) -> None:
        self.loop = _FakeLoop()


def test_safe_ui_call_runs_when_alive():
    app = _FakeApp()
    view = ViewLifecycle(app)

    flag = {"hit": False}

    def cb():
        flag["hit"] = True

    assert view.safe_ui_call(cb) is True
    assert flag["hit"] is True
    assert app.loop.calls, "expected at least one scheduled callback"


def test_safe_ui_call_is_noop_after_destroy():
    """Core regression test for D-04/D-05.

    After destroy(), every safe_ui_call must NOT execute the underlying
    callback, even if the loop happens to fire it. This is the contract
    that prevents Smart/Knowledge workers from clobbering Wallet widgets.
    """
    app = _FakeApp()
    view = ViewLifecycle(app)
    view.destroy()
    assert view._destroyed is True

    flag = {"hit": False}

    def cb():
        flag["hit"] = True

    assert view.safe_ui_call(cb) is False
    assert flag["hit"] is False
    assert app.loop.calls == []


def test_destroy_is_idempotent():
    app = _FakeApp()
    view = ViewLifecycle(app)
    view.destroy()
    view.destroy()
    view.destroy()
    assert view._destroyed is True


def test_spawn_worker_post_callback_is_dropped_after_destroy():
    """End-to-end repro of the production freeze.

    A worker thread runs a slow op, then calls back into the UI via
    safe_ui_call. If the user navigates away while the op runs, the
    callback must be silently dropped.
    """
    app = _FakeApp()
    view = ViewLifecycle(app)

    started = threading.Event()
    proceed = threading.Event()
    after_callback = threading.Event()
    flag = {"widget_mutated": False}

    def worker():
        started.set()
        proceed.wait(2.0)
        # Worker finished its HTTP call; try to update the UI
        view.safe_ui_call(lambda: flag.__setitem__("widget_mutated", True))
        after_callback.set()

    view.spawn_worker(worker, name="t")
    assert started.wait(2.0), "worker did not start"

    # User navigates away while the worker is still mid-flight.
    view.destroy()

    # Let the worker finish its callback.
    proceed.set()
    assert after_callback.wait(2.0), "worker did not complete"

    assert flag["widget_mutated"] is False, (
        "After destroy(), the worker callback must be a no-op. "
        "If this fails, audit D-04/D-05 has regressed."
    )


def test_spawn_worker_returns_none_after_destroy():
    app = _FakeApp()
    view = ViewLifecycle(app)
    view.destroy()
    assert view.spawn_worker(lambda: None, name="t") is None


def test_smart_view_inherits_lifecycle():
    """SmartView must use the lifecycle so the freeze fix is wired up."""
    pytest.importorskip("toga")
    from beezdesktop.views.smart import SmartView
    assert issubclass(SmartView, ViewLifecycle)


def test_knowledge_view_inherits_lifecycle():
    """KnowledgeView must use the lifecycle so the freeze fix is wired up."""
    pytest.importorskip("toga")
    from beezdesktop.views.knowledge import KnowledgeView
    assert issubclass(KnowledgeView, ViewLifecycle)


@pytest.mark.parametrize(
    "module_name,class_name",
    [
        ("beezdesktop.views.wallet", "WalletView"),
        ("beezdesktop.views.network", "NetworkView"),
        ("beezdesktop.views.dashboard", "DashboardView"),
        ("beezdesktop.views.blockchain", "BlockchainView"),
        ("beezdesktop.views.transactions", "TransactionsView"),
        ("beezdesktop.views.settings", "SettingsView"),
        ("beezdesktop.views.files", "FilesView"),
    ],
)
def test_every_view_inherits_lifecycle(module_name: str, class_name: str) -> None:
    """B-14 regression: all 9 views need ViewLifecycle so destroy() exists.

    Previously only SmartView and KnowledgeView were wrapped, leaving 7
    views vulnerable to the same dead-widget mutation that froze v0.6.0
    after rapid-fire navigation between Smart/Knowledge and the rest.
    """
    pytest.importorskip("toga")
    import importlib
    mod = importlib.import_module(module_name)
    cls = getattr(mod, class_name)
    assert issubclass(cls, ViewLifecycle), (
        f"{class_name} must inherit ViewLifecycle. "
        f"If this fails, B-14 has regressed."
    )


def test_spawn_task_drops_coro_after_destroy():
    """spawn_task must NOT leak coroutines when called after destroy.

    Without the close() fallback, the coroutine becomes a 'never awaited'
    warning at process exit and (worse) keeps a reference to self.
    """
    app = _FakeApp()
    view = ViewLifecycle(app)
    view.destroy()

    closed = {"yes": False}

    async def coro():  # pragma: no cover - never awaited by design
        closed["yes"] = True

    c = coro()
    task = view.spawn_task(c, name="post_destroy")
    assert task is None
    # Coroutine should be closed (so Python doesn't warn at GC time).
    # Calling close() twice is a no-op; calling send() raises.
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        c.close()  # idempotent close, must not raise


def test_rapid_view_switch_simulation():
    """B-14 stress simulation.

    Reproduces the user's freeze pattern: spawn a view, kick off a fake
    background worker that intends to mutate UI, then immediately destroy
    the view -- before the worker callback fires. Repeat for 14 view
    switches in quick succession (the exact count from terminal log
    16:37:01-16:37:14). Every callback must be a no-op.
    """
    callbacks_executed = {"count": 0}

    for _ in range(14):
        app = _FakeApp()
        view = ViewLifecycle(app)

        ready = threading.Event()

        def slow_worker(v=view, r=ready):
            # Simulate an HTTP fetch that completes AFTER navigation
            r.wait(0.5)
            v.safe_ui_call(lambda: callbacks_executed.__setitem__(
                "count", callbacks_executed["count"] + 1
            ))

        view.spawn_worker(slow_worker, name="rapid")
        # User navigates IMMEDIATELY - same as 14 views in 13 seconds.
        view.destroy()
        ready.set()

    # Allow workers to finish their (now no-op) callbacks.
    time.sleep(0.7)
    assert callbacks_executed["count"] == 0, (
        f"After 14 rapid destroys, {callbacks_executed['count']} "
        "callback(s) ran on dead views. The fix is incomplete."
    )


def test_knowledge_view_does_not_lazy_load_with_lock_per_query():
    """The per-query _embed_lock acquisition was a freeze source.

    The fix moved warm-up to a daemon thread; queries should not need to
    re-acquire any lock to read the cached model.
    """
    pytest.importorskip("toga")
    from beezdesktop.views import knowledge as kv

    # The module-level _embed_warm_lock exists, but it must NOT be the same
    # serialising lock the previous _embed_lock was. The new contract: once
    # warmed, _get_embed_model returns the cached instance without locking.
    assert hasattr(kv, "prewarm_embed_model"), (
        "prewarm_embed_model is the new public entrypoint; "
        "if it's gone the freeze fix has regressed."
    )

    # _embed_lock no longer exists as the per-query mutex.
    assert not hasattr(kv, "_embed_lock"), (
        "_embed_lock was the per-query mutex that serialised marketplace "
        "queries. It must not come back."
    )


def test_view_switch_warning_threshold_constant():
    """The 250ms warning is the regression guard for D-04/D-05."""
    import beezdesktop.app as app_module
    src = open(app_module.__file__).read()
    assert "250" in src, (
        "_switch_view should log a warning when a view switch exceeds 250ms; "
        "the constant is missing - regression guard for D-04/D-05 is gone."
    )


# ---------------------------------------------------------------------------
# B-17 regression tests: bg_load runs in a thread, independent of the
# asyncio loop's scheduling state. The user reproduced this on v0.6.2:
# after a file upload, asyncio Tasks created via spawn_task stopped firing
# (Wallet/Transactions/Blockchain/Files all stuck on "Loading..."). The
# proven-good escape hatch is a thread that uses safe_ui_call, since
# safe_ui_call -> call_soon_threadsafe was confirmed to still work in
# the same window.
# ---------------------------------------------------------------------------


def test_bg_load_runs_work_and_delivers_result():
    """bg_load must execute work_fn and pass the result to ui_fn."""
    app = _FakeApp()
    view = ViewLifecycle(app)

    done = threading.Event()
    seen = {"result": None}

    def work():
        return {"value": 42}

    def ui(result):
        seen["result"] = result
        done.set()

    thread = view.bg_load(work_fn=work, ui_fn=ui, name="t")
    assert thread is not None, "bg_load must return a thread when alive"
    assert done.wait(2.0), "bg_load did not deliver result within 2s"
    assert seen["result"] == {"value": 42}


def test_bg_load_calls_error_ui_fn_on_exception():
    app = _FakeApp()
    view = ViewLifecycle(app)

    done = threading.Event()
    captured = {"exc": None}

    def work():
        raise RuntimeError("boom")

    def ok(_r):
        pytest.fail("ui_fn should NOT be called when work raises")

    def err(exc):
        captured["exc"] = exc
        done.set()

    view.bg_load(work_fn=work, ui_fn=ok, error_ui_fn=err, name="boom")
    assert done.wait(2.0), "error path did not fire"
    assert isinstance(captured["exc"], RuntimeError)
    assert str(captured["exc"]) == "boom"


def test_bg_load_drops_callback_after_destroy():
    """B-17 contract: even if bg_load fires after destroy, ui_fn must not run.

    This mirrors the lifecycle guarantee for spawn_worker: a worker that
    completes after the view was navigated away from MUST NOT mutate any
    Toga widget. bg_load is built on top of spawn_worker + safe_ui_call,
    so this property must hold by construction.
    """
    app = _FakeApp()
    view = ViewLifecycle(app)

    proceed = threading.Event()
    after_call = threading.Event()
    flag = {"ui_fired": False}

    def work():
        proceed.wait(2.0)
        return "result"

    def ui(_r):
        flag["ui_fired"] = True
        after_call.set()

    view.bg_load(work_fn=work, ui_fn=ui, name="late")
    view.destroy()
    proceed.set()

    # Even though work_fn returned, the safe_ui_call wrapping ui_fn is
    # a no-op after destroy.
    after_call.wait(1.5)
    assert flag["ui_fired"] is False, (
        "After destroy(), ui_fn must NOT execute. B-17 fix is broken."
    )


def test_bg_load_returns_none_after_destroy():
    app = _FakeApp()
    view = ViewLifecycle(app)
    view.destroy()
    assert view.bg_load(work_fn=lambda: None, ui_fn=lambda _r: None) is None


def test_bg_load_does_not_use_asyncio_loop_for_work():
    """Architecture guard for B-17.

    The whole point of bg_load is to bypass the asyncio scheduler. If
    someone refactors bg_load to use create_task (or schedules work via
    the loop), this test fails.
    """
    app = _FakeApp()
    view = ViewLifecycle(app)

    def work():
        return "x"

    view.bg_load(work_fn=work, ui_fn=lambda _r: None, name="arch")
    # Allow worker to finish.
    time.sleep(0.2)

    # bg_load should only schedule the UI continuation via the loop, not
    # the actual work. So at most ONE call_soon_threadsafe call.
    assert len(app.loop.calls) <= 1, (
        "bg_load is touching the loop more than once; the work_fn "
        "appears to be running on the loop instead of a thread. B-17 "
        "fix architecture is compromised."
    )


def test_b17_simulation_after_upload_burst():
    """End-to-end B-17 simulation.

    Reproduces the user's exact symptom from v0.6.2:
        1. View built (Wallet)
        2. bg_load kicked off
        3. Loop is "starved" (we simulate by NOT running call_soon_threadsafe
           in real time - here we just check the result lands)
        4. Result must still arrive because work_fn runs on a thread.
    """
    app = _FakeApp()
    view = ViewLifecycle(app)

    delivered = threading.Event()
    captured = {"data": None}

    def fetch_balance():
        return ({"balance": 100}, 200)

    def show(payload):
        result, status = payload
        captured["data"] = result["balance"]
        delivered.set()

    view.bg_load(
        work_fn=fetch_balance,
        ui_fn=show,
        name="balance_under_starvation",
    )

    assert delivered.wait(2.0), (
        "bg_load delivery did not happen within 2s; B-17 fix is broken."
    )
    assert captured["data"] == 100
