from enum import Enum

class CanonicalTopic(str, Enum):
    """
    Fixed taxonomy of canonical topics to prevent semantic fragmentation.
    For v1, we constrain the extraction LLM strictly to these topics.
    Clustering discovery of new topics is deferred to v2.
    """
    
    # Accommodation types & vibes
    LUXURY = "Luxury"
    BUDGET = "Budget"
    BOUTIQUE = "Boutique"
    ECO_FRIENDLY = "Eco-Friendly"
    ROMANTIC = "Romantic"
    FAMILY_FRIENDLY = "Family-Friendly"
    ADULTS_ONLY = "Adults-Only"
    BUSINESS = "Business"
    
    # Amenities & Features
    POOL = "Pool"
    BEACHFRONT = "Beachfront"
    SPA_WELLNESS = "Spa & Wellness"
    FITNESS_CENTER = "Fitness Center"
    PET_FRIENDLY = "Pet-Friendly"
    
    # Location context
    CITY_CENTER = "City Center"
    SECLUDED = "Secluded"
    NATURE = "Nature"
    
    # Food & Dining
    FINE_DINING = "Fine Dining"
    BREAKFAST_INCLUDED = "Breakfast Included"
    LOCAL_CUISINE = "Local Cuisine"
    NIGHTLIFE = "Nightlife"
    
    # Activities
    CULTURE_HISTORY = "Culture & History"
    ADVENTURE = "Adventure"
    SHOPPING = "Shopping"
    
    # Escape Valve
    OTHER_UNCLASSIFIED = "Other/Unclassified"

def get_allowed_topic_names() -> list[str]:
    """Returns the list of string values for the LLM prompt constraint."""
    return [topic.value for topic in CanonicalTopic]
