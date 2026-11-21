"""Small indoor depth and semantic models. Offline at runtime; CPU/MPS, no CUDA required."""
from pathlib import Path
import os
import numpy as np
import cv2

ROOT=Path(__file__).resolve().parents[1]
DEPTH_REPO='depth-anything/Depth-Anything-V2-Metric-Indoor-Small-hf'
STRUCTURE_REPO='nvidia/segformer-b0-finetuned-ade-512-512'
LABELS={0:'wall',3:'floor',5:'ceiling',8:'window',14:'door',58:'screen door'}
COLORS={0:(120,165,215),3:(100,180,115),5:(190,155,205),8:(210,190,90),14:(65,170,245),58:(65,170,245)}

def setup_cache():
    os.environ.setdefault('HF_HOME',str(ROOT/'vision/models/huggingface'))

class IndoorDepth:
    def __init__(self,download=False):
        setup_cache()
        import torch
        from transformers import AutoImageProcessor,AutoModelForDepthEstimation
        self.device='mps' if torch.backends.mps.is_available() else 'cpu'
        self.processor=AutoImageProcessor.from_pretrained(DEPTH_REPO,local_files_only=not download)
        self.model=AutoModelForDepthEstimation.from_pretrained(DEPTH_REPO,local_files_only=not download).to(self.device).eval()
        if getattr(self.model.config,'depth_estimation_type',None)!='metric':raise ValueError('Expected the indoor metric checkpoint')
        # Older Transformers silently use the relative-depth head for this config.
        if type(self.model.head.activation2).__name__!='Sigmoid':raise RuntimeError('Metric depth requires transformers>=4.46.3; rerun setup.')
    def predict(self,frame):
        import torch
        # 266 pixels keeps ViT patches valid without claiming full-resolution accuracy.
        inputs=self.processor(images=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB),size={'height':266,'width':266},return_tensors='pt').to(self.device)
        with torch.inference_mode():raw=self.model(**inputs).predicted_depth[:,None]
        raw=torch.nn.functional.interpolate(raw,size=frame.shape[:2],mode='bilinear',align_corners=False)[0,0]
        return raw.detach().cpu().numpy().astype(np.float32)

class RoomStructure:
    def __init__(self,download=False):
        setup_cache()
        import torch
        from transformers import AutoImageProcessor,AutoModelForSemanticSegmentation
        self.device='mps' if torch.backends.mps.is_available() else 'cpu'
        self.processor=AutoImageProcessor.from_pretrained(STRUCTURE_REPO,local_files_only=not download)
        self.model=AutoModelForSemanticSegmentation.from_pretrained(STRUCTURE_REPO,local_files_only=not download).to(self.device).eval()
    def predict(self,frame):
        import torch
        inputs=self.processor(images=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB),size={'height':320,'width':320},return_tensors='pt').to(self.device)
        with torch.inference_mode():logits=self.model(**inputs).logits
        logits=torch.nn.functional.interpolate(logits,size=frame.shape[:2],mode='bilinear',align_corners=False)
        confidence,labels=logits.softmax(1).max(1)
        return labels[0].cpu().numpy().astype(np.uint8),confidence[0].cpu().numpy().astype(np.float32)

def doorway_candidates(frame,labels,confidence,depth):
    """Door/frame proposals, never a clearance or traversability decision.

    Semantic door regions provide leaf proposals; paired near-vertical image edges
    provide frame proposals, gated by wall/door context. Open/closed is a depth
    heuristic, not a trained state classifier, and remains unknown without support.
    """
    h,w=labels.shape;regions=[]
    mask=((np.isin(labels,[14,58]))&(confidence>.45)).astype(np.uint8)
    count,_,stats,_=cv2.connectedComponentsWithStats(mask)
    for x,y,bw,bh,area in stats[1:]:
        if area>max(100,.002*h*w) and bh>h*.2:regions.append((int(x),int(y),int(bw),int(bh),'semantic door'))
    edges=cv2.Canny(frame,70,150)
    lines=cv2.HoughLinesP(edges,1,np.pi/180,threshold=35,minLineLength=int(h*.4),maxLineGap=12)
    vertical=[] if lines is None else [a[0] for a in lines if abs(int(a[0][2])-int(a[0][0]))<max(4,.08*abs(int(a[0][3])-int(a[0][1])))]
    for i,a in enumerate(vertical[:24]):
        for b in vertical[i+1:24]:
            left,right=sorted([int((a[0]+a[2])/2),int((b[0]+b[2])/2)])
            top=max(min(a[1],a[3]),min(b[1],b[3]));bottom=min(max(a[1],a[3]),max(b[1],b[3]))
            bw=right-left;bh=int(bottom-top)
            if not w*.15<bw<w*.65 or not bh>h*.45 or not .2<bw/bh<1.2:continue
            context=labels[max(0,top):bottom,max(0,left-8):min(w,right+8)]
            if context.size and np.isin(context,[0,14,58]).mean()>.25:regions.append((left,int(top),bw,bh,'paired vertical edges; frame candidate'))
    result=[]
    for x,y,bw,bh,basis in regions:
        if any(abs(x-r['box'][0])+abs(y-r['box'][1])<20 for r in result):continue
        x2=min(w,x+bw);y2=min(h,y+bh);cx1=x+bw//4;cx2=x+3*bw//4;cy1=y+bh//4;cy2=y+3*bh//4
        center=depth[cy1:cy2,cx1:cx2];jamb=np.concatenate([depth[y:y2,max(0,x-5):min(w,x+5)].ravel(),depth[y:y2,max(0,x2-5):min(w,x2+5)].ravel()])
        center=center[np.isfinite(center)&(center>.15)&(center<15)];jamb=jamb[np.isfinite(jamb)&(jamb>.15)&(jamb<15)]
        state='unknown';gap=None
        coverage=float(mask[y:y2,x:x2].mean())
        if len(center)>=60 and len(jamb)>=60 and x>5 and x2<w-5 and y>5 and y2<h-5:
            gap=float(np.median(center)-np.median(jamb))
            if gap>max(.5,.25*np.median(jamb)):state='possibly open'
            elif basis=='semantic door' and coverage>.65 and abs(gap)<.15:state='possibly closed'
        result.append({'box':[x,y,x2,y2],'state':state,'basis':basis,'depth_gap_predicted_m':gap,'verified':False,'traversable':False})
    return result[:12]

def structure_preview(frame,labels,confidence,doors):
    display=frame.copy()
    for label,color in COLORS.items():
        valid=(labels==label)&(confidence>.45);display[valid]=(.65*display[valid]+.35*np.array(color)).astype(np.uint8)
    for door in doors:
        x,y,x2,y2=door['box'];cv2.rectangle(display,(x,y),(x2,y2),(0,190,255),1)
        cv2.putText(display,'door/frame: '+door['state'],(x,max(10,y-4)),cv2.FONT_HERSHEY_SIMPLEX,.32,(0,210,255),1)
    return display
