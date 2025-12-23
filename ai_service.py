from openai import OpenAI

client = OpenAI(api_key="YOUR_OPENAI_API_KEY")


def ask_ai(question: str, context: str) -> str:
    """
    Answers user questions strictly based on website context.
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. "
                    "Answer ONLY using the website content provided. "
                    "If the answer is not available, say you don't know."
                )
            },
            {"role": "system", "content": context},
            {"role": "user", "content": question}
        ],
        temperature=0.2
    )

    return response.choices[0].message.content
