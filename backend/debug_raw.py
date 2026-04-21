import os
import requests
import json

# 1. Setup
API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL = "gemini-2.0-flash-exp"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"

print(f"--- 🕵️ DEBUGGING RAW REQUEST ---")
print(f"Target URL: ...models/{MODEL}:generateContent")
print(f"API Key Present: {'YES' if API_KEY else 'NO'}")

# 2. Test Simple Connection (No Schema)
print("\n[TEST 1] Sending simple 'Hello'...")
headers = {"Content-Type": "application/json"}
simple_payload = {
    "contents": [{"parts": [{"text": "Reply with one word: Online"}]}]
}

try:
    response = requests.post(URL, headers=headers, json=simple_payload)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print(f"✅ Success! Response: {response.json()['candidates'][0]['content']['parts'][0]['text']}")
    else:
        print(f"❌ Failed! Body:\n{response.text}")
except Exception as e:
    print(f"❌ Connection Error: {e}")

# 3. Test Schema Structure
print("\n[TEST 2] Testing Schema...")
schema_payload = {
    "contents": [{"parts": [{"text": "Extract: Apple, 100 ETB"}]}],
    "generationConfig": {
        "response_mime_type": "application/json",
        "response_schema": {
            "type": "OBJECT",
            "properties": {
                "item_name": {"type": "STRING"},
                "price": {"type": "INTEGER"}
            }
        }
    }
}

try:
    response = requests.post(URL, headers=headers, json=schema_payload)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print(f"✅ Schema Success! Response:\n{response.text}")
    else:
        print(f"❌ Schema Failed! Body:\n{response.text}")
except Exception as e:
    print(f"❌ Connection Error: {e}")

print("--- DEBUG END ---")
