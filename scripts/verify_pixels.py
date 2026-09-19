import argparse,json
from PIL import Image,ImageChops
p=argparse.ArgumentParser();p.add_argument('original');p.add_argument('edited');p.add_argument('mask');a=p.parse_args()
x=Image.open(a.original).convert('RGB');y=Image.open(a.edited).convert('RGB');m=Image.open(a.mask).convert('L')
if x.size!=y.size or x.size!=m.size:raise SystemExit('Canvas size mismatch')
outside=m.point(lambda v:255 if v==0 else 0)
diff=ImageChops.multiply(ImageChops.difference(x,y),outside.convert('RGB'))
passed=not diff.getbbox();print(json.dumps({'canvas_unchanged':True,'outside_mask_unchanged':passed,'outside_difference_bbox':diff.getbbox()}))
if not passed:raise SystemExit(1)
