import json
from openai import OpenAI
from app.config import settings

client = OpenAI(api_key=settings.openai_api_key)

def gpt_extract_job_metadata_from_html(html: str,prompt: str = None) -> dict:
    """
        Sends HTML to OpenAI to extract specific job fields.
        Supports dynamic prompts for only the missing fields.
        Returns parsed JSON and prints token cost.
        """
    if not prompt:
        prompt = f"""
You are an AI that extracts job information from raw HTML. 

Return a JSON object with these fields:
- title
- location 
- description
- responsibilities (as list)
- requirements (as list or string)
- posted_date (if mentioned)

Here's the page content:
---
{html[:4000]}  # Truncate for token safety
    """

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You extract structured job data from HTML."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )

        content = response.choices[0].message.content.strip("```json").strip("```")
        usage = response.usage

        pricing = {"input": 0.0005, "output": 0.0015}
        cost_usd = (
            usage.prompt_tokens * pricing["input"] +
            usage.completion_tokens * pricing["output"]
        ) / 1000

        print(f"💰 GPT used: {usage.total_tokens} tokens → Estimated cost: ${cost_usd:.5f}")
        return json.loads(content)

    except Exception as e:
        print(f"❌ GPT fallback failed: {e}")
        return {}
        return {}
