# Absolute imports are safer in Docker
from ai_engine.groq_client import extract_text_only
from ai_engine.gemini_client import extract_multimodal
from typing import List, Optional

def extract_product_info(text: str, image_path: str = None, visual_hints: Optional[List[str]] = None):
    """
    Hybrid Router:
    1. Default: Sends to Groq (Fastest).
       - Injects 'visual_hints' (from CLIP analysis) to guide the LLM.
    2. Fallback: If Groq fails, try Gemini (Multimodal/Backup).
    """
    
    print("🤖 AI Router: Routing to Groq (Primary)...")
    
    # Pass the visual hints to Groq if available
    result = extract_text_only(text, visual_hints=visual_hints)
    
    if result:
        return result
        
    print("⚠️ Groq failed or returned empty. Failing over to Gemini (Backup)...")
    # Gemini analyzes the image natively, so it doesn't need hints
    return extract_multimodal(text, image_path)