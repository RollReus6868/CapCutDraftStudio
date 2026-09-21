from __future__ import annotations
import json, re
from pathlib import Path
from .models import Settings, ScenePlan, LogFn

def split_sentences(text: str, max_words: int = 12) -> list[str]:
    text=re.sub(r"\s+"," ",text).strip()
    if not text:return []
    sentences=re.split(r"(?<=[.!?…])\s+",text)
    out=[]
    for sentence in sentences:
        words=sentence.split()
        while len(words)>max_words:
            cut=max_words
            # prefer a comma/semicolon boundary near the end
            for j in range(max_words-1,max(3,max_words//2)-1,-1):
                if re.search(r"[,;:，；：]$",words[j-1]): cut=j; break
            out.append(" ".join(words[:cut]).strip()); words=words[cut:]
        if words: out.append(" ".join(words).strip())
    return [x for x in out if x]

def balance_text_lines(text: str, max_chars: int = 35) -> str:
    words=text.split()
    if len(text)<=max_chars or len(words)<2:return text
    best=None
    for i in range(1,len(words)):
        a=" ".join(words[:i]); b=" ".join(words[i:])
        score=max(len(a),len(b))+abs(len(a)-len(b))*0.25
        if len(a)<=max_chars*1.35 and len(b)<=max_chars*1.35 and (best is None or score<best[0]): best=(score,a,b)
    return f"{best[1]}\n{best[2]}" if best else text

def _manifest_texts(path: Path) -> dict[int,str]:
    data=json.loads(path.read_text(encoding="utf-8"))
    out={}
    def add(n,v):
        try:n=int(n)
        except Exception:return
        if isinstance(v,str) and v.strip(): out[n]=v.strip(); return
        if isinstance(v,dict):
            for k in ("script","text","content","narration","voiceover"):
                if isinstance(v.get(k),str) and v[k].strip(): out[n]=v[k].strip(); return
    if isinstance(data,dict):
        if isinstance(data.get("scenes"),list):
            for item in data["scenes"]:
                if isinstance(item,dict): add(item.get("scene_id",item.get("scene",item.get("id",item.get("number")))),item)
        else:
            for k,v in data.items(): add(k,v)
    elif isinstance(data,list):
        for item in data:
            if isinstance(item,dict): add(item.get("scene_id",item.get("scene",item.get("id",item.get("number")))),item)
    return out

def _find_header(rows):
    script_terms=("script","text","content","narration","thoại","thoai","kịch","kich","lời","loi","nội dung","noi dung")
    for i,row in enumerate(rows[:20]):
        vals=[str(x or "").strip().lower() for x in row]
        if any(any(t in v for t in script_terms) for v in vals): return i
    return 0

def excel_columns(path: Path, sheet_name: str="") -> tuple[list[str],list[str]]:
    import openpyxl
    wb=openpyxl.load_workbook(path,read_only=True,data_only=True)
    sheets=wb.sheetnames
    ws=wb[sheet_name] if sheet_name in wb.sheetnames else wb[wb.sheetnames[0]]
    rows=list(ws.iter_rows(min_row=1,max_row=20,values_only=True))
    idx=_find_header(rows)
    headers=[str(v or "").strip() for v in rows[idx]]
    wb.close(); return sheets,headers

def _excel_texts(path: Path, script_col: str, scene_col: str="", sheet_name: str="") -> dict[int,str]:
    import openpyxl
    wb=openpyxl.load_workbook(path,read_only=True,data_only=True)
    ws=wb[sheet_name] if sheet_name in wb.sheetnames else wb[wb.sheetnames[0]]
    rows=list(ws.iter_rows(values_only=True)); hidx=_find_header(rows)
    headers=[str(v or "").strip() for v in rows[hidx]]
    def col(name, candidates):
        if name:
            for i,h in enumerate(headers):
                if h.strip().lower()==name.strip().lower(): return i
        for i,h in enumerate(headers):
            hl=h.lower()
            if any(c in hl for c in candidates): return i
        return None
    sidx=col(script_col,("script","text","content","narration","thoại","thoai","kịch","kich","lời","loi","nội dung","noi dung"))
    nidx=col(scene_col,("scene","panel","stt","number","cảnh","canh","số","so","#","index"))
    if sidx is None: raise ValueError("Không tìm thấy cột lời thoại trong Excel")
    out={}; auto=1
    for row in rows[hidx+1:]:
        if sidx>=len(row):continue
        txt=str(row[sidx] or "").strip()
        if not txt:continue
        n=auto
        if nidx is not None and nidx<len(row) and row[nidx] not in (None,""):
            try:n=int(float(row[nidx]))
            except Exception:continue
        out[n]=txt; auto+=1
    wb.close(); return out

def load_scene_texts(s: Settings, plan: list[ScenePlan], log: LogFn=print) -> dict[int,str]:
    src=s.subtitle_source.lower(); nums={p.number for p in plan}; out={}
    if src=="off": return {}
    if src in ("manifest","auto"):
        candidates=[s.input_dir/"_manifest.json", s.input_dir.parent/"_manifest.json"]
        mp=next((p for p in candidates if p.is_file()),None)
        if mp:
            out=_manifest_texts(mp); log(f"[SUB] Manifest: {mp.name} ({len(out)} scene)")
            if src=="manifest": return {k:v for k,v in out.items() if k in nums}
    if src in ("excel","auto") and s.subtitle_file and Path(s.subtitle_file).is_file():
        p=Path(s.subtitle_file)
        if p.suffix.lower() in (".xlsx",".xlsm"):
            out=_excel_texts(p,s.excel_script_col,s.excel_scene_col,s.excel_sheet); log(f"[SUB] Excel: {p.name} ({len(out)} scene)")
            if src=="excel" or out:return {k:v for k,v in out.items() if k in nums}
    if src in ("texts","auto"):
        td=s.input_dir/"Texts"
        if td.is_dir():
            for f in td.glob("*.txt"):
                if f.stem.isdigit(): out[int(f.stem)]=f.read_text(encoding="utf-8-sig").strip()
            if out: log(f"[SUB] Texts/: {len(out)} file")
    return {k:v for k,v in out.items() if k in nums}

def srt_ts(sec: float) -> str:
    ms=max(0,int(round(sec*1000))); h,ms=divmod(ms,3600000); m,ms=divmod(ms,60000); ss,ms=divmod(ms,1000)
    return f"{h:02d}:{m:02d}:{ss:02d},{ms:03d}"

def build_srt(s: Settings, plan: list[ScenePlan], out_path: Path, log: LogFn=print) -> int:
    texts=load_scene_texts(s,plan,log); entries=[]
    for p in plan:
        raw=texts.get(p.number,"").strip()
        if not raw:
            log(f"[WARN] {p.number:04d} audio không có lời thoại")
            continue
        chunks=split_sentences(raw,s.sub_max_words) or [raw]
        weights=[max(1,len(c.split())) for c in chunks]; total=sum(weights); t=p.start
        for idx,(c,w) in enumerate(zip(chunks,weights)):
            dur=p.audio_duration*w/total
            # keep readability, but preserve exact scene boundary by adjusting last chunk
            if idx==len(chunks)-1: dur=p.audio_end-t
            entries.append((t,t+dur,balance_text_lines(c))); t+=dur
    out_path.parent.mkdir(parents=True,exist_ok=True)
    with out_path.open("w",encoding="utf-8") as f:
        for i,(st,en,txt) in enumerate(entries,1):
            f.write(f"{i}\n{srt_ts(st)} --> {srt_ts(en)}\n{txt}\n\n")
    log(f"[BUILD] Subtitles: {len(entries)} câu → {out_path}")
    return len(entries)
