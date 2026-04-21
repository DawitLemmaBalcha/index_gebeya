import os
import requests
import json

API_KEY = os.getenv("GOOGLE_API_KEY")
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

print(f"--- 🕵️ FINAL DIAGNOSTIC ---")

# 1. Try gemini-1.5-flash (The one we want)
print("\n[TEST 1] Hitting gemini-1.5-flash...")
url = f"{BASE_URL}/models/gemini-1.5-flash:generateContent?key={API_KEY}"
headers = {"Content-Type": "application/json"}
payload = {"contents": [{"parts": [{"text": "Hello"}]}]}

try:
    response = requests.post(url, headers=headers, json=payload)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print("✅ gemini-1.5-flash is WORKING! (We should use this)")
    else:
        print(f"❌ gemini-1.5-flash Failed. Reason:\n{response.text}")
except Exception as e:
    print(f"❌ Connection Error: {e}")

# 2. List Models (To see what IS available)
print("\n[TEST 2] Listing All Available Models for your Key...")
url = f"{BASE_URL}/models?key={API_KEY}"
try:
    response = requests.get(url)
    if response.status_code == 200:
        models = response.json().get('models', [])
        print(f"Found {len(models)} models.")
        found_flash = False
        for m in models:
            # Only show models that can generate text
            if 'generateContent' in m.get('supportedGenerationMethods', []):
                print(f" - {m['name']}")
                if 'flash' in m['name']:
                    found_flash = True
        
        if not found_flash:
            print("\n⚠️ WARNING: No 'Flash' models found in your list!")
    else:
        print(f"❌ Could not list models: {response.text}")
except Exception as e:
    print(f"❌ Connection Error: {e}")

print("--- END ---")
