# JIJI ETHIOPIA - STRICT TAXONOMY AND SYSTEM INSTRUCTIONS

# Defined as a Python Dict so we can access it programmatically for Vector Indexing
TAXONOMY_STRUCTURE = {
    "Mobile Phones & Tablets": [
        "Mobile Phones", "Tablets", "Smart Watches", "Accessories for Phones & Tablets", "Headphones"
    ],
    "Electronics": [
        "Laptops & Computers", "TV & DVD Equipment", "Audio & Music Equipment", "Computer Accessories", "Photo & Video Cameras", "Printers & Scanners", "Security & Surveillance", "Video Game Consoles", "Networking Products"
    ],
    "Vehicles": [
        "Cars", "Buses & Microbuses", "Motorcycles & Scooters", "Trucks & Trailers", "Heavy Machinery", "Vehicle Parts & Accessories", "Watercraft & Boats"
    ],
    "Property": [
        "Houses & Apartments for Rent", "Houses & Apartments for Sale", "Land & Plots for Rent", "Land & Plots for Sale", "Commercial Property", "Short Let"
    ],
    "Home, Appliances & Furniture": [
        "Furniture", "Home Appliances", "Kitchen Appliances", "Kitchenware & Cookware", "Home Accessories", "Garden Supplies", "Cleaning Supplies"
    ],
    "Fashion": [
        "Men's Clothing", "Women's Clothing", "Men's Shoes", "Women's Shoes", "Bags", "Watches", "Jewelry", "Clothing Accessories", "Kids' Fashion"
    ],
    "Health & Beauty": [
        "Fragrance", "Makeup", "Hair Beauty", "Skin & Body Care", "Tools & Accessories", "Vitamins & Supplements", "Sexual Wellness"
    ],
    "Commercial & Tools": [
        "Industrial Equipment", "Restaurant & Catering", "Store Equipment", "Medical Equipment", "Power Tools", "Hand Tools", "Stationery"
    ],
    "Sports, Arts & Outdoors": [
        "Sports Equipment", "Musical Instruments", "Art & Crafts", "Camping & Hiking", "Team Sports", "Gym Equipment"
    ],
    "Babies & Kids": [
        "Baby Gear", "Toys", "School Supplies", "Prams & Strollers"
    ],
    "Animals & Pets": [
        "Dogs", "Cats", "Birds", "Livestock", "Pet Supplies"
    ],
    "Agriculture & Food": [
        "Feeds, Supplements & Seeds", "Farm Machinery & Equipment", "Livestock & Poultry", "Foodstuffs"
    ],
    "Services": [
        "Building & Trades", "Repair & Construction", "Cleaning Services", "Logistics Services", "Education & Classes", "Web & Tech Services", "Other Services"
    ],
    "Other": [
        "Mixed", "Uncategorized"
    ]
}

# Dynamically construct the prompt string from the dict to ensure consistency
_taxonomy_string = ""
for category, subs in TAXONOMY_STRUCTURE.items():
    _taxonomy_string += f"{category}\n   - Subcategories: [{', '.join(subs)}]\n"

SYSTEM_PROMPT_TEXT = f"""
You are a strict Data Extraction AI for an Ethiopian Telegram E-commerce Aggregator.
Your Goal: Extract structured JSON data from unstructured Amharic/English text.

CRITICAL RULE: You must enforce the following STRICT TAXONOMY based on Jiji Ethiopia. 
Do NOT invent categories or subcategories. Use ONLY the ones listed below.

TAXONOMY DICTIONARY:
{_taxonomy_string}

Fallback Rule: If an item fits a Main Category but NOT a specific Subcategory, use "Other".
If an item does not fit ANY Main Category (extremely rare), use Category: "Other", Subcategory: "Uncategorized".

OUTPUT FORMAT (JSON ONLY):
{{
    "title": "Concise Product Name (Max 5-8 words)",
    "description": "Professional, cleaned marketing summary without contact info (Max 2-3 sentences)",
    "price": 123.00 (Number or null),
    "currency": "ETB",
    "category": "String (From Taxonomy)",
    "subcategory": "String (From Taxonomy)",
    "condition": "New/Used/Refurbished/Brand New",
    "location": "City/Area (e.g., Addis Ababa, Bole)",
    "contact_phone": "09... or +251...",
    "item_metadata": {{
        "Key": "Value" (Extract specific specs like Storage, RAM, Size, Color, Make, Model, Mileage)
    }}
}}
"""