import json
import psycopg2
import os
from datetime import datetime
from psycopg2.extras import execute_values
import re
from google import genai
from google.genai import types

client = genai.Client()

# # 임베딩 생성 함수
def get_embedding(text: str):
    response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=1024)
    )
    return response.embeddings[0].values

# 문자열, 리스트, 중첩 리스트에서 순수 텍스트만 뽑아 하나로 합치는 함수
def extract_clean_text(content) -> str:
    if not content:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        flat_list = []
        for item in content:
            text = extract_clean_text(item)
            if text:
                flat_list.append(text)
        return " ".join(flat_list)
    
    return str(content).strip()


# 저장할려는 법률 파일명 작성
law = "주택임대차보호법 시행령.json"
law_name = law.split()[0]
law_type = law.split()[1].split(".")[0]


# DB 연결 (환경에 맞게 수정)
try:
    conn = psycopg2.connect(
        host="localhost",
        database="LAW",
        user="postgres",
        password=""
    )
    cursor = conn.cursor()
    print("연결됨")
except:
    print("연결안됨")


# 1. laws 테이블 저장 (없으면 삽입 후 ID 반환, 있으면 조회)
def laws_table_save()->str:
    cursor.execute("""INSERT INTO laws (law_name, law_type) VALUES (%s, %s) ON CONFLICT (law_name, law_type) DO NOTHING RETURNING id;""", (law_name, law_type))

    row = cursor.fetchone()
    if row:
        law_id = row[0]
    else:
        cursor.execute("SELECT id FROM laws WHERE law_name = %s AND law_type = %s", (law_name, law_type))
        law_id = cursor.fetchone()[0]

    conn.commit()

    return law_id

# article 테이블에 저장
def articles_table_save(law_id:int):
    with open(law,"r",encoding="utf-8") as f:
        law_data = json.load(f)

    inserted_count = 0

    for item in law_data:
        # article_no 가져오기
        try:
            article_no = item.get("조문내용",0)
            if re.search("제[0-9]장",article_no):
                continue
            article_no = article_no.split("(")[0]
        except:
            article_no = item.get("조문내용")

        # article_title 가져오기
        try:
            article_title = item.get("조문내용").split("(")[1].split(")")[0]
        except:
            article_title = None

        # effective_from
        effective_from = item.get("조문시행일자")

        # effective_to 
        effective_to = None

        # is_mandatory 
        is_mandatory = False
        if law_name == "주택임대차보호법" and law_type == "법률":
            if article_no != "제8조의2" and not re.search("제(?:1[4-9]|2[0-9])조", article_no):
                is_mandatory = True
        elif law_name == "주택임대차보호법" and law_type == "시행령":
            if article_no != "제10조":
                is_mandatory = True
        elif law_name == "민법":
            if article_no in ["제627조", "제628조", "제631조", "제635조", "제638조", "제640조", "제641조","제643조" ,"제644조","제645조","제646조","제647조"]:
                is_mandatory = True

        cursor.execute("""INSERT INTO articles (law_id, article_no, article_title, effective_from, effective_to, is_mandatory) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (law_id, article_no, effective_from) DO NOTHING RETURNING id;""", (law_id, article_no, article_title, effective_from, effective_to, is_mandatory))

        row = cursor.fetchone()
        if row:
            article_id = row[0]
        else:
            cursor.execute("""SELECT id FROM articles WHERE law_id = %s AND article_no = %s AND effective_from = %s""", (law_id, article_no, effective_from))
            article_id = cursor.fetchone()[0]
            cursor.execute("DELETE FROM article_chunks WHERE article_id = %s", (article_id,))

        
        # article_chunks 테이블 저장
        chunks_to_insert = []
        chunk_index = 0

        # 내용만 추출
        base_content = item.get("조문내용", "").strip()
        clean_base_content = re.sub(r'^제\d+(?:의\d+)?조\s*(?:\([^)]+\))?\s*', '', base_content).strip()
        base_chunk_text = f"{law_name} {article_no} {clean_base_content}".strip()

        real_hangs = []
        
        # 항 리스트 순회 (항내용이 없고 호만 이루어진 경우)
        for hang in item.get("항", []):
            hang_content = hang.get("항내용", "").strip()

            # 항내용이 없는경우/ 호,목 한꺼번에 붙임
            if not hang_content:
                for ho in hang.get("호", []):
                    base_chunk_text += f"\n  {ho.get('호내용', '').strip()}"
                    for mo in ho.get("목", []):
                        base_chunk_text += f"\n  {mo.get('목내용', '').strip()}"
            # 항내용이 있는경우
            else:
                real_hangs.append(hang)

        # 3. 항내용도 없고 호 내용도 없는경우
        if base_chunk_text != f"{law_name} {article_no}":
            chunks_to_insert.append((article_id, base_chunk_text, str(get_embedding(base_chunk_text)), chunk_index))
            chunk_index += 1

        # 4. 항에 항내용이 있는경우
        for index, hang in enumerate(real_hangs):
            hang_content = hang.get("항내용", "").strip()
            hang_no = f"제{index + 1}항"
            
            chunk_text = f"{law_name} {article_no} {hang_no} {hang_content}"
            
            for ho in hang.get("호", []):
                chunk_text += f"\n  {ho.get('호내용', '').strip()}"
                for mo in ho.get("목", []):
                    chunk_text += extract_clean_text(mo.get("목내용",""))
                    
            chunks_to_insert.append((article_id, chunk_text, str(get_embedding(chunk_text)), chunk_index))
            chunk_index += 1

        # 청크 일괄 삽입
        if chunks_to_insert:
            insert_query = """INSERT INTO article_chunks (article_id, content, embedding, chunk_index)VALUES %s"""
            execute_values(cursor, insert_query, chunks_to_insert)
        
        inserted_count += 1
        conn.commit()
        


law_id = laws_table_save()
articles_table_save(law_id)
print(law_id)
cursor.close()
conn.close()
