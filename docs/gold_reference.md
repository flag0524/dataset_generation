# gold 정답셋 — 의미 유사도 절대 기준

의미 유사도를 `유사도(output, input)`로 재면 output(재진술)과 input(원문 발췌)이 애초에
다른 글이라 0.7~0.8이 나와도 합격선을 세울 수 없다. **gold = "이 원문에 대한 이상적 정답
output"**(사람 검증본)이면 `유사도(생성output, gold output)`로 절대 기준을 세운다.

소스가 겹치는 레코드만 비교한다(같은 원천 문서 재생성 시 소스 일치). 무관한 도메인은
억지 비교 없이 매칭 0으로 정직 처리한다.

## 활성화

```bash
# gold 폴더를 GOLD_PATH로 지정 + 의미 유사도 켜기(임베딩 모델 필요)
GOLD_PATH=gold SEMANTIC_ENABLED=1 .venv/Scripts/python.exe -m uvicorn web.app:app --reload
```

리포트 방법론 검증표에 `의미 유사도(gold 기준) — N건 매칭` 행이 나온다. N은 소스가 겹쳐
실제 비교된 건수다. 임베딩 모델은 `SEMANTIC_MODEL`(기본 ko-sroberta) 로드가 필요하며,
망분리 환경은 오프라인 반입해야 한다.

## gold 폴더 구성

`GOLD_PATH`가 **폴더**면 그 안 `*.json`을 전부 합쳐 로드한다(도메인별 파일 여러 개). 파일
하나를 직접 가리켜도 된다. `gold/`는 대용량 로컬 운영물이라 git에서 제외돼 있으니 각자 시드한다.

```
gold/
  건설국토.json   ← 손 검증본(신뢰 gold)
  금융.json       ← 검증 후 추가
  ...
```

시드 예(이미 검증된 건설국토 산출물을 gold로):

```bash
mkdir -p gold && cp output/건설국토_dataset.json gold/건설국토.json
```

## 새 도메인 gold 만들기 (큐레이션)

새 도메인은 **좋은 원천 문서로 생성 → 큐레이션 → 사람 검토 → 승격** 순서로 넓힌다.

```bash
# 검증된 산출물에서 고품질 레코드만 후보로 추출
.venv/Scripts/python.exe -c "from src.gold import build_candidate_file as b; \
  print(b('output/금융_20260715-104054/금융_dataset.json', 'gold/금융_후보.json'))"
```

큐레이션 통과 기준(모두 만족): `grounded=True` · 근거성 ≥ 0.4 · 환각 엔티티 없음 ·
output 길이 32~137자. 후보 레코드에는 `metadata.gold_status="candidate"`가 붙는다.

**중요**: 큐레이션 통과분은 '일관성 기준(consistency)'일 뿐 사람 검증(verified) gold가
아니다. 자동 통과분을 그대로 gold로 쓰면 생성물을 생성물과 비교하는 순환이 되어 절대
품질이 아니라 드리프트만 잡는다. 반드시 사람이 검토·수정한 뒤 `gold_status`를 지우고
신뢰 gold로 승격해 `gold/`에 넣어라.
