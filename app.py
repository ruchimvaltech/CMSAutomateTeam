import asyncio
import sys
import pandas as pd
from io import BytesIO

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
import streamlit as st
from crawler import crawl_website
from ai_service import ask_ai
from suggested_questions_service import get_suggested_questions

# ---------------- PAGE CONFIG ----------------
st.set_page_config(page_title="AI Website Chatbot", page_icon="🤖", layout="centered")

# ---------------- SESSION STATE ----------------
for key, default in {
    "sitemap_url": None,
    "context": "",
    "messages": [],
    "suggested_questions": []
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

if "rfp_data" not in st.session_state:
    st.session_state["rfp_data"] = None

if "suggested_questions" not in st.session_state:
    st.session_state["suggested_questions"] = []

if "messages" not in st.session_state:
    st.session_state["messages"] = []

if "context" not in st.session_state:
    st.session_state["context"] = ""    

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
        '<div class="bot">Hello! 👋<br>Please enter a website Sitemap URL to get started.</div>',
        unsafe_allow_html=True
    )

for msg in st.session_state["messages"]:
    css = "user" if msg["role"] == "user" else "bot"
    st.markdown(f'<div class="{css}">{msg["content"]}</div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)



# Input
st.markdown('<div class="chat-input">', unsafe_allow_html=True)

if not st.session_state["sitemap_url"]:
    # Crawl controls
    col_a, col_b = st.columns(2)
    with col_a:
        ui_max_pages = st.number_input("Max pages to crawl", min_value=50, max_value=5000, value=300, step=50)
    with col_b:
        ui_concurrency = st.number_input("Concurrent fetches", min_value=1, max_value=24, value=8, step=1)

    sitemap = st.text_input("Sitemap URL", placeholder="https://example.com/sitemap.xml", label_visibility="collapsed")

    if st.button("Load Sitemap"):
        if not sitemap.startswith("http"):
            st.warning("Please enter a valid sitemap URL.")
        else:
            with st.spinner("Crawling sitemap..."):
                context, crawled = asyncio.run(crawl_website(sitemap, max_pages=int(ui_max_pages), concurrency=int(ui_concurrency)))
            st.session_state["context"] = context
            st.session_state["crawled_urls"] = crawled
            st.session_state["sitemap_url"] = sitemap
            if not st.session_state["suggested_questions"]:
                st.session_state["suggested_questions"] = get_suggested_questions(context)

            st.session_state["messages"].append({
                "role": "bot",
                "content": (
                             "Nice! 👍 Sitemap indexed successfully.\n\n"
                                f"**Sitemap:** [{sitemap}]({sitemap})\n\n"
                            "Ask me anything about it."
                            )
                        })
            if crawled:
                st.session_state["messages"].append({
                    "role": "bot",
                    "content": f"Indexed representative URLs (showing up to 20 of {len(crawled)}):\n\n" + "\n".join(crawled[:20])
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

# ---------------- Auto-suggested questions UI ----------------
if st.session_state["suggested_questions"]:
    st.markdown("### Suggested RFP Questions")

    for i, q in enumerate(st.session_state["suggested_questions"]):
        if st.button(q["ui_label"], key=f"suggest_{i}"):

            # Show question in chat
            st.session_state["messages"].append({
                "role": "user",
                "content": q["ui_label"]
            })

            with st.spinner("Thinking..."):
                answer = ask_ai(
                    q["ai_prompt"],
                    st.session_state["context"]
                )

            st.session_state["messages"].append({
                "role": "bot",
                "content": answer
            })

            st.rerun()

# ---------------- RFP Analysis & Download Excel----------------
if st.session_state["sitemap_url"]:
    if st.button("📊 Generate RFP Analysis"):
        crawled_count = len(st.session_state.get("crawled_urls", []))
        
        # Show estimated time based on URL count
        if crawled_count <= 100:
            time_est = "~15-30 seconds"
        elif crawled_count <= 500:
            time_est = f"~{int(crawled_count/100) * 20} seconds - {int(crawled_count/100) * 40} seconds"
        else:
            time_est = f"~{int(crawled_count/80) * 20} seconds - {int(crawled_count/80) * 40} seconds"
        
        with st.spinner(f"Generating RFP analysis for {crawled_count} pages (est. {time_est})..."):
            from ai_service import generate_rfp_analysis
            # Automatic batch sizing based on URL count for optimal performance
            st.session_state["rfp_data"] = generate_rfp_analysis(
                st.session_state["context"],
                st.session_state.get("crawled_urls", []),
                batch_size=None  # Auto-adjust: 100 for <500, 80 for <1000, 50 for >1000
            )
        
        final_count = len(st.session_state["rfp_data"].get("pages", []))
        st.success(f"✅ RFP analysis complete! Analyzed {final_count} pages.")
        st.rerun()

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



