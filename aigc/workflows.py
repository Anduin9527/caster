import copy
import hashlib
import json
from pathlib import Path

from .anima_defaults import NEGATIVE, positive_prompt

ROOT = Path(__file__).resolve().parents[1]


def read_bindings(kind):
    path = ROOT / "workflows" / "bindings.json"
    if not path.exists():
        raise ValueError("Workflow bindings not installed")
    bindings = json.loads(path.read_text())
    if kind not in bindings:
        raise ValueError("Workflow not installed: " + kind)
    return bindings[kind]


def read_template(kind):
    path = ROOT / "workflows" / (kind + ".api.json")
    if not path.exists():
        raise ValueError("Workflow not installed: " + kind)
    return json.loads(path.read_text())


def digest(template):
    return hashlib.sha256(json.dumps(template, sort_keys=True).encode()).hexdigest()


def build(kind, prompt, seed, job_id, inputs=None, template=None, bindings=None):
    """Build a ComfyUI graph.

    ``template`` and ``bindings`` supply the graph and its field mapping
    explicitly. Agent-originated work always passes the snapshots captured at
    approval time, so editing ``workflows/*.api.json`` or ``bindings.json`` after
    the user approved cannot change what is executed: the graph alone is not
    enough, because the bindings decide which node receives the prompt.
    """
    if template is None:
        template = read_template(kind)
    if bindings is None:
        bindings = read_bindings(kind)
    graph = copy.deepcopy(template)
    values = {
        "positive": prompt["positive"],
        "negative": prompt["negative"],
        "seed": seed,
        "prefix": "aigc/jobs/" + job_id,
        **({"width": 1024, "height": 1536} if kind in ("sprite", "outfit", "pose") else {}),
        **(inputs or {}),
    }
    for key, targets in bindings["fields"].items():
        if key not in values:
            raise ValueError("Missing workflow input: " + key)
        for node, field in targets:
            graph[node]["inputs"][field] = values[key]
    # Pre-v2 prompts were finalized here, after approval. Preserve that behavior
    # for historical jobs and direct raw callers. New prompt recipes carry an
    # explicit marker and must reach CLIP byte-for-byte as shown on the card.
    exact_prompt = prompt.get("workflow_prompt_mode") == "exact"
    if not exact_prompt and any(
        "anima" in str(n.get("inputs", {}).get("unet_name", "")).lower() for n in graph.values()
    ):
        for node, field in bindings["fields"].get("positive", []):
            graph[node]["inputs"][field] = positive_prompt(graph[node]["inputs"][field])
        for node, field in bindings["fields"].get("negative", []):
            text = graph[node]["inputs"][field]
            if not text.startswith(NEGATIVE):
                graph[node]["inputs"][field] = NEGATIVE + ", " + text
    return (
        graph,
        bindings["outputs"],
        {
            "workflow": kind,
            "template_sha256": digest(template),
            "bindings_sha256": digest(bindings),
            "graph": graph,
        },
    )


async def validate_models(comfy, graph):
    info = await comfy.info()
    for node in graph.values():
        cls = node["class_type"]
        if cls not in info:
            raise ValueError("Missing ComfyUI node: " + cls)
        schema = info[cls]["input"]
        fields = {**schema.get("required", {}), **schema.get("optional", {})}
        for name, value in node["inputs"].items():
            if name in ("unet_name", "clip_name", "vae_name", "lora_name", "model_name"):
                spec = fields.get(name)
                if spec and isinstance(spec[0], list) and value not in spec[0]:
                    raise ValueError("Missing model: " + str(value))
