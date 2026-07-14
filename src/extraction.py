import json
import logging
from typing import List, Dict, Any
from src.models.topics import get_allowed_topic_names

logger = logging.getLogger(__name__)

class ContentExtractor:
    """
    Handles Phase 1 & 3: LLM Extraction and Topic Canonicalization.
    """
    def __init__(self, llm_client):
        self.llm = llm_client

    async def run_extraction_pipeline(self, raw_text: str) -> Dict[str, Any]:
        """
        Runs the full extraction pipeline on a chunk of text using gpt-4o.
        """
        allowed_topics = get_allowed_topic_names()
        
        prompt = f"""
        You are an expert travel data extraction assistant.
        Analyze the following blog post text and extract structured information.
        
        CRITICAL CONSTRAINT ON TOPICS: You must ONLY select topics from the following exact list:
        {json.dumps(allowed_topics)}
        Do not invent new topics. Do not use synonyms. If a topic is not in this list, do not include it.
        
        Return a JSON object matching the requested schema. Ensure that you actually extract entities from the provided text. Do not make up entities.
        
        Entity "type" should be one of: "Hotel", "Attraction", "Restaurant", "Location".
        Sentiment should be one of: "positive", "negative", "neutral".
        
        BLOG POST TEXT:
        {raw_text}
        """
        
        # Define strict JSON schema for NVIDIA guided_json
        extraction_schema = {
            "type": "object",
            "properties": {
                "topics": {
                    "type": "array",
                    "items": {"type": "string", "enum": allowed_topics}
                },
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string", "enum": ["Hotel", "Attraction", "Restaurant", "Location"]},
                            "location_context": {"type": "string"},
                            "claims": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "claim": {"type": "string"},
                                        "sentiment": {"type": "string", "enum": ["positive", "negative", "neutral"]}
                                    },
                                    "required": ["claim", "sentiment"]
                                }
                            }
                        },
                        "required": ["name", "type", "claims"]
                    }
                }
            },
            "required": ["topics", "entities"]
        }
        
        try:
            response = await self.llm.complete(
                prompt, 
                extra_body={"nvext": {"guided_json": extraction_schema}}
            )
            data = json.loads(response)
        except Exception as e:
            logger.error(f"Failed to extract structured data: {e}")
            return {"topics": [], "entities": []}
        
        # Validation step: Strip out any hallucinated topics
        extracted_topics = data.get("topics", [])
        validated_topics = [t for t in extracted_topics if t in allowed_topics]
        
        if len(extracted_topics) != len(validated_topics):
            logger.warning(f"LLM hallucinated topics outside taxonomy. Dropped {len(extracted_topics) - len(validated_topics)} topics.")
            
        data["topics"] = validated_topics
        return data
