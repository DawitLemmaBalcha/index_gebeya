import os
import requests
import json
import re
from .prompts import SYSTEM_PROMPT_TEXT
from .guardrails import gemini_limiter

API_KEY = os.getenv("GEMINI_API_KEY")
# Targeting the Lite model for better stability
URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={API_KEY}"

def extract_multimodal(text: str, image_path: str = None):
    """
    Uses Google Gemini for requests requiring vision capabilities or as backup.
    """
    if not API_KEY:
        print("❌ Gemini API Key missing!")
        return None

    gemini_limiter.enforce()

    # Base payload (Text Only for now - logic ready for Image expansion)
    payload = {
        "contents": [{
            "parts": [
                {"text": SYSTEM_PROMPT_TEXT},
                {"text": f"Analyze this post:\n{text}"}
            ]
        }],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1
        }
    }

    try:
        headers = {"Content-Type": "application/json"}
        response = requests.post(URL, json=payload, headers=headers, timeout=60)
        
        if response.status_code != 200:
            print(f"❌ Gemini API Error {response.status_code}: {response.text}")
            return None

        result = response.json()
        
        try:
            raw_text = result['candidates'][0]['content']['parts'][0]['text']
        except (KeyError, IndexError):
            print(f"❌ AI Response Malformed: {result}")
            return None

        clean_json = re.sub(r"```json|```", "", raw_text).strip()
        return json.loads(clean_json)

    except Exception as e:
        print(f"⚠️ Gemini Engine Exception: {e}")
        return None