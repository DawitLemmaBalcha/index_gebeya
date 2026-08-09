import os
import json
import logging
import httpx 
from enum import Enum

logger = logging.getLogger("index_llm")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.1-8b-instant" 

class JudgeVerdict(Enum):
    """NB-20: tri-state LLM judge verdict — the orchestrator distinguishes
    a genuine REJECTION from an ERROR (fail-open) and APPROVAL.

    - APPROVED: 200 + valid JSON + `match: true`.
    - REJECTED: 200 + valid JSON + `match: false` OR a MISSING `match` key
      (fail-closed preserved — see the call-site comment).
    - ERRORED:  no key / non-200 / unparseable payload / exception — the
      orchestrator fail-OPENS and counts it for ops observability.
    """
    APPROVED = "approved"
    REJECTED = "rejected"
    ERRORED = "errored"

def verify_match_with_llm(item_title: str, alert_query: str, preferences: dict) -> JudgeVerdict:
    """
    Synchronous LLM Judge with 3-Scenario Logic.
    Decides which persona to adopt based on the user's strictness settings.
    """
    if not GROQ_API_KEY:
        logger.warning("⚠️ GROQ_API_KEY missing. Skipping LLM verification.")
        return JudgeVerdict.ERRORED

    strict_brand = preferences.get("strict_brand", False)
    strict_model = preferences.get("strict_model", False)

    # ---------------------------------------------------------
    # SCENARIO B: STRICT MODEL (Highest Specificity)
    # ---------------------------------------------------------
    if strict_model:
        system_prompt = (
            "You are a specific Product Verification Agent. "
            "The user wants a EXACT MATCH for a specific model. "
            "Reject the item if the model number, generation, or variant is different.\n"
            "Output ONLY JSON: {\"match\": true} or {\"match\": false}."
        )
        constraints = (
            f"- EXACT MATCH: The item must be '{alert_query}'.\n"
            f"- MODEL CHECK: 'iPhone 13' != 'iPhone 12', 'S22' != 'S22 Ultra'.\n"
            f"- BRAND CHECK: Must match exactly."
        )
        mode_log = "Strict Model"

    # ---------------------------------------------------------
    # SCENARIO A: STRICT BRAND (Brand Guard, Model Flexible)
    # ---------------------------------------------------------
    elif strict_brand:
        system_prompt = (
            "You are a Brand Guardian Agent. "
            "The user wants a specific BRAND, but is open to different MODELS.\n"
            "Output ONLY JSON: {\"match\": true} or {\"match\": false}."
        )
        constraints = (
            f"- BRAND CHECK: The item must be from the brand mentioned in '{alert_query}'.\n"
            f"- MODEL FLEXIBILITY: You CAN match different models (e.g. User: 'iPhone 13' -> Item: 'iPhone 14' is OK).\n"
            f"- CATEGORY CHECK: Must be the same product type (e.g. Don't match a Phone Case if user wants a Phone)."
        )
        mode_log = "Strict Brand"

    # ---------------------------------------------------------
    # SCENARIO C: LOOSE (Category/Intent Match)
    # ---------------------------------------------------------
    else:
        system_prompt = (
            "You are a Category Intent Agent. "
            "The user is looking for a TYPE of product. "
            "Brand and Model can vary, but the INTENT must match.\n"
            "Output ONLY JSON: {\"match\": true} or {\"match\": false}."
        )
        constraints = (
            f"- CATEGORY MATCH: If user wants '{alert_query}' (e.g. 'Blender'), accept any brand (Philips, Geepas, etc).\n"
            f"- REJECT ACCESSORIES: If user wants a 'Phone', reject 'Phone Case'.\n"
            f"- REJECT PARTS: If user wants a 'Laptop', reject 'Laptop Screen'."
        )
        mode_log = "Category Match"

    user_prompt = (
        f"USER SEARCH: '{alert_query}'\n"
        f"ITEM FOUND: '{item_title}'\n\n"
        f"VERIFICATION RULES:\n{constraints}\n\n"
        "Is this a valid match?"
    )

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"}
    }

    with httpx.Client(timeout=10.0) as client:
        try:
            response = client.post(
                GROQ_URL, 
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"}, 
                json=payload
            )
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    content = data['choices'][0]['message']['content']
                    result = json.loads(content)
                except Exception:
                    logger.error(f"💥 LLM Client Exception: unparseable judge payload for '{alert_query}'")
                    return JudgeVerdict.ERRORED

                if not isinstance(result, dict):
                    logger.error(f"💥 LLM Client Exception: judge payload is not a JSON object for '{alert_query}'")
                    return JudgeVerdict.ERRORED

                logger.info(f"🤖 LLM Verdict: {result.get('match')} | Mode: {mode_log} | Query: '{alert_query}' vs Item: '{item_title}'")

                if "match" not in result:
                    # NB-20: the pre-tri-state code read result.get("match",
                    # False) — a 200 with a MISSING `match` key fail-CLOSED.
                    # Mapped to REJECTED so match outcomes never change (only
                    # logging granularity and the ops counter differ).
                    return JudgeVerdict.REJECTED
                if result.get("match"):
                    return JudgeVerdict.APPROVED
                return JudgeVerdict.REJECTED
            else:
                logger.error(f"❌ LLM Error {response.status_code}: {response.text}")
                return JudgeVerdict.ERRORED # Fail open if LLM is down
                
        except Exception as e:
            logger.error(f"💥 LLM Client Exception: {e}")
            return JudgeVerdict.ERRORED