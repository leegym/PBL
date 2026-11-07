-- 벡터 검색 확장
CREATE EXTENSION IF NOT EXISTS vector;


-- 회원
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT,
    provider TEXT NOT NULL DEFAULT 'local'
        CHECK (provider IN ('local', 'naver', 'google', 'kakao')),
    provider_user_id TEXT,
    nickname TEXT UNIQUE,
    campus TEXT
        CHECK (campus IN ('gajwa', 'chilam')),
    scrap_post_ids INT[] NOT NULL DEFAULT '{}',
    liked_post_ids INT[] NOT NULL DEFAULT '{}',
    liked_review_ids INT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (
        (provider = 'local' AND password_hash IS NOT NULL AND provider_user_id IS NULL)
        OR
        (provider <> 'local' AND password_hash IS NULL AND provider_user_id IS NOT NULL)
    ),
    UNIQUE (provider, provider_user_id)
);

-- 수정 시 updated_at을 현재 시각으로 바꾸는 함수
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

-- users가 수정될 때마다 위 함수를 실행하는 트리거
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- 앱 푸시 토큰
CREATE TABLE push_tokens (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL
        REFERENCES users(id) ON DELETE CASCADE,
    token TEXT NOT NULL UNIQUE,
    platform TEXT NOT NULL
        CHECK (platform IN ('android', 'ios')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_push_tokens_user ON push_tokens (user_id);


-- 매물
CREATE TABLE listings (
    id SERIAL PRIMARY KEY,
    campus TEXT NOT NULL
        CHECK (campus IN ('gajwa', 'chilam')),
    dong TEXT NOT NULL,
    address TEXT NOT NULL,
    building_name TEXT,
    building_key TEXT NOT NULL,
    room_type TEXT NOT NULL
        CHECK (room_type IN ('one_room', 'two_room', 'officetel', 'etc')),
    area_m2 NUMERIC(6,2),
    floor INT,
    deposit INT NOT NULL CHECK (deposit >= 0),
    monthly_rent INT NOT NULL CHECK (monthly_rent > 0),
    maintenance_fee INT NOT NULL DEFAULT 0 CHECK (maintenance_fee >= 0),
    options TEXT,
    image_path TEXT,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_listings_campus ON listings (campus);
CREATE INDEX idx_listings_building ON listings (building_key);


-- 시세 원천 데이터
CREATE TABLE rent_prices (
    id SERIAL PRIMARY KEY,
    dong TEXT NOT NULL,
    housing_type TEXT NOT NULL
        CHECK (housing_type IN ('detached_multi', 'row_multi', 'officetel')),
    contract_date DATE NOT NULL,
    deposit INT NOT NULL CHECK (deposit >= 0),
    monthly_rent INT NOT NULL CHECK (monthly_rent >= 0),
    area_m2 NUMERIC(6,2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_rent_prices_dong_date ON rent_prices (dong, contract_date);


-- 법령
CREATE TABLE laws (
    id SERIAL PRIMARY KEY,
    law_name TEXT NOT NULL,
    law_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (law_name, law_type)
);


-- 조문
CREATE TABLE articles (
    id SERIAL PRIMARY KEY,
    law_id INT NOT NULL
        REFERENCES laws(id) ON DELETE CASCADE,
    article_no TEXT NOT NULL,
    article_title TEXT,
    effective_from DATE NOT NULL,
    effective_to DATE,
    is_mandatory BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (effective_to IS NULL OR effective_to >= effective_from),
    UNIQUE (law_id, article_no, effective_from)
);


-- 조문 조각
CREATE TABLE article_chunks (
    id SERIAL PRIMARY KEY,
    article_id INT NOT NULL
        REFERENCES articles(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector(1024) NOT NULL,
    chunk_index INT NOT NULL CHECK (chunk_index >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (article_id, chunk_index)
);


-- 판례·해설 카드
CREATE TABLE case_cards (
    id SERIAL PRIMARY KEY,
    card_type TEXT NOT NULL
        CHECK (card_type IN ('precedent', 'guide')),
    title TEXT NOT NULL,
    original_text TEXT NOT NULL,
    summary TEXT NOT NULL,
    outcome TEXT
        CHECK (outcome IN ('valid', 'invalid', 'partial')),
    category_major TEXT
        CHECK (category_major IN ('A', 'B', 'C', 'D', 'E', 'F')),
    related_article TEXT,
    case_no TEXT,
    decided_at DATE,
    as_of DATE,
    source TEXT NOT NULL,
    source_url TEXT,
    embedding vector(1024) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (card_type <> 'precedent' OR (case_no IS NOT NULL AND decided_at IS NOT NULL)),
    CHECK (card_type <> 'guide' OR as_of IS NOT NULL)
);


-- 계약서
CREATE TABLE contracts (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL
        REFERENCES users(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    raw_text TEXT,
    structured_text JSONB,
    contract_date DATE,
    monthly_rent INT CHECK (monthly_rent >= 0),
    deposit INT CHECK (deposit >= 0),
    maintenance_fee INT CHECK (maintenance_fee >= 0),
    lease_start DATE,
    lease_end DATE,
    landlord_name TEXT,
    overall_level TEXT
        CHECK (overall_level IN ('risk', 'caution', 'normal')),
    starred BOOLEAN NOT NULL DEFAULT false,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'waiting_input', 'completed', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (lease_start IS NULL OR lease_end IS NULL OR lease_end > lease_start)
);
CREATE INDEX idx_contracts_user ON contracts (user_id);


-- 계약서 조각
CREATE TABLE contract_chunks (
    id SERIAL PRIMARY KEY,
    contract_id INT NOT NULL
        REFERENCES contracts(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector(1024) NOT NULL,
    chunk_index INT NOT NULL CHECK (chunk_index >= 0),
    page_no INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (contract_id, chunk_index)
);


-- 계약서 특약 분석 결과
CREATE TABLE contract_findings (
    id SERIAL PRIMARY KEY,
    contract_id INT NOT NULL
        REFERENCES contracts(id) ON DELETE CASCADE,
    clause_no INT NOT NULL CHECK (clause_no > 0),
    unit_index INT NOT NULL CHECK (unit_index > 0),
    category_major TEXT NOT NULL
        CHECK (category_major IN ('A', 'B', 'C', 'D', 'E', 'F')),
    category_minor TEXT NOT NULL DEFAULT '기타',
    level TEXT NOT NULL
        CHECK (level IN ('risk', 'caution', 'normal')),
    decided_by TEXT NOT NULL
        CHECK (decided_by IN ('rule', 'catch_all', 'law_check', 'llm_adjust')),
    rule_id TEXT,
    review_priority BOOLEAN NOT NULL DEFAULT false,
    precedent_dispute BOOLEAN NOT NULL DEFAULT false,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    fix_suggestion TEXT,
    target_clause TEXT NOT NULL,
    target_summary TEXT,
    evidence JSONB,
    case_refs JSONB,
    order_no INT NOT NULL,
    extracted JSONB,
    judgment_log JSONB,
    CHECK ((decided_by IN ('rule', 'catch_all')) = (rule_id IS NOT NULL)),
    CHECK (decided_by <> 'catch_all' OR level = 'normal'),
    CHECK (decided_by <> 'law_check' OR level = 'risk'),
    CHECK (level = 'caution' OR (NOT review_priority AND NOT precedent_dispute)),
    CHECK (decided_by NOT IN ('rule', 'law_check') OR evidence IS NOT NULL),
    CHECK (evidence IS NULL OR evidence NOT IN ('{}'::jsonb, '[]'::jsonb)),
    CHECK (precedent_dispute = (case_refs IS NOT NULL)),
    CHECK (case_refs IS NULL OR case_refs NOT IN ('{}'::jsonb, '[]'::jsonb)),
    UNIQUE (contract_id, clause_no, unit_index),
    UNIQUE (contract_id, order_no)
);


-- 등기부등본
CREATE TABLE registries (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL
        REFERENCES users(id) ON DELETE CASCADE,
    contract_id INT
        REFERENCES contracts(id) ON DELETE SET NULL,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    raw_text TEXT,
    structured_text JSONB,
    property_address TEXT,
    issued_at DATE,
    owner_name TEXT,
    mortgage_total BIGINT CHECK (mortgage_total >= 0),
    has_seizure BOOLEAN,
    has_trust BOOLEAN,
    overall_level TEXT
        CHECK (overall_level IN ('risk', 'caution', 'normal')),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_registries_user ON registries (user_id);


-- 등기부 분석 결과
CREATE TABLE registry_findings (
    id SERIAL PRIMARY KEY,
    registry_id INT NOT NULL
        REFERENCES registries(id) ON DELETE CASCADE,
    item_type TEXT NOT NULL
        CHECK (item_type IN ('owner', 'address', 'mortgage', 'seizure', 'trust', 'issued_date', 'etc')),
    level TEXT NOT NULL
        CHECK (level IN ('risk', 'caution', 'normal')),
    rule_id TEXT,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    target_clause TEXT NOT NULL,
    evidence JSONB,
    order_no INT NOT NULL,
    CHECK (evidence IS NULL OR evidence NOT IN ('{}'::jsonb, '[]'::jsonb)),
    UNIQUE (registry_id, order_no)
);


-- 계약서 기반 AI 채팅
CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    contract_id INT NOT NULL
        REFERENCES contracts(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'ai')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_messages_contract ON messages (contract_id, created_at);


-- 자주 묻는 질문
CREATE TABLE faqs (
    id SERIAL PRIMARY KEY,
    category TEXT NOT NULL
        CHECK (category IN ('contract', 'registry', 'living', 'app')),
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    sort_order INT NOT NULL DEFAULT 0
);


-- 내 집
CREATE TABLE residences (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL
        REFERENCES users(id) ON DELETE CASCADE,
    contract_id INT
        REFERENCES contracts(id) ON DELETE SET NULL,
    address TEXT NOT NULL,
    dong TEXT NOT NULL,
    campus TEXT
        CHECK (campus IN ('gajwa', 'chilam')),
    room_type TEXT
        CHECK (room_type IN ('one_room', 'two_room', 'officetel', 'etc')),
    area_m2 NUMERIC(6,2),
    deposit INT NOT NULL DEFAULT 0 CHECK (deposit >= 0),
    monthly_rent INT NOT NULL CHECK (monthly_rent >= 0),
    maintenance_fee INT NOT NULL DEFAULT 0 CHECK (maintenance_fee >= 0),
    rent_pay_day INT CHECK (rent_pay_day BETWEEN 1 AND 31),
    lease_start DATE NOT NULL,
    lease_end DATE NOT NULL,
    move_in_date DATE,
    move_in_reported BOOLEAN NOT NULL DEFAULT false,
    is_current BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (lease_end > lease_start)
);
CREATE INDEX idx_residences_user ON residences (user_id);


-- 입주 사진
CREATE TABLE photos (
    id SERIAL PRIMARY KEY,
    residence_id INT NOT NULL
        REFERENCES residences(id) ON DELETE CASCADE,
    photo_type TEXT NOT NULL
        CHECK (photo_type IN ('defect', 'electric', 'water', 'gas')),
    meter_value NUMERIC(10,2),
    memo TEXT,
    file_path TEXT NOT NULL,
    taken_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (photo_type <> 'defect' OR meter_value IS NULL)
);
CREATE INDEX idx_photos_residence ON photos (residence_id);


-- 지출
CREATE TABLE expenses (
    id SERIAL PRIMARY KEY,
    residence_id INT NOT NULL
        REFERENCES residences(id) ON DELETE CASCADE,
    category TEXT NOT NULL
        CHECK (category IN ('rent', 'maintenance', 'electric', 'water', 'gas', 'internet', 'etc')),
    bill_month DATE NOT NULL
        CHECK (EXTRACT(DAY FROM bill_month) = 1),
    amount INT NOT NULL CHECK (amount >= 0),
    due_date DATE,
    paid_at DATE,
    memo TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_expenses_month ON expenses (residence_id, bill_month);


-- 분리수거 일정
CREATE TABLE recycle_schedules (
    id SERIAL PRIMARY KEY,
    dong TEXT NOT NULL,
    waste_type TEXT NOT NULL,
    days TEXT NOT NULL,
    time_range TEXT,
    how_to TEXT,
    UNIQUE (dong, waste_type)
);


-- 루틴
CREATE TABLE todos (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL
        REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    repeat_type TEXT NOT NULL DEFAULT 'none'
        CHECK (repeat_type IN ('none', 'daily', 'weekly', 'monthly')),
    repeat_days TEXT,
    remind_time TIME,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (repeat_type NOT IN ('weekly', 'monthly') OR repeat_days IS NOT NULL)
);
CREATE INDEX idx_todos_user ON todos (user_id);


-- 루틴 완료 기록
CREATE TABLE todo_logs (
    id SERIAL PRIMARY KEY,
    todo_id INT NOT NULL
        REFERENCES todos(id) ON DELETE CASCADE,
    done_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (todo_id, done_date)
);


-- 캘린더 일정 및 알림
CREATE TABLE schedules (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL
        REFERENCES users(id) ON DELETE CASCADE,
    type TEXT NOT NULL DEFAULT 'etc'
        CHECK (type IN ('rent', 'recycle', 'move_in_report', 'utility', 'etc')),
    title TEXT NOT NULL,
    memo TEXT,
    schedule_date DATE NOT NULL,
    remind_at TIMESTAMPTZ,
    is_sent BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_schedules_user_date ON schedules (user_id, schedule_date);
CREATE INDEX idx_schedules_to_send ON schedules (remind_at) WHERE is_sent = false;


-- 게시글
CREATE TABLE posts (
    id SERIAL PRIMARY KEY,
    user_id INT
        REFERENCES users(id) ON DELETE SET NULL,
    campus TEXT
        CHECK (campus IN ('gajwa', 'chilam')),
    post_type TEXT NOT NULL DEFAULT 'free'
        CHECK (post_type IN ('free', 'question')),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    image_path TEXT,
    is_anonymous BOOLEAN NOT NULL DEFAULT false,
    like_count INT NOT NULL DEFAULT 0 CHECK (like_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_posts_board ON posts (campus, created_at DESC);


-- 댓글
CREATE TABLE comments (
    id SERIAL PRIMARY KEY,
    post_id INT NOT NULL
        REFERENCES posts(id) ON DELETE CASCADE,
    parent_id INT,
    user_id INT
        REFERENCES users(id) ON DELETE SET NULL,
    content TEXT NOT NULL,
    is_anonymous BOOLEAN NOT NULL DEFAULT false,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (post_id, id),
    FOREIGN KEY (post_id, parent_id)
        REFERENCES comments (post_id, id) ON DELETE CASCADE
);
CREATE INDEX idx_comments_post ON comments (post_id, created_at);


-- 리뷰
CREATE TABLE reviews (
    id SERIAL PRIMARY KEY,
    building_key TEXT NOT NULL,
    building_name TEXT,
    building_address TEXT NOT NULL,
    user_id INT
        REFERENCES users(id) ON DELETE SET NULL,
    rating INT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    content TEXT NOT NULL,
    like_count INT NOT NULL DEFAULT 0 CHECK (like_count >= 0),
    image_path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_reviews_building ON reviews (building_key);
