"""Transactional delivery ledger. RabbitMQ transports IDs; SQLite owns execution.

An ACK means the message has reached this durable inbox, not that GPU work has
finished. The executor resumes accepted jobs from SQLite after any restart.
"""

import json
import time
import uuid
from contextvars import ContextVar

request_id = ContextVar("request_id", default="")
ACTIVE = ("submitting", "running", "recovering", "submission_uncertain")


def initialize(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS job_delivery(
            job_id TEXT PRIMARY KEY, generation INTEGER NOT NULL DEFAULT 0,
            received INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0,
            retryable INTEGER NOT NULL DEFAULT 0, available REAL NOT NULL DEFAULT 0,
            request_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS job_outbox(
            id TEXT PRIMARY KEY, job_id TEXT NOT NULL, generation INTEGER NOT NULL,
            kind TEXT NOT NULL, request_id TEXT NOT NULL, created REAL NOT NULL,
            published REAL, attempts INTEGER NOT NULL DEFAULT 0,
            available REAL NOT NULL DEFAULT 0, error TEXT,
            UNIQUE(job_id,generation,kind));
        CREATE INDEX IF NOT EXISTS outbox_pending ON job_outbox(published,available);
        CREATE TABLE IF NOT EXISTS job_events(
            seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
            state TEXT NOT NULL, at REAL NOT NULL);
        CREATE TRIGGER IF NOT EXISTS job_state_created AFTER INSERT ON jobs BEGIN
            INSERT INTO job_events(job_id,state,at) VALUES(NEW.id,NEW.state,NEW.updated);
        END;
        CREATE TRIGGER IF NOT EXISTS job_dead AFTER UPDATE OF state ON jobs
        WHEN NEW.state='failed' AND OLD.state <> NEW.state BEGIN
            INSERT OR IGNORE INTO job_outbox(id,job_id,generation,kind,request_id,created)
            SELECT lower(hex(randomblob(16))),NEW.id,generation,'dead',request_id,NEW.updated
            FROM job_delivery WHERE job_id=NEW.id;
        END;
        CREATE TRIGGER IF NOT EXISTS job_state_changed AFTER UPDATE OF state ON jobs
        WHEN OLD.state <> NEW.state BEGIN
            INSERT INTO job_events(job_id,state,at) VALUES(NEW.id,NEW.state,NEW.updated);
        END;
    """)
    # Old queued work remains recoverable during upgrade, without publishing
    # anything until a configured relay is actually running.
    db.execute("BEGIN IMMEDIATE")
    for row in db.execute("SELECT id FROM jobs WHERE id NOT IN (SELECT job_id FROM job_delivery)"):
        enqueue(db, row["id"], freeze=False)


def enqueue(db, job_id, *, freeze=True):
    """Called inside the SAME transaction as approval + job insertion."""
    trace = request_id.get() or uuid.uuid4().hex
    db.execute("INSERT INTO job_delivery(job_id,request_id) VALUES(?,?)", (job_id, trace))
    _outbox(db, job_id, 0, "dispatch", trace)
    if freeze:
        from .job_snapshot import freeze as freeze_job

        freeze_job(db, job_id)


def _outbox(db, job_id, generation, kind, trace):
    db.execute(
        "INSERT OR IGNORE INTO job_outbox(id,job_id,generation,kind,request_id,created) "
        "VALUES(?,?,?,?,?,?)",
        (uuid.uuid4().hex, job_id, generation, kind, trace, time.time()),
    )


class Delivery:
    def __init__(self, store):
        self.store = store

    def bind_mode(self, mode):
        if mode not in ("local", "rabbitmq"):
            raise ValueError("AIGC_EXECUTION_MODE must be local or rabbitmq")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT body FROM records WHERE kind='runtime' AND id='delivery'"
            ).fetchone()
            if row and json.loads(row["body"])["mode"] != mode:
                raise ValueError(
                    "Execution mode differs from database; stop workers and migrate explicitly"
                )
            db.execute(
                "INSERT OR IGNORE INTO records VALUES('runtime','delivery',?)",
                (json.dumps({"mode": mode}),),
            )

    def accept(self, job_id, generation):
        """Commit inbox receipt before ACK. Duplicate/stale deliveries are harmless."""
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT generation FROM job_delivery WHERE job_id=?", (job_id,)
            ).fetchone()
            if not row or generation > row["generation"]:
                raise ValueError("Unknown task or delivery generation")
            db.execute(
                "UPDATE job_delivery SET received=1 WHERE job_id=? AND generation=?",
                (job_id, generation),
            )

    def eligible(self, job_id, mode):
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM job_delivery WHERE job_id=?", (job_id,)).fetchone()
        return bool(
            row and row["available"] <= time.time() and (mode == "local" or row["received"])
        )

    def begin_submission(self, job_id, mode):
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM jobs WHERE state IN (?,?,?,?) LIMIT 1", ACTIVE).fetchone():
                return False
            receipt = db.execute(
                "SELECT received FROM job_delivery WHERE job_id=?", (job_id,)
            ).fetchone()
            if mode == "rabbitmq" and (not receipt or not receipt["received"]):
                return False
            changed = (
                db.execute(
                    "UPDATE jobs SET state='submitting',updated=? WHERE id=? AND state='queued'",
                    (time.time(), job_id),
                ).rowcount
                == 1
            )
            if changed:
                db.execute("UPDATE job_delivery SET retryable=0 WHERE job_id=?", (job_id,))
            return changed

    def fail_before_submit(self, job_id, error, *, transient, max_attempts=3):
        """Only errors BEFORE submit may retry. The submit intent never gets reset."""
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            job = db.execute("SELECT state,prompt_id FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job or job["state"] != "queued" or job["prompt_id"]:
                return
            row = db.execute("SELECT * FROM job_delivery WHERE job_id=?", (job_id,)).fetchone()
            attempts = row["attempts"] + 1
            retry = transient and attempts < max_attempts
            now = time.time()
            db.execute(
                "UPDATE job_delivery SET attempts=?,retryable=?,available=? WHERE job_id=?",
                (attempts, int(transient), now + min(60, 2**attempts), job_id),
            )
            db.execute(
                "UPDATE jobs SET state=?,error=?,updated=? WHERE id=?",
                ("queued" if retry else "failed", error, now, job_id),
            )
            if not retry:
                _outbox(db, job_id, row["generation"], "dead", row["request_id"])

    def retry(self, job_id, generation):
        """Optimistic retry token prevents double clicks from granting extra attempts."""
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT d.*,j.state,j.prompt_id FROM job_delivery d JOIN jobs j ON j.id=d.job_id WHERE j.id=?",
                (job_id,),
            ).fetchone()
            if not row:
                raise LookupError("Unknown job")
            if row["generation"] == generation + 1 and row["state"] == "queued":
                return
            if (
                row["generation"] != generation
                or row["state"] != "failed"
                or not row["retryable"]
                or row["prompt_id"]
            ):
                raise ValueError("Task cannot be safely retried; reconcile or prepare a new plan")
            db.execute(
                "UPDATE job_delivery SET generation=generation+1,received=0,attempts=0,retryable=0,available=0 WHERE job_id=?",
                (job_id,),
            )
            db.execute(
                "UPDATE jobs SET state='queued',error=NULL,updated=? WHERE id=?",
                (time.time(), job_id),
            )
            _outbox(db, job_id, generation + 1, "dispatch", row["request_id"])

    def info(self, job_id):
        with self.store.connect() as db:
            row = db.execute(
                "SELECT d.*,j.state,j.prompt_id FROM job_delivery d JOIN jobs j ON j.id=d.job_id WHERE j.id=?",
                (job_id,),
            ).fetchone()
        if not row:
            return {}
        return {
            "generation": row["generation"],
            "attempts": row["attempts"],
            "received": bool(row["received"]),
            "request_id": row["request_id"],
            "retryable": bool(
                row["retryable"] and row["state"] == "failed" and not row["prompt_id"]
            ),
        }

    def pending(self):
        with self.store.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM job_outbox WHERE published IS NULL AND available<=? ORDER BY created LIMIT 100",
                    (time.time(),),
                )
            ]

    def published(self, message_id):
        with self.store.connect() as db:
            db.execute(
                "UPDATE job_outbox SET published=?,error=NULL WHERE id=?", (time.time(), message_id)
            )

    def publish_failed(self, message_id, error):
        with self.store.connect() as db:
            db.execute(
                "UPDATE job_outbox SET attempts=attempts+1,available=?+MIN(60,POWER(2,MIN(attempts+1,6))),error=? WHERE id=?",
                (time.time(), error, message_id),
            )

    def events_since(self, stream, cursor="", limit=200):
        from pydantic import BaseModel

        class Event(BaseModel):
            event_id: str
            job_id: str
            state: str
            at: float

        with self.store.connect() as db:
            seq = 0
            if cursor:
                if not cursor.startswith("jobs:") or not cursor[5:].isdigit():
                    raise LookupError("Invalid job event cursor")
                seq = int(cursor[5:])
                if not db.execute("SELECT 1 FROM job_events WHERE seq=?", (seq,)).fetchone():
                    raise LookupError("Unknown job event cursor")
            return [
                Event(
                    event_id="jobs:" + str(r["seq"]),
                    job_id=r["job_id"],
                    state=r["state"],
                    at=r["at"],
                )
                for r in db.execute(
                    "SELECT * FROM job_events WHERE seq>? ORDER BY seq LIMIT ?", (seq, limit)
                )
            ]

    def pending_count(self):
        with self.store.connect() as db:
            return db.execute("SELECT COUNT(*) FROM job_outbox WHERE published IS NULL").fetchone()[
                0
            ]
