import os
import re
import json
import time
import requests
from reviewer.prompt import SYSTEM_PROMPT, build_prompt

HF_API_URL = (
    "https://api-inference.huggingface.co/models/"
    "mistralai/Mistral-7B-Instruct-v0.3"
)
MAX_RETRIES = 3
RETRY_DELAY = 20  


def review_chunk(diff_content: str) -> list[dict]:

    token = os.environ.get("HF_TOKEN")
    if not token:
        raise EnvironmentError("HF_TOKEN environment variable is not set.")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    formatted_prompt = (
        f"[INST] {SYSTEM_PROMPT}\n\n{build_prompt(diff_content)} [/INST]"
    )

    payload = {
        "inputs": formatted_prompt,
        "parameters": {
            "max_new_tokens": 1024,
            "temperature": 0.1,        
            "return_full_text": False,  
            "do_sample": True,
        },
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                HF_API_URL,
                headers=headers,
                json=payload,
                timeout=60,
            )

            if response.status_code == 503:
                print(f"[llm_client] Model loading, retrying in {RETRY_DELAY}s "
                      f"(attempt {attempt}/{MAX_RETRIES})...")
                time.sleep(RETRY_DELAY)
                continue

            response.raise_for_status()
            data = response.json()

            raw_text = data[0]["generated_text"].strip()
            return _parse_json_response(raw_text)

        except requests.exceptions.Timeout:
            print(f"[llm_client] Request timed out (attempt {attempt}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES:
                time.sleep(5)
        except requests.exceptions.RequestException as e:
            print(f"[llm_client] Request error: {e}")
            break

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