# Document AI 기반 데이터셋 검증 방법론

## 개요

Document AI로 생성된 데이터셋은 OCR 정확도, 구조, 의미, Grounding, LLM
학습 적합성을 종합 검증해야 합니다.

## 검증 단계

1.  OCR 품질 검증
2.  문서 구조 검증
3.  의미 보존 검증
4.  Entity 검증
5.  Grounding 검증
6.  Dataset 품질 검증
7.  자동 품질평가
8.  Human Review

## OCR 품질

-   CER 1% 이하
-   WER 3% 이하
-   헤더/푸터/페이지 번호 제거
-   표 구조 유지

## 구조 검증

-   Heading, Table, Paragraph 유지
-   조/항/호 구조 보존

## 의미 검증

-   Semantic Similarity 0.95 이상(BERTScore, SentenceTransformer)

## Entity 검증

-   기관명, 법령명, 날짜, 금액, 인명, 조문
-   Precision/Recall/F1

## Grounding

-   Grounding Score 0.80 이상 권장
-   grounded=false 데이터 재검토

## Dataset 품질

-   Instruction: 다양성, 중복
-   Input: OCR 오류, 노이즈
-   Output: 정확성, 완전성, Hallucination

## 자동 평가

-   RAGAS
-   DeepEval
-   LangSmith
-   Promptfoo
-   G-Eval

## Human Review

전체의 5\~10% 샘플 검수

## 공공기관 권장 기준

  항목                            기준
  --------------------- --------------
  OCR 정확도                  99% 이상
  Semantic Similarity        0.95 이상
  Grounding                  0.80 이상
  Hallucination                2% 이하
  중복                         3% 이하
  Metadata                        100%
  Human Review                95% 이상
  최종 품질               90점 이상(A)
