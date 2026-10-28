"""Unit tests for the e2e time-budgeted wait helper (issue #626).

Deterministic: ``wait_until`` takes injectable ``sleep``/``clock``, so a fake sleep
advances a fake clock and no real time passes.
"""

from __future__ import annotations


class _FakeTime:
    """A monotonic clock a fake ``sleep`` advances, so the budget is deterministic."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds

    def clock(self) -> float:
        return self.now


async def test_wait_until_returns_true_when_the_predicate_flips() -> None:
    from tests.integration._godot import wait_until

    fake = _FakeTime()
    calls = {"n": 0}

    async def pred() -> bool:
        calls["n"] += 1
        return calls["n"] >= 3

    ok = await wait_until(pred, timeout=10.0, interval=1.0, sleep=fake.sleep, clock=fake.clock)
    assert ok is True
    assert calls["n"] == 3
    assert fake.slept == [1.0, 1.0]


async def test_wait_until_returns_false_when_the_budget_is_exhausted() -> None:
    from tests.integration._godot import wait_until

    fake = _FakeTime()

    async def pred() -> bool:
        return False

    ok = await wait_until(pred, timeout=3.0, interval=1.0, sleep=fake.sleep, clock=fake.clock)
    assert ok is False
    # It polled until now() >= deadline (3.0s), not a fixed iteration count.
    assert fake.now >= 3.0


async def test_wait_until_accepts_a_sync_predicate() -> None:
    from tests.integration._godot import wait_until

    assert await wait_until(lambda: True, timeout=1.0) is True


async def test_wait_probe_connected_succeeds_when_connected_flips() -> None:
    """Shared helper used by play-session e2e (incl. 4.8 advisory lane)."""
    import tests.integration._godot as godot_helpers
    from mcp_server.models.envelope import ResponseEnvelope
    from tests.integration._godot import wait_probe_connected

    fake = _FakeTime()
    calls = {"n": 0}
    original = godot_helpers.wait_until

    async def _wait_until(pred, *, timeout, interval=0.25, sleep=None, clock=None):
        return await original(
            pred, timeout=timeout, interval=interval, sleep=fake.sleep, clock=fake.clock
        )

    class _Bridge:
        async def send(self, command: str, params: dict | None = None) -> ResponseEnvelope:
            assert command == "cmd_get_game_scene_tree"
            calls["n"] += 1
            return ResponseEnvelope.success(
                "id", {"connected": calls["n"] >= 3, "tree": None}
            )

    godot_helpers.wait_until = _wait_until  # type: ignore[assignment]
    try:
        await wait_probe_connected(_Bridge(), timeout=10.0, interval=1.0)
    finally:
        godot_helpers.wait_until = original  # type: ignore[assignment]
    assert calls["n"] == 3


async def test_wait_probe_connected_fails_with_last_state() -> None:
    import tests.integration._godot as godot_helpers
    from mcp_server.models.envelope import ResponseEnvelope
    from tests.integration._godot import wait_probe_connected

    fake = _FakeTime()
    original = godot_helpers.wait_until

    async def _wait_until(pred, *, timeout, interval=0.25, sleep=None, clock=None):
        return await original(
            pred, timeout=timeout, interval=interval, sleep=fake.sleep, clock=fake.clock
        )

    class _Bridge:
        async def send(self, command: str, params: dict | None = None) -> ResponseEnvelope:
            return ResponseEnvelope.success("id", {"connected": False, "playing": True})

    godot_helpers.wait_until = _wait_until  # type: ignore[assignment]
    try:
        try:
            await wait_probe_connected(_Bridge(), timeout=2.0, interval=1.0)
            raised = False
            message = ""
        except AssertionError as exc:
            raised = True
            message = str(exc)
        assert raised
        assert "never connected" in message
        assert "playing" in message
    finally:
        godot_helpers.wait_until = original  # type: ignore[assignment]
