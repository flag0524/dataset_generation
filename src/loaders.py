# 다중 포맷 문서를 평문 텍스트로 변환하는 로더 (TRD §3)
import os


def load_document(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md", ".markdown"):
        return _read_text(path)
    if ext == ".pdf":
        return _load_pdf(path)
    if ext == ".docx":
        return _load_docx(path)
    if ext == ".pptx":
        return _load_pptx(path)
    if ext == ".xlsx":
        return _load_xlsx(path)
    if ext == ".hwp":
        return _load_hwp(path)
    if ext in (".png", ".jpg", ".jpeg", ".tiff", ".bmp"):
        return _load_ocr(path)
    raise ValueError(f"지원하지 않는 포맷: {ext}")


def _read_text(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def _load_pdf(path):
    from pypdf import PdfReader

    reader = PdfReader(path)
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def _load_docx(path):
    import docx

    d = docx.Document(path)
    return "\n".join(p.text for p in d.paragraphs)


def _load_pptx(path):
    from pptx import Presentation

    prs = Presentation(path)
    out = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                out.append(shape.text_frame.text)
    return "\n".join(out)


def _load_xlsx(path):
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            out.append("\t".join("" if c is None else str(c) for c in row))
    return "\n".join(out)


def _load_hwp(path):
    # HWP는 best-effort. 완전 지원이 어려워 본문 스트림만 추출 시도
    import olefile

    if not olefile.isOleFile(path):
        raise ValueError("유효한 HWP(OLE) 파일이 아님")
    ole = olefile.OleFileIO(path)
    try:
        if ole.exists("PrvText"):
            data = ole.openstream("PrvText").read()
            return data.decode("utf-16-le", errors="ignore")
    finally:
        ole.close()
    return ""


def _load_ocr(path):
    import pytesseract
    from PIL import Image

    return pytesseract.image_to_string(Image.open(path), lang="kor+eng")
