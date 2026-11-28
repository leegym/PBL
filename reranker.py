import os
import re
import json

from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, Field, ValidationError
from rag_search import rag_search, generate_legal_queries, print_usage, get_articles

load_dotenv()

# Gemini 설정
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

client = genai.Client(
    api_key=GOOGLE_API_KEY
)

RERANK_MODEL = "gemini-3.1-flash-lite"   # 리랭커 모델 (토큰을 가장 많이 써서 저렴한 모델 사용)
RERANK_MAX_OUTPUT_TOKENS = 4096          # 응답 폭주 방지 (정상 출력은 약 1,200~2,200)

TOP_N = 5        # 최종으로 남길 조문 수
MIN_SCORE = 6    # 이 점수 미만은 버림 (결과가 0개면 관련 법령 근거 없음)

# 강행규정 규칙표 (리랭커 후보에서 빼고, 최종 결과에 관련 조문이 있을 때만 코드로 붙임)
# trigger_articles가 None이면 그 법령의 모든 조문(법률·시행령 등)이 조건
MANDATORY_RULES = [
    {
        "law_name": "주택임대차보호법",
        "law_type": "법률",
        "article_no": "제10조",
        "trigger_law_name": "주택임대차보호법",
        "trigger_articles": None,
        "reason": "이 법에 위반된 약정으로서 임차인에게 불리한 것은 효력이 없다는 강행규정",
    },
    {
        "law_name": "민법",
        "law_type": "법률",
        "article_no": "제652조",
        "trigger_law_name": "민법",
        "trigger_articles": {
            "제627조", "제628조", "제631조", "제635조", "제638조", "제640조",
            "제641조", "제643조", "제644조", "제645조", "제646조", "제647조",
        },
        "reason": "이 조문들에 위반하는 약정으로 임차인에게 불리한 것은 효력이 없다는 강행규정",
    },
]


# Reranker 출력 형식 (reason을 먼저 쓰고 score를 정하도록 순서 고정)
class ScoredArticle(BaseModel):
    article_id: int = Field(
        description="후보 목록에 있는 법률 조항의 article_id"
    )
    reason: str = Field(
        description="판단 근거 한 문장 (5점 이하면 빈 문자열)"
    )
    score: int = Field(
        ge=0,
        le=10,
        description="계약서 조항 검토에 대한 관련도 점수 (0~10)"
    )


class RerankResult(BaseModel):
    results: list[ScoredArticle] = Field(
        description="모든 후보에 대한 점수 목록"
    )



# 후보 중복 제거
def dedupe_candidates(candidates: list[dict]) -> list[dict]:
    """같은 article_id가 여러 번 나오면 벡터 검색 순위가 높은 첫 번째만 남김"""

    seen = set()
    unique = []

    for rank, candidate in enumerate(candidates, start=1):

        article_id = candidate["article_id"]

        if article_id in seen:
            continue

        seen.add(article_id)
        unique.append({**candidate, "vector_rank": rank})

    return unique


# 잘린 JSON에서 끝까지 완성된 {article_id, reason, score} 항목만 꺼냄
SCORED_ITEM_RE = re.compile(
    r'\{\s*"article_id"\s*:\s*(\d+)\s*,\s*"reason"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"score"\s*:\s*(\d+)\s*\}'
)


def salvage_results(text: str | None) -> list[ScoredArticle]:
    items = []

    for article_id, reason, score in SCORED_ITEM_RE.findall(text or ""):
        try:
            items.append(ScoredArticle(
                article_id=int(article_id),
                reason=json.loads(f'"{reason}"'),
                score=int(score)
            ))
        except (ValidationError, ValueError):
            continue

    return items


# 강행규정 규칙표에 있는 조문인지 확인
def is_mandatory(candidate: dict) -> bool:
    return any(
        candidate["law_name"] == rule["law_name"]
        and candidate["law_type"] == rule["law_type"]
        and candidate["article_number"] == rule["article_no"]
        for rule in MANDATORY_RULES
    )


# 최종 결과에 관련 조문이 있으면 강행규정을 뒤에 붙임 (TOP_N과 별도)
def attach_mandatory(selected: list[dict], excluded: list[dict]) -> list[dict]:

    excluded_dict = {
        (c["law_name"], c["law_type"], c["article_number"]): c
        for c in excluded
    }

    to_attach = []

    for rule in MANDATORY_RULES:
        triggers = [
            c for c in selected
            if c["law_name"] == rule["trigger_law_name"]
            and (rule["trigger_articles"] is None or c["article_number"] in rule["trigger_articles"])
        ]

        if triggers:
            to_attach.append((rule, triggers))

    if not to_attach:
        return selected

    # 검색에 걸리지 않은 강행규정은 DB에서 가져옴
    keys = [(rule["law_name"], rule["law_type"], rule["article_no"]) for rule, _ in to_attach]
    fetched = {
        (c["law_name"], c["law_type"], c["article_number"]): c
        for c in get_articles([key for key in keys if key not in excluded_dict])
    }

    attached = []

    for (rule, triggers), key in zip(to_attach, keys):
        article = excluded_dict.get(key) or fetched.get(key)

        if article is None:
            print(f"[경고] 강행규정 조문을 찾지 못함: {' '.join(key)}")
            continue

        trigger_text = ", ".join(f"{c['law_label']} {c['article_number']}" for c in triggers)

        attached.append({
            **article,
            "vector_rank": article.get("vector_rank"),
            "rerank_score": None,
            "rerank_reason": f"선택된 {trigger_text}에 관한 {rule['reason']}",
            "attached": True
        })

    return selected + attached


# Reranker
def rerank(term: dict, candidates: list[dict]) -> list[dict]:

    candidates = dedupe_candidates(candidates)

    # 강행규정은 리랭커 후보에서 빼고 나중에 코드로 붙임
    excluded = [c for c in candidates if is_mandatory(c)]
    candidates = [c for c in candidates if not is_mandatory(c)]

    if not candidates:
        return []

    candidate_text = ""

    for i, candidate in enumerate(candidates, start=1):

        # 검색에 걸린 조각만 최대 3개
        content = "\n".join(candidate["hit_content"][:3])

        candidate_text += (
            f"---\n"
            f"[후보 {i}]\n"
            f"article_id: {candidate['article_id']}\n"
            f"법률명: {candidate['law_label']}\n"
            f"조문번호: {candidate['article_number']}\n"
            f"조문제목: {candidate['article_title']}\n"
            f"내용:\n"
            f"{content}\n"
        )

    candidate_text += "---"


    # legal_query는 넣지 않음 (LLM이 자기가 만든 문장에 끌려가지 않게)
    prompt = f"""당신은 주택 월세 계약서의 특약을 임차인 입장에서 검토하는 법률 검토자입니다.
아래 특약이 법적으로 유효한지, 임차인에게 불리한지 판단할 때
각 법률 후보가 근거로 얼마나 쓸모 있는지 점수를 매기세요.

[검토 대상 특약]
분류: {term["category"]}
조항: {term["clause_text"]}
요약: {term["summary_text"]}

[법률 후보]
각 후보는 검색에 걸린 일부 항만 보여 줍니다.
{candidate_text}

[점수 기준]
- 9~10점: 이 특약의 내용을 직접 금지·제한·무효로 하는 조문,
          또는 이 특약이 제한하려는 임차인의 권리 자체를 정한 조문
- 6~8점: 직접 근거는 아니지만 판단에 필요한 조문 (금액·기간 계산, 절차, 예외 조건 등)
- 3~5점: 같은 주제지만 이 특약과는 상황이 다른 조문
- 0~2점: 단어만 비슷하거나 관련 없는 조문

[주의]
- 후보 대부분은 0~4점이 정상입니다. 9~10점은 보통 1~3개입니다.
- 이 서비스는 주택 임대차만 다룹니다.
- 공인중개사법은 중개보수·중개사 의무와 관련된 특약일 때만 높은 점수를 줍니다.
- 분쟁조정위원회, 조정 신청 등 기관이나 절차에 관한 조문은 특약의 효력을 판단하는 근거가 아니므로 0~3점입니다.
- 특약의 내용이 다른 제도의 요건이나 사유로만 언급된 조문은 3~5점입니다.
  (예: 차임 연체를 다루는 특약에 대해, 차임 연체를 갱신 거절 사유로 나열한 조문)
  단, 특약이 그 제도 자체(갱신요구권 등)를 제한하는 경우에는 9~10점입니다.

[예시]
특약: "임차인은 계약갱신요구권을 행사하지 아니한다."
- 주택임대차보호법 제6조의3(계약갱신 요구 등) → 10점: 포기하려는 권리를 정한 조문
- 주택임대차보호법 제6조(계약의 갱신) → 5점: 묵시적 갱신으로, 갱신요구권과는 다른 제도
- 공인중개사법 제32조(중개보수 등) → 0점: 관련 없음

[작성 규칙]
1. 후보 목록의 모든 article_id에 대해 한 번씩만 점수를 매깁니다.
2. 목록에 없는 article_id를 만들지 않습니다.
3. reason을 먼저 쓰고, 그 근거에 맞게 score를 정합니다.
4. 5점 이하는 reason을 빈 문자열("")로 둡니다.
"""


    # 결과 개수를 후보 수로 제한 (다 쓴 뒤 처음부터 다시 쓰는 폭주 방지)
    schema = RerankResult.model_json_schema()
    schema["properties"]["results"]["maxItems"] = len(candidates)

    # Gemini 호출 (temperature 0, 출력 토큰 상한)
    response = client.models.generate_content(
        model=RERANK_MODEL,
        contents=prompt,
        config={
            "temperature": 0,
            "max_output_tokens": RERANK_MAX_OUTPUT_TOKENS,
            "response_mime_type": "application/json",
            "response_json_schema": schema
        }
    )
    print_usage(f"리랭커 {term['target_id']} (후보 {len(candidates)}개)", response)

    # 상한에 걸려 응답이 잘린 경우 (이어서 파싱 실패 → 완성된 항목만 사용)
    if response.candidates and str(response.candidates[0].finish_reason).endswith("MAX_TOKENS"):
        print(f"[경고] 리랭커 출력이 {RERANK_MAX_OUTPUT_TOKENS}토큰 상한에 걸려 잘림")


    # 결과 파싱 (실패하면 완성된 항목만 살리고, 그것도 없으면 벡터 검색 순서로 대체)
    try:
        rerank_result = RerankResult.model_validate_json(
            response.text
        )
    except (ValidationError, TypeError) as e:
        salvaged = salvage_results(response.text)

        if not salvaged:
            print(f"[경고] 리랭커 응답 파싱 실패, 벡터 검색 순서로 대체: {e}")
            return attach_mandatory(candidates[:TOP_N], excluded)

        print(f"[경고] 리랭커 응답 파싱 실패, 완성된 항목 {len(salvaged)}개만 사용")
        rerank_result = RerankResult(results=salvaged)


    # 후보에 있는 결과만, 중복 없이 모으기
    candidate_dict = {
        candidate["article_id"]: candidate
        for candidate in candidates
    }

    scored = {}

    for item in rerank_result.results:

        if item.article_id not in candidate_dict:
            continue

        # 같은 article_id가 또 나오면 처음 것만 사용
        if item.article_id in scored:
            continue

        scored[item.article_id] = {
            **candidate_dict[item.article_id],
            "rerank_score": item.score,
            "rerank_reason": item.reason
        }


    # 점수순 정렬 (동점이면 벡터 검색 순위가 높은 쪽 우선)
    ranked = sorted(
        scored.values(),
        key=lambda c: (-c["rerank_score"], c["vector_rank"])
    )

    ranked = [
        c for c in ranked
        if c["rerank_score"] >= MIN_SCORE
    ]

    return attach_mandatory(ranked[:TOP_N], excluded)


# 실행
if __name__ == "__main__":

    special_terms = [
        {
            "target_id": "T001",
            "category": "C 차임 및 기타 금전",
            "clause_text": "임차인이 계약 기간 중 중도 해지하는 경우 위약금으로 월세 2개월분을 임대인에게 지급한다.",
            "summary_text": "임차인이 계약 기간 중간에 나가면 월세 2개월분을 위약금으로 임대인에게 내야 합니다."
        },
        {
            "target_id": "T002",
            "category": "C 차임 및 기타 금전",
            "clause_text": "본 계약의 중개수수료는 임대인과 임차인 몫 모두 임차인이 전액 부담한다.",
            "summary_text": "임대인 몫을 포함한 중개수수료 전액을 임차인이 내도록 정합니다."
        },
        {
            "target_id": "T003",
            "category": "D 주택의 유지·관리 및 책임",
            "clause_text": "임차목적물의 모든 수선 및 유지보수 비용은 임차인이 부담한다.",
            "summary_text": "집에서 생기는 모든 수리비와 유지보수 비용을 임차인이 내도록 정합니다."
        },
        {
            "target_id": "T004",
            "category": "F 생활",
            "clause_text": "실내 흡연 및 반려동물 사육을 금지하며, 위반 시 임대인은 계약을 해지할 수 있다.",
            "summary_text": "집 안에서 담배를 피우거나 반려동물을 키우면 임대인이 계약을 해지할 수 있습니다."
        }
    ]

    # 0. 검색 질의 생성 (계약서 1건당 1회)
    legal_queries = generate_legal_queries(special_terms)

    for term in special_terms:

        legal_query = legal_queries.get(term["target_id"], "")

        # 1. Vector Search
        candidates = rag_search([term["summary_text"], legal_query])

        # 2. Reranking (점수 매기기 + 정렬)
        selected = rerank(term, candidates)

        # 3. 결과 출력
        print("\n" + "=" * 60)
        print(f"target_id: {term['target_id']}")
        print(f"clause: {term['clause_text']}")
        print(f"legal_query: {legal_query or '(빈 문자열)'}")
        print(f"후보 조문 수: {len(candidates)}")

        print("\n[Vector Search Top 20]")
        for rank, c in enumerate(candidates[:20], start=1):
            print(
                f"{rank:>2}. {c['law_label']} {c['article_number']} {c['article_title']} "
                f"(거리 {c['distance']:.4f}, 걸린 조각 {c['hit_chunks']})"
            )

        print(f"\n[Reranker Top {TOP_N}]")
        if not selected:
            print("관련 법령 근거 없음")

        for rank, c in enumerate(selected, start=1):
            score = "강행규정" if c.get("attached") else f"{c.get('rerank_score', '-')}점"
            vector = f"벡터 {c['vector_rank']}위" if c.get("vector_rank") else "검색 안 걸림"
            print(
                f"{rank}. [{score}] "
                f"{c['law_label']} {c['article_number']} {c['article_title']} "
                f"({vector})"
            )
            if c.get("rerank_reason"):
                print(f"   이유: {c['rerank_reason']}")
