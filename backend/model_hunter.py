import os
import requests
import json

API_KEY = os.getenv("GEMINI_API_KEY")

# The list of suspects (from your previous logs + standard stable ones)
CANDIDATES = [
    "gemini-2.0-flash-lite-preview-02-05", # Specific preview often works when general alias fails
    "gemini-2.0-flash",
    "gemini-1.5-flash", 
    "gemini-1.5-flash-latest",
    "gemini-1.5-pro-latest",
    "gemini-pro"
]

print(f"--- 🏹 HUNTING FOR WORKING MODEL (Key: {API_KEY[:5]}...) ---\n")

working_model = None

for model in CANDIDATES:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}"
    
    payload = {
        "contents": [{"parts": [{"text": "Reply with 'OK'."}]}]
    }
    
    try:
        print(f"👉 Testing: {model} ...", end=" ", flush=True)
        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
        
        if response.status_code == 200:
            print("✅ SUCCESS!")
            print(f"   Response: {response.json().get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', 'No text')}")
            working_model = model
            break # STOP AT THE FIRST WORKING ONE
        else:
            print(f"❌ FAILED ({response.status_code})")
            # Print the specific error message to see if it's 'limit: 0'
            err = response.json().get('error', {}).get('message', 'Unknown error')
            print(f"   Reason: {err[:100]}...") # Truncate for readability

    except Exception as e:
        print(f"⚠️ ERROR: {e}")

print("\n------------------------------------------------")
if working_model:
    print(f"🏆 WINNER: {working_model}")
    print("Update your ai_engine.py URL to use this model!")
else:
    print("💀 ALL MODELS FAILED. Check your Region/IP or Billing status.")