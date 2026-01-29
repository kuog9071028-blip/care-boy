import streamlit as st
import json
import re
import os
import time
import google.generativeai as genai

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

# --- 上面那個函式結束了，這裡要回到最左邊 ---

import smtplib
from email.mime.text import MIMEText
from email.header import Header

def send_careplan_email(user_email, user_input, ai_reply):
    """實作寄信服務：眼鏡理論、動態主旨、尊嚴聲明"""
    email_user = "careboy.taoyuan@gmail.com"
    email_password = st.secrets.get("jrfkbjlhfbtfwrkq", "")
    
    if not email_password:
        return False, "⚠️ 系統尚未設定郵件授權碼 (EMAIL_PASSWORD)。"

    current_time = time.strftime("%Y/%m/%d %H:%M")
    subject = f"【桃園照小子的信】關於「{user_input[:15]}...」的建議 —— {current_time}"
    
    content = f"您好，這是一封由「桃園照小子」為您準備的專屬建議。\n\n【想法提醒：眼鏡理論】\n在看方案前，請記得：戴眼鏡是為了讓我們看更清楚，沒人會說眼鏡是負擔；同樣地，助行器、洗澡椅等輔具，也是為了讓我們走更遠、活得更自由的科技工具。這不是因為「老」，而是為了「生活品質的擴充」。\n\n【您的諮詢問題】\n問：{user_input}\n\n【照小子的實戰建議】\n{ai_reply}\n\n---\n【專業宣告與隱私保護】\n本分析建議由 AI 生成，您的主訴僅用於提供長照組合建議與優化系統邏輯。桃園照小子致力於保護您的尊嚴，所有內容不包含個人隱私識別，僅作為您與專業醫療人員討論之參考。\n\n桃園地區長照資源：撥打 1966\n署名：桃園照小子 俊葳小弟 敬上"

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
    
    if not api_key: return "⚠️ (AI 模式未啟動) 請設定 GOOGLE_API_KEY。"
    
    try:
        genai.configure(api_key=api_key)
        
        # 關鍵修改：使用您 Log 中出現過的「gemini-flash-latest」
        # 這是免費版最穩定的代號
        model = genai.GenerativeModel('gemini-flash-latest')
        
        # 加入重試機制 (Retry Logic)
        # 如果免費版因為「太頻繁」被擋 (429)，我們就休息 2 秒再試一次
        try:
            return model.generate_content(prompt_text).text
        except Exception as e:
            if "429" in str(e):
                time.sleep(2) # 休息一下
                try:
                    return model.generate_content(prompt_text).text
                except:
                    return "⚠️目前使用人數較多 (Google 免費額度限制)，請過 1 分鐘後再試。"
            else:
                return f"⚠️ 連線異常：{str(e)}"

    except Exception as e:
        return f"⚠️ 系統嚴重錯誤：{str(e)}"

# ==========================================
# 2. 側邊欄元件
# ==========================================
def render_sidebar_content():
    st.sidebar.title("🛡️ 桃園照小子")
    st.sidebar.markdown("我是俊葳小弟，您的智慧長照顧問。")
    
    app_mode = st.sidebar.radio("請選擇功能", ["🏠 智慧長照顧問 (主頁)", "🕊️ 幽谷伴行 (安寧諮詢)"])
    st.sidebar.markdown("---")
    
    # --- 支柱 1 & 2：錢與輔具 ---
    st.sidebar.subheader("🧮 補助額度試算 (V9.3)")
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
    # 這裡所有的程式碼都必須比 def main() 往右縮排 4 個半形空格
    dementia_db, caregiver_db, services_db = load_data()
    app_mode, chronic_diseases = render_sidebar_content()

    # --- 模式一：長照主頁 ---
    if app_mode == "🏠 智慧長照顧問 (主頁)":
        # 1. Logo 與 標題 並排區塊
        logo_path = "assets/logo.png"
        col1, col2 = st.columns([0.5, 5], vertical_alignment="center")

        with col1:
            if os.path.exists(logo_path):
                st.image(logo_path, width=80)
            else:
                st.write("🏠")

        with col2:
            st.title("桃園照小子 - 智慧長照顧問")

        st.markdown("### 四大支柱：給付、輔具、失智引導、四全照顧")
        
        # 2. 輸入區塊
        col_input, col_hint = st.columns([2, 1])
        with col_input:
            user_input = st.text_area("請告訴我您的困難 (例如：媽媽失智會打人，而且我好累想休息...)", height=120)

        with col_hint:
            st.info("💡 **系統核心**：\n我們會同時分析「失智行為」與「照顧者壓力」，並提供具體補助建議。")

        # 3. 啟動分析按鈕
        if st.button("🔍 啟動四全分析", type="primary", key="btn_start_analysis"):
            if not user_input:
                st.warning("請輸入狀況！")
            else:
                dem_matches = calculate_score(user_input, dementia_db)
                # 確保變數存在
                disease_info = f"長輩病史包含：{', '.join(chronic_diseases)}。" if chronic_diseases else ""
                
                # --- V9.3 Prompt ---
                prompt = f"""
                #你現在是「桃園照小子」，一位結合社工專業與安寧種子背景的長照顧問。
                #
                #【使用者情境】：
                #- 長輩狀況：{disease_info}
                #- 家屬主訴："{user_input}"
                你現在是「桃園照小子」，請「務必」根據以下資料庫內容來回答。

                【長照服務資料庫】：
               {json.dumps(services_db, ensure_ascii=False)}  

                【長輩狀況】：{disease_info}
                【家屬主訴】："{user_input}"

                【任務要求】：
                - 如果使用者提到的問題在「長照服務資料庫」中有對應代碼（如 BA01、GA03），請詳細說明該項目的名稱、價格與內容。
                - 如果資料庫裡找不到，請委婉告知並引導撥打 1966。
                - 嚴禁 LaTeX。
                【任務目標】：請先在內心進行「四大支柱檢核」，再輸出給家屬的建議。

                【系統參考數據 (Cheat Sheet)】：
                - CMS 2~8 級補助額度（略）...
                
                【最終輸出要求】：
                1. 嚴禁 LaTeX。
                2. 必須引導撥打 1966。
                3. 最後加上免責聲明。
                """
                
                with st.spinner("🤖 照小子正在為您思考..."):
                    ai_reply = get_ai_response(prompt)
                
                st.divider()
                st.subheader("🤖 照小子 AI 顧問分析")
                st.success(ai_reply)

                # 4. 推薦服務卡片
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
                        # ==========================================
                # 4. Email 打包服務 (分析完畢後顯示)
                # ==========================================
                st.divider()
                st.markdown("### ✉️ 打包這份計畫帶回家")
                st.info("💡 **尊嚴保護聲明**：本分析不含個人隱私識別，僅供參考。")
                
                user_email_addr = st.text_input("接收信件的 Email 地址", placeholder="example@mail.com", key="save_email_addr")
                
                if st.button("🚀 一鍵打包建議書", key="btn_send_email"):
                    if not user_email_addr:
                        st.warning("請輸入 Email 地址！")
                    else:
                        with st.spinner("📧 正在打包眼鏡理論與分析建議..."):
                            success, msg = send_careplan_email(user_email_addr, user_input, ai_reply)
                            if success:
                                st.success(msg)
                                st.balloons()
                            else:
                                st.error(msg)

    # --- 模式二：安寧諮詢 ---
    elif app_mode == "🕊️ 幽谷伴行 (安寧諮詢)":
        st.title("🕊️ 幽谷伴行 - 安寧照護顧問")
        st.markdown("### 四全照顧：全人、全家、全程、全隊")
        
        kb = load_hospice_knowledge()
        user_q = st.chat_input("請輸入安寧相關問題...")
        
        if user_q:
            st.chat_message("user").write(user_q)
            docs = retrieve_hospice_info(user_q, kb)
            
            prompt = f"使用者問：{user_q}。參考資料：{docs}。" # 此處簡略
            
            with st.chat_message("assistant"):
                with st.spinner("查詢安寧知識庫..."):
                    reply = get_ai_response(prompt)
                    st.write(reply)

# 啟動點 (最左邊，不能縮排)
if __name__ == "__main__":
    main()
