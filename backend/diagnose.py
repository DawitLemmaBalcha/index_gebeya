import os
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List

# 1. Setup
api_key = os.getenv("GOOGLE_API_KEY")
print(f"--- DIAGNOSTIC START ---")
print(f"API Key found: {'Yes' if api_key else 'NO'}")
if api_key:
    print(f"Key starts with: {api_key[:5]}...")

client = genai.Client(api_key=api_key)

# 2. Test Basic Connectivity (No Schema)
print("\n[TEST 1] Basic Connection to gemini-1.5-flash...")
try:
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents="Are you online? Reply with 'Yes'."
    )
    print(f"✅ Success! Response: {response.text}")
except Exception as e:
    print(f"❌ Connection Failed: {e}")

# 3. Test Schema Generation
print("\n[TEST 2] Schema Strictness...")
class TestItem(BaseModel):
    name: str
    price: int

try:
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents="Extract: Apple, 10 birr",
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TestItem
        )
    )
    print(f"✅ Schema Success! Response: {response.text}")
except Exception as e:
    print(f"❌ Schema Failed: {e}")
    
print("--- DIAGNOSTIC END ---")
