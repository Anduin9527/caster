from .schema import SceneSpec
from .anima_defaults import POSITIVE, NEGATIVE, positive_prompt, escape_template_tags

def compile_prompt(spec:SceneSpec,character=None):
    fixed=[];prose=[]
    if character:
        fixed.extend(character['fixed_tags']);prose.append(character.get('description',''))
        if spec.outfit_id:
            outfits={o['id']:o for o in character['outfits']}
            if spec.outfit_id not in outfits:raise ValueError('Unknown outfit')
            fixed.extend(outfits[spec.outfit_id]['tags']);prose.append(outfits[spec.outfit_id].get('description',''))
    prefix=['no people','empty scene'] if spec.asset_type=='background' else ['solo','full body']
    seen=set();tags=[]
    for tag in prefix+fixed+spec.visual_tags:
        tag=escape_template_tags(tag.strip());key=tag.casefold()
        if tag and key not in seen:tags.append(tag);seen.add(key)
    prose.extend([spec.action,spec.expression,spec.scene,spec.composition,spec.description])
    positive=', '.join(tags)+'. '+' '.join(s.strip() for s in prose if s.strip())
    negative='low quality, blurry, text, watermark'+(', people, person, human figure' if spec.asset_type=='background' else ', malformed hands, cropped feet')
    if spec.asset_type in ('sprite','background','outfit'):
        positive=positive_prompt(positive)
        negative=NEGATIVE+(', people, person, human figure' if spec.asset_type=='background' else ', cropped feet')
    return {'positive':positive,'negative':negative,'compiler_version':'1.2-anima-rella' if spec.asset_type in ('sprite','background','outfit') else '1.0'}
