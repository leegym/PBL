from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
import os

# .env 로드
load_dotenv()

# 환경변수
MODEL_NAME = os.getenv("MODEL_NAME")
TEMPERATURE = float(os.getenv("TEMPERATURE", 0))

# LLM 객체 생성 (프로그램 실행 시 한 번만 생성)
_llm = init_chat_model(
    MODEL_NAME,
    temperature=TEMPERATURE,
)

def get_llm():
    """
    생성된 LLM 객체를 반환한다.
    """
    return _llm