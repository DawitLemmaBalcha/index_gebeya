import requests
import json

# Your VPS API URL (use localhost if running from inside VPS, or public IP from laptop)
# Since we are running this ON the VPS, we can use localhost:8000
API_URL = "http://localhost:8000/parse-telegram-post"

payload = {
    "post_text": "Test Item with Image. Price 500 ETB. Location Test.",
    "image_path": "test_image_123.jpg" 
}

print(f"--- 🧪 Testing Image Path Save ---")
print(f"Sending payload: {json.dumps(payload, indent=2)}")

try:
    response = requests.post(API_URL, json=payload)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print(f"✅ Success! Response: {response.json()}")
    else:
        print(f"❌ Failed! Body: {response.text}")
except Exception as e:
    print(f"❌ Connection Error: {e}")
