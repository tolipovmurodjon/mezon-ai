"""Text helpers: pull plain text out of uploaded files, and render AI text safely."""
import io
import re
import zipfile
from xml.etree import ElementTree

from django.utils.html import escape
from django.utils.safestring import mark_safe

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extract_text(field_file):
    """Best-effort text extraction for .txt, .docx and (if pypdf is installed) .pdf."""
    name = field_file.name.lower()
    try:
        field_file.open("rb")
        data = field_file.read()
    except Exception:
        return ""
    finally:
        try:
            field_file.seek(0)
        except Exception:
            pass

    if name.endswith((".txt", ".md")):
        for enc in ("utf-8", "cp1251", "latin-1"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return ""
    if name.endswith(".docx"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                root = ElementTree.fromstring(z.read("word/document.xml"))
            paras = []
            for p in root.iter(f"{W_NS}p"):
                paras.append("".join(t.text or "" for t in p.iter(f"{W_NS}t")))
            return "\n".join(p for p in paras if p.strip())
        except Exception:
            return ""
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader  # optional dependency
        except ImportError:
            return ""
        try:
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:
            return ""
    return ""


_BOLD = re.compile(r"\*\*(.+?)\*\*")


BULLET = re.compile(r"^\s*[-•]\s+")


def format_ai_text(text):
    """
    Turn the model's light markup into kit markup, escaping everything first:
    blank-line paragraphs, "- " bullets and **bold**.
    """
    if not text:
        return ""
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        para, bullets = [], []
        for ln in (ln.rstrip() for ln in block.splitlines()):
            if not ln.strip():
                continue
            if BULLET.match(ln):
                bullets.append(BULLET.sub("", ln))
            elif bullets:  # text after a list closes it and starts a new paragraph
                out.append(_list(para, bullets))
                para, bullets = [ln], []
            else:
                para.append(ln)
        out.append(_list(para, bullets))
    return mark_safe("".join(out))


def _list(para, bullets):
    html = ""
    if para:
        html += "<p>" + "<br>".join(_inline(p) for p in para) + "</p>"
    if bullets:
        html += "<ul>" + "".join("<li>" + _inline(b) + "</li>" for b in bullets) + "</ul>"
    return html


def _inline(s):
    s = escape(re.sub(r"\s*\[\d{1,2}\]", "", s))  # drop old [n] source markers
    s = _BOLD.sub(r"<b>\1</b>", s)
    return s


MIXED_SCRIPT = re.compile(r"\b(?=\w*[A-Za-z])(?=\w*[Ѐ-ӿ])\w+\b")


def mixed_script_words(text):
    """Words that mix Latin and Cyrillic letters, e.g. 'TАRKIBI' with a Cyrillic А."""
    return sorted(set(MIXED_SCRIPT.findall(text)))
