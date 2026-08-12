import os
import glob
import pymupdf
import numpy as np
from paddleocr import PaddleOCR


# PaddleOCR 초기화
Parser_ocr = PaddleOCR(
    use_textline_orientation=True,
    lang="korean",
    device="cpu",
    enable_mkldnn=False
)


def pdf_text(pdf_path):
    Result = []  # 순서대로 정렬된 전체 텍스트 저장

    try:
        document = pymupdf.open(pdf_path)

        for page in document:
            page_text = page.get_text()

            # A. 텍스트 PDF: PyMuPDF 표(Table) 파서 사용
            if page_text.strip():
                tabs = page.find_tables()
                if tabs.tables:
                    for table in tabs.tables:
                        for row in table.extract():
                            for cell in row:
                                if cell and cell.strip():
                                    Result.append(cell.strip().replace('\n', ' ')) # 각 셀단위로 수집
                else:
                    Result.extend([line.strip() for line in page_text.splitlines() if line.strip()]) # 줄바꿈을 기준으로 분할

            # B. 스캔본/이미지 PDF: PaddleOCR 사용
            image_list = page.get_images(full=True)
            if not page_text.strip() or image_list: # 스캔본이거나 이미지일때
                pix = page.get_pixmap(dpi=300) # DPi 200의 고해상도로 랜더링
                # pix는 현재 1차원 배열
                # PaddleOCR은 3차원 배열을 input으로 받음
                # pix를 frombuffer을 통해 3차원 배열로 전환하는 과정
                # frombuffer는 바이트 데이터를 3차원 넘파이 이미지 배열로 바꿈
                # 높이 x 너비 x 3(채널)
                img_np = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, 3))
                img_np = img_np[:, :, ::-1] # RGB인데 PaddleOCR은 BGR순으로 읽음
                
                # 변환된 이미지를 ocr에 넣어 텍스트 인식 후 정상적으로 들어왔는지 확인
                Result_ocr = Parser_ocr.predict(img_np)
                if Result_ocr and len(Result_ocr) > 0:
                    Result_dict = Result_ocr[0]  # 딕셔너리 객체
                    texts = Result_dict.get("rec_texts", [])  # 인식한 텍스트 딕셔너리
                    polys = Result_dict.get("rec_polys", Result_dict.get("rec_boxes", [])) # 인식한 텍스트의 위치 딕셔너리

                    lines = []
                    for text, poly in zip(texts, polys):
                        String_text = str(text).strip()
                        if String_text:
                            # poly의 첫 번째 점 (x, y) 좌표 추출
                            x = poly[0][0]
                            y = poly[0][1]
                            lines.append((y, x, String_text))

                    # Y축, X축 정렬
                    lines.sort(key=lambda item: (round(item[0] / 15), item[1]))

                    for _, _, text in lines:
                        Result.append(text)

        document.close()

    except Exception as e:
        print(f"{pdf_path} 처리 중 오류 발생: {e}")

    # 리스트에 모인 모든 토큰을 줄바꿈으로 연결하여 하나의 텍스트로 만듦
    return "\n".join(Result)


# --- 실행부 ---
pdf_files = glob.glob("*.pdf")

for file_path in pdf_files:
    file_name = os.path.basename(file_path)
    print("\n" + "="*50)
    print(f"파일명: {file_name}")
    print("="*50)
    
    full_text = pdf_text(file_path)
    print(full_text)