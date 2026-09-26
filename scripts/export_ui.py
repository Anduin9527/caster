"""Produce ComfyUI frontend graphs from explicit API graph + runtime node schemas."""

import json
import urllib.request
from pathlib import Path

from _config import COMFY_URL

root = Path(__file__).resolve().parents[1]
info = json.load(urllib.request.urlopen(COMFY_URL + "/object_info"))


def convert(graph):
    nodes = []
    links = []
    node_map = {}
    link_id = 0
    anima = any(
        "anima" in str(n.get("inputs", {}).get("unet_name", "")).lower() for n in graph.values()
    )
    for order, (id, item) in enumerate(graph.items()):
        typ = item["class_type"]
        schema = info[typ]
        inputs = []
        widgets = []
        required = schema["input"].get("required", {})
        optional = schema["input"].get("optional", {})
        for name, definition in {**required, **optional}.items():
            t = definition[0]
            opts = definition[1] if len(definition) > 1 else {}
            value = item["inputs"].get(name)
            linked = (
                isinstance(value, list)
                and len(value) == 2
                and isinstance(value[0], str)
                and value[0] in graph
            )
            primitive = isinstance(t, list) or t in [
                "INT",
                "FLOAT",
                "STRING",
                "BOOLEAN",
                "COMBO",
                "COLORCODE",
            ]
            if not primitive or opts.get("forceInput") or linked:
                if name in optional and value is None:
                    continue
                inputs.append(
                    {"name": name, "type": t if isinstance(t, str) else "COMBO", "link": None}
                )
            if primitive and not opts.get("forceInput"):
                if value is None:
                    value = opts.get(
                        "default",
                        t[0]
                        if isinstance(t, list) and t
                        else (False if t == "BOOLEAN" else 0 if t in ["INT", "FLOAT"] else ""),
                    )
                widgets.append(value if not linked else opts.get("default", 0))
                if name in ("seed", "noise_seed"):
                    widgets.append("randomize" if anima else "fixed")
        if typ == "LoadImage":
            widgets.append("image")
        n = {
            "id": int(id),
            "type": typ,
            "pos": [(order % 4) * 390, (order // 4) * 340],
            "size": [340, 240],
            "flags": {},
            "order": order,
            "mode": 0,
            "inputs": inputs,
            "outputs": [
                {"name": name, "type": t, "links": []}
                for name, t in zip(
                    schema.get("output_name", schema.get("output", [])), schema.get("output", [])
                )
            ],
            "properties": {"Node name for S&R": typ},
            "widgets_values": widgets,
        }
        nodes.append(n)
        node_map[id] = n
    for id, item in graph.items():
        for name, value in item["inputs"].items():
            if isinstance(value, list) and len(value) == 2 and str(value[0]) in node_map:
                source, slot = value
                target = node_map[id]
                idx = next(i for i, x in enumerate(target["inputs"]) if x["name"] == name)
                link_id += 1
                target["inputs"][idx]["link"] = link_id
                node_map[source]["outputs"][slot]["links"].append(link_id)
                links.append(
                    [
                        link_id,
                        int(source),
                        slot,
                        int(id),
                        idx,
                        node_map[source]["outputs"][slot]["type"],
                    ]
                )
    return {
        "last_node_id": max(int(x) for x in graph),
        "last_link_id": link_id,
        "nodes": nodes,
        "links": links,
        "groups": [],
        "config": {},
        "extra": {"ds": {"scale": 0.65, "offset": [20, 20]}},
        "version": 0.4,
    }


def main(selected=None):
    for p in selected or list((root / "workflows").glob("*.api.json")):
        graph = json.loads(p.read_text())
        (p.parent / (p.name.replace(".api.json", ".workflow.json"))).write_text(
            json.dumps(convert(graph), indent=2)
        )
    if selected:
        return
    pose = json.loads((root / "workflows/pose.api.json").read_text())
    state = json.loads((root / "workflows/pose-default.json").read_text())
    pose["12"] = {
        "class_type": "VNCCS_PoseStudio",
        "inputs": {"pose_data": json.dumps(state), "animation_image_batch": False},
    }
    pose["14"] = {
        "class_type": "SaveImage",
        "inputs": {"images": ["12", 0], "filename_prefix": "aigc/pose-render"},
    }
    (root / "workflows/pose-studio.workflow.json").write_text(json.dumps(convert(pose), indent=2))

    render = {
        "1": {
            "class_type": "VNCCS_PoseStudio",
            "inputs": {"pose_data": json.dumps(state), "animation_image_batch": False},
        },
        "2": {
            "class_type": "SaveImage",
            "inputs": {"images": ["1", 0], "filename_prefix": "aigc/pose-render"},
        },
    }
    ui = convert(render)
    ui["nodes"][0]["size"] = [1100, 1100]
    ui["nodes"][0]["pos"] = [0, 0]
    ui["nodes"][1]["pos"] = [1150, 0]
    ui["extra"]["ds"] = {"scale": 0.6, "offset": [20, 20]}
    (root / "workflows/pose-render.workflow.json").write_text(json.dumps(ui, indent=2))


if __name__ == "__main__":
    import sys

    main([Path(p) for p in sys.argv[1:]] or None)
