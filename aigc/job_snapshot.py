"""Freeze legacy/workbench inputs at enqueue; Agent authorizations own their snapshot."""

import json

from .workflows import read_bindings, read_template


def freeze(db, job_id):
    def record(kind, key):
        row = db.execute("SELECT body FROM records WHERE kind=? AND id=?", (kind, key)).fetchone()
        return dict(json.loads(row["body"]), id=key) if row else None

    body = json.loads(db.execute("SELECT body FROM jobs WHERE id=?", (job_id,)).fetchone()["body"])
    if body.get("agent_plan_id"):
        return  # The authorization transaction already freezes these inputs.
    spec = record("scene_spec", body.get("scene_spec_id", ""))
    if not spec:
        return  # Historical incomplete records remain inspectable, never executable.
    kind = spec["spec"].get("asset_type")
    from .prompt_settings import get_prompt_settings

    class Reader:
        get = staticmethod(record)

    snapshot = {
        "spec": spec["spec"],
        "character": record("character", spec["spec"].get("character_id", "")),
        "settings": get_prompt_settings(Reader()),
        "graph": read_template(kind),
        "bindings": read_bindings(kind),
        "pose": record("pose", body.get("pose_asset_id", "")),
        "sources": {
            key: record("asset", body[key])
            for key in ("reference_asset_id", "mask_asset_id")
            if body.get(key)
        },
    }
    db.execute("INSERT INTO records VALUES('job_snapshot',?,?)", (job_id, json.dumps(snapshot)))
