import streamlit as st
import json
import re
import os
from google import genai  # <--- 使用新版引擎

# ==========================================
# 0. 系統設定
# ==========================================
st.set_page_config(
    page_title="桃園照小子 - 智慧長照顧問",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 1. 資料庫與工具函式
# ==========================================
@st.cache_data
def load_data():
    """讀取資料庫 (容錯模式)"""
    dementia_data = []
    caregiver_data = []
    services_data = {}

    try:
        if os.path.exists(os.path.join("data", "dementia.json")):
            with open(os.path.join("data", "dementia.json"), "r", encoding="utf-8") as f:
                dementia_data = json.load(f)
        if os.path.exists(os.path.join("data", "caregiver.json")):
            with open(os.path.join("data", "caregiver.json"), "r", encoding="utf-8") as f:
                caregiver_data = json.load(f)
        if os.path.exists(os.path.join("data", "services.json")):
            with open(os.path.join("data", "services.json"), "r", encoding="utf-8") as f:
                services_data = json.load(f)
    except Exception as e:
        # 僅在後台紀錄錯誤，不影響前台
        print(f"資料庫讀取錯誤：{e}")
            
    return dementia_data, caregiver_data, services_data

@st.cache_data
def load_hospice_knowledge():
    """載入安寧照護 RAG 資料庫"""
    paths_to_check = [os.path.join("data", "hospice_rag_database.json"), "hospice_rag_database.json"]
    for path in paths_to_check:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    return [] 

def calculate_score(user_text, database):
    """規則比對邏輯"""
    results = []
    for item in database:
        score = 0
        matches = []
        for keyword in item['triggers']:
            if re.search(keyword, user_text, re.IGNORECASE):
                score += 1
                matches.append(keyword)
        if score > 0:
            results.append({"data": item, "score": score, "matches": matches})
    return sorted(results, key=lambda x: x['score'], reverse=True)

def retrieve_hospice_info(user_query, knowledge_base):
    """安寧 RAG 檢索邏輯"""
    relevant_chunks = []
    keywords = user_query.split()
    for item in knowledge_base:
        content = f"{item['topic']} {item['question']} {item['answer']}"
        score = 0
        for kw in keywords:
            if kw in content: score += 1
        if item['topic'] in user_query: score += 5
        if score > 0: relevant_chunks.append((score, item))
    relevant_chunks.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in relevant_chunks[:3]]

def get_ai_response(prompt_text):
    """Gemini API 呼叫 (V8.6 新引擎版)"""
    # 這裡換成了新的 google-genai 語法
    api_key = st.secrets.get("GOOGLE_API_KEY", None)
    if not api_key: return "⚠️ (AI 模式未啟動) 請設定 GOOGLE_API_KEY。"
    
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt_text
        )
        return response.text
    except Exception as e:
        return f"⚠️ AI 連線異常：{str(e)}\n(請確認 API Key 是否正確)"

# ==========================================
# 2. 側邊欄元件
# ==========================================
def render_sidebar_content():
    st.sidebar.title("🛡️ 桃園照小子")
    st.sidebar.markdown("我是俊葳小弟，您的智慧長照顧問。")
    
    app_mode = st.sidebar.radio("請選擇功能", ["🏠 智慧長照顧問 (主頁)", "🕊️ 幽谷伴行 (安寧諮詢)"])
    st.sidebar.markdown("---")
    
    # --- 支柱 1 & 2：錢與輔具 ---
    st.sidebar.subheader("🧮 補助額度試算 (V8.6)")
    with st.sidebar.expander("點擊展開計算機", expanded=False):
        cms_level = st.slider("CMS 失能等級", 2, 8, 7)
        income_type = st.selectbox("福利身分", ["一般戶", "中低收入戶", "低收入戶"])
        
        # A. 照顧及專業服務 (每月)
        caps = {2: 10020, 3: 15460, 4: 18580, 5: 24100, 6: 28070, 7: 32090, 8: 36180}
        copays = {"一般戶": 0.16, "中低收入戶": 0.05, "低收入戶": 0.0}
        limit = caps[cms_level]
        rate = copays[income_type]
        self_pay = int(limit * rate)
        
        st.markdown(f"**1. 照顧服務 (每月)**")
        st.markdown(f"總額度：${limit:,}")
        st.markdown(f"自付額：<span style='color:red'>${self_pay:,}</span>", unsafe_allow_html=True)
        
        st.divider()
        
        # B. 輔具
        assistive_limit = 40000
        assistive_copay_rate = {"一般戶": 0.3, "中低收入戶": 0.1, "低收入戶": 0.0}[income_type]
        assistive_self_pay = int(assistive_limit * assistive_copay_rate)
        
        st.markdown(f"**2. 輔具/修繕 (每3年)**")
        st.caption("如：輪椅、氣墊床、扶手安裝")
        st.markdown(f"總額度：**$40,000**")
        st.markdown(f"最高補助：<span style='color:green'>${assistive_limit - assistive_self_pay:,}</span>", unsafe_allow_html=True)
        
    st.sidebar.markdown("---")
    st.sidebar.subheader("💊 慢性病史 (AI 參考)")
    chronic_diseases = st.sidebar.multiselect(
        "長輩狀況：",
        ["高血壓", "糖尿病", "心臟病", "曾中風", "腎臟病/洗腎", "骨質疏鬆", "失智症"],
        default=[]
    )
    
    return app_mode, chronic_diseases

# ==========================================
# 3. 主程式介面
# ==========================================
def main():
    dementia_db, caregiver_db, services_db = load_data()
    app_mode, chronic_diseases = render_sidebar_content()

    # --- 模式一：長照主頁 ---
    if app_mode == "🏠 智慧長照顧問 (主頁)":
        st.title("🏠 桃園照小子 - 智慧長照顧問")
        st.markdown("### 四大支柱：給付、輔具、失智引導、四全照顧")
        
        col_input, col_hint = st.columns([2, 1])
        with col_input:
            user_input = st.text_area("請告訴我您的困難 (例如：媽媽失智會打人，而且我好累想休息...)", height=120)
        with col_hint:
            st.info("💡 **系統核心**：\n我們會同時分析「失智行為」與「照顧者壓力」，並提供具體補助建議。")

        if st.button("🔍 啟動四全分析", type="primary", key="btn_start_analysis"):
            if not user_input:
                st.warning("請輸入狀況！")
            else:
                dem_matches = calculate_score(user_input, dementia_db)
                
                # B. AI 分析
                disease_info = f"長輩病史包含：{', '.join(chronic_diseases)}。" if chronic_diseases else ""
                
                # --- V8.6 融合版 Prompt：保留你的 V8.5 聰明判斷 ---
                prompt = f"""
                你現在是「桃園照小子」，一位結合社工專業與安寧種子背景的長照顧問。
                
                【使用者情境】：
                - 長輩狀況：{disease_info}
                - 家屬主訴："{user_input}"
                
                【任務目標】：請先在內心進行「四大支柱檢核」，再輸出給家屬的建議。

                【系統參考數據 (Cheat Sheet) - 觸發式使用】：
                **注意：只有當使用者明確詢問「錢、補助、額度、費用、申請」或描述內容明顯涉及「需要經濟資源」時，才引用下列數據。否則請忽略此區塊。**
                
                - CMS 2級：每月補助 $10,020
                - CMS 3級：每月補助 $15,460
                - CMS 4級：每月補助 $18,580
                - CMS 5級：每月補助 $24,100
                - CMS 6級：每月補助 $28,070
                - CMS 7級：每月補助 $32,090 (一般戶自付16%約 $5,134)
                - CMS 8級：每月補助 $36,180 (一般戶自付16%約 $5,789)
                
                - 輔具補助：每 3 年最高補助 40,000 元 (CMS 2級以上)
                - 喘息服務：每年最高額度 $48,510 (依等級不同約 14~42 天)
                
                【請先在內心執行以下思考程序】：
                1. 掃描(Scan)：家屬現在最痛的點是什麼？是心情？是照顧技巧？還是缺錢？
                2. 判斷(Judge)：**需要列出補助金額嗎？** - 如果使用者只是在發洩情緒 -> 專注於同理心與喘息服務建議，不要列出冷冰冰的金額。
                   - 如果使用者問「怎麼辦」、「多少錢」 -> 引用上方的 Cheat Sheet。
                3. 草稿(Draft)：組合成溫暖的建議。

                【最終輸出要求 (嚴格執行)】：
                1. **【格式禁令】**：嚴禁使用 LaTeX 或數學公式。金額請直接寫中文 ($5,134)。
                2. **開頭**：務必先同理家屬情緒。
                3. **內容**：根據判斷結果，提供適當的建議。
                4. **結尾行動**：一定要明確引導撥打「1966 長照專線」。
                5. **【免責聲明】(必要！)**：
                   請在回答的最後面，換行並加上這段警語：
                   「⚠️ **照小子小提醒**：以上分析僅供參考。實際補助額度與資格，仍須經由長期照顧管理中心（照管專員）到府評估後才能確定喔！」
                """
                
                with st.spinner("🤖 照小子正在為您思考..."):
                    ai_reply = get_ai_response(prompt)
                
                st.divider()
                st.subheader("🤖 照小子 AI 顧問分析")
                st.success(ai_reply)

                # C. 推薦服務卡片
                if dem_matches:
                    top_match = dem_matches[0]
                    st.markdown(f"### 📋 建議處方：{top_match['data']['name']}")
                    if "recommend_services" in top_match['data']:
                        rec_codes = top_match['data']['recommend_services']
                        valid_svcs = [code for code in rec_codes if code in services_db]
                        cols = st.columns(2)
                        for idx, code in enumerate(valid_svcs):
                            svc = services_db[code]
                            with cols[idx % 2]:
                                with st.container(border=True):
                                    st.markdown(f"**{svc['name']} ({code})**")
                                    st.caption(svc['desc'])
                                    st.markdown(f"單價：${svc['price']}")
                        st.caption("*以上服務皆可申請長照補助。")

    # --- 模式二：安寧諮詢 ---
    elif app_mode == "🕊️ 幽谷伴行 (安寧諮詢)":
        st.title("🕊️ 幽谷伴行 - 安寧照護顧問")
        st.markdown("### 四全照顧：全人、全家、全程、全隊")
        
        kb = load_hospice_knowledge()
        user_q = st.chat_input("請輸入安寧相關問題 (如：嗎啡迷思、斷食)...")
        
        if user_q:
            st.chat_message("user").write(user_q)
            docs = retrieve_hospice_info(user_q, kb)
            
            # --- V8.6 融合版 Prompt：保留你的 V8.5 安寧免責聲明 ---
            prompt = f"""
            使用者問：{user_q}。
            參考資料：{docs}。
            
            請以「安寧種子」的溫暖語氣，強調「善終即是福氣」與「四全照顧」的精神來回答。
            
            【必要要求】：
            1. 回答需溫暖且具備專業同理心。
            2. **結尾必須加上以下免責聲明**：
               「⚠️ **照小子小提醒**：以上建議僅供參考，安寧緩和醫療的具體執行，請務必諮詢您的主治醫師或安寧團隊。」
            """
            
            with st.chat_message("assistant"):
                with st.spinner("查詢安寧知識庫..."):
                    reply = get_ai_response(prompt)
                    st.write(reply)

if __name__ == "__main__":
    main()
