const ASSISTANT_ID = process.env.OPENAI_ASSISTANT_ID;

async function ask(question) {
  const res = await fetch("https://api.openai.com/v1/threads/" + threadId + "/messages", {
    method: "POST",
    body: JSON.stringify({ role: "user", content: question }),
  });
  return res.json();
}
