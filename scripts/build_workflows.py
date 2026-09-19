import json,copy
from pathlib import Path
root=Path(__file__).resolve().parents[1];wf=root/'workflows'
def node(cls,**inputs):return {'class_type':cls,'inputs':inputs}
def qwen():
 return {'1':node('UNETLoader',unet_name='qwen_image_edit_2511_bf16.safetensors',weight_dtype='default'),'2':node('CLIPLoader',clip_name='qwen_2.5_vl_7b_fp8_scaled.safetensors',type='qwen_image',device='default'),'3':node('VAELoader',vae_name='qwen_image_vae.safetensors'),'4':node('LoraLoaderModelOnly',model=['1',0],lora_name='Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors',strength_model=1.0),'5':node('ModelSamplingAuraFlow',model=['4',0],shift=3.0),'6':node('CFGNorm',model=['5',0],strength=1.0),'7':node('LoadImage',image='reference.png'),'8':node('VNCCS_QWEN_Encoder',clip=['2',0],vae=['3',0],prompt='Change the lighting to sunset. Preserve the scene layout.',image1=['7',0],latent_image_index=1,target_size=1024,upscale_method='lanczos',crop_method='disabled',vl_size=384,qwen_2511=True,weight1=1.0,weight2=1.0,weight3=1.0),'9':node('KSampler',model=['6',0],positive=['8',0],negative=['8',1],latent_image=['8',2],seed=9527,steps=4,cfg=1.0,sampler_name='euler',scheduler='simple',denoise=1.0),'10':node('VAEDecode',samples=['9',0],vae=['3',0]),'11':node('SaveImage',images=['10',0],filename_prefix='aigc/qwen-baseline')}
bindings=json.loads((wf/'bindings.json').read_text())
g=qwen();(wf/'qwen-edit.api.json').write_text(json.dumps(g,indent=2))
pose=copy.deepcopy(g)
pose['12']=node('LoadImage',image='pose.png')
pose['13']=node('LoraLoaderModelOnly',model=['6',0],lora_name='VNCCS_QIE2511_PoseStudio_ART_V5.9.5.safetensors',strength_model=1.0)
pose['9']['inputs']['model']=['13',0]
pose['8']['inputs'].update(image1=['12',0],image2=['7',0],prompt='Draw character from image2 in the pose shown in image1. Preserve the character identity and clothing from image2.')
(wf/'pose.api.json').write_text(json.dumps(pose,indent=2))
bindings['pose']={'fields':{'reference':[['7','image']],'pose':[['12','image']],'positive':[['8','prompt']],'seed':[['9','seed']],'prefix':[['11','filename_prefix']]},'outputs':{'11':'original'}}
expr=copy.deepcopy(g)
expr['12']=node('UltralyticsDetectorProvider',model_name='bbox/face_yolov8m.pt')
expr['13']=node('SAMLoader',model_name='sam_vit_b_01ec64.pth',device_mode='CPU')
expr['14']=node('AIGCFaceCrop',image=['7',0],bbox_detector=['12',0],sam_model=['13',0],region='[]',mask_file='',feather=8)
expr['8']['inputs'].update(image1=['14',0],target_size=768)
expr['15']=node('AIGCMaskedPaste',original=['7',0],edited=['10',0],mask=['14',1],region=['14',2])
expr['11']['inputs']['images']=['15',0]
expr['16']=node('MaskToImage',mask=['14',1])
expr['17']=node('SaveImage',images=['16',0],filename_prefix='aigc/expression-mask')
expr['18']=node('SaveImage',images=['14',0],filename_prefix='aigc/expression-crop')
expr['19']=node('SaveImage',images=['10',0],filename_prefix='aigc/expression-edited-crop')
expr['20']=node('SaveImage',images=['14',3],filename_prefix='aigc/expression-detection')
(wf/'expression.api.json').write_text(json.dumps(expr,indent=2))
bindings['expression']={'fields':{'reference':[['7','image']],'region':[['14','region']],'mask':[['14','mask_file']],'positive':[['8','prompt']],'seed':[['9','seed']],'prefix':[[n,'filename_prefix'] for n in ['11','17','18','19','20']]},'outputs':{'11':'original','17':'mask','18':'crop','19':'edited_crop','20':'detection'}}
matte={'1':node('LoadImage',image='reference.png'),'2':node('BiRefNetRMBG',image=['1',0],model='BiRefNet-general',sensitivity=1.0,mask_blur=0,mask_offset=0,invert_output=False,refine_foreground=False,background='Alpha',background_color='#222222'),'3':node('SaveImage',images=['2',0],filename_prefix='aigc/transparent'),'4':node('SaveImage',images=['2',2],filename_prefix='aigc/alpha-mask')}
(wf/'matte.api.json').write_text(json.dumps(matte,indent=2))
bindings['matte']={'fields':{'reference':[['1','image']],'prefix':[['3','filename_prefix'],['4','filename_prefix']]},'outputs':{'3':'transparent','4':'mask'}}
(wf/'bindings.json').write_text(json.dumps(bindings,indent=2))
