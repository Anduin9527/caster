import copy,json,hashlib
from pathlib import Path
from .anima_defaults import positive_prompt, NEGATIVE
ROOT=Path(__file__).resolve().parents[1]

def build(kind,prompt,seed,job_id,inputs=None):
    path=ROOT/'workflows'/(kind+'.api.json')
    if not path.exists():raise ValueError('Workflow not installed: '+kind)
    template=json.loads(path.read_text());graph=copy.deepcopy(template)
    mapping=json.loads((ROOT/'workflows'/'bindings.json').read_text())[kind]
    values={'positive':prompt['positive'],'negative':prompt['negative'],'seed':seed,'prefix':'aigc/jobs/'+job_id,**({'width':1024,'height':1536} if kind in ('sprite','outfit','pose') else {}),**(inputs or {})}
    for key,bindings in mapping['fields'].items():
        if key not in values:raise ValueError('Missing workflow input: '+key)
        for node,field in bindings:graph[node]['inputs'][field]=values[key]
    if any('anima' in str(n.get('inputs', {}).get('unet_name', '')).lower() for n in graph.values()):
        for node,field in mapping['fields'].get('positive', []):
            graph[node]['inputs'][field]=positive_prompt(graph[node]['inputs'][field])
        for node,field in mapping['fields'].get('negative', []):
            text=graph[node]['inputs'][field]
            if not text.startswith(NEGATIVE):graph[node]['inputs'][field]=NEGATIVE+', '+text
    digest=hashlib.sha256(json.dumps(template,sort_keys=True).encode()).hexdigest()
    return graph,mapping['outputs'],{'workflow':kind,'template_sha256':digest,'graph':graph}

async def validate_models(comfy,graph):
    info=await comfy.info()
    for node in graph.values():
        cls=node['class_type']
        if cls not in info:raise ValueError('Missing ComfyUI node: '+cls)
        schema=info[cls]['input'];fields={**schema.get('required',{}),**schema.get('optional',{})}
        for name,value in node['inputs'].items():
            if name in ('unet_name','clip_name','vae_name','lora_name','model_name'):
                spec=fields.get(name)
                if spec and isinstance(spec[0],list) and value not in spec[0]:raise ValueError('Missing model: '+str(value))
