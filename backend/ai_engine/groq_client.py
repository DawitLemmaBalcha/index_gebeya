import os
import requests
import json
from .prompts import SYSTEM_PROMPT_TEXT
from .guardrails import groq_limiter
from typing import List, Optional

API_KEY = os.getenv("GROQ_API_KEY")
URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.1-8b-instant"

def extract_text_only(text: str, visual_hints: Optional[List[str]] = None):
    """
    Uses Groq Llama 3.1 8B for fast, high-volume text extraction.
    Supports 'Visual Hinting' via the visual_hints parameter.
    """
    if not API_KEY:
        print("❌ Groq API Key missing!")
        return None

    groq_limiter.enforce()

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    # Construct the hint string
    hint_text = ""
    if visual_hints:
        hint_text = f"\n\n[VISUAL ANALYSIS HINT]\nThe image associated with this post visually resembles these categories: {', '.join(visual_hints)}.\nUse this hint to resolve ambiguity if the text is unclear."

    # Reinforcement Block
    reinforcement = """
    CRITICAL INSTRUCTIONS:
    1. Output strictly valid JSON.
    2. Use ONLY the categories from the Taxonomy Dictionary provided in the system prompt.
    3. If unsure, use 'Other' -> 'Uncategorized'.
    4. Do not include any conversational text, only the JSON object.
    """

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT_TEXT},
            # Sandwich: Text + Visual Hints + Reinforcement
            {"role": "user", "content": f"Analyze this post:\n{text}{hint_text}\n\n{reinforcement}"}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1
    }

    try:
        response = requests.post(URL, headers=headers, json=payload, timeout=30)
        
        if response.status_code != 200:
            print(f"❌ Groq API Error {response.status_code}: {response.text}")
            return None

        result = response.json()
        content = result['choices'][0]['message']['content']
        
        return json.loads(content)

    except Exception as e:
        print(f"⚠️ Groq Engine Exception: {e}")
        return None