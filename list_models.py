import os
from dotenv import load_dotenv

load_dotenv('/home/e193752468/kkgroup/.env')
api_key = os.getenv("AI_API_KEY")

import google.generativeai as genai
genai.configure(api_key=api_key)

print("=== 可用的 Gemini 模型 ===")
for model in genai.list_models():
    if 'generateContent' in model.supported_generation_methods:
        print(f"✓ {model.name}")
