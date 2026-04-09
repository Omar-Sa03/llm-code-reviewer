import os
import re
import json
from openai import OpenAI
from reviewer.prompt import SYSTEM_PROMPT, build_prompt

HF_ROUTER_URL = "https://router.huggingface.co/v1"

MODEL = "Qwen/Qwen2.5-Coder-32B-Instruct"


def _get_client() -> OpenAI:
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise EnvironmentError("HF_TOKEN environment variable is not set.")
    return OpenAI(
        base_url=HF_ROUTER_URL,
        api_key=token,
    )


def review_chunk(diff_content: str) -> list[dict]:
    
    client = _get_client()

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": build_prompt(diff_content)},
            ],
            max_tokens=1024,
            temperature=0.1,   
        )

        raw_text = response.choices[0].message.content or ""
        return _parse_json_response(raw_text.strip())

    except Exception as e:
        print(f"[llm_client] Error calling HF Inference Providers: {e}")
        return []


def _parse_json_response(text: str) -> list[dict]:
    
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()

    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        print(f"[llm_client] No JSON array found in response: {text[:200]}")
        return []

    try:
        issues = json.loads(match.group())
        if not isinstance(issues, list):
            return []

        valid = []
        required_keys = {"line", "severity", "category", "comment", "confidence"}
        for issue in issues:
            if required_keys.issubset(issue.keys()):
                issue["confidence"] = max(0.0, min(1.0, float(issue["confidence"])))
                valid.append(issue)

        return valid

    except json.JSONDecodeError as e:
        print(f"[llm_client] JSON parse error: {e} — raw: {text[:200]}")
        return []