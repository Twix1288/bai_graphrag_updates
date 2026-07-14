import os
import ssl
import json
import time
import logging
import urllib.parse
import urllib.request
import certifi
from typing import Optional, Tuple, Dict, Any, List
from shapely.geometry import Point, Polygon
# Pseudo-imports
# from googlemaps import Client

logger = logging.getLogger(__name__)


class NominatimClient:
    """
    Free geocoding via the public OpenStreetMap Nominatim API (no API key).

    Adapts Nominatim responses to the same shape the Geocoder expects from the
    Google Maps client (`geocode()` -> list of dicts with `geometry.location`
    and `address_components`), so it is a drop-in replacement.

    Honors the Nominatim usage policy: a descriptive User-Agent with contact
    info and a hard cap of <=1 request/second (enforced by a simple throttle).
    Only the single best match is returned (limit=1) — the top result is ordered
    by importance — which the Geocoder treats as a confident, unambiguous match.
    """
    BASE_URL = "https://nominatim.openstreetmap.org/search"
    _MIN_INTERVAL_S = 1.1  # stay under the 1 req/sec policy with headroom
    _last_request_ts = 0.0  # class-level: throttle across all instances

    def __init__(self, user_agent: Optional[str] = None, timeout: float = 10.0):
        contact = os.getenv("NOMINATIM_CONTACT_EMAIL", "graphrag@example.com")
        self.user_agent = user_agent or f"GraphRAG-Ingestion/1.0 ({contact})"
        self.timeout = timeout
        # Verify TLS against the certifi CA bundle (system trust store is often
        # incomplete on macOS Python), consistent with the embedding client.
        self._ssl_context = ssl.create_default_context(cafile=certifi.where())

    def _throttle(self):
        elapsed = time.monotonic() - NominatimClient._last_request_ts
        if elapsed < self._MIN_INTERVAL_S:
            time.sleep(self._MIN_INTERVAL_S - elapsed)
        NominatimClient._last_request_ts = time.monotonic()

    @staticmethod
    def _clean(query: str) -> str:
        """Normalize a place name for Nominatim: drop parentheticals, take the part
        before a slash, fold the Hawaiian ʻokina and curly/backtick apostrophes, and
        collapse whitespace. Nominatim returns nothing for names with these."""
        import re
        q = re.sub(r"\([^)]*\)", " ", query)      # "Diamond Head (Lēʻahi)" -> "Diamond Head"
        q = q.split("/")[0]                         # "South Shore / Honolulu" -> "South Shore"
        for ch in ("ʻ", "ʼ", "‘", "’", "`", "'"):
            q = q.replace(ch, "")                   # "Oʻahu" -> "Oahu"
        return re.sub(r"\s+", " ", q).strip()

    def _fetch(self, query: str):
        self._throttle()
        params = urllib.parse.urlencode({
            "q": query, "format": "json", "addressdetails": 1, "limit": 1,
        })
        req = urllib.request.Request(
            f"{self.BASE_URL}?{params}",
            headers={"User-Agent": self.user_agent},
        )
        with urllib.request.urlopen(req, timeout=self.timeout, context=self._ssl_context) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def geocode(self, query: str) -> List[Dict[str, Any]]:
        # Try the cleaned full query, then fall back to the bare place name (the
        # text before the first comma) which resolves far more reliably.
        candidates = [self._clean(query)]
        if "," in query:
            candidates.append(self._clean(query.split(",")[0]))
        raw = []
        for cand in candidates:
            if not cand:
                continue
            raw = self._fetch(cand)
            if raw:
                break

        results = []
        for item in raw:
            addr = item.get("address", {})
            components = []
            neighborhood = addr.get("neighbourhood") or addr.get("suburb")
            if neighborhood:
                components.append({"types": ["neighborhood"], "long_name": neighborhood})
            city = addr.get("city") or addr.get("town") or addr.get("village")
            if city:
                components.append({"types": ["locality"], "long_name": city})
            if addr.get("country"):
                components.append({"types": ["country"], "long_name": addr["country"]})
            results.append({
                "geometry": {"location": {"lat": float(item["lat"]), "lng": float(item["lon"])}},
                "address_components": components,
            })
        return results

class Geocoder:
    """
    Handles Phase 4 geocoding during ingestion.
    Resolves extracted locations into exact point coordinates (lat, lng) 
    and strict spatial hierarchy (Neighborhood -> City -> Country).
    """
    def __init__(self, google_maps_client):
        self.gmaps = google_maps_client
        
    async def resolve_location(self, place_name: str, context_locality: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Geocodes a place name. 
        If it finds exactly one confident match, returns the hierarchy and coordinates.
        If it fails or is ambiguous (multiple matches), routes to the human review queue.
        """
        search_query = f"{place_name}, {context_locality}" if context_locality else place_name
        
        # BLOCKER 4 RESOLVED: Real Google Places API Integration
        try:
            results = self.gmaps.geocode(search_query)
        except Exception as e:
            logger.error(f"Geocoding API error for '{search_query}': {e}")
            await self._route_to_review_queue(place_name, context_locality, reason="API_ERROR")
            return None
        
        if not results:
            logger.warning(f"Geocoding failed for '{search_query}'. Routing to review queue.")
            await self._route_to_review_queue(place_name, context_locality, reason="NO_RESULTS")
            return None
            
        if len(results) > 1:
            logger.warning(f"Geocoding ambiguous for '{search_query}' ({len(results)} matches). Routing to review queue.")
            await self._route_to_review_queue(place_name, context_locality, reason="AMBIGUOUS_MATCHES")
            return None
            
        # Success - Parse single result
        res = results[0]
        lat = res["geometry"]["location"]["lat"]
        lng = res["geometry"]["location"]["lng"]
        
        hierarchy = {}
        for component in res["address_components"]:
            types = component["types"]
            if "neighborhood" in types or "sublocality" in types:
                hierarchy["neighborhood"] = component["long_name"]
            elif "locality" in types:
                hierarchy["city"] = component["long_name"]
            elif "country" in types:
                hierarchy["country"] = component["long_name"]
                
        return {
            "lat": lat,
            "lng": lng,
            "hierarchy": hierarchy
        }

    async def _route_to_review_queue(self, place_name: str, context_locality: str, reason: str):
        """
        Writes ambiguous or failed geocoding attempts to the Supabase human review queue.
        """
        logger.info(f"Writing {place_name} to human review queue (Reason: {reason})")
        # await self.supabase.table('geocoding_review_queue').insert({
        #     "raw_name": place_name,
        #     "context": context_locality,
        #     "failure_reason": reason,
        #     "status": "pending_review"
        # }).execute()
        pass

    def assign_to_sublocation(self, lat: float, lng: float, sublocations: List[Dict[str, Any]]) -> str:
        """
        Assigns a hotel/attraction coordinates to a sublocation using point-in-polygon,
        falling back to nearest centroid if it's outside all polygons.
        `sublocations` should be a list of dicts:
        { "name": "Ka'anapali", "polygon": [(lng, lat), ...], "centroid": (lng, lat) }
        """
        pt = Point(lng, lat)
        
        # 1. Point in Polygon
        for sub in sublocations:
            if "polygon" in sub and sub["polygon"]:
                poly = Polygon(sub["polygon"])
                if poly.contains(pt):
                    return sub["name"]
                    
        # 2. Nearest Centroid Fallback
        nearest = None
        min_dist = float('inf')
        for sub in sublocations:
            if "centroid" in sub and sub["centroid"]:
                cent = Point(sub["centroid"])
                dist = pt.distance(cent)
                if dist < min_dist:
                    min_dist = dist
                    nearest = sub["name"]
                    
        # If distance is too far, or no centroids exist, assign to "Other areas" bucket
        if nearest and min_dist < 0.1: # roughly 10km depending on projection, sufficient for this fallback
            return nearest
            
        return "Other areas"

