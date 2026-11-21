"""User-supplied decisions (PDF / DOCX / pasted text): extract text, run the real Mezon checks, keep the result on disk."""
import html
import io
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

from . import eqaror


def _pdftotext() -> str:
    """pdftotext is on PATH on the server, but on Windows it often lives only in Git's mingw64 or Poppler."""
    import shutil
    for cand in (os.environ.get("MEZON_PDFTOTEXT"), shutil.which("pdftotext"),
                 r"C:\Program Files\Git\mingw64\bin\pdftotext.exe", r"C:\Program Files\poppler\Library\bin\pdftotext.exe"):
        if cand and os.path.exists(cand):
            return cand
    return "pdftotext"
from .ai import uz
from .ai.real import audit_live

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "tmp_real" / "uploads"
MAX_BYTES = 20 * 1024 * 1024


class UploadError(Exception):
    pass


def extract(name, data):
    n = name.lower()
    if n.endswith(".docx"):
        try:
            xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")
        except Exception as exc:
            raise UploadError("DOCX faylni o‘qib bo‘lmadi (buzilgan yoki boshqa format).") from exc
        xml = re.sub(r"</w:p>|<w:br[^>]*/>", "\n", xml)
        return html.unescape(re.sub(r"<[^>]+>", "", xml))
    if n.endswith(".pdf"):
        if data[:4] != b"%PDF":
            raise UploadError("Bu haqiqiy PDF fayl emas.")
        d = tempfile.mkdtemp()
        src, out = os.path.join(d, "in.pdf"), os.path.join(d, "out.txt")  # ASCII names: pdftotext can't open Cyrillic paths
        open(src, "wb").write(data)
        try:
            subprocess.run([_pdftotext(), "-enc", "UTF-8", "-layout", src, out], check=True, timeout=90, capture_output=True)
            return open(out, encoding="utf-8", errors="replace").read()
        except FileNotFoundError as exc:
            raise UploadError("Serverda pdftotext topilmadi.") from exc
        except Exception as exc:
            raise UploadError("PDF faylni o‘qib bo‘lmadi.") from exc
    if n.endswith(".txt"):
        return data.decode("utf-8", "replace")
    raise UploadError("Faqat PDF, DOCX yoki TXT fayl yuklang.")


def check(name, data=None, text=None):
    """Returns the upload id. Raises UploadError with a clear Uzbek message."""
    is_pdf = bool(name) and name.lower().endswith(".pdf")
    if text is None:
        if not data:
            raise UploadError("Fayl bo‘sh.")
        if len(data) > MAX_BYTES:
            raise UploadError("Fayl 20 MB dan katta.")
        text = extract(name, data)
    raw_text = text
    text = re.sub(r"[ \t]+", " ", text.replace(" ", " ").replace("ʻ", "‘").replace("ʼ", "’")).strip()
    if len(text) < 80:
        raise UploadError("Skanerlangan PDF — matn topilmadi. Bu faylda matn qatlami yo‘q (rasm); skaner matnini taniydigan OCR bu kompyuterda yo‘q. "
                          "Matnni nusxalab «Matnni qo‘ying» maydoniga qo‘ying." if is_pdf else "Matn juda qisqa — tekshirib bo‘lmaydi.")
    if len(text) > 600_000:
        raise UploadError("Matn juda uzun (600 000 belgidan ortiq).")
    m0 = re.search(r"([^.]{10,260}?(?:to‘g‘risida|toʻgʻrisida|tog‘risida))", re.sub(r"\s+", " ", text))
    title0 = (m0.group(1) if m0 else re.sub(r"\s+", " ", text)[:240]).strip()[:300]
    rep = audit_live(text, title0)
    det = rep.get("detected") or {}
    reg, region, dist = det.get("reg") or "", det.get("region") or 0, det.get("district") or 0
    date = det.get("adopted") or time.strftime("%Y-%m-%d")
    first = re.sub(r"\s+", " ", text)[:240]
    m = re.search(r"([^.]{10,260}?(?:to‘g‘risida|to‘g‘risida|toʻgʻrisida|tog‘risida))", re.sub(r"\s+", " ", text))
    title = (m.group(1) if m else first).strip()[:300]
    try:
        laws = eqaror.laws("up-" + uuid.uuid4().hex[:6], text, date)
    except Exception:
        laws = []
    flags = []
    for fl in rep["flags"]:
        t, e = uz.translate(fl)
        c = fl["citations"][0] if fl["citations"] else {}
        flags.append({"title": t, "explanation": e, "law_ref": uz.law_ref(c), "law_text": c.get("quote", ""),
                      "quote": (fl["evidence"][0]["quote"] if fl["evidence"] else "").strip("… "), "severity": fl["severity"], "status": fl["status"]})
    uid = uuid.uuid4().hex[:12]
    DIR.mkdir(parents=True, exist_ok=True)
    kengash = bool(re.search(r"-K/\d\d", reg)) if reg else False
    rec = {"id": uid, "file": name or "Qo‘yilgan matn", "title": title, "text": text, "reg": reg, "region": region, "dist": dist,
           "date": date, "organ": eqaror.organ_for(region, dist, kengash) if region else "", "flags": flags, "laws": laws,
           "checks": {"total": len(rep["checks_run"]), "flags": len(flags)}, "pdf": bool(is_pdf and data),
           "words": len(text.split()), "matched": rep.get("matched"), "pages": (raw_text.count("\f") or 1) if is_pdf else 0}
    (DIR / f"{uid}.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    if is_pdf and data:
        (DIR / f"{uid}.pdf").write_bytes(data)
    return uid


def get(uid):
    p = DIR / f"{re.sub(r'[^0-9a-f]', '', uid)}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def pdf_path(uid):
    p = DIR / f"{re.sub(r'[^0-9a-f]', '', uid)}.pdf"
    return p if p.exists() else None


ATT = DIR / "attached.json"


def attached(code):
    d = json.loads(ATT.read_text(encoding="utf-8")) if ATT.exists() else {}
    return d.get(code)


def attach(code, uid):
    DIR.mkdir(parents=True, exist_ok=True)
    d = json.loads(ATT.read_text(encoding="utf-8")) if ATT.exists() else {}
    d[code] = uid
    ATT.write_text(json.dumps(d), encoding="utf-8")
