"""
Run this to see every model available for your API key.
Usage:  docker-compose exec app python -m scripts.list_models
"""
import asyncio
import httpx
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import settings

API_KEY = settings.gemini_api_key
BASE = "https://generativelanguage.googleapis.com"


async def list_models():
    async with httpx.AsyncClient(timeout=15) as client:
        for version in ["v1", "v1beta"]:
            print(f"\n=== {version} models that support generateContent ===")
            try:
                r = await client.get(f"{BASE}/{version}/models", params={"key": API_KEY})
                data = r.json()
                if "error" in data:
                    print(f"  ERROR: {data['error']['message']}")
                    continue
                found = [
                    m for m in data.get("models", [])
                    if "generateContent" in m.get("supportedGenerationMethods", [])
                ]
                if not found:
                    print("  (none found)")
                for m in found:
                    print(f"  {m['name']}")
            except Exception as e:
                print(f"  Request failed: {e}")


asyncio.run(list_models())
