import json
import numpy as np
import torch
from PIL import Image,ImageFilter,ImageDraw
import folder_paths
from .composite import masked_paste

def pil(t):return Image.fromarray(np.clip(t.detach().cpu().numpy()[0]*255,0,255).round().astype(np.uint8))
def tensor(im):return torch.from_numpy(np.array(im).astype(np.float32)/255.0).unsqueeze(0)

class AIGCFaceCrop:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'image':('IMAGE',),'bbox_detector':('BBOX_DETECTOR',),'sam_model':('SAM_MODEL',),'region':('STRING',{'default':'[]'}),'mask_file':('STRING',{'default':''}),'feather':('INT',{'default':8,'min':0,'max':32})}}
    RETURN_TYPES=('IMAGE','MASK','STRING','IMAGE')
    RETURN_NAMES=('context_crop','effective_mask','crop_metadata','detection_preview')
    FUNCTION='run';CATEGORY='AIGC/LocalEdit'
    def run(self,image,bbox_detector,sam_model,region,mask_file,feather):
        from impact import core
        if image.shape[0]!=1:raise ValueError('AIGC_FACE_SELECTION: exactly one image required')
        original=pil(image).convert('RGB');w,h=original.size
        selected=json.loads(region)
        detections=bbox_detector.detect(image,0.35,0,2.0,10)
        candidates=[list(map(int,s.bbox)) for s in detections[1]]
        if mask_file:
            import pathlib
            base=pathlib.Path(folder_paths.get_input_directory()).resolve();p=(base/mask_file).resolve()
            if not p.is_relative_to(base):raise ValueError('Invalid mask path')
            mask=Image.open(p).convert('L')
            if mask.size!=(w,h):raise ValueError('Mask canvas mismatch')
            box=mask.getbbox()
            if not box:raise ValueError('AIGC_FACE_SELECTION: uploaded mask is empty')
        else:
            if selected:
                if len(selected)!=4:raise ValueError('AIGC_FACE_SELECTION: region must contain x1,y1,x2,y2')
                box=tuple(map(int,selected))
                if not(0<=box[0]<box[2]<=w and 0<=box[1]<box[3]<=h):raise ValueError('AIGC_FACE_SELECTION: invalid selected region')
                # Impact SAM interface accepts SEGS; explicit selection overrides detector ambiguity.
                from collections import namedtuple
                SEG=namedtuple('SEG','cropped_image cropped_mask confidence crop_region bbox label control_net_wrapper')
                seg=SEG(None,np.ones((box[3]-box[1],box[2]-box[0]),dtype=np.float32),1.0,box,box,'face',None)
                segs=((h,w),[seg])
            else:
                if len(candidates)!=1:raise ValueError('AIGC_FACE_SELECTION: '+json.dumps({'count':len(candidates),'candidates':candidates}))
                box=tuple(candidates[0]);segs=detections
            sam=core.make_sam_mask(sam_model,segs,image,'center-1',0,0.93,0,0.7,'False')
            raw=np.clip(sam.cpu().numpy().reshape(h,w)*255,0,255).astype(np.uint8)
            mask=Image.fromarray(raw,'L')
            # SAM may segment a whole person. Restrict to the face detector/selected ROI.
            roi=Image.new('L',(w,h));ImageDraw.Draw(roi).rectangle((box[0],box[1],box[2]-1,box[3]-1),fill=255)
            from PIL import ImageChops
            mask=ImageChops.multiply(mask,roi)
            if not mask.getbbox():raise ValueError('AIGC_FACE_SELECTION: SAM returned empty face mask')
            if feather:mask=ImageChops.multiply(mask.filter(ImageFilter.GaussianBlur(feather)),roi)
        # Quantized effective mask is exactly the mask saved and used for compositing.
        mask=mask.convert('L');extent=mask.getbbox()
        bw,bh=box[2]-box[0],box[3]-box[1];padding=max(32,int(max(bw,bh)*0.65))
        crop=(max(0,min(box[0],extent[0])-padding),max(0,min(box[1],extent[1])-padding),min(w,max(box[2],extent[2])+padding),min(h,max(box[3],extent[3])+padding))
        metadata=json.dumps({'bbox':box,'crop':crop,'candidates':candidates,'canvas':[w,h],'mask_nonzero_bbox':extent})
        debug=original.copy();draw=ImageDraw.Draw(debug);draw.rectangle(box,outline='red',width=2);draw.rectangle(crop,outline='green',width=2)
        return {'ui':{'text':[metadata]},'result':(tensor(original.crop(crop)),torch.from_numpy(np.array(mask).astype(np.float32)/255).unsqueeze(0),metadata,tensor(debug))}

class AIGCMaskedPaste:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'original':('IMAGE',),'edited':('IMAGE',),'mask':('MASK',),'region':('STRING',{'forceInput':True})}}
    RETURN_TYPES=('IMAGE',);FUNCTION='run';CATEGORY='AIGC/LocalEdit'
    def run(self,original,edited,mask,region):
        m=Image.fromarray(np.clip(mask.cpu().numpy().reshape(original.shape[1:3])*255,0,255).round().astype(np.uint8),'L')
        result=masked_paste(pil(original),pil(edited),m,json.loads(region)['crop'])
        return (tensor(result),)
NODE_CLASS_MAPPINGS={'AIGCFaceCrop':AIGCFaceCrop,'AIGCMaskedPaste':AIGCMaskedPaste}

from .canvas import AIGCQwenCanvasEncoder
NODE_CLASS_MAPPINGS["AIGCQwenCanvasEncoder"] = AIGCQwenCanvasEncoder
