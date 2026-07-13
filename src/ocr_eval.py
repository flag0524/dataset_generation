# OCR 정확도(CER/WER) 독립 측정: PDF 텍스트 레이어(참조) vs 렌더링+OCR(가설) 대조
#
# 기존 리포트는 source_span == input(같은 값)을 비교해 OCR 100%라고 볼 수 없었다(자기비교).
# 여기서는 '독립적인 두 경로'를 대조한다:
#   참조(reference) = PDF에 내장된 텍스트 레이어 (디지털 PDF의 정본)
#   가설(hypothesis) = 같은 페이지를 이미지로 렌더링해 Tesseract로 OCR한 결과
# 두 경로는 서로 독립이므로 CER/WER이 OCR 엔진의 실제 오류율을 나타낸다.
# 스캔 PDF(텍스트 레이어 없음)는 참조가 없어 측정 불가 → None(미측정)을 반환한다.
import re

_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    # 공백 차이는 OCR 오류로 보지 않는다(표준 CER 관행). 공백을 하나로 접고 양끝을 자른다.
    return _WS.sub(" ", (s or "")).strip()


def _levenshtein(a, b) -> int:
    # 편집거리(삽입·삭제·치환). a/b는 문자열(CER) 또는 단어 리스트(WER) 모두 가능.
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1,        # 삭제
                           cur[j - 1] + 1,     # 삽입
                           prev[j - 1] + (ca != cb)))  # 치환
        prev = cur
    return prev[-1]


def cer(reference: str, hypothesis: str) -> float:
    ref, hyp = _norm(reference), _norm(hypothesis)
    if not ref:
        return 0.0
    return _levenshtein(ref, hyp) / len(ref)


def wer(reference: str, hypothesis: str) -> float:
    ref, hyp = _norm(reference).split(), _norm(hypothesis).split()
    if not ref:
        return 0.0
    return _levenshtein(ref, hyp) / len(ref)


# 텍스트 레이어가 이보다 적은 페이지는 스캔면으로 보고 참조 없음 처리(측정 제외).
_MIN_REF_CHARS = 50


def measure_pdf_ocr(path: str, max_pages: int = None) -> dict:
    """PDF의 텍스트 레이어를 참조로 삼아 렌더+OCR 결과의 CER/WER을 측정한다.

    반환: {"pages": n, "cer": float, "wer": float, "accuracy": float(%)} 또는
          측정 불가 시 {"pages": 0, "reason": "..."} (참조 부재·의존성 미설치 등).
    """
    try:
        from pypdf import PdfReader
        import pypdfium2 as pdfium
        from .loaders import _ocr_image
    except ModuleNotFoundError as e:
        return {"pages": 0, "reason": f"의존성 미설치({e.name})"}

    reader = PdfReader(path)
    refs = [(p.extract_text() or "") for p in reader.pages]
    idx = [i for i, t in enumerate(refs) if len(_norm(t)) >= _MIN_REF_CHARS]
    if max_pages:
        idx = idx[:max_pages]
    if not idx:
        # 스캔 PDF: 텍스트 레이어(참조)가 없어 OCR을 대조할 정본이 없다.
        return {"pages": 0, "reason": "텍스트 레이어 없음(스캔 PDF) — 참조 부재로 측정 불가"}

    pdf = pdfium.PdfDocument(path)
    try:
        ref_all, hyp_all = [], []
        for i in idx:
            img = pdf[i].render(scale=300 / 72).to_pil()  # 로더와 동일한 300DPI
            hyp_all.append(_ocr_image(img))
            ref_all.append(refs[i])
    except Exception as e:  # Tesseract 미설치 등
        return {"pages": 0, "reason": f"OCR 실행 불가({e})"}
    finally:
        pdf.close()

    ref, hyp = "\n".join(ref_all), "\n".join(hyp_all)
    c, w = cer(ref, hyp), wer(ref, hyp)
    return {
        "pages": len(idx),
        "cer": round(c, 4),
        "wer": round(w, 4),
        "accuracy": round((1 - c) * 100, 2),  # 문자 정확도(%) = 1 - CER
        "ref_chars": len(_norm(ref)),
    }
