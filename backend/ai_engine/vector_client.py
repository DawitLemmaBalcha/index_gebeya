from fastembed import ImageEmbedding, TextEmbedding
import os
import numpy as np
from typing import List, Dict

# Import the taxonomy structure to vectorize it
from .prompts import TAXONOMY_STRUCTURE

TEXT_MODEL_NAME = "Qdrant/clip-ViT-B-32-text"
IMAGE_MODEL_NAME = "Qdrant/clip-ViT-B-32-vision"

_text_model = None
_image_model = None
CACHE_PATH = os.path.join(os.getcwd(), "model_cache")

# --- VISUAL HINTING CACHE ---
# Stores { "Headphones": [vector], "Cars": [vector] }
_taxonomy_vectors: Dict[str, np.ndarray] = {}

def get_text_model():
    global _text_model
    if _text_model is None:
        print(f"📥 Loading Text Model: {TEXT_MODEL_NAME}...")
        os.makedirs(CACHE_PATH, exist_ok=True)
        _text_model = TextEmbedding(model_name=TEXT_MODEL_NAME, cache_dir=CACHE_PATH)
        print("✅ Text Model Loaded!")
    return _text_model

def get_image_model():
    global _image_model
    if _image_model is None:
        print(f"📥 Loading Image Model: {IMAGE_MODEL_NAME}...")
        os.makedirs(CACHE_PATH, exist_ok=True)
        _image_model = ImageEmbedding(model_name=IMAGE_MODEL_NAME, cache_dir=CACHE_PATH)
        print("✅ Image Model Loaded!")
    return _image_model

def vectorize_text(text: str) -> list[float]:
    try:
        model = get_text_model()
        embeddings = model.embed([text])
        vec = next(embeddings)
        
        if len(vec.shape) > 1:
            vec = vec.flatten()
            
        return vec.tolist()
    except Exception as e:
        print(f"❌ Text Vectorization Error: {e}")
        return None

def vectorize_image(image_path: str) -> list[float]:
    try:
        if not os.path.exists(image_path):
            return None
            
        model = get_image_model()
        embeddings = model.embed([image_path])
        vec = next(embeddings)
        
        if len(vec.shape) > 1:
            vec = vec.flatten()

        return vec.tolist()
    except Exception as e:
        print(f"❌ Image Vectorization Error: {e}")
        return None

# --- NEW: VISUAL HINTING LOGIC ---

def initialize_taxonomy_index():
    """
    Runs on startup. Pre-calculates vectors for every Subcategory in the Taxonomy.
    This allows us to instantly check what an image 'looks like' mathematically.
    """
    global _taxonomy_vectors
    if _taxonomy_vectors:
        return # Already initialized

    print("🧠 Initializing Visual Taxonomy Index...")
    model = get_text_model()
    
    # Flatten the taxonomy into a list of strings for batch embedding
    # Format: "MainCategory - Subcategory" (Context helps specificity)
    labels = []
    flat_keys = []
    
    for main_cat, subs in TAXONOMY_STRUCTURE.items():
        for sub in subs:
            # We encode "Electronics Headphones" to give context, but map it to "Headphones"
            labels.append(f"{main_cat} {sub}") 
            flat_keys.append(sub)

    try:
        # Batch embed all subcategories at once (much faster)
        embeddings = list(model.embed(labels))
        
        for i, vec in enumerate(embeddings):
            if len(vec.shape) > 1:
                vec = vec.flatten()
            # Store the vector mapped to the Subcategory Name
            _taxonomy_vectors[flat_keys[i]] = vec
            
        print(f"✅ Taxonomy Index Ready: {len(_taxonomy_vectors)} categories cached.")
    except Exception as e:
        print(f"❌ Failed to initialize Taxonomy Index: {e}")

def get_visual_hints(image_vector: list[float], top_k: int = 3) -> List[str]:
    """
    Compares an Image Vector against the known Taxonomy Vectors.
    Returns the names of the top_k matching subcategories.
    """
    if not _taxonomy_vectors or not image_vector:
        return []

    query_vec = np.array(image_vector)
    scores = []

    for subcategory, cat_vec in _taxonomy_vectors.items():
        # Cosine Similarity
        score = np.dot(query_vec, cat_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(cat_vec))
        scores.append((score, subcategory))

    # Sort by score descending
    scores.sort(key=lambda x: x[0], reverse=True)
    
    # Return the top K names (e.g. ['Headphones', 'Audio Equipment', 'Gaming'])
    return [item[1] for item in scores[:top_k]]