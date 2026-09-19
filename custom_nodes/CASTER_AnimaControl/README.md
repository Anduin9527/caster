# Experimental Anima pose adapter

Vendored from [Claquasse/Anima-Control-Pose](https://huggingface.co/Claquasse/Anima-Control-Pose), revision `8f559771d5a49a02fa03f7df2a05ccb7eecb3a2a`, `comfyui/anima_control_lora/`. Upstream license is included. This is an experimental node, not connected to CASTER production bindings.

Local compatibility changes:

- Accept 4D image latents by adding the single temporal axis.
- Move the control embedder and latent to the patch output's actual device/dtype during execution. The upstream captured parameter changes device under ComfyUI low-VRAM loading while the embedder remains on CPU.
- Optional `normalize_control` applies the model's latent input normalization. Default false preserves upstream behavior; this is an explicit experimental variable, not an asserted upstream requirement.

Use the same adapter file in `LoraLoaderModelOnly` and `AnimaControlApply`. The two `control_embedder.proj.*` keys ignored by the LoRA loader are loaded by this node. Do not treat adapter strength zero alone as a no-control baseline: the separately loaded LoRA still affects the model. Our baseline omits both nodes.

The upstream UI's `R0_thin` renderer differs from `scripts/render_skeletons.py`; the training script uses `rtmlib.draw_skeleton(..., openpose_skeleton=False)`. Preserve control-map aspect ratio and inspect keypoints before evaluating output.

Model versions and hashes are defined in `integrations/anima-pose-control.json`. Weights and runtime outputs are stored in the ignored project `data/` directory.
