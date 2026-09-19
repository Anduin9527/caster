import hashlib,io,uuid,time
from PIL import Image,ImageOps

def save_image(store,blob,metadata,asset_id=None):
    if len(blob)>64*1024*1024:raise ValueError('Image exceeds 64 MiB')
    with Image.open(io.BytesIO(blob)) as im:
        im.load()
        if im.width*im.height>32_000_000:raise ValueError('Image too large')
        im=ImageOps.exif_transpose(im)
        im=im.convert('RGBA' if 'A' in im.getbands() else 'RGB')
        asset_id=asset_id or uuid.uuid4().hex
        existing=store.get('asset',asset_id)
        if existing:return existing
        path=store.root/'files'/(asset_id+'.png')
        im.save(path)
        return store.put('asset',dict(metadata,path=path.name,width=im.width,height=im.height,mode=im.mode,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),created=time.time()),asset_id)

def asset_path(store,asset):return store.root/'files'/asset['path']
