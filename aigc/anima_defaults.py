"""Shared Anima-only quality defaults extracted from the supplied reference."""
ARTIST = '@rella'
QUALITY = 'masterpiece, very aesthetic, best quality, score_9, score_8, score_7, year 2025, official_art'
POSITIVE = ARTIST + ', ' + QUALITY
NEGATIVE = ('score_1, score_2, score_3, blurry, worst quality, low quality, jpeg artifacts, '
            'signature, watermark, username, error, deformed hands, bad anatomy, extra limbs, '
            'poorly drawn hands, poorly drawn face, mutation, deformed, extra eyes, extra arms, '
            'extra legs, malformed limbs, fused fingers, too many fingers, long neck, cross-eyed, '
            'bad proportions, missing arms, missing legs, extra digit, fewer digits, cropped, '
            'normal quality, monochrome, greyscale, lineart')


def positive_prompt(text):
    """One shared style/quality prefix, including for direct workflow callers."""
    defaults = {tag.casefold() for tag in POSITIVE.split(', ')}
    body = ', '.join(tag.strip() for tag in text.split(',')
                     if tag.strip() and tag.strip().casefold() not in defaults)
    return POSITIVE + (', ' + body if body else '')


def escape_template_tags(text):
    """Escape literal name qualifiers without rewriting explicit attention groups."""
    import re
    parts = text.replace('（', '(').replace('）', ')').split(',')
    for i, part in enumerate(parts):
        stripped = part.strip()
        if stripped.startswith('(') and stripped.endswith(')'):
            continue
        parts[i] = re.sub(r'(?<!\\)([()])', r'\\\1', part)
    return ','.join(parts)
