import streamlit as st
import json
import re
import os
import time
import google.generativeai as genai
import smtplib
from datetime import datetime

def get_subject_keypoint(user_input, client):
    """
    這個 Function 會把使用者的碎碎念，變成 15 字內的精華
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o", # 或者你用的模型名稱
            messages=[
                {"role": "system", "content": "你是一個長照專家照小子。請從家屬問題中抓出2個核心痛點，組合成15字內的一句話。例如：牙口與行走不穩的實戰對策"},
                {"role": "user", "content": user_input}
            ]
        )
        key_point = response.choices[0].message.content
    except:
        # 如果 AI 壞掉或抓不出來，給個保險的預設值
        key_point = user_input[:15] 
        
    return key_point
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

import streamlit as st
import json
import re
import os
import time
import google.generativeai as genai
import smtplib
from email.mime.text import MIMEText
from email.header import Header

# ==========================================
# 0. 系統設定與資料載入 (省略 load_data 等，保持原樣)
# ==========================================

# ... (保留你原本的 load_data, load_hospice_knowledge, calculate_score, retrieve_hospice_info) ...

def get_ai_response(prompt_text):
    """Gemini API 呼叫 (V9.3 純免費生存版)"""
    api_key = st.secrets.get("GOOGLE_API_KEY", None)
    if not api_key: return "⚠️ (AI 模式未啟動) 請設定 GOOGLE_API_KEY。"
    
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-flash-latest')
        try:
            return model.generate_content(prompt_text).text
        except Exception as e:
            if "429" in str(e):
                time.sleep(2)
                try:
                    return model.generate_content(prompt_text).text
                except:
                    return "⚠️目前使用人數較多，請稍後。"
            else:
                return f"⚠️ 連線異常：{str(e)}"
    except Exception as e:
        return f"⚠️ 系統嚴重錯誤：{str(e)}"

# --- 這裡開始是「寄信功能」，確保回到最左邊不縮排 ---

def send_careplan_email(user_email, user_input, ai_reply, client):
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
    key_point = get_subject_keypoint(user_input, client)
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
    # 🎯 加上這一段「初始化筆記本」，避免 AttributeError
    if "ai_reply" not in st.session_state:
        st.session_state.ai_reply = None
    if "current_user_q" not in st.session_state:
        st.session_state.current_user_q = ""

    if app_mode == "🏠 智慧長照顧問 (主頁)":
        st.title("🏠 桃園照小子 - 智慧長照顧問")
        st.markdown("### 四大支柱：給付、輔具、失智引導、四全照顧")
        
        user_input = st.text_area("請告訴我您的困難...", height=120)

        # 3. 啟動分析按鈕
        if st.button("🔍 啟動四全分析", type="primary", key="btn_start_analysis"):
            if not user_input:
                st.warning("請輸入狀況！")
            else:
                # 確保慢性病史有被讀到
                disease_info = f"長輩病史：{', '.join(chronic_diseases)}"
                prompt = f"你現在是桃園照小子，請根據以下主訴提供長照建議：{user_input}。{disease_info}"
                
                with st.spinner("🤖 照小子正在為您思考..."):
                    # 💡 重點：把分析結果存進「筆記本」裡，才不會因為按了打包按鈕就消失
                    st.session_state.ai_reply = get_ai_response(prompt)
                    st.session_state.user_q = user_input # 把問題也記下來
                
        # 4. 顯示分析與打包區塊 (只要筆記本裡有內容，就一直顯示)
        if "ai_reply" in st.session_state:
            st.divider()
            st.subheader("🤖 照小子 AI 顧問分析")
            st.success(st.session_state.ai_reply)

            # ==========================================
            # 3.1 每個人都能打包的 Email 區塊
            # ==========================================
            st.divider()
            st.markdown("### ✉️ 打包這份計畫帶回家")
            st.info("💡 **尊嚴保護聲明**：本分析不含個人隱私識別，僅供參考。")
                
            # 這裡就是輸入 Email 的格子
            user_email_addr = st.text_input("接收信件的 Email 地址", placeholder="example@mail.com", key="save_email_addr")
                
            if st.button("🚀 一鍵打包建議書", key="btn_send_email"):
                if not user_email_addr:
                    st.warning("請輸入 Email 地址！")
                else:
                    with st.spinner("📧 正在打包眼鏡理論與分析建議..."):
                        # 這裡會呼叫我們剛才寫好的第一部分函式
                        success, msg = send_careplan_email(
                            user_email_addr, 
                            st.session_state.current_user_q, 
                            st.session_state.ai_reply,
                            client
                        )
                        if success:
                            st.success(msg)
                            st.balloons()
                        else:
                            st.error(msg)

                # ==========================================
                # 3.2 推薦服務卡片 (原本的失智比對移到這裡)
                # ==========================================
                dem_matches = calculate_score(user_input, dementia_db)
                if dem_matches:
                    top_match = dem_matches[0]
                    # 1. 標題要大方
                    st.markdown(f"### 📋 建議處方：{top_match['data']['name']}")
                    
                    # 2. 加入一段解釋 (這就是解決「太短」的關鍵)
                    # 假設你的 JSON 裡有 'desc' 或 'reason'
                    st.info(f"💡 **照小子提醒**：針對長輩的狀況，這項活動能透過不同水溫與觸覺，穩定長輩的情緒，減少感知異常帶來的不安。")
                    
                    # 3. 顯示具體可申請的長照服務代碼
                    if "recommend_services" in top_match['data']:
                        st.markdown("#### 🛠️ 建議搭配長照服務 (可申請補助)：")
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

    # --- 模式二：安寧諮詢 (接在主頁模式的整個結束之後) ---
    elif app_mode == "🕊️ 幽谷伴行 (安寧諮詢)":
        st.title("🕊️ 幽谷伴行 - 安寧照護顧問")
        st.markdown("### 四全照顧：全人、全家、全程、全隊")
        st.info("💡**研發團隊的話**：安寧不是放棄治療，而是選擇更有尊嚴的陪伴。")
        
        kb = load_hospice_knowledge()
        user_q = st.chat_input("請輸入安寧相關問題 (例如：如何跟長輩談預立醫療？)")
        
        if user_q:
            st.chat_message("user").write(user_q)
            docs = retrieve_hospice_info(user_q, kb)
            
            # 安寧諮詢的 Prompt
            h_prompt = f"你現在是安寧顧問，請根據資料庫內容回答使用者：{user_q}。參考資料：{docs}"
            
            with st.chat_message("assistant"):
                with st.spinner("查詢安寧知識庫..."):
                    reply = get_ai_response(h_prompt)
                    st.write(reply)

# ==========================================
# 4. 啟動點 (最左邊，完全不縮排)
# ==========================================
if __name__ == "__main__":
    main()
