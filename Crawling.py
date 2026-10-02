from playwright.sync_api import sync_playwright
import time
import random
import pandas as pd

start_time = time.time()

# 검색하고자하는 위치를 영어로
# 파일명을 저장하기위해 사용
place = "Chiramdong" 

# 크롤링할 네이버 부동산 주소 입력
search_url = "https://new.land.naver.com/rooms?ms=2za1Im,3A2lgx,16&a=APT:OPST:ABYG:OBYG:GM:OR:DDDGG:JWJT:SGJT:VL&e=RETAIL&aa=SMALLSPCRENT"


# 크롤링해서 추출할 데이터 정의
security_deposit = None # 보증금
Monthly_rent = None  # 월세
where = None # 소재지
feature = None # 매물 특징
space = None # 공급/전용면적
floor = None # 해당층/총층
room_bathroom = None # 방수/욕실수
maintenance_cost = None # 관리비
maintenance_cost_criteria = None # 관리비부과기준
move_possible = None # 입주가능일
approval_use_date = None # 사용승인일
direction = None # 방향
parking_availability = None # 주차가능여부
room_layout = None # 방구조
duplex_status = None # 복층여부
building_use = None # 건축물 용도
listing_ID = None # 매물번호
total_parking_spaces = None # 총주차대수
image_urls = None # 이미지 url
real_estate_agency = None # 공인중개사무소


def run(playwright):
    # 우회, 자동태그 비활성화
    args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
    ]

    browser = playwright.chromium.launch(headless=False, args=args)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 900}
    )

    page = context.new_page()

    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        })
    """)

    target_url = search_url

    print("네이버 부동산 우회 접속 중")
    page.goto(target_url)

    # 처음 화면에 뜨는 다시 보지 않기 팝업 제거
    try:
        popup_btn = page.wait_for_selector("text='다시 보지 않기'", timeout=3000)
        if popup_btn:
            popup_btn.click()
            time.sleep(random.uniform(1.5, 1.8))
    except:
        page.keyboard.press("Escape")
        time.sleep(random.uniform(1.5, 1.8))

    # 크롤링 시작
    try:
        page.wait_for_selector(".item_inner", timeout=15000) 
        time.sleep(random.uniform(1.5, 1.8))

        # 크롤링 결과 데이터 저장할 리스트
        all_content = []
        processed_count = 0 

        for i in range(1): # test용
        # while True:
            items = page.locator(".item_inner")
            current_count = items.count()

            for i in range(processed_count, current_count):
                if i != 168:
                    pass

                item = items.nth(i)
                item.scroll_into_view_if_needed()
                item_text = item.inner_text()

                # 조건에 맞는 경우에만 클릭 및 데이터 수집
                if "원룸" in item_text and "아파트" not in item_text and "오피스텔" not in item_text and "네이버에서 보기" not in item_text:

                    # 상세정보를 보기위해 매물 클릭
                    try:
                        item.locator(".item_link").evaluate("el => el.click()")
                        time.sleep(random.uniform(1.5, 1.8))
                    except:
                        print(f"{i} 클릭 시 오류발생")
                        
                    try:
                        # 추출 시작
                        panel = page.locator("div.detail_panel").first  # detial_panel 크롤링
                        security_deposit,Monthly_rent = page.locator("div.info_article_price").first.locator("span.price").inner_text().split("/",1) # 보증금 월세
                        where = panel.locator("th:has-text('소재지') + td").inner_text() # 소재지
                        feature = panel.locator("th:has-text('매물특징') + td").inner_text() # 매물특징
                        space = panel.locator("th:has-text('공급/전용면적') + td").inner_text() # 공급/전용면적
                        floor = panel.locator("th:has-text('해당층/총층') + td").inner_text() # 해당층/총층
                        room_bathroom = panel.locator("th:has-text('방수/욕실수') + td").inner_text() # 방수/욕실수
                        maintenance_cost = panel.locator("th:has-text('관리비') + td > div").inner_text().split()[0] # 관리비

                        # 관리비부과기준
                        criteria = panel.locator("th:has-text('관리비부과기준') + td")
                        if criteria.count() > 0: # 예외 처리
                            maintenance_cost_criteria = criteria.inner_text()
                        else:
                            maintenance_cost_criteria = "정액관리비"

                        move_possible = panel.locator("th:has-text('입주가능일') + td").inner_text() # 입주가능일
                        approval_use_date = panel.locator("th:has-text('사용승인일') + td, th:has-text('사용검사일') + td").inner_text() # 사용승인일
                        direction = panel.locator("th:has-text('방향') + td").inner_text() # 방향
                        parking_availability = panel.locator("th:has-text('주차가능여부') + td").inner_text() # 주차가능여부

                        # # 방구조 없는 경우가 있음
                        room_check = panel.locator("th:has-text('방구조') + td")
                        if room_check.count() > 0:
                            room_layout = room_check.inner_text() # 방구조
                        else:
                            room_check = ""

                        duplex_status = panel.locator("th:has-text('복층여부') + td").inner_text() # 복층여부
                        building_use = panel.locator("th:has-text('건축물 용도') + td").inner_text() # 건출물 용도
                        listing_ID = panel.locator("th:has-text('매물번호') + td").inner_text() # 매물번호
                        total_parking_spaces = panel.locator("th:has-text('총주차대수') + td").inner_text() # 총주차대수

                        # 이미지처리
                        image_url_list = panel.locator(".main_photo_wrap > button").all()# 이미지
                        img_list = []
                        for image in image_url_list:
                            img_url = image.get_attribute("style").split("url(")[1].split(")")[0]
                            img_list.append(img_url)
                        image_urls = ", ".join(img_list)

                        real_estate_agency = panel.locator("strong.info_title").inner_text() # 공인중개사무소 

                        all_content.append({
                            "소재지": where,
                            "공급/전용면적": space,
                            "보증금" : security_deposit,
                            "월세" : Monthly_rent,
                            "매물특징" : feature,
                            "해당층/총층" : floor,
                            "방수/욕실수" : room_bathroom,
                            "관리비" : maintenance_cost,
                            "관리비부과기준" : maintenance_cost_criteria,
                            "입주가능일" : move_possible,
                            "사용승인일" : approval_use_date,
                            "방향" : direction,
                            "주차가능여부" : parking_availability,
                            "방구조" : room_layout,
                            "복층여부" : duplex_status,
                            "건축물 용도" : building_use,
                            "매물번호" : listing_ID,
                            "총주차대수" : total_parking_spaces,
                            "공인중개사무소" : real_estate_agency,
                            "이미지" : image_urls
                        })
                        print(f"수집 완료: {i}")
                        
                    except:
                        print(f"[{i}] 상세 정보 추출 오류")

            # 다음 스크롤할 수 있게 현재 마지막 스크롤 번호를 processed_count에 대입
            processed_count = current_count
            
            # 스크롤 내려서 다음 매물 로딩
            items.nth(current_count - 1).hover()
            page.mouse.wheel(0, 1500)
            
            time.sleep(random.uniform(1.5, 1.8))

            # 현재 count와 총 count가 같으면 break -> 모든 매물을 크롤링했다는 의미
            new_count = page.locator(".item_inner").count()
            if new_count == current_count:
                break
            
    except Exception as e:
        print(f"오류 발생: {e}")
        
    finally:
        time.sleep(random.uniform(1.5, 1.8))
        browser.close()

    return all_content

if __name__ == "__main__":
    with sync_playwright() as p:
        result = run(p)

        df = pd.DataFrame(data=result)
        df.to_csv(f"{place}_result.csv", index=False, encoding="utf-8-sig")
        print(f"저장 완료 ({place}_result.csv)")

        end_time = time.time()
        print(f"총 소요 시간: {end_time - start_time:.2f}초")
