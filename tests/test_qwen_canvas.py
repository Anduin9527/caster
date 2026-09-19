import importlib.util
from pathlib import Path
import pytest

path=Path(__file__).resolve().parents[1]/'custom_nodes/AIGC_LocalEdit/canvas.py'
spec=importlib.util.spec_from_file_location('canvas',path)
canvas=importlib.util.module_from_spec(spec);spec.loader.exec_module(canvas)

@pytest.mark.parametrize('source,expected', [((1024,1536),(1024,1536,0,0)),((1024,1024),(1024,1024,0,256)),((1536,1024),(1024,683,0,426)),((832,1216),(1024,1497,0,19))])
def test_canvas_fits_without_stretch_or_crop(source,expected):
    assert canvas.fit_geometry(*source,1024,1536)==expected


def test_adapter_keeps_vl_encoding_separate(monkeypatch):
    import sys, types
    calls=[]
    class Upstream:
        @classmethod
        def INPUT_TYPES(cls):return {'required':{'target_size':([1024],{}),'clip':('CLIP',)}}
        def _process_image(self,image,target_size,method,crop):
            calls.append(('vl',target_size));return image
        def encode(self,target_size,**kwargs):
            return (self._process_image('reference',target_size,'lanczos','disabled'),
                    self._process_image('reference',384,'lanczos','disabled'),kwargs)
    monkeypatch.setitem(sys.modules,'nodes',types.SimpleNamespace(NODE_CLASS_MAPPINGS={'VNCCS_QWEN_Encoder':Upstream}))
    monkeypatch.setattr(canvas,'fit_canvas',lambda image,w,h,method: calls.append(('vae',w,h)) or 'full-resolution')
    schema=canvas.AIGCQwenCanvasEncoder.INPUT_TYPES()
    assert 'target_size' not in schema['required']
    result=canvas.AIGCQwenCanvasEncoder().encode(1024,1536,prompt='happy')
    assert result[0]=='full-resolution' and result[2]['prompt']=='happy'
    assert calls==[('vae',1024,1536),('vl',384)]
