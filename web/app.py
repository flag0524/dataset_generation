# 문서 업로드 → 데이터셋 생성 → 검증 결과를 제공하는 FastAPI 웹 서버
import os
import sys
import tempfile

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.runner import run
from src.config import config

app = FastAPI(title="도메인 특화 데이터셋 생성 시스템")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as f:
        return f.read()


@app.post("/api/generate")
async def generate(file: UploadFile = File(...)):
    suffix = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    # 원본 파일명을 유지해 source_document에 반영
    named = os.path.join(os.path.dirname(tmp_path), file.filename)
    os.replace(tmp_path, named)
    try:
        result = run(named)
    except (ValueError, ModuleNotFoundError) as e:
        # 지원하지 않는 포맷·파서 의존성 누락 등은 사용자에게 보이는 오류로 반환
        return JSONResponse({"error": f"문서를 처리할 수 없습니다: {e}"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": f"생성 중 오류가 발생했습니다: {e}"}, status_code=500)
    finally:
        if os.path.exists(named):
            os.remove(named)
    v = result["validation"]
    return JSONResponse({
        "domain": result["meta"]["domain"],
        "expert": result["expert"],
        "llm_mode": result["llm_mode"],
        "extraction_mode": result["extraction_mode"],
        "quality_score": v["quality_score"],
        "status": v["status"],
        "row_count": v["row_count"],
        "duplicates_removed": v["duplicates_removed"],
        "format_consistent": v["format_consistent"],
        "issues": v["issues"],
        "output_dir": result["output_dir"],
    })


@app.get("/api/download/{name}")
def download(name: str):
    path = os.path.join(config.output_dir, name)
    if not os.path.exists(path):
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path, filename=name)
