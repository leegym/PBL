import os
import psycopg
import json
import glob
from google import genai
from google.genai import types
from pypdf import PdfReader
from pydantic import BaseModel

# Gemini Client 설정
client = genai.Clinet()

psycopg_db = {
    "dbname": "Practice",
    "user": "postgres",
    "password": "kyeongmin1",
    "host": "localhost",
    "port": "5432",
}

# 1. AI가 반환할 데이터 구조를 Pydantic 모델로 정의
class LawItem(BaseModel):
    law_name: str
    law_number: str
    law_title: str
    paragraph_number: str
    content: str
    is_mandatory: bool

class LawExtractionResponse(BaseModel):
    laws: list[LawItem]

# 2. PDF 텍스트를 읽고 AI에게 구조화 추출 요청

def extract_laws(pdf_path: str) -> list[dict]:
    reader = PdfReader(pdf_path)
    all_laws = []
    
    file_name = os.path.basename(pdf_path)
    
    # 중복 추출 방지를 위한 Set
    seen_keys = set()
    
    # 이전 페이지 텍스트를 저장할 변수
    prev_text = ""

    for i, page in enumerate(reader.pages):
        current_text = page.extract_text()
        if not current_text:
            continue
            
        # 줄바꿈을 공백으로 처리하여 문장 끊김 방지
        current_text = current_text.replace('\n', ' ')
        
        # 핵심: 이전 페이지와 현재 페이지를 이어 붙여 조문이 두 동강 나는 것을 방지
        batch_text = prev_text + " " + current_text
        
        print(f"[{file_name}] {i + 1}/{len(reader.pages)} 페이지")
        
        prompt = f"""
        아래 제공된 [현재 파일명: {file_name}]의 PDF 텍스트를 분석하여 각 조문 단위로 정확하게 찾아내어 구조화해주세요.
        텍스트가 페이지 경계에서 잘려있거나 단어 중간에 줄바꿈이 있어도(예: 조\n정위원) 문맥을 파악해 완성된 단어와 문장으로 복원하여 추출해야 합니다.

        [추출 규칙]
        1. law_name: 파일명을 참고하여 해당 법령의 명칭을 기재합니다. (장/절 제목은 제외)
        2. law_number: 조문 번호를 입력하세요. ("제3조의2", "제10조의2" 등 '의'가 포함된 번호도 필수 추출)
        3. law_title: 괄호 () 안의 조문 제목을 추출하세요. 괄호가 없으면 "제목없음"으로 기재하세요.
        4. paragraph_number: 동그라미 기호(①, ②)는 '항', 아라비아 숫자(1., 2.)는 '호'입니다.
           - 주의: 항(①) 기호 없이 조문 본문 아래에 바로 호(1., 2.)가 나열되는 경우, paragraph_number를 "본문 제1호", "본문 제2호" 형태로 기재하세요.
           - 특정 항 아래에 여러 호가 있다면 "제2항 제1호", "제2항 제1의2호"처럼 묶어서 표기하고, 기호가 아예 없으면 "본문"으로 적으세요.
        5. content: 문맥을 이어붙여 완성된 원문만 담아주세요.
           - '호' 단위로 세부 항목이 나열된 경우 절대 하나로 합치지 말고, 각 '호'마다 별도의 데이터(LawItem)로 완벽히 분리하세요.
           - "[본조신설 2017. 5. 29.]", "[전문개정 2008. 3. 21.]" 등 대괄호 [ ] 로 묶인 조문 제/개정 연혁 정보는 데이터에 포함하지 말고 모두 삭제하세요.
           - "<개정 2020. 6. 9.>" 같은 꺾쇠 정보도 지우세요.
           - "삭제"만 명시된 조문은 아예 추출하지 마세요.
        6. is_mandatory: 해당 조문이 당사자 합의로 배제할 수 없는 강행규정 성격이면 true, 임의규정이면 false로 설정하세요.

        [PDF 텍스트 내용]
        {batch_text}
        """

        try:
            response = client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=LawExtractionResponse,
                    temperature=0.0, 
                ),
            )
            
            result_dict = json.loads(response.text)
            extracted = result_dict.get("laws", [])
            
            # 중복 데이터 걸러내기 (이전 페이지 텍스트와 겹쳐서 두 번 추출된 경우 방지)
            for item in extracted:
                # 1. 값 추출 및 공백(띄어쓰기) 완벽 제거 (정규화)
                law_name_norm = str(item.get('law_name', '')).replace(" ", "")
                law_num_norm = str(item.get('law_number', '')).replace(" ", "")
                para_num_norm = str(item.get('paragraph_number', '')).replace(" ", "")
                
                unique_key = f"{law_name_norm}_{law_num_norm}_{para_num_norm}"
                
                if unique_key not in seen_keys:
                    seen_keys.add(unique_key)
                    all_laws.append(item)
                else:
                    pass
                    
        except Exception as e:
            print(f"오류발생({i+1} 부근): {e}")
        
        # 다음 루프를 위해 현재 페이지 텍스트를 prev_text로 이관
        prev_text = current_text

    return all_laws

# 3. 임베딩 생성 함수
# def get_embedding(text: str):
#     response = client.models.embed_content(
#         model="gemini-embedding-001",
#         contents=text,
#         config=types.EmbedContentConfig(output_dimensionality=1024)
#     )
#     return response.embeddings[0].values

# 4. DB 저장 메인 함수
def save_ai_parsed_laws_to_db(pdf_path: str):
    laws_data = extract_laws(pdf_path)
    print(f"총 {len(laws_data)}개 발견")

    with psycopg.connect(**psycopg_db) as conn:
        with conn.cursor() as cur:
            for item in laws_data:
                law_name = item.get("law_name", "민법")
                law_number = item.get("law_number")
                law_title = item.get("law_title")
                paragraph_number = item.get("paragraph_number", "본문")
                content = item.get("content")
                is_mandatory = item.get("is_mandatory", False)

                # 임베딩 생성
                # chunk_text = f"[{law_name} {law_number}({law_title})] {content}"
                # vector_data = get_embedding(chunk_text)

                # DB 삽입
                cur.execute("""
                    INSERT INTO law_articles 
                    (law_name, law_number, law_title, paragraph_number, content, is_mandatory) VALUES (%s, %s, %s, %s, %s, %s)""", (law_name, law_number, law_title, paragraph_number, content, is_mandatory))
            conn.commit()
            print("완료")

pdf_files = glob.glob("*.pdf")

# 실행 예시
if __name__ == "__main__":
    for file_path in pdf_files:
        file_name = os.path.basename(file_path)
        print("\n" + "="*50)
        print(f"파일명: {file_name}")
        print("="*50)
        save_ai_parsed_laws_to_db(file_path)