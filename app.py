import streamlit as st
import json
import re
import os
import time
#from groq import Groq  # 換成這行
import google.generativeai as genai
#from google import genai  # 替換原本的 import google.generativeai as genai
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.header import Header

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
        st.error(f"資料讀取失敗：{e}") # 讓它直接在畫面上噴出錯誤紅字
        pass
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
    """規則比對邏輯：自動修正字串與列表的差異"""
    results = []
    if not user_text: return []
    
    for item in database:
        score = 0
        matches = []
        
        # 1. 取得觸發詞 (相容 triggers 或 trigger_behavior)
        raw_trigger = item.get('triggers', item.get('trigger_behavior', []))
        
        # 2. 強制轉成「列表」：如果是字串 "覺得醬油在動" -> 變成 ["覺得醬油在動"]
        # 這樣下方的 for 迴圈才會拿「整句話」去比對，而不是拆成單個字
        triggers_list = [raw_trigger] if isinstance(raw_trigger, str) else raw_trigger
        
        # 3. 開始比對
        for keyword in triggers_list:
            if keyword and str(keyword) in user_text:
                score += 1
                matches.append(str(keyword))
        
        if score > 0:
            # 確保有標題可以顯示
            if 'name' not in item:
                item['name'] = item.get('scene', '長照處方')
            results.append({"data": item, "score": score, "matches": matches})
            
    return sorted(results, key=lambda x: x['score'], reverse=True)
    #"""規則比對邏輯"""
    #results = []
    #for item in database:
    #    score = 0
    #    matches = []
    #    for keyword in item['triggers']:
    #        if re.search(keyword, user_text, re.IGNORECASE):
    #            score += 1
    #            matches.append(keyword)
    #    if score > 0:
    #        results.append({"data": item, "score": score, "matches": matches})
    #return sorted(results, key=lambda x: x['score'], reverse=True)

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


# ==========================================
# 0. 系統設定與資料載入 (省略 load_data 等，保持原樣)
# ==========================================

# ... (保留你原本的 load_data, load_hospice_knowledge, calculate_score, retrieve_hospice_info) ...

def get_ai_response(prompt_text):
    """Gemini API 呼叫 (已修正為最新 google-genai 寫法)"""
    api_key = st.secrets.get("GOOGLE_API_KEY", None)
    if not api_key: 
        return "標題摘要", "⚠️ (AI 模式未啟動) 請設定 GOOGLE_API_KEY。"
    
    # 1. 初始化設定
    genai.configure(api_key=api_key)
    
    # 2. 設定模型 (建議用 gemini-1.5-flash，速度快且免費額度較多)
    #model = genai.GenerativeModel('gemini-1.5-flash')
    #model = genai.GenerativeModel('models/gemini-1.5-flash')
    model = genai.GenerativeModel('gemini-flash-latest')
    # 3. 組合優化後的指令
    final_prompt = (
    "你現在是桃園長照專家『桃園照小子』。請用『台灣繁體中文』回覆。\n\n"
        f"家屬目前的困擾：{prompt_text}\n\n"
        "### 寫作規範：\n"
        "1. **角色設定**：稱呼家屬為『親愛的照顧者』。口氣要像溫暖的學長，不要有『1. 2.』這種僵硬的編號。\n"
        "2. **比例分配**：\n"
        "   - [重點摘要]：這部分是精華，請嚴格控制在 250 字以內。內容包含：暖心開場、一個最核心的病理比喻、以及一個最重要的行動(1966)。\n"
        "   - [完整內文]：這部分是細節，請盡情發揮，挑戰 800 字以上。包含：深入的病理衛教、桃園 3 大資源詳細介紹、長照 2.0 錢與額度的計算、以及給照顧者的心理建設。\n"
        "3. **格式標籤**：必須嚴格包含 [標題]、[內容]、[重點摘要]、[完整內文] 這四個標籤。\n\n"
        "[標題]：(請寫出一個充滿力量的專業標題)\n\n"
        "[內容]：\n"
        "### 1. [重點摘要]：\n"
        "(請在這裡寫下 250 字內的精簡精華)\n\n"
        "### 2. [完整內文]：\n"
        "(請在這裡展開長篇大論的專業建議與溫暖喊話)\n\n"
        "請開始撰寫這份比例完美的長照戰術計畫："
    )
    try:
        # 4. 呼叫 Gemini 產生內容
        response = model.generate_content(final_prompt)
        full_text = response.text
        
        # 5. 解析邏輯：根據 [內容] 標籤拆分標題與內文
        if "[內容]" in full_text:
            # 取 [內容] 之前的部分作為標題，去掉 [標題] 字樣
            key_point = full_text.split("[內容]")[0].replace("[標題]", "").replace(":", "").strip()
            # 取 [內容] 之後的部分作為完整回覆
            full_reply = full_text.split("[內容]")[1].strip()
            return key_point, full_reply
        else:
            # 如果 AI 沒有乖乖按照格式，就給個預設標題並回傳全文
            return "照小子照顧計畫建議", full_text
            
    except Exception as e:
        return "系統異常", f"⚠️ Gemini 引擎回報錯誤：{str(e)}"
        

# --- 這裡開始是「寄信功能」，確保回到最左邊不縮排 ---

def send_careplan_email(
    user_email, 
    user_input, 
    ai_reply, 
    key_point# 這裡有傳入第4個參數，正確！
):
    """實作寄信服務：眼鏡理論、動態主旨、尊嚴聲明"""
    email_user = "careboy.taoyuan@gmail.com"
    # 注意：這裡要填 Secrets 的標籤名稱 EMAIL_PASSWORD
    email_password = st.secrets.get("EMAIL_PASSWORD", "") 
    
    if not email_password:
        return False, "⚠️ 系統尚未設定郵件授權碼 (EMAIL_PASSWORD)。"

    current_time = time.strftime("%Y/%m/%d %H:%M")
# 原本的：subject = f"【桃園照小子的信】關於「{user_input[:15]}...」的建議 —— {current_time}"

# 新的（去冰顯眼版）：
# 1. 產生標題（把原本 \n 換成 ｜ 確保不亂跑）
    today_md = datetime.now().strftime("%m/%d")
    subject = f"🚨【重要】照小子：{today_md} 照顧計畫摘要 ｜ 關鍵：{key_point} 【寄送】"

    # 2. 產生內容（請確保這整塊前面都有 4 個空格對齊）
    content = (
        f"您好，這是一封由「桃園照小子」為您準備的專屬建議。\n\n"
        f"【想法提醒：眼鏡理論】\n"
        f"在看方案前，請記得：戴眼鏡是為了讓我們看更清楚，沒人會說眼鏡是負擔；同樣地，助行器、洗澡椅等輔具，也是為了讓我們走更遠、活得更自由的科技工具。這不是因為「老」，而是為了「生活品質的擴充」。\n\n"
        f"【您的諮詢問題】\n"
        f"問：{user_input}\n\n"
        f"【照小子的實戰建議】\n"
        f"{ai_reply}\n\n"
        f"---\n"
        f"【專業宣告與隱私保護】\n"
        f"本分析建議由 AI 生成，您的主訴僅用於提供長照組合建議與優化系統邏輯。桃園照小子致力於保護您的尊嚴，所有內容不包含個人隱私識別，僅作為您與專業醫療人員討論之參考。\n\n"
        f"桃園地區長照資源：撥打 1966\n"
        f"署名：桃園照小子 研發團隊 敬上"
    )
    try:
        msg = MIMEText(content, 'plain', 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = f"桃園照小子 <{email_user}>"
        msg['To'] = user_email
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(email_user, email_password)
        server.sendmail(email_user, [user_email], msg.as_string())
        server.quit()
        return True, "✅ 建議計畫已打包寄送！"
    except Exception as e:
        return False, f"❌ 寄送失敗：{str(e)}"

# ==========================================
# 2. 側邊欄元件 (請確保與 def 同一排，不縮排)
# ==========================================
def render_sidebar_content():
    st.sidebar.title("🛡️ 桃園照小子")
    st.sidebar.markdown("桃園照小子研發團隊，為您提供智慧長照顧問服務。")
    
    app_mode = st.sidebar.radio("請選擇功能", ["🏠 智慧長照顧問 (主頁)", "🕊️ 幽谷伴行 (安寧諮詢)"])
    st.sidebar.markdown("---")
    
    st.sidebar.subheader("🧮 補助額度試算 (V9.3)")
    with st.sidebar.expander("點擊展開計算機", expanded=False):
        cms_level = st.slider("CMS 失能等級", 2, 8, 7)
        income_type = st.selectbox("福利身分", ["一般戶", "中低收入戶", "低收入戶"])
        
        caps = {2: 10020, 3: 15460, 4: 18580, 5: 24100, 6: 28070, 7: 32090, 8: 36180}
        copays = {"一般戶": 0.16, "中低收入戶": 0.05, "低收入戶": 0.0}
        limit = caps[cms_level]
        self_pay = int(limit * copays[income_type])
        
        st.markdown(f"**1. 照顧服務 (每月)**")
        st.markdown(f"總額度：${limit:,}")
        st.markdown(f"自付額：<span style='color:red'>${self_pay:,}</span>", unsafe_allow_html=True)
        
    chronic_diseases = st.sidebar.multiselect(
        "長輩狀況：",
        ["高血壓", "糖尿病", "失智症", "曾中風", "腎臟病/洗腎"],
        default=[]
    )
    return app_mode, chronic_diseases

# ==========================================
# 3. 主程式介面 - 核心分析區
# ==========================================
def main():
    
    dementia_db, caregiver_db, services_db = load_data()
    app_mode, chronic_diseases = render_sidebar_content()
    
    # 初始化筆記本
    if "ai_reply" not in st.session_state: st.session_state.ai_reply = None
    if "key_point" not in st.session_state: st.session_state.key_point = ""
    if "user_q" not in st.session_state: st.session_state.user_q = ""

    if app_mode == "🏠 智慧長照顧問 (主頁)":
        st.title("🏠 桃園照小子 - 智慧長照顧問")
        st.markdown("### 四大支柱：給付、輔具、失智引導、四全照顧")
        
        user_input = st.text_area("請告訴我您的困難...", height=120)

        # 1. 啟動分析按鈕 (只負責計算)
        if st.button("🔍 啟動四全分析", type="primary"):
            if not user_input:
                st.warning("請輸入狀況！")
            else:
                disease_info = f"長輩病史：{', '.join(chronic_diseases)}"
                prompt = f"你現在是桃園照小子，請根據以下主訴提供長照建議：{user_input}。{disease_info}"
                with st.spinner("🤖 照小子正在為您思考並抓取核心痛點..."):
                    kp, reply = get_ai_response(prompt)
                    st.session_state.key_point = kp
                    st.session_state.ai_reply = reply
                    st.session_state.user_q = user_input

        # 2. 顯示區 (只要筆記本有東西就顯示)
        if st.session_state.ai_reply:
            st.divider()
            st.subheader("🤖 照小子 AI 顧問分析")
          
            full_text = st.session_state.ai_reply

            # --- 強壯的解析邏輯開始 ---
            # 我們預設尋找 [摘要] 或 [重點摘要]
            # 使用 re.split 確保大小寫或空格稍微不對也能拆分
            import re
    
            # 嘗試拆分摘要與內文
            if "[完整內文]" in full_text:
                # 先切開摘要區與內文區
                parts = full_text.split("[完整內文]")
        
                # 處理摘要部分：去掉 [標題] [內容] [重點摘要] 等標籤
                summary_raw = parts[0]
                # 把所有標籤格式都清除，只留下純文字
                summary_clean = re.sub(r"\[標題\].*?\[內容\]|\[摘要\]|### 1. \[重點摘要\]：", "", summary_raw, flags=re.DOTALL).strip()
        
                # 處理內文部分：去掉標籤
                detail_clean = parts[1].replace("### 2. [完整內文]：", "").strip()
        
                # 1. 顯示摘要（直接顯示，讓家屬先看重點）
                st.info(summary_clean)

                # 2. 顯示內文（預設縮起來，降低資訊壓力）
                with st.expander("🔍 點擊展開：照小子為您準備的詳細戰術包", expanded=False):
                    # 使用 markdown 確保 AI 的換行與粗體能正確顯示
                    st.markdown(detail_clean) 
            
            else:
                # 備援計畫：如果 AI 忘記加標籤，就直接全顯示，但給一個提示
                st.warning("ℹ️ 照小子提示：詳細計畫整理中，請先參考以下完整內容：")
                st.markdown(full_text)
            # --- 解析邏輯結束 ---
        
            # 物理隔離邏輯：從 [完整內文] 處切開(old)
            #if "[完整內文]" in st.session_state.ai_reply:
            #    parts = st.session_state.ai_reply.split("[完整內文]")
            #    summary_part = parts[0].replace("[摘要]", "").strip()
            #    full_detail_part = parts[1].strip()
        
                # 1. 顯示摘要（戰友溫馨版）
            #    st.info(summary_part)
        
                # 2. 顯示按鈕（摺疊完整內文）
            #    with st.expander("🔍 點擊展開：照小子為您準備的詳細戰術包", expanded=False):
                    #st.markdown(full_detail_part)
            #        st.success(full_detail_part) # 這樣點開後，裡面整片都會是綠色底、深綠字
            #else:
                # 如果格式意外沒對上，就維持原樣顯示
            #    st.success(st.session_state.ai_reply)
    
            # --- (B) 📋 建議處方卡片 (緊跟在回覆後) ---
            st.divider()
            st.divider()
            # 確保使用 user_input 或 st.session_state.user_q 進行比對
            dem_matches = calculate_score(st.session_state.user_q, dementia_db)

            if dem_matches:
                # 取得最高分的匹配項
                match_data = dem_matches[0]['data']
    
                st.markdown(f"### 📋 建議處方：{match_data.get('name', '失智照顧建議')}")
    
                # 1. 顯示「警訊觀測」：讓家屬看見病理真相 (使用 warning 黃色框)
                st.warning(f"⚠️ **照小子【警訊觀測】**：\n\n{match_data.get('warning_signal', '暫無特定警訊說明。')}")
    
                # 2. 顯示「實戰錦囊」：具體的行動指引 (使用 success 綠色框)
                st.success(f"💡 **照小子【實戰錦囊】**：\n\n{match_data.get('prevention_strategy', '暫無特定預防策略。')}")
    
                # 3. 原始服務列表：如果資料庫有推薦代碼，就顯示小卡片
                if "recommend_services" in match_data:
                    st.markdown("#### 🛠️ 建議搭配長照服務 (可申請補助)：")
                    # 篩選出資料庫中存在的服務代碼
                    valid_svcs = [c for c in match_data['recommend_services'] if c in services_db]
        
                    if valid_svcs:
                        cols = st.columns(2)
                        for idx, code in enumerate(valid_svcs):
                            svc = services_db[code]
                            with cols[idx % 2]:
                                with st.container(border=True):
                                    st.markdown(f"**{svc['name']} ({code})**")
                                    st.caption(svc['desc'])
                                    st.markdown(f"單價：${svc['price']}")
                    else:
                        st.caption("ℹ️ 此處方暫無對應的給付項目，建議諮詢 A 個管員。")
            else:
                st.caption("ℹ️ 目前狀況未觸發特定失智照顧處方，建議諮詢專業醫護。")
            #dem_matches = calculate_score(st.session_state.user_q, dementia_db)
            #if dem_matches:
            #    top_match = dem_matches[0]
            #    st.markdown(f"### 📋 建議處方：{top_match['data']['name']}")
            #    st.info(f"💡 **照小子提醒**：針對長輩的狀況，建議採取穩定情緒的照顧策略。")
            #    
            #    if "recommend_services" in top_match['data']:
            #        st.markdown("#### 🛠️ 建議搭配長照服務 (可申請補助)：")
            #        valid_svcs = [c for c in top_match['data']['recommend_services'] if c in services_db]
            #        cols = st.columns(2)
            #        for idx, code in enumerate(valid_svcs):
            #            svc = services_db[code]
            #            with cols[idx % 2]:
            #                with st.container(border=True):
            #                    st.markdown(f"**{svc['name']} ({code})**")
            #                    st.caption(svc['desc'])
            #                    st.markdown(f"單價：${svc['price']}")
            #else:
            #    st.caption("ℹ️ 目前狀況未觸發特定失智照顧處方，建議諮詢專業醫護。")

            # --- (C) ✉️ 打包建議書區塊 (最後的行動呼籲) ---
            st.divider()
            st.markdown("### ✉️ 打包這份計畫帶回家")
            st.info(f"🎯 **本郵件摘要**：{st.session_state.key_point}") # 讓使用者看到摘要
            user_email_addr = st.text_input("接收信件的 Email 地址", key="save_email_addr")
                
            if st.button("🚀 一鍵打包建議書", key="btn_send_email"):
                if not user_email_addr:
                    st.warning("請輸入 Email 地址！")
                else:
                    with st.spinner("📧 正在寄送建議書..."):
                        success, msg = send_careplan_email(
                            user_email_addr, 
                            st.session_state.user_q, 
                            st.session_state.ai_reply,
                            st.session_state.key_point
                        )
                        if success:
                            st.success(msg)
                            st.balloons()
                        else:
                            st.error(msg)

    

    # --- 模式二：安寧諮詢 (接在主頁模式的整個結束之後) ---
    elif app_mode == "🕊️ 幽谷伴行 (安寧諮詢)":
        st.title("🕊️ 幽谷伴行 - 安寧照護顧問")
        st.markdown("### 四全照顧：全人、全家、全程、全隊")
        st.info("💡 **設計者的心裡話**：安寧不是放棄治療，而是選擇更有尊嚴的陪伴。")
        st.caption("※ 系統會自動記錄您最近的 3 則諮詢，您可以隨時一鍵打包寄回家。")
        
        kb = load_hospice_knowledge()
        
        # 1. 初始化「三格錦囊資料夾」
        if "h_reports" not in st.session_state:
            st.session_state.h_reports = []

        # 2. 對話輸入框
        user_q = st.chat_input("請輸入安寧相關問題 (例如：如何跟長輩談預立醫療？)")
        
        if user_q:
            docs = retrieve_hospice_info(user_q, kb)
            h_prompt = f"你現在是安寧顧問，請根據資料回答：{user_q}。參考資料：{docs}"
            
            with st.spinner("🤖 照小子正在為您整理安寧錦囊..."):
                kp_h, reply_h = get_ai_response(h_prompt)
                
                # 將新對話存成小包
                new_report = {
                    "question": user_q,
                    "answer": reply_h,
                    "key_point": kp_h
                }
                
                # 限制最多三封的邏輯
                st.session_state.h_reports.append(new_report)
                if len(st.session_state.h_reports) > 3:
                    st.session_state.h_reports.pop(0)

        # 3. 畫面顯示 (把現有的錦囊都列出來)
        for idx, report in enumerate(st.session_state.h_reports):
            # 計算總數，讓標籤顯示為 (1/2, 2/2) 這種格式
            total = len(st.session_state.h_reports)
            with st.expander(f"📋 安寧錦囊 ({idx+1}/{total})：{report['key_point']}", expanded=True):
                st.markdown(f"**問**：{report['question']}")
                st.info(report['answer'])
                # --- 解析標籤並進行內部摺疊 ---（new）
                if "[完整內文]" in full_h_text:
                    h_parts = full_h_text.split("[完整內文]")
                    # 清理摘要標籤
                    h_summary = h_parts[0].replace("### 1. [重點摘要]：", "").replace("[摘要]", "").strip()
                    # 清理內文標籤
                    h_detail = h_parts[1].replace("### 2. [完整內文]：", "").strip()
                    
                    # 顯示摘要 (用藍色框框住，增加層次感)
                    st.info(h_summary)
                    
                    # 再次摺疊：內文縮在更深一層，讓畫面乾淨
                    with st.status("🔍 查看照小子提供的詳細安寧建議...", expanded=False):
                        st.markdown(h_detail)
                else:
                    # 如果沒標籤，就直接顯示原本的 answer
                    st.info(full_h_text)
        # 4. 一鍵打包區 (只要有一封以上就能打包)
        if st.session_state.h_reports:
            st.divider()
            st.markdown("### ✉️ 一鍵打包寄送安寧錦囊")
            num_reports = len(st.session_state.h_reports)
            st.write(f"目前已就緒報告：{num_reports} 封")
            
            h_email_addr = st.text_input("接收信件的 Email 地址", key="h_email_batch")
            
            if st.button("🚀 啟動打包寄送", key="h_send_batch_btn"):
                if not h_email_addr:
                    st.warning("請輸入 Email 地址！")
                else:
                    with st.spinner(f"📧 正在寄送 {num_reports} 封錦囊..."):
                        success_count = 0
                        for i, r in enumerate(st.session_state.h_reports):
                            # 加工主旨，加入「安寧錦囊」字樣
                            h_kp = f"安寧錦囊({i+1}/{num_reports}) ｜ {r['key_point']}"
                            
                            success, msg = send_careplan_email(
                                h_email_addr, 
                                r['question'], 
                                r['answer'], 
                                h_kp
                            )
                            if success: success_count += 1
                        
                        if success_count > 0:
                            st.success(f"✅ 成功寄出 {success_count} 封安寧錦囊！請檢查信箱。")
                            st.balloons()
                            
# ==========================================
# 4. 啟動點 (最左邊，完全不縮排)
# ==========================================
if __name__ == "__main__":
    main()
