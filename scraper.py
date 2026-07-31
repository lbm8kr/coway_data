import firebase_admin
from firebase_admin import credentials, firestore
from playwright.sync_api import sync_playwright, TimeoutError
import json

# 1. 파이어베이스 DB 연결
cred = credentials.Certificate("firebase_key.json")
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)
db = firestore.client()

# 2. 카테고리 설정
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

def scrape_coway_products():
    print("🚀 영혼까지 끌어모으는 풀(Full) 데이터 크롤링 시작...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        
        for category_name, url in CATEGORY_URLS.items():
            print(f"\n📂 [{category_name}] 카테고리 스캔 중...")
            page.goto(url)
            
            try:
                page.wait_for_selector("li.lp_renew_product", timeout=10000)
            except TimeoutError:
                print(f"⚠️ {category_name} 통과 (제품 없음)")
                continue

            # 스크롤 처리
            for _ in range(5):
                page.mouse.wheel(0, 1500)
                page.wait_for_timeout(1000) 
                
            cards = page.locator("li.lp_renew_product").all()
            print(f"🎯 총 {len(cards)}개 제품 발견. 데이터 추출 시작!")
            
            for card in cards:
                try:
                    # 1. 기본 텍스트 및 이미지
                    name = card.locator(".product_name").inner_text().strip()
                    model_code = card.locator(".product_code").inner_text().strip()
                    image_url = card.locator(".img_wrap img").first.get_attribute("data-original")
                    
                    # 2. 내부 JSON 메타데이터 (data-ec-product)
                    raw_meta = card.get_attribute("data-ec-product")
                    meta_data = json.loads(raw_meta) if raw_meta else {}
                    
                    # 3. 색상 정보 배열화
                    colors = [el.inner_text().strip() for el in card.locator(".colorchip .bg_color").all() if el.inner_text().strip()]
                    
                    # 4. 특징 및 뱃지 (냉수, 온수, 정수 / 아이스페스타 등)
                    features = [el.inner_text().strip() for el in card.locator(".op_water span").all()]
                    badges = [el.inner_text().strip() for el in card.locator(".flag span").all()]
                    
                    # 5. 리뷰 평점 및 카운트
                    rating = card.locator(".number_text").inner_text().strip() if card.locator(".number_text").count() > 0 else "0"
                    review_count = card.locator(".count").inner_text().strip() if card.locator(".count").count() > 0 else "(0)"
                    
                    # 6. 가격 정보 (렌탈가 및 일시불 구매가 모두 추출)
                    rental_original = card.locator(".rental_price del").inner_text().strip() if card.locator(".rental_price del").count() > 0 else ""
                    rental_discount = int(card.locator(".rental_price ins data").get_attribute("value")) if card.locator(".rental_price ins data").count() > 0 else 0
                    purchase_price = int(card.locator(".pay ins data").get_attribute("value")) if card.locator(".pay ins data").count() > 0 else 0
                    
                    # 최종 데이터 딕셔너리 조립
                    product_data = {
                        "category": category_name,
                        "name": name,
                        "model_code": model_code,
                        "image_url": image_url,
                        "colors": colors,
                        "features": features,
                        "badges": badges,
                        "rating": rating,
                        "review_count": review_count,
                        "price": {
                            "rental_original": rental_original,
                            "rental_discount": rental_discount,
                            "purchase_price": purchase_price
                        },
                        "meta_data": meta_data
                    }
                    
                    doc_id = model_code.replace("/", "_")
                    doc_ref = db.collection("products").document(doc_id)
                    
                    # 기존 데이터와 비교 로직 (가격 구조가 딕셔너리로 바뀌어 검증 방식 변경)
                    existing_doc = doc_ref.get()
                    is_changed = True
                    
                    if existing_doc.exists:
                        old_data = existing_doc.to_dict()
                        # 주요 데이터가 일치하면 변경 없는 것으로 간주
                        if (old_data.get("name") == name and
                            old_data.get("price") == product_data["price"] and
                            old_data.get("colors") == colors and
                            old_data.get("rating") == rating):
                            is_changed = False
                    
                    if is_changed:
                        product_data["updated_at"] = firestore.SERVER_TIMESTAMP
                        doc_ref.set(product_data, merge=True)
                        print(f"✅ [저장/업데이트] {name} (일시불: {purchase_price:,}원 / 렌탈: {rental_discount:,}원)")
                    else:
                        pass # 변경 없음 (로그 생략하여 터미널 깔끔하게 유지)
                        
                except Exception as e:
                    print(f"⚠️ 데이터 파싱 오류 ({name if 'name' in locals() else '알 수 없음'}): {e}")
                    continue
                    
        browser.close()
        print("\n🎉 모든 데이터 수집 및 비교 업데이트 완료!")

if __name__ == "__main__":
    scrape_coway_products()
