import asyncio
import sys
import pandas as pd
from io import BytesIO
from dotenv import load_dotenv
load_dotenv(override=True)  # This reloads .env file each time

# Handle asyncio event loops for Streamlit compatibility
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import nest_asyncio
nest_asyncio.apply()  # Allow nested event loops for Streamlit

# Ensure Playwright browsers are installed on startup
import subprocess
import os
try:
    # Check if browsers are already installed
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        pass
except Exception:
    # If browsers not found, install them
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], 
                      check=True, capture_output=True, timeout=300)
    except Exception as e:
        print(f"Warning: Could not install Playwright browsers: {e}")
    
import streamlit as st
from crawler import crawl_website
from ai_service import ask_ai, generate_suggested_questions
from suggested_questions_service import get_suggested_questions

import base64
from pathlib import Path

def img_to_base64(relative_path: str) -> str:
    """
    Convert local image to base64 string for Streamlit HTML embedding
    """
    img_path = Path(__file__).parent / relative_path
    if not img_path.exists():
        raise FileNotFoundError(f"Image not found: {img_path}")

    return base64.b64encode(img_path.read_bytes()).decode("utf-8")
#--FE changes end--#

# ---------------- PAGE CONFIG ----------------
st.set_page_config(page_title="CMS AutomateX Team", page_icon="🤖", layout="centered")

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

# ---------------- CSS (external file) ----------------

from pathlib import Path
# Load external CSS (Tailwind + custom overrides) from assets/theme.css

css_path = Path(__file__).parent / "assets" / "theme.css"
if css_path.exists():
    with open(css_path, "r", encoding="utf-8") as f:
        css_content = f.read()
    st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)
else:
    # Fallback: minimal styles if assets file is missing
    st.markdown(
        """
        <style>
        .fallback-container{display:flex;justify-content:center}
        </style>
        """,
        unsafe_allow_html=True,
    )

# ---------------- UI ----------------

# logo and title
st.markdown(
    """
<div class="flex justify-center logo-container">
  <h2 class="text-2xl font-bold tracking-wide text-gray-800">
    CMS AutomateX Team
  </h2>
</div>
""",
    unsafe_allow_html=True,
)

# ---------------- BANNER ----------------
img_base64 = img_to_base64("assets/banner.png")

st.markdown(
    f"""
    <div class="mx-auto bg-white p-4 flex flex-col lg:flex-row gap-8 my-6">
        <div>
            <img class="w-full rounded" src="data:image/png;base64,{img_base64}" alt="hero">
        </div>
        <div>
            <h3 class="font-bold text-xl mb-3">
                CMSAutomateX — Automated RFP Analysis & Component Mapping
            </h3>
            <p class="text-gray-600">
                Automated RFP analysis tool that inspects a website (URL index / sitemap)
                and produces a structured RFP-ready output focused on page types,
                exhaustive UX-led component identification, and third-party integration detection.
            </p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if not st.session_state["messages"]:
    st.markdown(
        '<div class="inline-block bg-gray-200 text-gray-800 p-3 rounded-lg mb-2 max-w-4/5 website-sitemap>Hello! 👋<br>Please enter a website Sitemap URL to get started.</div>',
        unsafe_allow_html=True
    )

for msg in st.session_state["messages"]:
    if msg["role"] == "user":
        st.markdown(f'<div class="ml-auto bg-indigo-600 text-white p-3 rounded-lg mb-2 max-w-4/5">{msg["content"]}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="bg-gray-200 text-gray-800 p-3 rounded-lg mb-2 max-w-4/5 website-sitemap">{msg["content"]}</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)



# Input
st.markdown('<div class="p-3 border-t bg-white">', unsafe_allow_html=True)

if not st.session_state["sitemap_url"]:
    # Crawl controls
    col_a, col_b = st.columns(2)
    with col_a:
        ui_max_pages = st.number_input("Max pages to crawl", min_value=50, max_value=5000, value=300, step=50)
    with col_b:
        ui_concurrency = st.number_input("Concurrent fetches", min_value=1, max_value=24, value=8, step=1)

    render_js = st.checkbox("Render JS (Playwright)", help="Enable for SPA/JS-heavy sites. Slower but captures dynamic content.", value=False)

    sitemap = st.text_input("Sitemap URL", placeholder="https://example.com/sitemap.xml", label_visibility="collapsed")

    if st.button("Load Sitemap"):
        if not sitemap.startswith("http"):
            st.warning("Please enter a valid sitemap URL.")
        else:
            with st.spinner("Crawling sitemap..."):
                context, crawled = asyncio.run(crawl_website(
                    sitemap,
                    max_pages=int(ui_max_pages),
                    concurrency=int(ui_concurrency),
                    render_js=bool(render_js)
                ))
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
    st.markdown("### Suggested Questions")

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
        
        # Validation: ensure we have crawled URLs
        if not st.session_state.get("context"):
            st.error("❌ No context available. Please crawl a sitemap first.")
        elif crawled_count == 0:
            st.error("❌ No URLs found. Please ensure the sitemap crawl was successful and returned pages.")
        # Show estimated time based on URL count
        elif crawled_count <= 100:
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
            # Derive per-page-type component list and add as 'component' and 'components_reusable' columns
            try:
                pt_to_components: dict[str, set] = {}
                for p in rfp_data.get("pages", []) or []:
                    pt = (p.get("page_type") or "").strip()
                    comps = [c.strip() for c in (p.get("components", []) or []) if isinstance(c, str) and c.strip()]
                    if not pt:
                        continue
                    if pt not in pt_to_components:
                        pt_to_components[pt] = set()
                    pt_to_components[pt].update(comps)

                # Compute reuse across page types
                comp_to_pts: dict[str, set] = {}
                for pt_name, comps in pt_to_components.items():
                    for c in comps:
                        comp_to_pts.setdefault(c, set()).add(pt_name)
                reusable_set = {c for c, pts in comp_to_pts.items() if len(pts) > 1}

                def _components_for_pt(name: str) -> str:
                    if not isinstance(name, str) or not name:
                        return ""
                    comps = sorted(pt_to_components.get(name, set()))
                    return ", ".join(comps)

                def _components_reusable_for_pt(name: str) -> str:
                    if not isinstance(name, str) or not name:
                        return ""
                    comps = sorted(pt_to_components.get(name, set()) & reusable_set)
                    return ", ".join(comps)

                page_types = page_types.copy()
                page_types["component"] = page_types.get("name").apply(_components_for_pt)
                page_types["components_reusable"] = page_types.get("name").apply(_components_reusable_for_pt)
            except Exception:
                # If anything fails, still export the base page types
                pass

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



