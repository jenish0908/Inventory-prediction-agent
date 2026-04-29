from groq import AsyncGroq
from app.config import settings

# Groq client — free tier, no billing required
groq_client = AsyncGroq(api_key=settings.groq_api_key)
