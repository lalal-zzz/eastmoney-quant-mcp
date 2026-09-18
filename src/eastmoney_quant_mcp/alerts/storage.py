from __future__ import annotations

import json
from datetime import datetime

from ..data.storage.paths import get_stock_db
from ..data.storage.schema import _write_conn
from .models import AlertEvent, AlertState


def load_alert_state(zone_id: str) -> AlertState | None:
    from ..data.storage.query import query_stock_db
    rows = query_stock_db("SELECT * FROM alert_state WHERE zone_id=?", (zone_id,))
    if not rows:
        return None
    row = rows[0]
    return AlertState(
        zone_id=row["zone_id"], episode=int(row["episode"]), relation=row["relation"],
        emitted=set(json.loads(row["emitted_json"] or "[]")),
        invalidated=bool(row["invalidated"]), last_timestamp=row["last_timestamp"],
    )


def persist_alert_evaluation(*, symbol: str, timeframe: str,
                             state: AlertState, events: list[AlertEvent]) -> int:
    """Atomically persist state and idempotent events for crash recovery."""
    now = datetime.now().isoformat()
    with _write_conn(get_stock_db()) as conn:
        conn.execute("""
            INSERT INTO alert_state
                (zone_id,symbol,timeframe,episode,relation,emitted_json,invalidated,
                 last_timestamp,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(zone_id) DO UPDATE SET
                symbol=excluded.symbol,timeframe=excluded.timeframe,
                episode=excluded.episode,relation=excluded.relation,
                emitted_json=excluded.emitted_json,invalidated=excluded.invalidated,
                last_timestamp=excluded.last_timestamp,updated_at=excluded.updated_at
        """, (state.zone_id, symbol, timeframe, state.episode, state.relation,
              json.dumps(sorted(state.emitted)), int(state.invalidated),
              state.last_timestamp, now))
        inserted = 0
        for event in events:
            before = conn.total_changes
            conn.execute("""
                INSERT OR IGNORE INTO alert_events
                    (idempotency_key,zone_id,symbol,timeframe,episode,event_type,
                     event_timestamp,close,lower,upper,confirmed,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """, (event.idempotency_key, event.zone_id, event.symbol, event.timeframe,
                  event.episode, event.event_type, event.timestamp, event.close,
                  event.lower, event.upper, int(event.confirmed), now))
            inserted += conn.total_changes - before
    return inserted


def list_alert_events(*, symbol: str | None = None, limit: int = 100) -> list[dict]:
    from ..data.storage.query import query_stock_db
    limit = max(1, min(int(limit), 1000))
    if symbol:
        return query_stock_db(
            "SELECT * FROM alert_events WHERE symbol=? ORDER BY event_timestamp DESC LIMIT ?",
            (symbol, limit),
        )
    return query_stock_db(
        "SELECT * FROM alert_events ORDER BY event_timestamp DESC LIMIT ?", (limit,),
    )
