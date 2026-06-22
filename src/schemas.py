# 단계 간 데이터 계약 검증 헬퍼 (TRD §4 고정 스키마)

CSV_COLUMNS = [
    "id", "domain", "category", "question", "answer",
    "instruction", "input", "output", "source_document", "keyword", "created_date",
]


def validate_metadata(m: dict) -> bool:
    return all(k in m for k in ("document_name", "domain", "purpose", "keywords"))


def validate_rule(r: dict) -> bool:
    return all(k in r for k in ("rule_id", "condition", "action", "exception"))


def validate_instruction(d: dict) -> bool:
    return all(k in d for k in ("instruction", "input", "output"))


def validate_qa(d: dict) -> bool:
    return all(k in d for k in ("question", "answer", "source"))


def validate_rag(d: dict) -> bool:
    return "id" in d and "title" in d and "content" in d and "keyword" in d.get("metadata", {})
