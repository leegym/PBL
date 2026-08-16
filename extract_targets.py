from langchain.messages import HumanMessage, SystemMessage, AIMessage
from pydantic import BaseModel
from llm import get_llm
import json
from pydantic import ValidationError
from enum import Enum

# category를 enum으로 만들기(이후 카테고리 세분화 필요)
class Category(str, Enum):
    보증금 = "보증금"
    계약기간 = "계약기간"
    차임 = "차임"
    관리비 = "관리비"
    수선의무 = "수선의무"
    원상복구 = "원상복구"
    계약해지 = "계약해지"
    특약 = "특약"

# Pydantic 모델 정의
class ExtractedTarget(BaseModel):
  category: Category
  clause_text: str
  summary_text: str

class ExtractResult(BaseModel):
  targets: list[ExtractedTarget]



llm = get_llm().with_structured_output(ExtractResult)
# with_structured_output(ExtractResult)은 LLM의 답변 형식을 ExtractResult라는 Pydantic 모델에 맞추도록 설정함

# JSON 파일 읽기
# with open("test.json", "r", encoding="utf-8") as f:
#     contract = json.load(f)

contract = """
  부동산임대차계약 서
전세
□월세
임대인과 임차인 쌍방은 아래 표시 부동산에 관하여 다음 계약내용과 같이 임대차계약을 체결한다.
1.부동산의 표시
소 재 지
토
지 지
목
면 적
m{²
건
물 구조·용도
면 적
m²
임대할부분
면적
m{}$
2.계약내용
제 1 조 (목적) 위 부동산의 임대차에 한하여 임대인과 임차인은 합의에 의하여 임차보증금 및 차임을 아래와 같이 지불하기로 한다.
보 증 금 금
원정(
)
계 약 금 금
원정은 계약시에 지불하고 영수함.영수자(
인)
중 도 금 금
원정은
년
월
일에 지불하며
잔
금 금
원정은
년
월
일에 지불한다.
차
임 금
원정은 (선불로·후불로) 매월
일에지불한다.
제 2조 (존속기간) 임대인은 위 부동산을 임대차 목적대로 사용·수익할 수 있는 상태로
년
월
일까지 임차인에게
인도하며,임대차 기간은 인도일로부터
년
월
일까지로 한다.
제 3조 (용도변경 및 전대 등) 임차인은 임대인의 동의없이 위 부동산의 용도나 구조를 변경하거나 전대·임차권 양도 또는담보제공을 하
지 못하며 임대차 목적 이외의 용도로 사용할 수 없다.
제 4조( (계약의 해지) 임차인이 제3조를 위반하였을 때 임대인은 즉시 본 계약을 해지 할 수 있다.
제 5조 (계약의 종료) 임대차계약이 종료된 경우에 임차인은 위 부동산을 원상으로 회복하여 임대인에게 반환한다.이러한경우 임대인은
보증금을 임차인에게 반환하고.연체 임대료 또는 손해배상금이 있을 때는 이들을 제하고 그 잔액을 반환한다.
"""

def extract_targets(contract: str) -> ExtractResult:
  # LLM이 지정된 타입과 다른 타입을 반환했을 때 다시 시도하는 횟수
  MAX_RETRY = 3

  system_prompt = """
  당신은 부동산 계약서 구조 분석 AI입니다.

  역할
  - 계약서를 읽고 법률 검토가 필요한 조항만 추출한다.
  - 위험 여부는 판단하지 않는다.
  - 법률적인 설명 하지 않는다.
  - clause_text는 OCR 결과를 기반으로 줄바꿈, 띄어쓰기, 문법 및 문장부호만 수정하여 계약서 원문의 표현을 최대한 유지한다.
  - summary_text는 원문의 의미를 유지하면서 조항의 핵심 내용을 한 문장으로 정리한다.
  OCR 오류(줄바꿈, 띄어쓰기, 문법, 문장부호)는 수정할 수 있으나,
  위험 여부나 법률적 판단을 추가해서는 안 된다.

  반드시 JSON만 출력한다.

  출력 형식

  {
    "targets": [
      {
        "category": "",
        "clause_text" : "",
        "summary_text": ""
      }
    ]
  }

  category 예시
  - 보증금
  - 계약기간
  - 차임
  - 관리비
  - 수선의무
  - 원상복구
  - 계약해지
  - 특약
  """


  user_prompt = f"""
  다음 계약서를 분석 대상으로 구조화하세요.

  # 파이썬 객체를 JSON 문자열로 변환(AI가 읽기 쉽게)
  {contract}
  """  
  
  # LLM이 Pydantic 구조를 제대로 맞추지 못하는 경우의 예외 처리
  for attempt in range(MAX_RETRY):
    try:
      result = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
      ])

    except ValidationError as e:
      print(f"{attempt + 1}번째 검증 실패")

      if attempt == MAX_RETRY - 1:
        raise e
      
    else:
      targets = []

      for i, target in enumerate(result.targets, start=1):
        targets.append({
          "target_id" : f"T{i:03d}",
          "category" : target.category,
          "clause_text" : target.clause_text,
          "summary_text" : target.summary_text
        })
      
      return targets


result = extract_targets(contract)

print(json.dumps(result, ensure_ascii=False, indent=4))