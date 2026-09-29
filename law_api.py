import requests
import json
import re
from bs4 import BeautifulSoup
from typing import List
import time

start_time = time.time()

# 1. API 파라미터 설정
api_oc = "PBL0306"  # 발급받은 OC 입력
service_url = "http://www.law.go.kr/DRF/lawService.do"
search_url = "http://www.law.go.kr/DRF/lawSearch.do"

# 법령명
title = "공인중개사법"

# 본문 파라미터
params = {
    "OC": api_oc,
    "target": "eflaw",  
    "type": "JSON",
    "LM": title,  
    "NW": "2",
}


# 개정,신설,삭제부분의 년도를 찾는 정규표현식
regex = r"<개정 \d{4}\.\d{1,2}\.\d{1,2}|<신설 \d{4}\.\d{1,2}\.\d{1,2}|삭제\s*<\d{4}\.\d{1,2}\.\d{1,2}"
year = r"\d{4}\.\d{1,2}\.\d{1,2}"
except_year = r"^\[시행일: \d{4}\. \d{1,2}\. \d{1,2}\.\]$"

# 처음 시행된 날짜 구하는 함수
# HTML 웹 크롤러로 필요한 데이터 추출
def find_default_year(title : str) -> str:
    default_year_params = {
        "OC": api_oc,
        "target": "lsHistory",  # 현행법령 본문
        "type": "HTML",
        "query" : title, # 법령명
        "sort" : "dasc"
    }

    response = requests.get(search_url,params=default_year_params)

    html = response.text
    soup = BeautifulSoup(html,"html.parser")

    post = soup.select_one("body > form > div > table > tbody > tr:nth-child(1) > td:nth-child(8)")
    result_default_year = re.findall(re.compile(year),str(post))

    result_default_year = result_default_year[0]
    parts = result_default_year.split(".")
    format_date = f"{parts[0]}{int(parts[1]):02d}{int(parts[2]):02d}"

    return format_date

default_year = find_default_year(title)
print(default_year)

# 본문에 있는 개정,신설,삭제의 년도를 보고 해당 법령의 시행일자를 찾는 함수
def find_year(real_year : List[str]) -> str:
    raw_date = real_year[-1]
    parts = raw_date.split(".")
    format_date = f"{parts[0]}{int(parts[1]):02d}{int(parts[2]):02d}"

    # 공포일자를 기준으로 법령의 시행일자를 찾는 파라미터
    sub_param = {
        "OC": api_oc,
        "target": "law", 
        "type": "JSON",
        "LM": title,  # 법령명
        "LD" : format_date
    }

    try:
        sub_respone = requests.get(service_url,params=sub_param)
        sub_data = sub_respone.json()
        sub_date = sub_data["법령"]["기본정보"]["시행일자"]
        return sub_date
    
    except:
        return format_date



# 2. API 호출
response = requests.get(service_url, params=params)

data = response.json()

revised_date = data["법령"]["기본정보"]["공포일자"]
original_data = data["법령"]["조문"]["조문단위"]

result = []

for item in original_data:
    it = {
        "조문번호": item.get("조문번호", 0),
        "조문시행일자": item.get("조문시행일자", 0),
        "조문변경여부": item.get("조문변경여부", 0),
        "조문내용": item.get("조문내용", 0)
    }

    if "삭제" in item["조문내용"]:
        continue

    if (item.get("조문변경여부") == "N" and not re.search(regex,item["조문내용"]) and item.get("조문참고자료")):
        real_year = re.findall(re.compile(year),item.get("조문참고자료"))
        if real_year:
            it["조문시행일자"] = find_year(real_year)

    elif item.get("조문변경여부") == "Y" and not re.search(regex,item["조문내용"]) and item.get("조문참고자료"):
        real_year = re.findall(re.compile(year),item.get("조문참고자료"))
        if real_year:
            it["조문시행일자"] = find_year(real_year)

    elif re.search(regex,item["조문내용"]):
        real_year = re.findall(re.compile(year),item.get("조문내용"))
        if real_year:
            it["조문시행일자"] = find_year(real_year)

    else:
        it["조문시행일자"] = default_year

    if "조문참고자료" in item:
        it["조문참고자료"] = item.get("조문참고자료")

    if "항" in item:
        hang_list = item["항"]

        if isinstance(hang_list, dict):
            hang_list = [hang_list]

        it["항"] = hang_list

        for hang in it["항"]:
            real_year = []
            hang_content = hang.get("항내용",it["조문내용"])

            if not re.search(regex,hang_content) and "조문참고자료" in item:
                real_year = re.findall(re.compile(year),item.get("조문참고자료"))
            else:
                real_year = re.findall(re.compile(year),hang_content)

            real = find_year(real_year) if real_year else default_year
            hang["년도"] = real

            if "호" in hang:
                ho_list = hang["호"]
                if isinstance(ho_list, dict):
                    ho_list = [ho_list]
                    hang["호"] = ho_list

                for ho in ho_list:
                    ho_content = ho.get("호내용","")
                    mo_list = ho.get("목","")

                    for mo in mo_list:
                        mo_content = mo.get("목내용","")

                        if isinstance(mo_content,list):
                            re_mo_list = []
                            for content in mo_content:
                                if isinstance(content,list):
                                    re_mo_list.extend(content)
                                else:
                                    re_mo_list.append(str(item))
                            mo_content = " ".join(re_mo_list)
                        else:
                            mo_content = str(content)

                        mo_year = re.findall(re.compile(year),mo_content)
                        if mo_year and re.search(regex,mo_content):
                            mo["년도"] = find_year(mo_year)
                        else:
                            mo["년도"] = real
    
                    ho_year = re.findall(re.compile(year),ho_content)
                    if ho_year and re.search(regex,ho_content):
                        ho["년도"] = find_year(ho_year)
                    else:
                        ho["년도"] = real

    result.append(it)

end_time = time.time()

with open("result.js","w",encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"총 소요시간 {end_time - start_time}")
    
