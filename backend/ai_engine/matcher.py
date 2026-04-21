import os
import re
import numpy as np
from enum import Enum
from typing import List, Dict, Optional, Tuple
from difflib import SequenceMatcher

# ==========================================
# CONFIGURATION & WEIGHTS
# ==========================================

# ⚠️ RESTORED CONSTANTS (Required by search.py)
SEMANTIC_WEIGHT = float(os.getenv("SEARCH_SEMANTIC_WEIGHT", "0.6"))
LEXICAL_WEIGHT = float(os.getenv("SEARCH_LEXICAL_WEIGHT", "0.4"))
DEFAULT_RESULT_LIMIT = int(os.getenv("SEARCH_RESULT_LIMIT", "20"))

# NEW THRESHOLDS
TIER_1_THRESHOLD = 0.82  # Bullseye (Strong match)
TIER_2_THRESHOLD = 0.55  # Ring (Good opportunity)

class MatchTier(Enum):
    BULLSEYE = "bullseye"
    RING = "ring"
    MISS = "miss"

class MatchResult:
    def __init__(self, tier: MatchTier, score: float, reason: str):
        self.tier = tier
        self.score = score
        self.reason = reason

    def __repr__(self):
        return f"<MatchResult tier={self.tier.value} score={self.score:.4f} reason='{self.reason}'>"

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    if not v1 or not v2: return 0.0
    a = np.array(v1)
    b = np.array(v2)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0: return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))

def normalize_string(s: str) -> str:
    """Removes spaces, punctuation, and casing for 'Speed Pass' matching."""
    if not s: return ""
    # Remove non-alphanumeric characters
    return re.sub(r'[^a-z0-9]', '', s.lower())

def evaluate_match(
    item_vector: List[float],
    alert_vector: List[float],
    item_price: Optional[float],
    alert_max_price: Optional[float],
    item_title: str,
    alert_query_text: Optional[str] = None
) -> MatchResult:
    """
    Cascading Logic:
    1. Price Check (Hard Filter)
    2. Speed Pass (Deterministic/Trigram-ish)
    3. Hybrid Score (Vector + Lexical)
    """
    
    # 1. Price Check
    if alert_max_price and item_price:
        if item_price > alert_max_price:
            return MatchResult(MatchTier.MISS, 0.0, f"Price {item_price} > {alert_max_price}")

    # 2. SPEED PASS (The "Trigram" Logic)
    # Checks if "iphone13" == "iphone 13" ignoring junk.
    if alert_query_text and item_title:
        norm_query = normalize_string(alert_query_text)
        norm_title = normalize_string(item_title)
        
        # Exact Normalized Match (e.g. "iphone13pro" in "brandnewiphone13pro")
        # Ensure query is substantial (>3 chars) to avoid matching "usb" in "bus"
        if len(norm_query) > 3 and norm_query in norm_title:
            return MatchResult(MatchTier.BULLSEYE, 1.0, "Speed Pass (Exact Normalized Match)")

    # 3. Hybrid Calculation
    semantic_sim = cosine_similarity(item_vector, alert_vector)
    
    lexical_sim = 0.0
    if alert_query_text and item_title:
        # Standard fuzzy ratio
        lexical_sim = SequenceMatcher(None, item_title.lower(), alert_query_text.lower()).ratio()

    # Weighted Score (Balanced)
    final_score = (semantic_sim * 0.5) + (lexical_sim * 0.5)

    # 4. Tier Classification
    if final_score >= TIER_1_THRESHOLD:
        return MatchResult(MatchTier.BULLSEYE, final_score, "Strong Hybrid Match")
    elif final_score >= TIER_2_THRESHOLD:
        return MatchResult(MatchTier.RING, final_score, "Moderate Hybrid Match")
    
    return MatchResult(MatchTier.MISS, final_score, "Score too low")