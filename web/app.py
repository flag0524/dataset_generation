# 문서 업로드 → 데이터셋 생성 → 검증 결과를 제공하는 FastAPI 웹 서버
import os
import sys
import shutil
import tempfile
from typing import List

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.runner import run, run_many
from src.config import config

app = FastAPI(title="도메인 특화 데이터셋 생성 시스템")

# '빠른 미리보기' 모드에서 STEP3~4 LLM 작업에 거는 벽시계 예산(초). 이 모드 산출물은
# 초과 청크가 드롭된 미완성본이며 학습용이 아니다. 기본(preview=False)은 무제한 생성.
PREVIEW_BUDGET_S = 25

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    # 루트는 랜딩페이지를 제공한다(데이터셋 생성 도구는 /generate).
    with open(os.path.join(STATIC_DIR, "landing.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read(), headers={"Cache-Control": "no-store"})


@app.get("/generate", response_class=HTMLResponse)
def generate_page():
    with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as f:
        return f.read()


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    # no-store로 서빙해 UI 갱신이 브라우저 캐시에 막히지 않게 한다(/static 정적 서빙은 캐시됨).
    with open(os.path.join(STATIC_DIR, "dashboard.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read(), headers={"Cache-Control": "no-store"})


def _fix_filename(name: str) -> str:
    # Starlette는 multipart 파일명을 latin-1로 디코드한다. 한글 파일명은 원래 바이트가
    # latin-1 문자열로 깨져 들어오므로 latin-1로 되돌린 뒤 실제 인코딩으로 디코드한다.
    # 클라이언트별로 UTF-8(브라우저)·CP949(한국어 Windows 셸)가 섞이므로 순서대로 시도한다.
    # 이미 올바른 유니코드(비 latin-1 문자 포함)면 latin-1 인코딩이 실패하니 그대로 둔다.
    if not name:
        return "upload"
    try:
        raw = name.encode("latin-1")
    except UnicodeEncodeError:
        return name
    for enc in ("utf-8", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return name


@app.post("/api/generate")
async def generate(files: List[UploadFile] = File(...), preview: bool = Form(False)):
    # 파일 1개면 단일 생성(run), 여러 개면 통합 생성(run_many). 여러 관련 문서
    # (예: 의안원문+검토보고서)를 함께 넣으면 소스가 커져 권장 행 수에 도달하기 쉽다.
    tmpdir = tempfile.mkdtemp()
    named_paths = []
    try:
        for f in files:
            # 원본 파일명을 유지해 source_document에 반영(경로 조작 방지 위해 basename만).
            # multipart 파일명은 Starlette가 latin-1로 디코드해 한글이 깨지므로 UTF-8로 복원한다.
            p = os.path.join(tmpdir, os.path.basename(_fix_filename(f.filename)))
            with open(p, "wb") as out:
                out.write(await f.read())
            named_paths.append(p)
        budget = PREVIEW_BUDGET_S if preview else None
        if len(named_paths) == 1:
            result = run(named_paths[0], time_budget=budget)
        else:
            result = run_many(named_paths, time_budget=budget)
    except (ValueError, ModuleNotFoundError) as e:
        # 지원하지 않는 포맷·파서 의존성 누락 등은 사용자에게 보이는 오류로 반환
        return JSONResponse({"error": f"문서를 처리할 수 없습니다: {e}"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": f"생성 중 오류가 발생했습니다: {e}"}, status_code=500)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    v = result["validation"]
    # run_many는 meta/expert/extraction_mode 대신 sources를 반환하므로 폴백을 둔다.
    meta = result.get("meta", {})
    return JSONResponse({
        "domain": meta.get("domain") or "법률 (통합)",
        "expert": result.get("expert") or "다중 전문가 통합",
        "llm_mode": result["llm_mode"],
        "extraction_mode": result.get("extraction_mode", "-"),
        "quality_score": v["quality_score"],
        "status": v["status"],
        "row_count": v["row_count"],
        "duplicates_removed": v["duplicates_removed"],
        "format_consistent": v["format_consistent"],
        "issues": v["issues"],
        "sources": result.get("sources"),  # 통합 생성일 때 소스 구성(문서별 행 수)
        "output_dir": result["output_dir"],
        "artifacts": result["artifacts"],
        "preview": preview,  # True면 미완성 미리보기(학습용 아님)
    })


@app.get("/api/history")
def history():
    # 생성 이력(history.jsonl)을 최신순으로 반환하고 PRD KPI를 집계한다.
    import json
    path = os.path.join(config.output_dir, "history.jsonl")
    runs = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    # 인코딩 수정 이전에 깨진 채 저장된 옛 이력의 파일명을 읽을 때 복원한다.
                    if rec.get("document_name"):
                        rec["document_name"] = _fix_filename(rec["document_name"])
                    runs.append(rec)
    runs.reverse()  # 최신 먼저

    total = len(runs)
    pass_count = sum(1 for r in runs if r.get("status") == "PASS")
    scores = [r.get("quality_score", 0) for r in runs]
    domains = {}
    for r in runs:
        d = r.get("domain", "기타")
        domains[d] = domains.get(d, 0) + 1
    kpi = {
        "total_runs": total,
        "avg_quality": round(sum(scores) / total, 1) if total else 0,
        "pass_rate": round(pass_count / total * 100, 1) if total else 0,
        "total_rows": sum(r.get("row_count", 0) for r in runs),
        "domains": domains,
    }
    return JSONResponse({"kpi": kpi, "runs": runs})


@app.get("/api/download/{name:path}")
def download(name: str):
    # 산출물은 실행별 폴더에 저장되므로 name은 '실행폴더/파일명' 형태다({name:path}로 수신).
    # 경로 조작(../)으로 output 밖 파일을 읽지 못하도록 실제 경로가 output 하위인지 검증한다.
    base = os.path.realpath(config.output_dir)
    path = os.path.realpath(os.path.join(base, name))
    if os.path.commonpath([base, path]) != base or not os.path.isfile(path):
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path, filename=os.path.basename(path))
