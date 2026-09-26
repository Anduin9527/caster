#!/usr/bin/env python3
"""Small CLI: JSON manifests, explicit approvals, persistent pose import."""

import argparse
import json
from pathlib import Path

import httpx
from _config import API_URL

p = argparse.ArgumentParser()
p.add_argument("--url", default=API_URL)
sub = p.add_subparsers(dest="cmd", required=True)
a = sub.add_parser("request")
a.add_argument("method")
a.add_argument("route")
a.add_argument("--json", type=Path)
a = sub.add_parser("batch")
a.add_argument("manifest", type=Path)
a.add_argument("--receipts", type=Path)
a = sub.add_parser("upload")
a.add_argument("image", type=Path)
a.add_argument("--role", default="reference", choices=["reference", "mask", "pose_render"])
a = sub.add_parser("import-pose")
a.add_argument("--state", required=True, type=Path)
a.add_argument("--render", required=True, type=Path)
a.add_argument("--lighting", default="")
a = sub.add_parser("download")
a.add_argument("asset_id")
a.add_argument("path", type=Path)
args = p.parse_args()
c = httpx.Client(base_url=args.url, timeout=120)


def checked(r):
    r.raise_for_status()
    return r.json()


def upload(path, role):
    with path.open("rb") as f:
        return checked(
            c.post("/assets", files={"file": (path.name, f, "image/png")}, data={"role": role})
        )


if args.cmd == "request":
    result = checked(
        c.request(
            args.method, args.route, json=json.loads(args.json.read_text()) if args.json else None
        )
    )
elif args.cmd == "upload":
    result = upload(args.image, args.role)
elif args.cmd == "import-pose":
    state = json.loads(args.state.read_text())
    if "nodes" in state:
        nodes = [n for n in state["nodes"] if n["type"] == "VNCCS_PoseStudio"]
        if len(nodes) != 1:
            raise SystemExit("Workflow must contain exactly one Pose Studio node")
        state = json.loads(nodes[0]["widgets_values"][0])
    # Keep geometry/camera state, remove transient browser captures only.
    state.pop("captured_images", None)
    state.pop("capture_id", None)
    render = upload(args.render, "pose_render")
    result = checked(
        c.post(
            "/poses",
            json={
                "state": state,
                "render_asset_id": render["id"],
                "lighting_prompt": args.lighting,
            },
        )
    )
elif args.cmd == "batch":
    import hashlib

    receipts_path = args.receipts or args.manifest.with_suffix(".receipts.json")
    receipts = json.loads(receipts_path.read_text()) if receipts_path.exists() else {}
    result = []

    def checkpoint():
        temp = receipts_path.with_suffix(".tmp")
        temp.write_text(json.dumps(receipts, indent=2))
        temp.replace(receipts_path)

    for item in json.loads(args.manifest.read_text()):
        key = item["job"]["idempotency_key"]
        digest = hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()
        if key in receipts and receipts[key]["hash"] != digest:
            raise SystemExit("Batch item changed under existing idempotency key: " + key)
        if key not in receipts:
            spec = checked(c.post("/scene-specs", json={"manual": item["scene_spec"]}))
            receipts[key] = {"hash": digest, "scene_spec_id": spec["id"]}
            checkpoint()
        job = checked(
            c.post("/jobs", json={**item["job"], "scene_spec_id": receipts[key]["scene_spec_id"]})
        )
        receipts[key]["job_id"] = job["id"]
        checkpoint()
        result.append(job)
else:
    r = c.get("/assets/" + args.asset_id + "/file")
    r.raise_for_status()
    args.path.write_bytes(r.content)
    result = {"path": str(args.path)}
print(json.dumps(result, ensure_ascii=False, indent=2))
