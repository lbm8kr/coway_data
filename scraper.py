import firebase_admin
from firebase_admin import credentials, firestore
from playwright.sync_api import sync_playwright, TimeoutError
import time

# 1. 파이어베이스 DB 연결
cred = credentials.Certificate("firebase_key.json")
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)
db = firestore.client()

# 2. 카테고리 설정 (전체 카테고리 오픈!)
CATEGORY_URLS = {
    "water-purifier": "https://www.coway.com/product/water-purifier",
    "air-purifier-air-conditioner": "https://www.coway.com/product/air-purifier-air-conditioner",
    "bidet-softener": "https://www.coway.com/product/bidet-softener",
    "berex-bed": "https://www.coway.com/product/berex-bed",
    "berex-massage-chair": "https://www.coway.com/product/berex-massage-chair",
    "kitchen-living": "https://www.coway.com/product/kitchen-living",
    "healthcare": "https://www.coway.com/product/healthcare",
    "filters-supplies": "https://www.coway.com/product/filters-supplies",
    "refurbished": "https://www.coway.com/product/refurbished"
}

def scrape_coway_deep_products():
    print("🚀 상세페이지 딥 크롤링 시작...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        # 💡 [핵심 수정 1] 완벽한 한국어 환경 및 일반 유저 위장 세팅
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            locale='ko-KR',
            timezone_id='Asia/Seoul',
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            extra_http_headers={
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
            }
        )
        page = context.new_page()
        
        for category_name, list_url in CATEGORY_URLS.items():
            print(f"\n📂 [{category_name}] 카테고리 스캔 중...")
            
            # 리스트 페이지 접속 시에도 네트워크 안정화 대기
            page.goto(list_url, wait_until="networkidle")
            
            try:
                page.wait_for_selector("li.lp_renew_product", timeout=10000)
            except TimeoutError:
                print(f"⚠️ {category_name} 통과 (제품 없음)")
                continue

            for _ in range(5):
                page.mouse.wheel(0, 1500)
                page.wait_for_timeout(1000) 
                
            # --- 1단계: 상세페이지 URL 수집 ---
            product_links = []
            cards = page.locator("li.lp_renew_product a").all()
            
            for card in cards:
                href = card.get_attribute("href")
                if href:
                    if "javascript:commonProductjs.goProductVip" in href:
                        try:
                            numbers_str = href.split("(")[1].split(")")[0]
                            params = numbers_str.split(",")
                            prdno = params[0].strip()
                            optno = params[1].strip() if len(params) > 1 and params[1].strip() else "1"
                            product_links.append(f"https://www.coway.com/product/detail?prdno={prdno}&optno={optno}")
                        except Exception:
                            pass
                    elif not href.startswith("javascript:") and href.startswith("/"):
                        product_links.append(f"https://www.coway.com{href}")
                    elif href.startswith("http"):
                        product_links.append(href)
                        
            product_links = list(set(product_links))
            print(f"🎯 총 {len(product_links)}개 상세페이지 진입 시작!")

            # --- 2단계: 개별 상세페이지 딥 크롤링 ---
            for detail_url in product_links:
                try:
                    print(f"  ➡️ 접속 중: {detail_url}")
                    
                    # 💡 [핵심 수정 2] 네트워크 통신이 완전히 끝날 때까지 대기
                    page.goto(detail_url, wait_until="networkidle")
                    
                    page.wait_for_selector("#vipPrdnm", timeout=10000)
                    
                    # 💡 [핵심 수정 3] 렌더링 덮어쓰기 지연 방지 (2초 확실히 대기)
                    page.wait_for_timeout(2000) 
                    
                    # 1. 제품명 및 모델명
                    name = page.locator("#vipPrdnm").inner_text().strip()
                    
                    # 💡 [안전장치] 혹시라도 이름이 모두 영어(ASCII)로만 되어있다면 2초 더 기다려봄
                    if name.isascii():
                        print(f"     ⏳ 영어 명칭 감지됨, 한글 변환 추가 대기 중... ({name})")
                        page.wait_for_timeout(2000)
                        name = page.locator("#vipPrdnm").inner_text().strip()
                        
                    model_code = page.locator("#vipModelno").inner_text().strip() if page.locator("#vipModelno").count() > 0 else ""
                    
                    # 2. 메인 썸네일 이미지
                    image_url = ""
                    if page.locator(".preview_slide .swiper-slide-active img").count() > 0:
                        image_url = page.locator(".preview_slide .swiper-slide-active img").first.get_attribute("src")

                    # 3. 색상, 뱃지, 평점 정보
                    colors = [el.inner_text().strip() for el in page.locator(".colorchip .bg_color").all() if el.inner_text().strip()]
                    badges = [el.inner_text().strip() for el in page.locator(".flag span").all()]
                    
                    rating_text = page.locator("#rep_review_info span").first.inner_text().strip() if page.locator("#rep_review_info span").count() > 0 else "0 (0)"
                    rating = rating_text.split(" ")[0] if " " in rating_text else "0"
                    review_count = rating_text.split(" ")[1] if " " in rating_text else "(0)"

                    # 4. 가격 정보
                    def extract_price(selector):
                        if page.locator(selector).count() > 0:
                            text = page.locator(selector).first.inner_text()
                            return int(''.join(filter(str.isdigit, text))) if any(c.isdigit() for c in text) else 0
                        return 0

                    rental_original = extract_price(".rentalType .total_price .ori_p em")
                    rental_discount = extract_price(".rentalType .total_price .sal_p em")
                    purchase_price = extract_price(".priceType .total_price .sal_p em")
                    
                    discount_desc = ""
                    if page.locator(".rentalType .info_wrap .desc").count() > 0:
                        discount_desc = page.locator(".rentalType .info_wrap .desc").first.inner_text().replace('\n', ' ').strip()
                        
                    rental_total_text = page.locator("#rental_price_total p").first.inner_text().strip() if page.locator("#rental_price_total p").count() > 0 else ""

                    # 5. 상세 통짜 이미지
                    for _ in range(3):
                        page.mouse.wheel(0, 2000)
                        page.wait_for_timeout(1000)

                    detail_images = []
                    for selector in [".detail_info", "#detailArea", ".prd_detail_view", ".tab_cont", ".detail_content"]:
                        if page.locator(selector).count() > 0:
                            img_locators = page.locator(f"{selector} img").all()
                            for img in img_locators:
                                src = img.get_attribute("src") or img.get_attribute("data-original")
                                if src and src.startswith("http") and ("icon" not in src.lower()):
                                    detail_images.append(src)
                            break
                            
                    detail_images = list(dict.fromkeys(detail_images))

                    # 6. 파이어베이스 저장
                    product_data = {
                        "category": category_name,
                        "name": name,
                        "model_code": model_code,
                        "detail_url": detail_url,
                        "image_url": image_url,
                        "colors": colors,
                        "badges": badges,
                        "rating": rating,
                        "review_count": review_count,
                        "price": {
                            "rental_original": rental_original,
                            "rental_discount": rental_discount,
                            "purchase_price": purchase_price,
                            "discount_desc": discount_desc,
                            "rental_total_text": rental_total_text
                        },
                        "detail_images": detail_images,
                        "updated_at": firestore.SERVER_TIMESTAMP
                    }
                    
                    doc_id = model_code.replace("/", "_") if model_code else name.replace("/", "_")
                    doc_ref = db.collection("products").document(doc_id)
                    doc_ref.set(product_data, merge=True)
                    
                    print(f"      ✅ [저장 완료] {name} (할인가: {rental_discount:,}원)")

                except Exception as e:
                    print(f"      ⚠️ 파싱 오류 ({detail_url}): {e}")
                    continue
                    
        browser.close()
        print("\n🎉 크롤링 및 DB 업데이트 성공!")

if __name__ == "__main__":
    scrape_coway_deep_products()
