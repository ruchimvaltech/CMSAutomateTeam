import streamlit as st

# ------------------ PAGE CONFIG ------------------
st.set_page_config(
    page_title="AI Website Chatbot",
    page_icon="🤖",
    layout="centered"
)

# ------------------ SESSION STATE ------------------
if "website_url" not in st.session_state:
    st.session_state["website_url"] = None

if "messages" not in st.session_state:
    st.session_state["messages"] = []

# ------------------ UI ------------------
st.title("🤖 AI Website Chatbot")

st.write(
    """
    **Hello! 👋**  
    I can chat with you about any website.

    👉 **Please enter a website URL to begin.**
    """
)

# ------------------ URL INPUT ------------------
url = st.text_input(
    "Website URL",
    placeholder="https://example.com"
)

if st.button("Load Website"):
    if not url.startswith("http"):
        st.error("Please enter a valid website URL.")
    else:
        st.session_state["website_url"] = url
        st.session_state["messages"] = []
        st.success("Website loaded successfully! You can start chatting below.")

st.divider()

# ------------------ CHAT UI ------------------
if st.session_state["website_url"]:
    st.subheader("💬 Chat")

    for msg in st.session_state["messages"]:
        st.chat_message(msg["role"]).markdown(msg["content"])

    user_input = st.chat_input("Ask something about the website...")
    if user_input:
        st.session_state["messages"].append(
            {"role": "user", "content": user_input}
        )
        st.chat_message("user").markdown(user_input)

        # Placeholder AI reply (replace later with real AI)
        ai_reply = "🤖 I’m ready! Website crawling & AI logic will go here."

        st.session_state["messages"].append(
            {"role": "assistant", "content": ai_reply}
        )
        st.chat_message("assistant").markdown(ai_reply)