# Two-level category configuration for Expert Forum

CATEGORY_STRUCTURE = {
    'farming-crop-management': {
        'name': '🧑‍🌾 Farming & Crop Management',
        'subcategories': {
            'crop-management': 'Crop Management',
            'seed-selection': 'Seed Selection',
            'fertilizers-nutrients': 'Fertilizers & Nutrients',
            'pest-control': 'Pest Control',
            'disease-identification': 'Disease Identification',
            'weed-management': 'Weed Management',
            'harvesting-storage': 'Harvesting & Storage',
            'organic-farming': 'Organic Farming'
        }
    },
    'soil-environment': {
        'name': '🌱 Soil & Environment',
        'subcategories': {
            'soil-health': 'Soil Health',
            'water-management': 'Water Management',
            'irrigation': 'Irrigation',
            'sustainable-farming': 'Sustainable Farming',
            'climate-impact': 'Climate Impact',
            'weather': 'Weather'
        }
    },
    'market-business': {
        'name': '🛒 Market & Business',
        'subcategories': {
            'marketing': 'Marketing',
            'crop-pricing': 'Crop Pricing',
            'export-trade': 'Export & Trade',
            'buyer-farmer-relations': 'Buyer–Farmer Relations',
            'supply-chain': 'Supply Chain',
            'government-schemes': 'Government Schemes'
        }
    },
    'technology-innovation': {
        'name': '🤖 Technology & Innovation',
        'subcategories': {
            'technology': 'Technology',
            'smart-farming': 'Smart Farming',
            'ai-agriculture': 'AI in Agriculture',
            'farm-equipment': 'Farm Equipment',
            'drone-sensor': 'Drone & Sensor Use'
        }
    },
    'community-general': {
        'name': '💬 Community & General',
        'subcategories': {
            'success-stories': 'Success Stories',
            'farming-challenges': 'Farming Challenges',
            'qa-discussions': 'Q&A Discussions',
            'announcements': 'Announcements',
            'general': 'General'
        }
    }
}

def get_main_categories():
    """Get list of main categories for dropdown"""
    return [(key, value['name']) for key, value in CATEGORY_STRUCTURE.items()]

def get_subcategories(main_category):
    """Get subcategories for a specific main category"""
    if main_category in CATEGORY_STRUCTURE:
        return [(key, value) for key, value in CATEGORY_STRUCTURE[main_category]['subcategories'].items()]
    return []

def get_all_subcategories_flat():
    """Get all subcategories as flat list"""
    result = []
    for main_key, main_data in CATEGORY_STRUCTURE.items():
        for sub_key, sub_name in main_data['subcategories'].items():
            result.append((sub_key, f"{main_data['name']} → {sub_name}"))
    return result

def get_main_category_from_subcategory(subcategory):
    """Find main category for a given subcategory"""
    for main_key, main_data in CATEGORY_STRUCTURE.items():
        if subcategory in main_data['subcategories']:
            return main_key
    return None

def get_category_display_name(main_category, subcategory):
    """Get full display name for category"""
    if main_category in CATEGORY_STRUCTURE:
        main_name = CATEGORY_STRUCTURE[main_category]['name']
        if subcategory in CATEGORY_STRUCTURE[main_category]['subcategories']:
            sub_name = CATEGORY_STRUCTURE[main_category]['subcategories'][subcategory]
            return f"{main_name} → {sub_name}"
    return "Unknown Category"

# Crop categories for marketplace
def get_crop_categories():
    """Get list of crop categories for marketplace"""
    return [
        ('grains', 'Grains & Cereals'),
        ('vegetables', 'Vegetables'),
        ('fruits', 'Fruits'),
        ('pulses', 'Pulses'),
        ('spices', 'Spices'),
        ('others', 'Others')
    ]
