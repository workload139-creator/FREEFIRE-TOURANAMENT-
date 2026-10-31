"""Four local FF evidence reviewers. No paid AI provider/API is called.
Uses on-host Tesseract OCR when installed and FFmpeg for video sampling.
OCR/heuristics are advisory only; unreadable or uncertain evidence goes to Admin.
"""
import hashlib, os, re, shutil, subprocess, tempfile
from pathlib import Path
from datetime import datetime, timezone
from PIL import Image, ImageChops, ImageStat
import io

class AIReviewError(RuntimeError): pass

def fingerprint_evidence(submission):
    result={}
    for name in ("history_video","history_image_one","history_image_two"):
        f=getattr(submission,name,None)
        if not f or not f.name: raise AIReviewError(f"Required evidence missing: {name}")
        h=hashlib.sha256(); f.open("rb")
        try:
            for chunk in f.chunks(): h.update(chunk)
        finally: f.close()
        result[name]=h.hexdigest()
    return result

def verify_evidence_integrity(submission):
    old=getattr(submission,"evidence_sha256",None) or {}
    if set(old)!={"history_video","history_image_one","history_image_two"}:
        raise AIReviewError("EVIDENCE_FINGERPRINT_MISSING: Admin Review required.")
    now=fingerprint_evidence(submission)
    if old!=now: raise AIReviewError("EVIDENCE_TAMPER_CHECK_FAILED: uploaded evidence changed after submission.")
    return now

def _bytes(f):
    f.open("rb")
    try: return f.read()
    finally: f.close()

def _ocr(data,suffix=".png",psm="6"):
    binary=shutil.which(os.getenv("TESSERACT_PATH","tesseract"))
    if not binary: return "","Tesseract OCR is not installed on this host."
    with tempfile.NamedTemporaryFile(suffix=suffix,delete=False) as tmp:
        tmp.write(data); path=tmp.name
    try:
        r=subprocess.run([binary,path,"stdout","--psm",psm],capture_output=True,text=True,timeout=25)
        return (r.stdout or "").strip(),("" if r.returncode in (0,1) else "OCR could not read image.")
    except Exception: return "","OCR unavailable or timed out."
    finally:
        try: os.unlink(path)
        except OSError: pass

def _frames(f):
    ff=os.getenv("FFMPEG_PATH","").strip()
    if not ff:
        try:
            import imageio_ffmpeg
            ff=imageio_ffmpeg.get_ffmpeg_exe()
        except Exception: ff=shutil.which("ffmpeg") or ""
    if not ff: return [],"FFmpeg is unavailable."
    with tempfile.NamedTemporaryFile(suffix=Path(f.name).suffix or ".mp4",delete=False) as tmp:
        f.open("rb")
        try: shutil.copyfileobj(f,tmp)
        finally: f.close()
        video=tmp.name
    try:
        p=subprocess.run([ff,"-hide_banner","-i",video,"-f","null","-"],capture_output=True,text=True,timeout=25)
        m=re.search(r"Duration:\\s*(\\d{2}):(\\d{2}):(\\d{2}(?:\\.\\d+)?)",(p.stderr or "")+(p.stdout or ""))
        if not m: return [],"Video duration could not be verified."
        h,mi,se=m.groups(); duration=int(h)*3600+int(mi)*60+float(se)
        if not 15<=duration<=30: return [],f"Video length {duration:.1f}s is outside 15–30 seconds."
        out=[]
        with tempfile.TemporaryDirectory() as d:
            for sec in (1,5,10,15,18,22,27):
                if sec>=duration: continue
                path=str(Path(d)/f"{sec}.png")
                r=subprocess.run([ff,"-hide_banner","-loglevel","error","-y","-ss",str(sec),"-i",video,"-frames:v","1",path],capture_output=True,timeout=15)
                if r.returncode==0 and os.path.exists(path): out.append((sec,Path(path).read_bytes()))
        return out,("" if out else "No video frames extracted.")
    except Exception: return [],"Video sampling failed."
    finally:
        try: os.unlink(video)
        except OSError: pass

def _uid(t): return set(re.findall(r"(?<!\\d)\\d{7,12}(?!\\d)",t or ""))
def _kills(t):
    p=[r"(?:kills?|eliminations?)\\s*[:#-]?\\s*(\\d{1,2})",r"(\\d{1,2})\\s*(?:kills?|eliminations?)"]
    return {int(x) for q in p for x in re.findall(q,t or "",re.I) if int(x)<=99}
def _dates(t):
    p=[r"\\b\\d{1,2}[/-]\\d{1,2}[/-]\\d{2,4}\\b",r"\\b\\d{1,2}\\s+[A-Za-z]{3,9}\\s+\\d{2,4}\\b"]
    return {x for q in p for x in re.findall(q,t or "")}
def _mode(t):
    x=(t or "").lower()
    if any(k in x for k in ("battle royale","ranked br","br mode")): return "BR"
    if any(k in x for k in ("clash squad","cs ranked","cs mode")): return "VS"
    return ""
def _report(name,reason,**kw):
    d={"name":name,"status":"NEEDS_ADMIN_REVIEW","checked_at":datetime.now(timezone.utc).isoformat(),
       "proposed_kills":None,"confidence":"low","uid_matches":None,"observed_uid":"",
       "history_consistent":False,"evidence_complete":False,"tampering_suspected":None,
       "tampering_notes":"Automated checks cannot prove pre-upload authenticity.","reason":reason}
    d.update(kw); return d

def analyze_kill_evidence(submission):
    verify_evidence_integrity(submission)
    a,b=_bytes(submission.history_image_one),_bytes(submission.history_image_two)
    frames,video_error=_frames(submission.history_video)
    ta,ea=_ocr(a,Path(submission.history_image_one.name).suffix or ".png")
    tb,eb=_ocr(b,Path(submission.history_image_two.name).suffix or ".png")
    frame_text=[]
    for sec,data in frames:
        tx,_=_ocr(data)
        if tx: frame_text.append((sec,tx))
    screenshots=ta+"\\n"+tb; video="\\n".join(x[1] for x in frame_text)
    su,vu=_uid(screenshots),_uid(video); sk,vk=_kills(screenshots),_kills(video)
    sd,vd=_dates(screenshots),_dates(video)
    sm,vm={_mode(ta),_mode(tb)}-{""},{_mode(video)}-{""}
    expected=str(submission.registered_uid or "").strip()
    submitted=str(submission.free_fire_uid or "").strip()
    try:
        ia=Image.open(io.BytesIO(a)).convert("RGB").resize((128,128))
        ib=Image.open(io.BytesIO(b)).convert("RGB").resize((128,128))
        diff=round(sum(ImageStat.Stat(ImageChops.difference(ia,ib)).mean)/3,2)
    except Exception: diff=None
    reports={}
    reports["ff_arena_assessment_local_1"]=_report("FF Arena AI Assessment 1 · History Screenshot Reader",
      ea or eb or "Screenshot OCR extracted; confirm the Free Fire screen manually.",
      observed_uid=next(iter(su)) if len(su)==1 else "",uid_matches=(expected in su and submitted==expected) if su else None,
      proposed_kills=next(iter(sk)) if len(sk)==1 else None,match_date=", ".join(sorted(sd)),
      match_mode=", ".join(sorted(sm)),evidence_complete=bool(ta and tb),confidence="medium" if ta and tb else "low",
      reason=f"Screenshot OCR chars: {len(ta)}/{len(tb)}; UID candidates: {sorted(su)}; kill candidates: {sorted(sk)}.")
    reports["ff_arena_assessment_local_2"]=_report("FF Arena AI Assessment 2 · Video Frame Reader",
      video_error or "Video OCR is advisory; confirm actual gameplay/history manually.",
      observed_uid=next(iter(vu)) if len(vu)==1 else "",uid_matches=(expected in vu and submitted==expected) if vu else None,
      proposed_kills=next(iter(vk)) if len(vk)==1 else None,match_date=", ".join(sorted(vd)),
      match_mode=", ".join(sorted(vm)),evidence_complete=bool(frames and frame_text),confidence="medium" if frame_text else "low",
      reason=f"Sampled frames: {len(frames)}; readable frames: {len(frame_text)}; UID candidates: {sorted(vu)}; kill candidates: {sorted(vk)}.")
    mismatch=[]
    if su and vu and not su&vu: mismatch.append("UID mismatch between screenshot and video")
    if sd and vd and not sd&vd: mismatch.append("Date mismatch between screenshot and video")
    if sk and vk and not sk&vk: mismatch.append("Kill count mismatch between screenshot and video")
    if sm and vm and not sm&vm: mismatch.append("BR/VS mode mismatch")
    reports["ff_arena_agent_local_1"]=_report("FF Arena AI Agent 1 · Cross-media Consistency",
      "; ".join(mismatch) or "Not enough readable fields to confirm same match.",
      observed_uid=next(iter(su&vu)) if len(su&vu)==1 else "",uid_matches=(bool(su&vu) and submitted==expected) if su and vu else None,
      proposed_kills=next(iter(sk&vk)) if len(sk&vk)==1 else None,
      history_consistent=bool(su&vu and sd&vd and sk&vk and sm&vm),
      evidence_complete=bool(ta and tb and frame_text),match_date=", ".join(sorted(sd&vd)),
      match_mode=", ".join(sorted(sm&vm)),tampering_suspected=True if mismatch else None,
      tampering_notes="; ".join(mismatch) or "No decisive mismatch signal; authenticity not established.",
      reason="; ".join(mismatch) or "Cross-media fields are insufficient for an automatic pass.")
    reports["ff_arena_agent_local_2"]=_report("FF Arena AI Agent 2 · Integrity / Duplicate Audit",
      "Original files fingerprinted. Similarity and OCR cannot establish that media was genuine before upload.",
      evidence_complete=bool(frames and ta and tb),tampering_suspected=None,
      tampering_notes=f"Screenshot pixel difference={diff}; SHA-256 only detects post-upload changes.",
      reason=f"Frame count={len(frames)}; screenshot difference score={diff}; no automated payout decision.")
    verify_evidence_integrity(submission)
    return {"proposed_kills":None,"confidence":"low","uid_matches":None,
      "history_consistent":all(x["history_consistent"] for x in reports.values()),
      "evidence_complete":all(x["evidence_complete"] for x in reports.values()),
      "four_way_agreement":False,"dual_agreement":False,"reviewer_reports":reports,
      "reason":"\\n".join(x["name"]+": "+x["reason"] for x in reports.values())+
      "\\nLocal reviewers are advisory only. Admin must inspect originals and approve verified kills."}
