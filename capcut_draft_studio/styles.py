from __future__ import annotations
import json, hashlib, math, shutil
from pathlib import Path
from .models import LogFn

#: CapCut lưu shadow_point theo hướng góc với hệ số ≈ 0.18 × shadow_distance
#: (distance 5.0 + góc -45° → point (0.6363961, -0.6363961) như draft thật).
SHADOW_POINT_K = 0.18


def _hex_to_rgb(value: str) -> list[float]:
    raw = str(value or "").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) != 6:
        return [0.0, 0.0, 0.0]
    try:
        return [int(raw[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    except ValueError:
        return [0.0, 0.0, 0.0]


def shadow_spec(s) -> dict | None:
    """Mô tả bóng đổ phụ đề lấy từ Settings; None nghĩa là tắt bóng."""
    if not getattr(s, "sub_shadow", False):
        return None
    angle = float(getattr(s, "sub_shadow_angle", -45.0))
    distance = float(getattr(s, "sub_shadow_distance", 5.0))
    alpha = max(0.0, min(1.0, float(getattr(s, "sub_shadow_alpha", 0.9))))
    smoothing = max(0.0, min(1.0, float(getattr(s, "sub_shadow_smoothing", 0.45))))
    color = str(getattr(s, "sub_shadow_color", "#000000") or "#000000")
    k = distance * SHADOW_POINT_K
    rad = math.radians(angle)
    return {
        "alpha": alpha, "angle": angle, "distance": distance,
        "smoothing": smoothing, "color": color,
        "point": {"x": round(k * math.cos(rad), 10), "y": round(k * math.sin(rad), 10)},
    }


def default_subtitle_style(s) -> dict | None:
    """Style áp cho phụ đề khi người dùng KHÔNG chọn style nào từ CapCut.

    Chỉ mang bóng đổ — cố tình không ghi đè font/cỡ chữ/màu do CapCut tự đặt
    lúc import SRT, để bản dựng vẫn giống các phiên bản trước.
    """
    spec = shadow_spec(s)
    return {"name": "default-shadow", "shadow_spec": spec} if spec else None


def merge_shadow(style: dict | None, s) -> dict | None:
    """Ghép bóng đổ theo cài đặt vào style đã harvest (nếu có)."""
    spec = shadow_spec(s)
    if style is None:
        return default_subtitle_style(s)
    out = dict(style)
    if spec:
        out["shadow_spec"] = spec
        out.pop("shadow", None)   # bản mô tả mới thay cho bản harvest cũ
    return out

def list_sub_styles(folder: Path) -> list[Path]:
    return sorted(folder.glob("*.json"),key=lambda p:p.stem.lower()) if folder.is_dir() else []

def _safe_color(v,default=(1.0,1.0,1.0)):
    if isinstance(v,list) and len(v)>=3:
        try:return [float(v[0]),float(v[1]),float(v[2])]
        except Exception:pass
    return list(default)

def parse_text_style(material: dict) -> dict | None:
    try: content=json.loads(material.get("content") or "{}")
    except Exception:return None
    styles=content.get("styles") or []
    if not styles:return None
    st=styles[0]
    fill=st.get("fill") or {}; color=((fill.get("content") or {}).get("solid") or {}).get("color") or fill.get("color")
    result={"style":{"size":st.get("size",8.0),"color":_safe_color(color),"bold":bool(st.get("bold",False)),"italic":bool(st.get("italic",False)),"alpha":fill.get("alpha",1.0),"align":material.get("alignment",2),"letter_spacing":material.get("letter_spacing",0.0),"line_spacing":material.get("line_spacing",0.0)},"transform_y":-0.8}
    for key,jsonkey in [("border","strokes"),("shadow","shadows")]:
        arr=st.get(jsonkey) or []
        if arr: result[key]=arr[0]
    for key in ("glow","background"):
        if st.get(key): result[key]=st[key]
    font={k:material.get(k) for k in ("font_id","font_name","font_path") if material.get(k)}
    if font: result["font"]=font
    return result

def harvest_sub_styles(dest: Path, capcut_drafts: Path, log: LogFn=print) -> int:
    dest.mkdir(parents=True,exist_ok=True); seen=set(); n=0
    if not capcut_drafts.is_dir(): return 0
    for dc in capcut_drafts.glob("*/draft_content.json"):
        try:data=json.loads(dc.read_text(encoding="utf-8"))
        except Exception:continue
        for mat in (data.get("materials") or {}).get("texts",[]):
            st=parse_text_style(mat)
            if not st:continue
            sig=hashlib.sha1(json.dumps(st,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()[:10]
            if sig in seen:continue
            seen.add(sig); name=f"style-{sig}"; (dest/f"{name}.json").write_text(json.dumps({"name":name,**st},ensure_ascii=False,indent=2),encoding="utf-8"); n+=1
    log(f"[HARVEST] Đã nhập {n} style phụ đề")
    return n

def _apply_shadow(material: dict, content: dict, spec: dict) -> None:
    """Ghi bóng đổ theo CẢ HAI schema mà các bản CapCut khác nhau đang đọc.

    Bản cũ đọc các khoá `shadow_*` ở cấp material, bản mới đọc
    `content.styles[0].shadows`. Ghi cả hai thì bóng chắc chắn hiện.
    """
    material.update({
        "has_shadow": True,
        "shadow_alpha": spec["alpha"],
        "shadow_angle": spec["angle"],
        "shadow_color": spec["color"],
        "shadow_distance": spec["distance"],
        "shadow_point": spec["point"],
        "shadow_smoothing": spec["smoothing"],
    })
    styles = content.setdefault("styles", [])
    if not styles:
        styles.append({})
    styles[0]["shadows"] = [{
        "content": {"render_type": "solid",
                    "solid": {"alpha": spec["alpha"], "color": _hex_to_rgb(spec["color"])}},
        "alpha": spec["alpha"],
        "angle": spec["angle"],
        "distance": spec["distance"],
        "smoothing": spec["smoothing"],
    }]


def inject_subtitle_style(draft_path: Path, style: dict, log: LogFn=print) -> int:
    p=draft_path/"draft_content.json"
    if not p.is_file() or not style:return 0
    data=json.loads(p.read_text(encoding="utf-8")); ids=set()
    for tr in data.get("tracks",[]):
        if tr.get("type")=="text" and tr.get("name")=="subtitles":
            ids.update(seg.get("material_id") for seg in tr.get("segments",[]) if seg.get("material_id"))
    if not ids:return 0
    st=style.get("style") or {}
    spec=style.get("shadow_spec")
    changed=0
    for m in (data.get("materials") or {}).get("texts",[]):
        if m.get("id") not in ids:continue
        try:cj=json.loads(m.get("content") or "{}")
        except Exception:cj={}
        styles=cj.setdefault("styles",[])
        if not styles:styles.append({})
        sty=styles[0]
        if st:
            m["alignment"]=st.get("align",m.get("alignment",2))
            m["letter_spacing"]=st.get("letter_spacing",m.get("letter_spacing",0))
            m["line_spacing"]=st.get("line_spacing",m.get("line_spacing",0))
            for k in ("size","bold","italic"):
                if k in st:sty[k]=st[k]
            color=_safe_color(st.get("color")); alpha=float(st.get("alpha",1.0))
            sty["fill"]={"alpha":alpha,"content":{"render_type":"solid","solid":{"color":color}}}
            if style.get("border"): sty["strokes"]=[style["border"]]
            if style.get("glow"): sty["glow"]=style["glow"]
            if style.get("background"): sty["background"]=style["background"]
        if style.get("shadow"): sty["shadows"]=[style["shadow"]]
        if spec: _apply_shadow(m,cj,spec)
        m["content"]=json.dumps(cj,ensure_ascii=False,separators=(",",":")); changed+=1
    p.write_text(json.dumps(data,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    detail="style + bóng đổ" if (st and spec) else ("bóng đổ" if spec else "style")
    log(f"[BUILD] Đã đồng bộ {detail} cho {changed} subtitle")
    return changed
