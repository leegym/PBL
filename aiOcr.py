# pip install requests

import requests
import os

api_key = "up_opdQOwaudjgnGaO5D2Q34xknTHcBe" # ex: up_xxxYYYzzzAAAbbbCCC

def ocr(file_path):
    url = "https://api.upstage.ai/v1/document-digitization"
    headers = {"Authorization": f"Bearer {api_key}"}

    files = {"document": open(file_path, "rb")}
    data = {"model": "ocr"}
    response = requests.post(url, headers=headers, files=files, data=data)

    return(response.json())

def paser(file_path):
    url = "https://api.upstage.ai/v1/document-digitization"
    headers = {"Authorization": f"Bearer {api_key}"}
    files = {"document": open(file_path, "rb")}
    data = {
        "model": "document-parse-260128",
        "ocr": "auto",
        "chart_recognition": True,
        "coordinates": True,
        "output_formats": '["markdown"]',
        "base64_encoding": '["figure"]',
    }

    response = requests.post(url, headers=headers, files=files, data=data)
    
    return(response.json())


file_path = input("주소를 입력하세요")
clean_file_path = file_path.strip(" '\"")
extenstion = os.path.splitext(clean_file_path)
print(clean_file_path, extenstion)

image = ['.png', '.jpg', '.jpeg']

if extenstion[1].lower() in image:
    print("해당 파일은 이미지 파일입니다.\n ocr을 진행하겠습니다")
    #result = ocr(clean_file_path)
    print(ocr(clean_file_path))
elif extenstion[1].lower() == '.pdf':
    print("해당 파일은 pdf 입니다.\n pasing을 진행하겠습니다")
    #result = paser(clean_file_path)
    print(paser(clean_file_path))
else:
    print("지원하지 않는 파일 형식입니다.")
    #result = "없음"







