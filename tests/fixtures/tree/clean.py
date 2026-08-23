from openai import OpenAI

client = OpenAI()


def answer(question):
    response = client.responses.create(
        model="gpt-5.5",
        input=[{"role": "user", "content": question}],
        tools=[{"type": "file_search", "vector_store_ids": ["vs_existing"]}],
    )
    return response.output_text
