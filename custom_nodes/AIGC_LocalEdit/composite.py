from PIL import Image, ImageChops


def masked_paste(original, edited, mask, region):
    original = original.convert("RGB")
    mask = mask.convert("L")
    if mask.size != original.size:
        raise ValueError("Mask size differs from canvas")
    x1, y1, x2, y2 = map(int, region)
    if not (0 <= x1 < x2 <= original.width and 0 <= y1 < y2 <= original.height):
        raise ValueError("Invalid crop region")
    canvas = original.copy()
    canvas.paste(
        edited.convert("RGB").resize((x2 - x1, y2 - y1), Image.Resampling.LANCZOS), (x1, y1)
    )
    result = Image.composite(canvas, original, mask)
    outside = mask.point(lambda v: 255 if v == 0 else 0)
    if ImageChops.multiply(
        ImageChops.difference(result, original), outside.convert("RGB")
    ).getbbox():
        raise AssertionError("Outside-mask pixels changed")
    return result
