"""HTTP-only ComfyUI stand-in for isolated process fault tests. No GPU imports."""

from io import BytesIO

from fastapi import FastAPI
from fastapi.responses import Response
from PIL import Image

from aigc.workflows import read_template

app = FastAPI()
prompts = {}
fault = ""
maximum = 0


@app.get("/object_info")
def info():
    return {n["class_type"]: {"input": {}} for n in read_template("background").values()}


@app.post("/prompt")
def submit(body: dict):
    global maximum
    pid = "mock-" + str(len(prompts) + 1)
    prompts[pid] = {"job_id": body["extra_data"]["aigc_job_id"], "complete": False}
    maximum = max(maximum, sum(not p["complete"] for p in prompts.values()))
    if fault == "uncertain":
        return Response("{invalid", media_type="application/json")
    return {"prompt_id": pid}


@app.get("/queue")
def queue():
    return {
        "queue_running": []
        if fault == "uncertain"
        else [
            [0, pid, {}, {"aigc_job_id": p["job_id"]}]
            for pid, p in prompts.items()
            if not p["complete"]
        ],
        "queue_pending": [],
    }


def result(pid, p):
    return {
        "prompt": [0, pid, {}, {"aigc_job_id": p["job_id"]}],
        "status": {"completed": True},
        "outputs": {"9": {"images": [{"filename": "mock.png", "type": "output"}]}},
    }


@app.get("/history")
@app.get("/history/{pid}")
def history(pid: str | None = None):
    return {
        key: result(key, p)
        for key, p in prompts.items()
        if p["complete"] and (pid is None or pid == key)
    }


@app.get("/view")
def view():
    image = BytesIO()
    Image.new("RGB", (16, 16), "blue").save(image, format="PNG")
    return Response(image.getvalue(), media_type="image/png")


@app.post("/mock/control")
def control(body: dict):
    global fault
    fault = body.get("fault", fault)
    for pid in body.get("complete", []):
        prompts[pid]["complete"] = True
    return {"ok": True}


@app.get("/mock/status")
def status():
    return {"prompts": prompts, "maximum_running": maximum}
