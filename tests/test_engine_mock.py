import sys, types
from pathlib import Path

from capcut_draft_studio.models import Settings, Assets, ScenePlan
import capcut_draft_studio.capcut_engine as eng

class _KP:
    uniform_scale='uniform_scale'; position_x='position_x'
class _TT:
    叠化='fade'
class _TrackType:
    video='video'; audio='audio'
class _Clip:
    def __init__(self, **kw): self.kw=kw
class _Seg:
    def __init__(self, material, target, **kw): self.material=material;self.target=target;self.kw=kw;self.kf=[];self.transitions=[]
    def add_keyframe(self,*a):self.kf.append(a)
    def add_transition(self,*a,**k):self.transitions.append((a,k))
    def add_fade(self,*a):pass
class _Script:
    def __init__(self,path):self.path=path;self.tracks=[];self.segs=[]
    def add_track(self,*a,**k):self.tracks.append((a,k));return self
    def add_segment(self,*a,**k):self.segs.append((a,k));return self
    def import_srt(self,*a,**k):return None
    def save(self):
        self.path.mkdir(parents=True,exist_ok=True)
        (self.path/'draft_content.json').write_text('{"tracks":[],"materials":{"texts":[]}}',encoding='utf-8')
class _Folder:
    def __init__(self,p):self.p=Path(p)
    def create_draft(self,name,w,h,fps,allow_replace=True):return _Script(self.p/name)

def _trange(a,b):return (a,b)
def _tim(a):return a

def fake_cc():
    m=types.ModuleType('pycapcut');m.KeyframeProperty=_KP;m.TransitionType=_TT;m.TrackType=_TrackType;m.ClipSettings=_Clip;m.VideoSegment=_Seg;m.AudioSegment=_Seg;m.DraftFolder=_Folder;m.trange=_trange;m.tim=_tim
    return m

def test_build_one_image(tmp_path, monkeypatch):
    sys.modules['pycapcut']=fake_cc()
    monkeypatch.setattr(eng,'media_duration_sec',lambda p:5.0)
    inp=tmp_path/'input';ch=tmp_path/'channel';drafts=tmp_path/'drafts';inp.mkdir();ch.mkdir();drafts.mkdir()
    aud=inp/'a.mp3';img=inp/'i.jpg';aud.write_bytes(b'x');img.write_bytes(b'x')
    s=Settings(inp,ch,'demo',drafts,enable_subtitles=False,enable_logo=False,enable_claim=False,enable_bgm=False,enable_transition=False,register_root_meta=False)
    a=Assets(audios={1:aud},images={1:img})
    p=[ScenePlan(1,aud,5.0,'IMAGE',img,start=0)]
    out=eng.build(s,a,p,lambda m:None)
    assert out == drafts/'demo'
    assert (out/'draft_content.json').is_file()
