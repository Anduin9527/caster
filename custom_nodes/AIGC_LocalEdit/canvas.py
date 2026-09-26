"""Exact Qwen reference canvas; fit without stretching or clipping limbs."""


def fit_geometry(source_width, source_height, width, height):
    if min(source_width, source_height, width, height) <= 0 or width % 8 or height % 8:
        raise ValueError("Canvas must be positive and divisible by 8")
    scale = min(width / source_width, height / source_height)
    w, h = max(1, round(source_width * scale)), max(1, round(source_height * scale))
    return w, h, (width - w) // 2, (height - h) // 2


def fit_canvas(image, width, height, method):
    import comfy.utils

    h, w = image.shape[1:3]
    if (w, h) == (width, height):
        return image
    rw, rh, x, y = fit_geometry(w, h, width, height)
    resized = comfy.utils.common_upscale(image.movedim(-1, 1), rw, rh, method, "disabled").movedim(
        1, -1
    )
    canvas = image.new_ones((image.shape[0], height, width, image.shape[-1]))
    canvas[:, y : y + rh, x : x + rw, :] = resized
    return canvas


class AIGCQwenCanvasEncoder:
    @classmethod
    def INPUT_TYPES(cls):
        import copy

        import nodes

        schema = copy.deepcopy(nodes.NODE_CLASS_MAPPINGS["VNCCS_QWEN_Encoder"].INPUT_TYPES())
        for group in schema.values():
            group.pop("target_size", None)
        schema["required"].update(
            width=("INT", {"default": 1024, "min": 64, "max": 4096, "step": 8}),
            height=("INT", {"default": 1536, "min": 64, "max": 4096, "step": 8}),
        )
        return schema

    RETURN_TYPES = ("CONDITIONING", "CONDITIONING", "LATENT")
    FUNCTION = "encode"
    CATEGORY = "AIGC/LocalEdit"

    def encode(self, width, height, **kwargs):
        import nodes

        fit_geometry(width, height, width, height)
        base = nodes.NODE_CLASS_MAPPINGS["VNCCS_QWEN_Encoder"]

        class ExactEncoder(base):
            def _process_image(self, image, target_size, upscale_method, crop_method):
                if target_size == 0:
                    return fit_canvas(image, width, height, upscale_method)
                return super()._process_image(image, target_size, upscale_method, crop_method)

        # Only VAE image/reference encoding changes; the VL encoder keeps its own scale.
        return ExactEncoder().encode(target_size=0, **kwargs)
