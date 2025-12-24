import asyncio
import sys

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
import streamlit as st
from crawler import crawl_website
from ai_service import ask_ai

# ---------------- PAGE CONFIG ----------------
st.set_page_config(page_title="AI Website Chatbot", page_icon="🤖", layout="centered")

# ---------------- SESSION STATE ----------------
for key, default in {
    "website_url": None,
    "context": "",
    "messages": []
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

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

# Input
st.markdown('<div class="chat-input">', unsafe_allow_html=True)

if not st.session_state["website_url"]:
    url = st.text_input("Website URL", placeholder="https://example.com", label_visibility="collapsed")

    if st.button("Load Website"):
        if not url.startswith("http"):
            st.warning("Please enter a valid website URL.")
        else:
            with st.spinner("Crawling website..."):
                st.session_state["context"] = asyncio.run(crawl_website(url))
                st.session_state["website_url"] = url
                st.session_state["messages"].append({
                    "role": "bot",
                    "content": "Nice! 👍 Website indexed. Ask me anything about it."
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
