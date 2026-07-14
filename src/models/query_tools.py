from pydantic import BaseModel, Field
from typing import Optional

class FindHotelsNearAttractionSchema(BaseModel):
    """
    Tool to find hotels near a specific attraction.
    Use this when the user is looking for a place to stay near a known point of interest.
    """
    attraction_name: str = Field(..., description="The name of the attraction or point of interest (e.g., 'Eiffel Tower', 'Tanah Lot').")
    max_distance_km: Optional[float] = Field(5.0, description="Maximum distance from the attraction in kilometers.")
    price_tier: Optional[str] = Field(None, description="Optional price tier constraint (e.g., 'budget', 'mid-range', 'luxury').")
    kid_friendly: Optional[bool] = Field(None, description="Set to true if the user specifically asked for kid-friendly/family-friendly hotels.")

class FindHotelsByTopicSchema(BaseModel):
    """
    Tool to find hotels associated with a specific vibe, topic, or theme.
    Use this when the user is looking for a conceptual match (e.g., 'romantic', 'family-friendly', 'wellness') rather than a specific location.
    """
    topic: str = Field(..., description="The canonical topic or vibe the user is looking for (e.g., 'romantic', 'family-friendly', 'wellness', 'luxury').")
    location_name: Optional[str] = Field(None, description="Optional location to bound the search (e.g., 'Ubud', 'Bali', 'Paris').")
    min_rating: Optional[float] = Field(None, description="Optional minimum star rating (1-5).")

class GetDestinationVibeSummarySchema(BaseModel):
    """
    Tool to retrieve a macro-level summary of a destination's vibe, communities, and general travel consensus.
    Use this for broad questions like 'What is the general vibe of Ubud?' or 'Tell me about Seminyak'.
    """
    destination_name: str = Field(..., description="The name of the destination (e.g., 'Ubud', 'Seminyak', 'Paris').")
    specific_interest: Optional[str] = Field(None, description="Any specific interest mentioned to filter the summary (e.g., 'food', 'nightlife').")

