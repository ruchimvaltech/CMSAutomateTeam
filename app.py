import asyncio
import sys
import pandas as pd
from io import BytesIO

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
import streamlit as st
from crawler import crawl_website
from ai_service import ask_ai, generate_suggested_questions

# ---------------- PAGE CONFIG ----------------
st.set_page_config(page_title="AI Website Chatbot", page_icon="🤖", layout="centered")

# ---------------- SESSION STATE ----------------
for key, default in {
    "website_url": None,
    "context": "",
    "messages": [],
    "suggested_questions": []
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

if "rfp_data" not in st.session_state:
    st.session_state["rfp_data"] = None

# ---------------- CSS ----------------
st.markdown("""
<style>
.block-container { display:flex; justify-content:center; }
.chat-card {
    width:420px; background:white; border-radius:14px;
    box-shadow:0 10px 30px rgba(0,0,0,0.15);
    overflow:hidden; margin-top:40px;
}
.chat-header { background:#b97ad9; color:white; padding:14px; font-weight:bold; }
.status { font-size:12px; opacity:0.9; }
.chat-body {
    height:86px; padding:15px; overflow-y:auto; background:#fafafa;
}
.bot {
    background:#eaeaea; color:#333; padding:10px 14px;
    border-radius:14px; margin-bottom:10px; max-width:80%;
}
.user {
    background:#b97ad9; color:white; padding:10px 14px;
    border-radius:14px; margin-bottom:10px; max-width:80%; margin-left:auto;
}
.chat-input { padding:10px; border-top:1px solid #eee; }
</style>
""", unsafe_allow_html=True)

# ---------------- UI ----------------
st.markdown('<div class="chat-card">', unsafe_allow_html=True)

# Header
st.markdown("""
<div class="chat-header">
    🤖 LeadBot<br>
    <span class="status">● Online now</span>
</div>
""", unsafe_allow_html=True)

# Body
st.markdown('<div class="chat-body">', unsafe_allow_html=True)

if not st.session_state["messages"]:
    st.markdown(
        '<div class="bot">Hello! 👋<br>Please enter a website URL to get started.</div>',
        unsafe_allow_html=True
    )

for msg in st.session_state["messages"]:
    css = "user" if msg["role"] == "user" else "bot"
    st.markdown(f'<div class="{css}">{msg["content"]}</div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

# ---------------- Auto-suggested questions UI ----------------
if st.session_state["website_url"] and st.session_state["suggested_questions"]:
    st.markdown(
        "<div style='padding:10px 15px; font-size:13px; color:#666;'>Suggested questions</div>",
        unsafe_allow_html=True
    )

    cols = st.columns(2)
    for i, question in enumerate(st.session_state["suggested_questions"]):
        if cols[i % 2].button(question, key=f"auto_suggest_{i}"):

            st.session_state["messages"].append({
                "role": "user",
                "content": question
            })

            with st.spinner("Thinking..."):
                answer = ask_ai(question, st.session_state["context"])

            st.session_state["messages"].append({
                "role": "bot",
                "content": answer
            })

            st.rerun()

# Input
st.markdown('<div class="chat-input">', unsafe_allow_html=True)

if not st.session_state["website_url"]:
    url = st.text_input("Website URL", placeholder="https://example.com", label_visibility="collapsed")

    if st.button("Load Website"):
        if not url.startswith("http"):
            st.warning("Please enter a valid website URL.")
        else:
            with st.spinner("Crawling website..."):
               context = crawl_website(url)
            st.session_state["context"] = context
            st.session_state["website_url"] = url
            if not st.session_state["suggested_questions"]:
                st.session_state["suggested_questions"] = generate_suggested_questions(context)
         
            st.session_state["messages"].append({
                "role": "bot",
                "content": (
                             "Nice! 👍 Website indexed successfully.\n\n"
                                f"**URL:** [{url}]({url})\n\n"
                            "Ask me anything about it."
                            )
                        })
            st.rerun()
else:
    with st.form("chat_form", clear_on_submit=True):
        user_input = st.text_input("Reply...", label_visibility="collapsed")
        send = st.form_submit_button("Send")

    if send and user_input.strip():
        st.session_state["messages"].append({
            "role": "user",
            "content": user_input
        })

        with st.spinner("Thinking..."):
            answer = ask_ai(user_input, st.session_state["context"])

        st.session_state["messages"].append({
            "role": "bot",
            "content": answer
        })

        st.rerun()


st.markdown('</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)


# ---------------- RFP Analysis & Download Excel----------------
if st.session_state["website_url"]:
    if st.button("📊 Generate RFP Analysis"):
        with st.spinner("Generating RFP-ready analysis..."):
            from ai_service import generate_rfp_analysis
            st.session_state["rfp_data"] = generate_rfp_analysis(
                st.session_state["context"]
            )
        st.success("RFP analysis ready!")

def generate_excel(rfp_data: dict):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:

        # ---------------- Overview ----------------
        pd.DataFrame([rfp_data.get("overview", {})]).to_excel(
            writer, sheet_name="Overview", index=False
        )

        # ---------------- Page Types ----------------
        page_types = pd.DataFrame(rfp_data.get("page_types", []))
        if not page_types.empty:
            page_types.to_excel(writer, sheet_name="Page Types", index=False)

        # ---------------- Components ----------------
        components = pd.DataFrame(rfp_data.get("components", []))
        if not components.empty:
            components.to_excel(writer, sheet_name="Components", index=False)

        # ---------------- Pages ----------------
        pages = pd.DataFrame(rfp_data.get("pages", []))
        if not pages.empty:
            pages.to_excel(writer, sheet_name="Pages", index=False)

        # ---------------- Third-party Integrations ----------------
        integrations = pd.DataFrame(
            rfp_data.get("third_party_integrations", [])
        )
        if not integrations.empty:
            integrations.to_excel(
                writer, sheet_name="Third Party Integrations", index=False
            )

        # ---------------- Recommendations ----------------
        recommendations = pd.DataFrame(
            rfp_data.get("recommendations", []),
            columns=["Recommendation"]
        )
        if not recommendations.empty:
            recommendations.to_excel(
                writer, sheet_name="Recommendations", index=False
            )

    output.seek(0)
    return output
     

if st.session_state.get("rfp_data"):
    excel_file = generate_excel(st.session_state["rfp_data"])

    st.download_button(
        label="📥 Download RFP Analysis (Excel)",
        data=excel_file,
        file_name="Website_RFP_Analysis.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


  
