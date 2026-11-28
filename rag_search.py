import os
import re
import time
import psycopg
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel
import json

load_dotenv()

# 파싱 내용
# special_terms = [
#     {
#         "clause_no": 1,
#         "clause_text": "제 3조 (용도변경 및 전대 등) 임차인은 임대인의 동의 없이 위 부동산의 용도나 구조를 변경하거나 전대·임차권 양도 또는 담보제공을 하지 못하며 임대차 목적 이외의 용도로 사용할 수 없다.",
#         "summary_text": "임차인의 용도 변경, 전대, 양도, 담보 제공 등에 대한 제한 사항을 정합니다."
#     }
# ]

special_terms = [
    {
        "target_id": "T001",
        "category": "C 차임 및 기타 금전",
        "clause_text": "임차인이 계약 기간 중 중도 해지하는 경우 위약금으로 월세 2개월분을 임대인에게 지급한다.",
        "summary_text": "임차인이 계약 기간 중 중도 해지하는 경우 위약금으로 월세 2개월분을 임대인에게 지급한다."
    }
    # {
    #     "clause_no": 2,
    #     "clause_text": "본 계약의 중개수수료는 임대인과 임차인 몫 모두 임차인이 전액 부담한다.",
    #     "summary_text": "임대인 몫을 포함한 중개수수료 전액을 임차인이 부담하도록 정합니다."
    # }
]

# 환경변수
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")

# Gemini Client 설정
client = genai.Client(api_key=GOOGLE_API_KEY)

psycopg_db = {
    "dbname": DB_NAME,
    "user": DB_USER,
    "password": DB_PASSWORD,
    "host": DB_HOST,
    "port": DB_PORT,
}

# 모델 설정
QUERY_MODEL = "gemini-3.8-flash"   # 검색 질의(legal_query) 생성 모델

# 검색 설정
MAX_RERANK_CANDIDATES = 60   # 리랭커로 넘길 후보 조문 최대 수

# content 맨 앞 머리말: "[법령명 제N조(제목)] " 또는 "법령명 제N조의M(제목) "
# ("제N항 제N호" 위치 표기와 본문 속 "[본조신설 ...]" 같은 대괄호는 남김)
HEADER_RE = re.compile(
    r"^\s*(?:"
    r"\[[^\[\]\n]*제\d+조[^\[\]\n]*\]"
    r"|[^\[\]\n()]{0,40}?(?:법|법률|령|규칙)\s+제\d+조(?:의\d+)?(?:\s*의\d+)?(?:\([^()]*\))?"
    r")\s*"
)


# 검색 질의 생성 출력 형식
class LegalQuery(BaseModel):
    target_id: str
    legal_query: str


class LegalQueryResult(BaseModel):
    results: list[LegalQuery]


LEGAL_QUERY_PROMPT = """아래 월세 계약서 특약들 각각에 대해, 그 특약이 법적으로 유효한지와
임차인에게 불리한지 판단할 때 근거가 될 법 내용을 법조문 말투로 1~3문장 작성하세요.

[작성 규칙]
1. 특약이 제한하거나 바꾸려는 임차인·임대인의 권리나 의무를 씁니다.
2. 조문 번호와 법령명은 쓰지 않습니다.
3. 특약이 유효한지·무효인지, 불리한지 같은 결론은 쓰지 않고, 법이 정한 내용만 씁니다.
4. 실제 조문과 문구가 정확히 같을 필요는 없습니다.
5. 관련된 법 내용이 떠오르지 않으면 빈 문자열("")을 씁니다.
6. 모든 target_id에 대해 한 번씩만 씁니다.

[특약 목록]
{targets_text}
"""


# 토큰 사용량 출력
def print_usage(label: str, response):
    usage = response.usage_metadata

    if usage is None:
        print(f"[토큰] {label}: 사용량 정보 없음")
        return

    thoughts = f" (생각 {usage.thoughts_token_count})" if usage.thoughts_token_count else ""
    print(
        f"[토큰] {label}: 입력 {usage.prompt_token_count} / "
        f"출력 {usage.candidates_token_count}{thoughts}"
    )


# content 맨 앞의 머리말만 제거
def strip_header(content: str) -> str:
    return HEADER_RE.sub("", content, count=1).strip()


# 검색 질의 생성 (계약서 1건의 특약 전체를 한 번에)
def generate_legal_queries(targets: list[dict]) -> dict[str, str]:
    target_ids = [target["target_id"] for target in targets]

    if not targets:
        return {}

    targets_text = "\n".join(
        f"---\n"
        f"target_id: {target['target_id']}\n"
        f"분류: {target['category']}\n"
        f"조항: {target['clause_text']}\n"
        f"요약: {target['summary_text']}"
        for target in targets
    )

    prompt = LEGAL_QUERY_PROMPT.format(targets_text=targets_text)

    # 호출이나 파싱에 실패하면 1초 쉬고 한 번만 다시 시도
    result = None

    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=QUERY_MODEL,
                contents=prompt,
                config={
                    "temperature": 0,
                    "response_mime_type": "application/json",
                    "response_json_schema": LegalQueryResult.model_json_schema()
                }
            )
            print_usage("검색 질의 생성", response)

            result = LegalQueryResult.model_validate_json(response.text)
            break

        except Exception as e:
            if attempt == 0:
                print(f"legal_query 생성 실패, 1초 후 다시 시도: {e}")
                time.sleep(1)
            else:
                print(f"[경고] legal_query 생성 실패: {e}")

    # 기본값은 빈 문자열 (검색은 summary_text만으로 진행)
    legal_queries = {target_id: "" for target_id in target_ids}

    if result is None:
        return legal_queries

    # 목록에 있는 target_id만, 처음 나온 것만 사용
    filled = set()

    for item in result.results:
        if item.target_id in legal_queries and item.target_id not in filled:
            legal_queries[item.target_id] = item.legal_query.strip()
            filled.add(item.target_id)

    missing = [target_id for target_id in target_ids if target_id not in filled]

    if missing:
        print(f"[경고] legal_query 생성 실패: 응답에 빠진 target_id {missing}")

    return legal_queries


# 임베딩 생성 함수
def get_embedding(text: str):
    response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=1024)
    )

    return response.embeddings[0].values


# 여러 문장을 한 번의 호출로 임베딩
def get_embeddings(texts: list[str]):
    response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=texts,
        config=types.EmbedContentConfig(output_dimensionality=1024)
    )
    time.sleep(0.7)

    return [embedding.values for embedding in response.embeddings]


# 법률 검색
def rag_search(queries: list[str], chunk_pool: int = 60, top_k: int | None = None):
    # 1. 빈 쿼리 제외 → 한 번에 임베딩
    queries = [query.strip() for query in queries if query and query.strip()]

    if not queries:
        return []

    query_embeddings = get_embeddings(queries)

    # 쿼리마다 가까운 조각 chunk_pool개 (<=> 코사인 거리: 작을수록 가까움)
    subqueries = []
    params = []

    for query_embedding in query_embeddings:
        embedding_str = str(query_embedding)
        subqueries.append("""
                    (SELECT
                        article_id,
                        chunk_index,
                        embedding <=> %s::vector AS distance
                    FROM article_chunks
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s)""")
        params += [embedding_str, embedding_str, chunk_pool]

    params.append(top_k)   # None이면 LIMIT NULL (제한 없음)

    # PostgreSQL 연결
    with psycopg.connect(**psycopg_db) as conn:
        with conn.cursor() as cur:

            # HNSW 인덱스가 있으면 한 번에 살펴보는 후보 수를 쿼리당 조각 수와 맞춤 (없으면 영향 없음)
            cur.execute(f"SET hnsw.ef_search = {int(chunk_pool)}")

            # 2. 쿼리별 조각을 합쳐 조문 단위로 묶기 (조문 거리 = 가장 가까운 조각의 거리)
            cur.execute(f"""
                WITH top_chunks AS ({" UNION ALL ".join(subqueries)}
                )
                SELECT
                    article_id,
                    MIN(distance) AS distance,
                    array_agg(DISTINCT chunk_index) AS hit_chunks
                FROM top_chunks
                GROUP BY article_id
                ORDER BY distance, article_id
                LIMIT %s;
            """, params)

            top_articles = cur.fetchall()

            if not top_articles:
                return []

            # 3. 후보 조문 수 제한 (거리순)
            if len(top_articles) > MAX_RERANK_CANDIDATES:
                print(f"[경고] 후보 조문 {len(top_articles)}개 → {MAX_RERANK_CANDIDATES}개로 제한")
                top_articles = top_articles[:MAX_RERANK_CANDIDATES]

            article_ids = [row[0] for row in top_articles]
            distance_map = {row[0]: row[1] for row in top_articles}
            hit_chunk_map = {row[0]: set(row[2]) for row in top_articles}

            # 4. 선택된 조문의 조각 전체를 한 번에 가져오기
            cur.execute("""
                SELECT
                    a.id AS article_id,
                    l.law_name,
                    l.law_type,
                    a.article_no,
                    a.article_title,
                    ac.chunk_index,
                    ac.content
                FROM article_chunks ac
                JOIN articles a
                    ON ac.article_id = a.id
                JOIN laws l
                    ON a.law_id = l.id
                WHERE a.id = ANY(%s)
                ORDER BY a.id, ac.chunk_index;
            """, (article_ids,))

            rows = cur.fetchall()

    # 5. 뽑은 조문 내용 정리하기
    articles = {}

    for article_id, law_name, law_type, article_no, article_title, chunk_index, content in rows:
        if article_id not in articles:
            articles[article_id] = {
                "law_name": law_name,
                "law_type": law_type,
                "law_label": law_name if law_type == "법률" else f"{law_name} {law_type}",
                "article_id": article_id,
                "article_number": article_no,
                "article_title": article_title,
                "content": [],
                "hit_chunks": sorted(hit_chunk_map[article_id]),
                "hit_content": [],
                "distance": distance_map[article_id],
                "similarity": 1 - distance_map[article_id]
            }

        # 머리말 제거 (제목만 있던 조각은 비게 되므로 뺌)
        text = strip_header(content)

        if not text:
            continue

        articles[article_id]["content"].append(text)

        if chunk_index in hit_chunk_map[article_id]:
            articles[article_id]["hit_content"].append(text)

    # 6. 검색 순위(가까운 순) 그대로 반환
    return [
        articles[article_id]
        for article_id in article_ids
        if article_id in articles
    ]


# 법령명·법령 종류·조 번호로 조문 가져오기 (검색에 걸리지 않은 조문을 붙일 때 사용)
def get_articles(keys: list[tuple[str, str, str]]) -> list[dict]:
    if not keys:
        return []

    with psycopg.connect(**psycopg_db) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    a.id AS article_id,
                    l.law_name,
                    l.law_type,
                    a.article_no,
                    a.article_title,
                    ac.content
                FROM article_chunks ac
                JOIN articles a
                    ON ac.article_id = a.id
                JOIN laws l
                    ON a.law_id = l.id
                WHERE (l.law_name, l.law_type, a.article_no) IN (
                    SELECT * FROM unnest(%s::text[], %s::text[], %s::text[])
                )
                ORDER BY a.id, ac.chunk_index;
            """, (
                [key[0] for key in keys],
                [key[1] for key in keys],
                [key[2] for key in keys],
            ))

            rows = cur.fetchall()

    articles = {}

    for article_id, law_name, law_type, article_no, article_title, content in rows:
        if article_id not in articles:
            articles[article_id] = {
                "law_name": law_name,
                "law_type": law_type,
                "law_label": law_name if law_type == "법률" else f"{law_name} {law_type}",
                "article_id": article_id,
                "article_number": article_no,
                "article_title": article_title,
                "content": [],
                "hit_chunks": [],
                "hit_content": [],
                "distance": None,
                "similarity": None
            }

        text = strip_header(content)

        if text:
            articles[article_id]["content"].append(text)

    return list(articles.values())


if __name__ == "__main__":
    legal_queries = generate_legal_queries(special_terms)

    for term in special_terms:
        legal_query = legal_queries.get(term["target_id"], "")
        result = rag_search([term["summary_text"], legal_query])

        print("\n" + "="*50)
        content = term["clause_text"]
        print("content = " + content)
        print("legal_query = " + legal_query)
        print(f"검색된 조문 수: {len(result)}")
        print(json.dumps(
                result,
                ensure_ascii=False,
                indent=2
            ))
