import os
from dotenv import load_dotenv

load_dotenv()  # loads .env into environment variables
from openai import OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in .env")
client = OpenAI(api_key=OPENAI_API_KEY)


def ask_ai(user_question, website_context):
    system_prompt = """
You are an expert UI/UX analyst and CMS architect.

You have been given structured content extracted from a website.
This content represents the COMPLETE and TRUSTED source of truth.

Your job:
- Analyze the website structure
- Identify page types, components, layouts, and patterns
- Infer reasonable conclusions even if labels are not explicit

IMPORTANT RULES:
- NEVER say "I don't know" if the information can be inferred
- If something is not explicitly stated, say "Based on the structure, it appears that..."
- Answer ONLY using the provided website context
- Be concise, structured, and confident
"""

    user_prompt = f"""
WEBSITE CONTENT:
----------------
{website_context}
----------------

USER QUESTION:
{user_question}

INSTRUCTIONS:
- Answer specifically about this website
- List components or page types when applicable
- Use bullet points if helpful
- Do not repeat the question
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",  # or gpt-4.1 if available
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2
    )

    return response.choices[0].message.content
