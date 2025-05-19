import json
from bs4 import BeautifulSoup
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



def summarize_job_description(job_title: str, company_name: str, html_description: str, model="gpt-4") -> str:
    """
    Summarize a job description into a friendly paragraph using OpenAI API.

    Args:
        job_title (str): e.g., "Senior Backend Developer"
        company_name (str): e.g., "Wix"
        html_description (str): raw HTML job description from site
        model (str): OpenAI model to use (default: "gpt-4")

    Returns:
        str: A clean, human-readable summary paragraph
    """
    try:
        # Step 1: Convert HTML to plain text
        soup = BeautifulSoup(html_description, "html.parser")
        plain_text = soup.get_text(separator="\n", strip=True)

        # Step 2: Build prompt
        prompt = f"""
            Summarize the following job posting into a clear and friendly paragraph (max 200 words).
Mention that it's for the role of "{job_title}" at "{company_name}".
            Include what the company does, what the role involves, and what kind of candidate would be a good fit.
            Write for a job seeker browsing job listings.
            Do not include any bullet points, formatting, or headings — return just one paragraph.

Job Description:
{plain_text}
""".strip()

        # Step 3: Call OpenAI
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes job listings for job seekers."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=400
        )

        # Step 4: Extract result
        usage = response.usage
        if model == "gpt-4":
            pricing = {"input": 0.03, "output": 0.06}
        elif model == "gpt-4-turbo":
            pricing = {"input": 0.01, "output": 0.03}
        else:
            pricing = {"input": 0.0015, "output": 0.002}

        cost_usd = (
            usage.prompt_tokens * pricing["input"] +
            usage.completion_tokens * pricing["output"]
        ) / 1000

        print(f"💰 GPT used: {usage.total_tokens} tokens → Estimated cost: ${cost_usd:.5f}")

        # ✅ Correct way to access content
        summary = response.choices[0].message.content.strip()
        return summary

    except Exception as e:
        print(f"❌ Error summarizing job description: {e}")
        return ""

      