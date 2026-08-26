CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE users (
    id SERIAL PRIMARY KEY,

    email TEXT NOT NULL UNIQUE,

    password_hash TEXT, -- 소셜 로그인은 비밀번호를 저장하지 않음

    provider TEXT NOT NULL DEFAULT 'local'
        CHECK (
            provider IN ('local', 'naver', 'google', 'kakao')
        ),

    provider_user_id TEXT,

    CHECK (
        (provider = 'local'
            AND password_hash IS NOT NULL
            AND provider_user_id IS NULL)
        OR
        (provider <> 'local'
            AND password_hash IS NULL
            AND provider_user_id IS NOT NULL)
    ),
    -- (provider이 로컬이면 password_hash가 널이 아니고, provider_user_id가 널인지 체크) or (provider이 로컬이 아니면 password_hash가 널이고, provider_user_id가 널이 아닌지 체크)

    UNIQUE (provider, provider_user_id),

    created_at TIMESTAMP NOT NULL DEFAULT now(),

    updated_at TIMESTAMP NOT NULL DEFAULT now()
    -- 이후 데이터 수정 시 자동으로 현재 시간으로 변경하는 트리거 필요
);

CREATE TABLE contracts (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL
        REFERENCES users(id)
        ON DELETE CASCADE, -- 사용자 삭제 시 계약서도 같이 삭제
    file_name TEXT NOT NULL,
    raw_text TEXT, -- 원본 텍스트
    structured_text JSONB, -- 구조화된 텍스트
    starred BOOLEAN NOT NULL DEFAULT false, -- 즐겨찾기
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    created_at TIMESTAMP NOT NULL DEFAULT now()
);
-- 이후 파일 저장 위치에 따라 약간 수정(file_path 추가 등) 필요

CREATE TABLE findings (
    id SERIAL PRIMARY KEY,
    contract_id INT NOT NULL
        REFERENCES contracts(id)
        ON DELETE CASCADE,
    level TEXT NOT NULL
        CHECK (level IN ('risk', 'warning', 'info', 'ok')),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
   	
    target_category TEXT NOT NULL,
    target_clause TEXT NOT NULL,
    target_summary TEXT,
    
    evidence JSONB NOT NULL, -- 계약서의 분석 대상 + 법령 근거 저장
    -- 빈 JSON이 들어오는 것을 막는 로직 필요
    order_no INT NOT NULL,
    UNIQUE (contract_id, order_no)
);

CREATE TABLE messages (
	  id SERIAL PRIMARY KEY,
	  contract_id INT NOT NULL
			  REFERENCES contracts(id)
			  ON DELETE CASCADE,
	  role TEXT NOT NULL CHECK (role IN ('user', 'ai')),
	  content TEXT NOT NULL,
	  created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE contract_chunks (
    id SERIAL PRIMARY KEY,

    contract_id INT NOT NULL
        REFERENCES contracts(id)
        ON DELETE CASCADE,

    content TEXT NOT NULL,

    embedding vector(1024) NOT NULL,
    -- 임베딩 모델에 따라 차원 변경 필요

    chunk_index INT NOT NULL,
    
    page_no INT NOT NULL,

    created_at TIMESTAMP NOT NULL DEFAULT now(),

    UNIQUE (contract_id, chunk_index)
);

CREATE TABLE laws (
    id SERIAL PRIMARY KEY,

    law_name TEXT NOT NULL,
    law_type TEXT NOT NULL,
    article_no TEXT NOT NULL,
    article_title TEXT,
    
    effective_from DATE NOT NULL,
    effective_to DATE,

    created_at TIMESTAMP NOT NULL DEFAULT now(),

    UNIQUE (law_name, law_type, article_no)
);

CREATE TABLE law_chunks (
    id SERIAL PRIMARY KEY,

    law_id INT NOT NULL
        REFERENCES laws(id)
        ON DELETE CASCADE,

    content TEXT NOT NULL,

    embedding vector(1536) NOT NULL,

    chunk_index INT NOT NULL,

    created_at TIMESTAMP NOT NULL DEFAULT now(),

    UNIQUE (law_id, chunk_index)
);

CREATE TABLE knowledge_documents (
    id SERIAL PRIMARY KEY,

    title TEXT NOT NULL,

    document_type TEXT NOT NULL
        CHECK (
            document_type IN (
                'guide',
                'checklist',
                'qna',
                'case'
            )
        ),

    source TEXT NOT NULL,

    description TEXT,

    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE knowledge_chunks (
    id SERIAL PRIMARY KEY,

    document_id INT NOT NULL
        REFERENCES knowledge_documents(id)
        ON DELETE CASCADE,

    content TEXT NOT NULL,

    embedding vector(1536) NOT NULL,

    chunk_index INT NOT NULL,

    page_no INT,

    created_at TIMESTAMP NOT NULL DEFAULT now(),

    UNIQUE (document_id, chunk_index)
);