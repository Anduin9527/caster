"""The store's transaction interface also owns the connection lifetime."""

import json
import sqlite3
from contextlib import closing

import pytest

from aigc.store import Store


def test_existing_event_records_survive_adding_the_cursor_index(tmp_path):
    from aigc.agent.events import EventLog

    event = {
        "event_id": "existing:1",
        "conversation_id": "existing",
        "run_id": None,
        "type": "activity",
        "at": 1.0,
        "schema_version": 1,
        "payload": {"detail": "保留旧记录"},
        "seq": 1,
    }
    with closing(sqlite3.connect(tmp_path / "state.sqlite3")) as connection:
        with connection:
            connection.execute(
                "CREATE TABLE records(kind TEXT,id TEXT,body TEXT NOT NULL,PRIMARY KEY(kind,id))"
            )
            connection.execute(
                "INSERT INTO records VALUES(?,?,?)",
                ("agent_event", "existing:1", json.dumps(event)),
            )
    store = Store(tmp_path)
    assert store.get("agent_event", "existing:1") == {**event, "id": "existing:1"}
    assert EventLog(store).since("existing")[0].payload == {"detail": "保留旧记录"}
    with store.connect() as connection:
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(records)")}
    assert "agent_event_cursor" in indexes


def test_transaction_commits_and_closes_connection(tmp_path):
    store = Store(tmp_path)
    with store.connect() as connection:
        connection.execute("INSERT INTO records VALUES ('example', 'one', '{}')")
    assert store.get("example", "one") == {"id": "one"}
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")


def test_failed_transaction_rolls_back_and_closes_connection(tmp_path):
    store = Store(tmp_path)
    with pytest.raises(RuntimeError, match="abort"):
        with store.connect() as connection:
            connection.execute("INSERT INTO records VALUES ('example', 'one', '{}')")
            raise RuntimeError("abort")
    assert store.get("example", "one") is None
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")
