from eastmoney_quant_mcp.alerts import AlertState, PriceUpdate, ZoneRule, evaluate_zone


def _rule(**kwargs):
    return ZoneRule(zone_id="z1", symbol="600000", timeframe="daily",
                    lower=9.8, upper=10.2, **kwargs)


def test_zone_alerts_approach_touch_and_closed_breakout_are_distinct():
    state = None
    state, events = evaluate_zone(_rule(), state, PriceUpdate("t1", 10.21, closed=False))
    assert [x.event_type for x in events] == ["approaching"]
    state, events = evaluate_zone(_rule(), state, PriceUpdate("t2", 10.1, high=10.3, low=10.0))
    assert [x.event_type for x in events] == ["touched"]
    state, events = evaluate_zone(_rule(), state, PriceUpdate("t3", 10.3, closed=False))
    assert [x.event_type for x in events] == ["crossed_intrabar"]
    state, events = evaluate_zone(_rule(), state, PriceUpdate("t4", 10.3, closed=True))
    assert [x.event_type for x in events] == ["breakout"]
    assert events[0].confirmed is True


def test_same_episode_dedupes_touch():
    state = AlertState(zone_id="z1", relation="below")
    state, first = evaluate_zone(_rule(), state, PriceUpdate("t1", 10.0, high=10.1, low=9.9))
    state, second = evaluate_zone(_rule(), state, PriceUpdate("t2", 10.0, high=10.1, low=9.9))
    assert any(x.event_type == "touched" for x in first)
    assert not second


def test_invalidated_is_once_and_terminal():
    state = None
    rule = _rule(invalidated=True)
    state, first = evaluate_zone(rule, state, PriceUpdate("t1", 10.0, closed=True))
    state, second = evaluate_zone(rule, state, PriceUpdate("t2", 10.0, closed=True))
    assert [x.event_type for x in first] == ["invalidated"]
    assert second == []


def test_alert_state_and_events_persist_idempotently(tmp_path):
    from eastmoney_quant_mcp.alerts import (
        list_alert_events, load_alert_state, persist_alert_evaluation,
    )
    from eastmoney_quant_mcp.data import storage

    storage.set_db_paths(str(tmp_path / "stock.db"), str(tmp_path / "sector.db"))
    try:
        storage.init_all()
        state, events = evaluate_zone(
            _rule(), None, PriceUpdate("2026-09-17T10:00:00", 10.0, high=10.1, low=9.9),
        )
        assert persist_alert_evaluation(
            symbol="600000", timeframe="daily", state=state, events=events,
        ) == len(events)
        assert persist_alert_evaluation(
            symbol="600000", timeframe="daily", state=state, events=events,
        ) == 0
        restored = load_alert_state("z1")
        assert restored is not None
        assert restored.emitted == state.emitted
        rows = list_alert_events(symbol="600000")
        assert len(rows) == len(events)
    finally:
        storage.set_db_paths(None, None)
