# High-Level Design (HLD)
# Blogger Content Knowledge Graph System
## LetsBai.ai - Travel Intelligence Platform

**Version:** 1.0  
**Date:** February 2025  
**Author:** LetsBai.ai Engineering Team

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Overview](#2-system-overview)
3. [Architecture Diagram](#3-architecture-diagram)
4. [Component Deep Dive](#4-component-deep-dive)
5. [Data Models & Schemas](#5-data-models--schemas)
6. [API Contracts](#6-api-contracts)
7. [Processing Pipeline Details](#7-processing-pipeline-details)
8. [Query & Retrieval Layer](#8-query--retrieval-layer)
9. [Technology Stack](#9-technology-stack)
10. [Deployment Architecture](#10-deployment-architecture)
11. [Security Considerations](#11-security-considerations)
12. [Scalability & Performance](#12-scalability--performance)
13. [Cost Estimation](#13-cost-estimation)
14. [Implementation Roadmap](#14-implementation-roadmap)

---

## 1. Executive Summary

### 1.1 Purpose

Build an intelligent content ingestion and knowledge extraction system that transforms travel blogger content (documents, blogs, videos) into a structured, queryable knowledge graph. This enables LetsBai.ai to provide users with authentic, blogger-sourced recommendations for hotels, attractions, and destinations.

### 1.2 Key Objectives

- **Ingest** multi-format content from travel influencers (PDFs, DOCX, blog URLs, videos)
- **Store** raw content in Google Cloud Storage for durability and compliance
- **Process** content through LLM pipeline for summarization and entity extraction
- **Structure** extracted entities (hotels, locations, attractions) in Neo4j graph database
- **Enable** semantic + graph-based queries for rich travel recommendations

### 1.3 Value Proposition

| Traditional Approach | LetsBai Knowledge Graph |
|---------------------|------------------------|
| Generic hotel reviews | Curated blogger perspectives |
| Anonymous ratings | Attributed, trustworthy sources |
| Keyword search only | Semantic + relationship queries |
| Static data | Living knowledge graph |

---

## 2. System Overview

### 2.1 High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CONTENT SOURCES                                    │
├───────────────────┬───────────────────┬─────────────────────────────────────┤
│    Documents      │    Blog Links     │           Videos                     │
│  (PDF, DOCX, TXT) │  (URLs to blogs)  │    (MP4, YouTube links)              │
└────────┬──────────┴─────────┬─────────┴──────────────┬──────────────────────┘
         │                    │                         │
         └────────────────────┼─────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      1. INGESTION SERVICE                                    │
│   • Upload API (multipart/form-data)                                        │
│   • URL scraping service                                                    │
│   • Video download/processing                                               │
│   • Metadata extraction                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              2. OBJECT STORAGE (Google Cloud Storage)                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │  /raw/                                                               │   │
│   │    ├── documents/{blogger_id}/{content_id}.pdf                      │   │
│   │    ├── blogs/{blogger_id}/{content_id}.html                         │   │
│   │    └── videos/{blogger_id}/{content_id}.mp4                         │   │
│   │  /processed/                                                         │   │
│   │    ├── text/{content_id}.txt                                        │   │
│   │    ├── transcripts/{content_id}.txt                                 │   │
│   │    └── summaries/{content_id}.json                                  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              3. PROCESSING QUEUE (Cloud Pub/Sub + Cloud Tasks)               │
│   • content-ingested topic → triggers processing                            │
│   • Exactly-once delivery                                                   │
│   • Dead letter queue for failures                                          │
│   • Rate limiting (1 item at a time per your requirement)                   │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    4. LLM PROCESSING PIPELINE                                │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  STAGE 1: Text Extraction                                           │    │
│   │  • PDF → PyPDF2/pdfplumber                                          │    │
│   │  • DOCX → python-docx                                               │    │
│   │  • HTML → BeautifulSoup (clean text)                                │    │
│   │  • Video → Whisper API (transcription)                              │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                              │                                               │
│                              ▼                                               │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  STAGE 2: LLM Summarization (Claude/Gemini)                         │    │
│   │  • Generate structured summary                                      │    │
│   │  • Extract key themes and sentiments                                │    │
│   │  • Identify travel context (trip type, season, budget)              │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                              │                                               │
│                              ▼                                               │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  STAGE 3: Named Entity Recognition (NER)                            │    │
│   │  • Hotels (name, location, rating mentioned)                        │    │
│   │  • Locations (cities, regions, countries)                           │    │
│   │  • Attractions (sites, restaurants, activities)                     │    │
│   │  • Prices/costs mentioned                                           │    │
│   │  • Time periods (season, month, duration)                           │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                              │                                               │
│                              ▼                                               │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │  STAGE 4: Entity Resolution & Enrichment                            │    │
│   │  • Match hotels to known database (Google Places API)               │    │
│   │  • Geocode locations                                                │    │
│   │  • Deduplicate entities                                             │    │
│   └────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌──────────────────────────────┐ ┌────────────────────────────────────────────┐
│      5. VECTOR STORE         │ │         6. GRAPH STORE (Neo4j)              │
│   (Supabase pgvector)        │ │                                            │
│                              │ │  ┌────────────────────────────────────┐    │
│  • Summary embeddings        │ │  │         NODES                      │    │
│  • Chunk embeddings          │ │  │  • Blogger (id, name, followers)   │    │
│  • Semantic search index     │ │  │  • Content (id, type, url, date)   │    │
│                              │ │  │  • Hotel (id, name, location)      │    │
│                              │ │  │  • Location (id, name, geo)        │    │
│                              │ │  │  • Attraction (id, name, type)     │    │
│                              │ │  └────────────────────────────────────┘    │
│                              │ │  ┌────────────────────────────────────┐    │
│                              │ │  │         EDGES                      │    │
│                              │ │  │  • CREATED (Blogger→Content)       │    │
│                              │ │  │  • REVIEWED (Content→Hotel)        │    │
│                              │ │  │  • MENTIONS (Content→Location)     │    │
│                              │ │  │  • RECOMMENDS (Content→Attraction) │    │
│                              │ │  │  • LOCATED_IN (Hotel→Location)     │    │
│                              │ │  │  • NEAR (Location→Location)        │    │
│                              │ │  └────────────────────────────────────┘    │
└──────────────────────────────┘ └────────────────────────────────────────────┘
              │                               │
              └───────────────┬───────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       7. QUERY LAYER (GraphRAG)                              │
│   • Hybrid search: Vector similarity + Graph traversal                      │
│   • Natural language to Cypher translation                                  │
│   • Response synthesis with source attribution                              │
│                                                                             │
│   Example Query: "Best boutique hotels in Bali for honeymooners"            │
│   1. Vector search → Find relevant content chunks                           │
│   2. Graph traversal → Find hotels connected to "Bali" + "honeymoon" tags   │
│   3. Rank by blogger credibility + recency                                  │
│   4. Synthesize response with citations                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Architecture Diagram

### 3.1 Logical Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PRESENTATION LAYER                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  Web App    │  │ Mobile App  │  │  API Users  │  │ Admin Portal│        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API GATEWAY LAYER                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Cloud Run / API Gateway                                             │    │
│  │  • Authentication (Firebase Auth / Supabase Auth)                    │    │
│  │  • Rate Limiting                                                     │    │
│  │  • Request Routing                                                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          ▼                           ▼                           ▼
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────────┐
│  INGESTION SERVICE  │  │   QUERY SERVICE     │  │  ADMIN SERVICE          │
│  (Cloud Run)        │  │   (Cloud Run)       │  │  (Cloud Run)            │
│                     │  │                     │  │                         │
│  /api/content       │  │  /api/search        │  │  /api/bloggers          │
│  /api/bloggers      │  │  /api/recommend     │  │  /api/content/status    │
│  /api/upload        │  │  /api/hotels        │  │  /api/reprocess         │
└─────────────────────┘  └─────────────────────┘  └─────────────────────────┘
          │                           │                           │
          └───────────────────────────┼───────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SERVICE MESH LAYER                                 │
└─────────────────────────────────────────────────────────────────────────────┘
          │                           │                           │
          ▼                           ▼                           ▼
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────────┐
│  PROCESSING SERVICE │  │  EMBEDDING SERVICE  │  │  GRAPH SERVICE          │
│  (Cloud Run Jobs)   │  │  (Cloud Run)        │  │  (Cloud Run)            │
│                     │  │                     │  │                         │
│  • Text Extraction  │  │  • Generate embeds  │  │  • Cypher queries       │
│  • LLM Processing   │  │  • Batch processing │  │  • Graph updates        │
│  • NER Extraction   │  │  • Model: text-     │  │  • Path traversal       │
│                     │  │    embedding-3-small│  │                         │
└─────────────────────┘  └─────────────────────┘  └─────────────────────────┘
          │                           │                           │
          └───────────────────────────┼───────────────────────────┘
                                      │
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA LAYER                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │     GCS      │  │   Supabase   │  │    Neo4j     │  │    Redis     │    │
│  │  (Objects)   │  │  (Postgres + │  │   (Graph)    │  │   (Cache)    │    │
│  │              │  │   pgvector)  │  │              │  │              │    │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Data Flow Sequence

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│ Blogger │     │Ingestion│     │   GCS   │     │ Pub/Sub │     │Processing│
│  Input  │     │ Service │     │         │     │         │     │ Service  │
└────┬────┘     └────┬────┘     └────┬────┘     └────┬────┘     └────┬─────┘
     │               │               │               │               │
     │ Upload File   │               │               │               │
     │──────────────>│               │               │               │
     │               │ Store Raw     │               │               │
     │               │──────────────>│               │               │
     │               │               │               │               │
     │               │ Publish Event │               │               │
     │               │───────────────────────────────>│               │
     │               │               │               │               │
     │               │               │               │ Trigger Job   │
     │               │               │               │──────────────>│
     │               │               │               │               │
     │               │               │  Fetch File   │               │
     │               │               │<──────────────────────────────│
     │               │               │               │               │
     │               │               │               │               │

┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│Processing│    │   LLM   │     │ Neo4j   │     │Supabase │
│ Service  │    │ (Claude)│     │         │     │         │
└────┬─────┘    └────┬────┘     └────┬────┘     └────┬────┘
     │               │               │               │
     │ Extract Text  │               │               │
     │───────────────│               │               │
     │               │               │               │
     │ Summarize +   │               │               │
     │ NER           │               │               │
     │──────────────>│               │               │
     │               │               │               │
     │ Entities JSON │               │               │
     │<──────────────│               │               │
     │               │               │               │
     │ Create Nodes  │               │               │
     │ & Edges       │               │               │
     │───────────────────────────────>│               │
     │               │               │               │
     │ Store Embeddings              │               │
     │──────────────────────────────────────────────>│
     │               │               │               │
```

---

## 4. Component Deep Dive

### 4.1 Ingestion Service

**Purpose:** Accept content from bloggers and prepare for processing.

**Technology:** Python FastAPI on Cloud Run

**Responsibilities:**
- File upload handling (multipart/form-data)
- URL validation and scraping
- Video download (YouTube-DL)
- Metadata extraction
- GCS upload
- Pub/Sub event publishing

**Supported Content Types:**

| Type | Extensions | Max Size | Processing |
|------|-----------|----------|------------|
| Documents | PDF, DOCX, TXT, MD | 50 MB | Direct text extraction |
| Blog Links | HTTP/HTTPS URLs | N/A | Web scraping |
| Videos | MP4, MOV, YouTube | 500 MB | Transcription |

**API Endpoints:**

```yaml
POST /api/v1/content/upload
  - Multipart file upload
  - Returns: content_id, processing_status

POST /api/v1/content/link
  - Body: { url, blogger_id, metadata }
  - Returns: content_id, processing_status

GET /api/v1/content/{content_id}/status
  - Returns: processing_status, stages_completed

POST /api/v1/bloggers
  - Register new blogger
  - Body: { name, email, social_links, bio }
```

---

### 4.2 Object Storage (GCS)

**Purpose:** Durable storage for raw and processed content.

**Bucket Structure:**

```
letsbai-blogger-content/
├── raw/
│   ├── documents/
│   │   └── {blogger_id}/
│   │       └── {content_id}/
│   │           ├── original.pdf
│   │           └── metadata.json
│   ├── blogs/
│   │   └── {blogger_id}/
│   │       └── {content_id}/
│   │           ├── page.html
│   │           ├── images/
│   │           └── metadata.json
│   └── videos/
│       └── {blogger_id}/
│           └── {content_id}/
│               ├── video.mp4
│               ├── thumbnail.jpg
│               └── metadata.json
│
├── processed/
│   └── {content_id}/
│       ├── extracted_text.txt
│       ├── transcript.txt (for videos)
│       ├── summary.json
│       ├── entities.json
│       └── embeddings.json
│
└── archive/
    └── {year}/{month}/
        └── {content_id}/
```

**Lifecycle Policies:**

| Location | Retention | Storage Class |
|----------|-----------|---------------|
| raw/ | 2 years | Standard |
| processed/ | 1 year | Standard |
| archive/ | 7 years | Coldline |

---

### 4.3 Processing Queue (Pub/Sub)

**Purpose:** Decouple ingestion from processing, enable sequential processing.

**Topics:**

```yaml
content-ingested:
  description: New content ready for processing
  message_schema:
    content_id: string
    blogger_id: string
    content_type: enum[document, blog, video]
    gcs_path: string
    priority: enum[high, normal, low]

content-processed:
  description: Content processing completed
  message_schema:
    content_id: string
    status: enum[success, failed, partial]
    entities_extracted: integer
    processing_time_ms: integer

content-failed:
  description: Dead letter queue for failed processing
  message_schema:
    content_id: string
    error: string
    retry_count: integer
    last_attempt: timestamp
```

**Flow Control Configuration:**

```yaml
subscription_config:
  ack_deadline_seconds: 600  # 10 minutes for LLM processing
  max_delivery_attempts: 3
  dead_letter_topic: content-failed
  
  # Sequential processing (1 at a time)
  flow_control:
    max_outstanding_messages: 1
    max_outstanding_bytes: 10_000_000
```

---

### 4.4 LLM Processing Pipeline

**Purpose:** Extract structured knowledge from raw content.

#### Stage 1: Text Extraction

```python
class TextExtractor:
    """
    Extracts text from various content formats.
    """
    
    def extract(self, content_type: str, file_path: str) -> ExtractedText:
        match content_type:
            case "pdf":
                return self._extract_pdf(file_path)
            case "docx":
                return self._extract_docx(file_path)
            case "html":
                return self._extract_html(file_path)
            case "video":
                return self._transcribe_video(file_path)
    
    def _extract_pdf(self, path: str) -> ExtractedText:
        # Use pdfplumber for layout-aware extraction
        # Falls back to PyPDF2 for simple PDFs
        pass
    
    def _transcribe_video(self, path: str) -> ExtractedText:
        # Use Whisper API for transcription
        # Returns timestamped transcript
        pass
```

#### Stage 2: LLM Summarization

**Prompt Template:**

```
You are a travel content analyst. Analyze the following travel blog/document 
and provide a structured summary.

CONTENT:
{extracted_text}

Provide your analysis in the following JSON format:
{
  "summary": "2-3 paragraph summary of the content",
  "key_themes": ["theme1", "theme2"],
  "travel_context": {
    "trip_type": "solo/couple/family/group",
    "travel_style": "budget/mid-range/luxury",
    "season": "summer/winter/monsoon/etc",
    "duration": "X days/weeks",
    "purpose": "leisure/adventure/business/honeymoon"
  },
  "sentiment": {
    "overall": "positive/negative/mixed",
    "highlights": ["what they loved"],
    "concerns": ["what they didn't like"]
  },
  "target_audience": "who would benefit from this content"
}
```

#### Stage 3: Named Entity Recognition

**Prompt Template:**

```
Extract all travel-related named entities from the following content.
Be thorough and extract every mention, even if repeated.

CONTENT:
{extracted_text}

Extract entities in this JSON format:
{
  "hotels": [
    {
      "name": "exact name mentioned",
      "location_mentioned": "city/area if specified",
      "sentiment": "positive/negative/neutral",
      "highlights": ["specific things mentioned about it"],
      "price_range": "if mentioned",
      "stay_duration": "if mentioned"
    }
  ],
  "locations": [
    {
      "name": "place name",
      "type": "city/region/country/neighborhood/beach/mountain",
      "context": "how it was mentioned"
    }
  ],
  "attractions": [
    {
      "name": "attraction name",
      "type": "restaurant/temple/museum/beach/activity",
      "location": "where it is",
      "recommendation_strength": "must-visit/worth-seeing/skip",
      "details": "specific tips or info shared"
    }
  ],
  "practical_info": {
    "costs_mentioned": [{"item": "x", "amount": "y"}],
    "tips": ["practical tips shared"],
    "warnings": ["things to avoid or watch out for"]
  }
}
```

#### Stage 4: Entity Resolution

**Purpose:** Match extracted entities to canonical records.

```python
class EntityResolver:
    """
    Resolves extracted entities to canonical database records.
    Uses fuzzy matching + Google Places API for verification.
    """
    
    async def resolve_hotel(self, extracted: ExtractedHotel) -> ResolvedHotel:
        # 1. Check existing Neo4j nodes for fuzzy match
        existing = await self.neo4j.fuzzy_match_hotel(
            name=extracted.name,
            location=extracted.location_mentioned,
            threshold=0.85
        )
        
        if existing:
            return existing
        
        # 2. Query Google Places API for verification
        places_result = await self.google_places.search(
            query=f"{extracted.name} hotel {extracted.location_mentioned}",
            type="lodging"
        )
        
        if places_result:
            # Create new canonical hotel node
            return await self.neo4j.create_hotel(
                name=places_result.name,
                place_id=places_result.place_id,
                location=places_result.geometry,
                address=places_result.formatted_address
            )
        
        # 3. Create unverified node for manual review
        return await self.neo4j.create_unverified_hotel(extracted)
```

---

### 4.5 Vector Store (Supabase pgvector)

**Purpose:** Store embeddings for semantic search.

**Schema:**

```sql
-- Content embeddings table
CREATE TABLE content_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content_id UUID NOT NULL REFERENCES contents(id),
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(1536),  -- OpenAI text-embedding-3-small
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(content_id, chunk_index)
);

-- Summary embeddings (one per content)
CREATE TABLE summary_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content_id UUID NOT NULL REFERENCES contents(id) UNIQUE,
    summary_text TEXT NOT NULL,
    embedding vector(1536),
    themes TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Entity embeddings (for semantic entity matching)
CREATE TABLE entity_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type VARCHAR(50) NOT NULL,  -- hotel, location, attraction
    entity_id UUID NOT NULL,
    entity_name TEXT NOT NULL,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(entity_type, entity_id)
);

-- Indexes for vector similarity search
CREATE INDEX ON content_embeddings 
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX ON summary_embeddings 
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX ON entity_embeddings 
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

---

### 4.6 Graph Store (Neo4j)

**Purpose:** Store entities and relationships for graph-based queries.

**Node Types:**

```cypher
// Blogger Node
(:Blogger {
    id: UUID,
    name: String,
    email: String,
    bio: String,
    social_links: Map,
    follower_count: Integer,
    credibility_score: Float,  // Calculated metric
    joined_at: DateTime,
    total_content: Integer
})

// Content Node
(:Content {
    id: UUID,
    type: String,  // document, blog, video
    title: String,
    gcs_path: String,
    original_url: String,
    summary: String,
    themes: [String],
    travel_context: Map,
    sentiment: String,
    word_count: Integer,
    published_date: Date,
    processed_at: DateTime,
    status: String
})

// Hotel Node
(:Hotel {
    id: UUID,
    name: String,
    google_place_id: String,
    address: String,
    city: String,
    country: String,
    latitude: Float,
    longitude: Float,
    star_rating: Integer,
    price_tier: String,  // budget, mid, luxury
    amenities: [String],
    verified: Boolean
})

// Location Node
(:Location {
    id: UUID,
    name: String,
    type: String,  // city, region, country, neighborhood
    parent_location_id: UUID,
    latitude: Float,
    longitude: Float,
    timezone: String,
    country_code: String
})

// Attraction Node
(:Attraction {
    id: UUID,
    name: String,
    type: String,  // restaurant, temple, museum, beach, activity
    google_place_id: String,
    address: String,
    latitude: Float,
    longitude: Float,
    categories: [String],
    price_level: Integer,
    verified: Boolean
})
```

**Relationship Types:**

```cypher
// Blogger relationships
(:Blogger)-[:CREATED {date: Date}]->(:Content)

// Content relationships (with rich properties)
(:Content)-[:REVIEWED {
    sentiment: String,
    highlights: [String],
    concerns: [String],
    rating_mentioned: Float,
    stay_duration: String,
    visit_date: Date
}]->(:Hotel)

(:Content)-[:MENTIONS {
    context: String,
    sentiment: String,
    times_mentioned: Integer
}]->(:Location)

(:Content)-[:RECOMMENDS {
    strength: String,  // must-visit, worth-seeing, skip
    tips: [String],
    best_time: String
}]->(:Attraction)

// Spatial relationships
(:Hotel)-[:LOCATED_IN]->(:Location)
(:Attraction)-[:LOCATED_IN]->(:Location)
(:Location)-[:PART_OF]->(:Location)  // Bali -> Indonesia
(:Location)-[:NEAR {distance_km: Float}]->(:Location)

// Discovery relationships
(:Hotel)-[:SIMILAR_TO {score: Float}]->(:Hotel)
(:Attraction)-[:PAIRS_WELL_WITH]->(:Attraction)
```

**Indexes:**

```cypher
// Unique constraints
CREATE CONSTRAINT blogger_id IF NOT EXISTS FOR (b:Blogger) REQUIRE b.id IS UNIQUE;
CREATE CONSTRAINT content_id IF NOT EXISTS FOR (c:Content) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT hotel_id IF NOT EXISTS FOR (h:Hotel) REQUIRE h.id IS UNIQUE;
CREATE CONSTRAINT location_id IF NOT EXISTS FOR (l:Location) REQUIRE l.id IS UNIQUE;
CREATE CONSTRAINT attraction_id IF NOT EXISTS FOR (a:Attraction) REQUIRE a.id IS UNIQUE;

// Search indexes
CREATE INDEX hotel_name IF NOT EXISTS FOR (h:Hotel) ON (h.name);
CREATE INDEX hotel_city IF NOT EXISTS FOR (h:Hotel) ON (h.city);
CREATE INDEX location_name IF NOT EXISTS FOR (l:Location) ON (l.name);
CREATE INDEX attraction_name IF NOT EXISTS FOR (a:Attraction) ON (a.name);

// Full-text search
CREATE FULLTEXT INDEX hotel_search IF NOT EXISTS 
FOR (h:Hotel) ON EACH [h.name, h.city, h.address];

// Point index for spatial queries
CREATE POINT INDEX hotel_location IF NOT EXISTS FOR (h:Hotel) ON (h.location);
```

---

## 5. Data Models & Schemas

### 5.1 PostgreSQL (Supabase) - Operational Data

```sql
-- Bloggers table
CREATE TABLE bloggers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    bio TEXT,
    social_links JSONB DEFAULT '{}',
    follower_count INTEGER DEFAULT 0,
    credibility_score DECIMAL(3,2) DEFAULT 0.50,
    status VARCHAR(20) DEFAULT 'pending',  -- pending, active, suspended
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Contents table
CREATE TABLE contents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    blogger_id UUID NOT NULL REFERENCES bloggers(id),
    type VARCHAR(20) NOT NULL,  -- document, blog, video
    title VARCHAR(500),
    original_filename VARCHAR(255),
    original_url TEXT,
    gcs_raw_path TEXT NOT NULL,
    gcs_processed_path TEXT,
    file_size_bytes BIGINT,
    mime_type VARCHAR(100),
    status VARCHAR(20) DEFAULT 'uploaded',
    -- uploaded, processing, processed, failed, archived
    processing_started_at TIMESTAMPTZ,
    processing_completed_at TIMESTAMPTZ,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Processing results table
CREATE TABLE processing_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content_id UUID NOT NULL REFERENCES contents(id),
    summary TEXT,
    themes TEXT[],
    travel_context JSONB,
    sentiment VARCHAR(20),
    raw_entities JSONB,  -- Before resolution
    resolved_entities JSONB,  -- After resolution
    word_count INTEGER,
    processing_time_ms INTEGER,
    llm_model VARCHAR(50),
    llm_tokens_used INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Processing audit log
CREATE TABLE processing_audit (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content_id UUID NOT NULL REFERENCES contents(id),
    stage VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    details JSONB,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    error_message TEXT
);

-- Indexes
CREATE INDEX idx_contents_blogger ON contents(blogger_id);
CREATE INDEX idx_contents_status ON contents(status);
CREATE INDEX idx_contents_type ON contents(type);
CREATE INDEX idx_processing_results_content ON processing_results(content_id);
```

### 5.2 API Request/Response Models

```python
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

class ContentType(str, Enum):
    DOCUMENT = "document"
    BLOG = "blog"
    VIDEO = "video"

class ProcessingStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"

# Request Models
class BloggerCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    email: str = Field(..., pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    bio: Optional[str] = None
    social_links: Optional[dict] = {}

class ContentLinkRequest(BaseModel):
    url: str = Field(..., pattern=r'^https?://')
    blogger_id: str
    title: Optional[str] = None
    metadata: Optional[dict] = {}

# Response Models
class ContentResponse(BaseModel):
    id: str
    blogger_id: str
    type: ContentType
    title: Optional[str]
    status: ProcessingStatus
    created_at: datetime
    processing_completed_at: Optional[datetime]

class ProcessingStatusResponse(BaseModel):
    content_id: str
    status: ProcessingStatus
    stages: List[dict]
    entities_found: Optional[dict]
    error_message: Optional[str]

class HotelRecommendation(BaseModel):
    hotel_id: str
    name: str
    location: str
    blogger_mentions: int
    average_sentiment: float
    highlights: List[str]
    source_contents: List[dict]

class SearchResponse(BaseModel):
    query: str
    results: List[HotelRecommendation]
    total_count: int
    search_time_ms: int
```

---

## 6. API Contracts

### 6.1 Ingestion APIs

```yaml
openapi: 3.0.3
info:
  title: LetsBai Blogger Content API
  version: 1.0.0

paths:
  /api/v1/bloggers:
    post:
      summary: Register a new blogger
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/BloggerCreate'
      responses:
        '201':
          description: Blogger created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Blogger'
        '409':
          description: Email already exists

  /api/v1/content/upload:
    post:
      summary: Upload content file
      requestBody:
        content:
          multipart/form-data:
            schema:
              type: object
              properties:
                file:
                  type: string
                  format: binary
                blogger_id:
                  type: string
                  format: uuid
                title:
                  type: string
                metadata:
                  type: object
      responses:
        '202':
          description: Upload accepted, processing queued
          content:
            application/json:
              schema:
                type: object
                properties:
                  content_id:
                    type: string
                  status:
                    type: string
                  message:
                    type: string

  /api/v1/content/link:
    post:
      summary: Submit blog URL for processing
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ContentLinkRequest'
      responses:
        '202':
          description: Link accepted, processing queued

  /api/v1/content/{content_id}/status:
    get:
      summary: Get processing status
      parameters:
        - name: content_id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Processing status
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProcessingStatus'
```

### 6.2 Query APIs

```yaml
  /api/v1/search/hotels:
    post:
      summary: Search hotels with blogger insights
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                query:
                  type: string
                  description: Natural language query
                  example: "romantic hotels in Bali with ocean view"
                filters:
                  type: object
                  properties:
                    location:
                      type: string
                    price_tier:
                      type: array
                      items:
                        type: string
                        enum: [budget, mid, luxury]
                    min_mentions:
                      type: integer
                    sentiment:
                      type: string
                      enum: [positive, any]
                limit:
                  type: integer
                  default: 10
      responses:
        '200':
          description: Search results
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SearchResponse'

  /api/v1/hotels/{hotel_id}/insights:
    get:
      summary: Get aggregated blogger insights for a hotel
      parameters:
        - name: hotel_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Hotel insights
          content:
            application/json:
              schema:
                type: object
                properties:
                  hotel:
                    $ref: '#/components/schemas/Hotel'
                  total_mentions:
                    type: integer
                  sentiment_breakdown:
                    type: object
                  top_highlights:
                    type: array
                  blogger_reviews:
                    type: array
                  similar_hotels:
                    type: array

  /api/v1/graph/explore:
    post:
      summary: Explore knowledge graph connections
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                start_entity:
                  type: object
                  properties:
                    type:
                      type: string
                      enum: [hotel, location, attraction, blogger]
                    id:
                      type: string
                relationship_types:
                  type: array
                  items:
                    type: string
                depth:
                  type: integer
                  default: 2
                  maximum: 4
      responses:
        '200':
          description: Graph exploration results
```

---

## 7. Processing Pipeline Details

### 7.1 Processing Worker Architecture

```python
"""
Processing Worker - Runs as Cloud Run Job
Processes one content item at a time (sequential processing)
"""

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import structlog

logger = structlog.get_logger()

class ProcessingStage(Enum):
    TEXT_EXTRACTION = "text_extraction"
    SUMMARIZATION = "summarization"
    NER_EXTRACTION = "ner_extraction"
    ENTITY_RESOLUTION = "entity_resolution"
    EMBEDDING_GENERATION = "embedding_generation"
    GRAPH_POPULATION = "graph_population"

@dataclass
class ProcessingContext:
    content_id: str
    blogger_id: str
    content_type: str
    gcs_path: str
    extracted_text: Optional[str] = None
    summary: Optional[dict] = None
    entities: Optional[dict] = None
    resolved_entities: Optional[dict] = None

class ContentProcessor:
    def __init__(
        self,
        gcs_client,
        llm_client,
        neo4j_client,
        supabase_client,
        embedding_client
    ):
        self.gcs = gcs_client
        self.llm = llm_client
        self.neo4j = neo4j_client
        self.supabase = supabase_client
        self.embeddings = embedding_client
    
    async def process(self, message: dict) -> bool:
        """
        Main processing entry point.
        Returns True on success, False on failure.
        """
        ctx = ProcessingContext(
            content_id=message["content_id"],
            blogger_id=message["blogger_id"],
            content_type=message["content_type"],
            gcs_path=message["gcs_path"]
        )
        
        try:
            # Update status to processing
            await self._update_status(ctx.content_id, "processing")
            
            # Stage 1: Text Extraction
            await self._run_stage(
                ProcessingStage.TEXT_EXTRACTION,
                ctx,
                self._extract_text
            )
            
            # Stage 2: Summarization
            await self._run_stage(
                ProcessingStage.SUMMARIZATION,
                ctx,
                self._summarize
            )
            
            # Stage 3: NER Extraction
            await self._run_stage(
                ProcessingStage.NER_EXTRACTION,
                ctx,
                self._extract_entities
            )
            
            # Stage 4: Entity Resolution
            await self._run_stage(
                ProcessingStage.ENTITY_RESOLUTION,
                ctx,
                self._resolve_entities
            )
            
            # Stage 5: Embedding Generation
            await self._run_stage(
                ProcessingStage.EMBEDDING_GENERATION,
                ctx,
                self._generate_embeddings
            )
            
            # Stage 6: Graph Population
            await self._run_stage(
                ProcessingStage.GRAPH_POPULATION,
                ctx,
                self._populate_graph
            )
            
            # Update status to processed
            await self._update_status(ctx.content_id, "processed")
            
            logger.info("Processing completed", content_id=ctx.content_id)
            return True
            
        except Exception as e:
            logger.error("Processing failed", 
                        content_id=ctx.content_id, 
                        error=str(e))
            await self._update_status(ctx.content_id, "failed", str(e))
            return False
    
    async def _run_stage(self, stage: ProcessingStage, ctx: ProcessingContext, func):
        """Run a processing stage with audit logging."""
        await self._log_stage_start(ctx.content_id, stage)
        try:
            await func(ctx)
            await self._log_stage_complete(ctx.content_id, stage)
        except Exception as e:
            await self._log_stage_failed(ctx.content_id, stage, str(e))
            raise
    
    async def _extract_text(self, ctx: ProcessingContext):
        """Extract text from content file."""
        # Download from GCS
        file_content = await self.gcs.download(ctx.gcs_path)
        
        # Extract based on type
        match ctx.content_type:
            case "document":
                ctx.extracted_text = await self._extract_document(file_content)
            case "blog":
                ctx.extracted_text = await self._extract_html(file_content)
            case "video":
                ctx.extracted_text = await self._transcribe_video(file_content)
        
        # Save extracted text to GCS
        await self.gcs.upload(
            f"processed/{ctx.content_id}/extracted_text.txt",
            ctx.extracted_text
        )
    
    async def _summarize(self, ctx: ProcessingContext):
        """Generate summary using LLM."""
        prompt = SUMMARIZATION_PROMPT.format(
            extracted_text=ctx.extracted_text[:50000]  # Limit for context
        )
        
        response = await self.llm.complete(
            model="claude-sonnet-4-20250514",
            prompt=prompt,
            max_tokens=2000
        )
        
        ctx.summary = self._parse_json_response(response)
        
        # Save summary
        await self.gcs.upload(
            f"processed/{ctx.content_id}/summary.json",
            ctx.summary
        )
    
    async def _extract_entities(self, ctx: ProcessingContext):
        """Extract named entities using LLM."""
        prompt = NER_PROMPT.format(
            extracted_text=ctx.extracted_text[:50000]
        )
        
        response = await self.llm.complete(
            model="claude-sonnet-4-20250514",
            prompt=prompt,
            max_tokens=4000
        )
        
        ctx.entities = self._parse_json_response(response)
        
        # Save entities
        await self.gcs.upload(
            f"processed/{ctx.content_id}/entities.json",
            ctx.entities
        )
    
    async def _resolve_entities(self, ctx: ProcessingContext):
        """Resolve entities to canonical records."""
        resolver = EntityResolver(self.neo4j, self.google_places)
        
        resolved = {
            "hotels": [],
            "locations": [],
            "attractions": []
        }
        
        # Resolve hotels
        for hotel in ctx.entities.get("hotels", []):
            resolved_hotel = await resolver.resolve_hotel(hotel)
            resolved["hotels"].append(resolved_hotel)
        
        # Resolve locations
        for location in ctx.entities.get("locations", []):
            resolved_location = await resolver.resolve_location(location)
            resolved["locations"].append(resolved_location)
        
        # Resolve attractions
        for attraction in ctx.entities.get("attractions", []):
            resolved_attraction = await resolver.resolve_attraction(attraction)
            resolved["attractions"].append(resolved_attraction)
        
        ctx.resolved_entities = resolved
    
    async def _generate_embeddings(self, ctx: ProcessingContext):
        """Generate and store embeddings."""
        # Summary embedding
        summary_embedding = await self.embeddings.embed(ctx.summary["summary"])
        await self.supabase.insert_summary_embedding(
            content_id=ctx.content_id,
            summary_text=ctx.summary["summary"],
            embedding=summary_embedding,
            themes=ctx.summary.get("key_themes", [])
        )
        
        # Chunk embeddings for full text
        chunks = self._chunk_text(ctx.extracted_text, chunk_size=1000)
        for i, chunk in enumerate(chunks):
            chunk_embedding = await self.embeddings.embed(chunk)
            await self.supabase.insert_chunk_embedding(
                content_id=ctx.content_id,
                chunk_index=i,
                chunk_text=chunk,
                embedding=chunk_embedding
            )
    
    async def _populate_graph(self, ctx: ProcessingContext):
        """Create nodes and relationships in Neo4j."""
        # Create Content node
        await self.neo4j.create_content_node(
            content_id=ctx.content_id,
            summary=ctx.summary,
            blogger_id=ctx.blogger_id
        )
        
        # Create relationships for hotels
        for hotel in ctx.resolved_entities["hotels"]:
            await self.neo4j.create_reviewed_relationship(
                content_id=ctx.content_id,
                hotel_id=hotel["id"],
                sentiment=hotel["sentiment"],
                highlights=hotel.get("highlights", [])
            )
        
        # Create relationships for locations
        for location in ctx.resolved_entities["locations"]:
            await self.neo4j.create_mentions_relationship(
                content_id=ctx.content_id,
                location_id=location["id"],
                context=location.get("context", "")
            )
        
        # Create relationships for attractions
        for attraction in ctx.resolved_entities["attractions"]:
            await self.neo4j.create_recommends_relationship(
                content_id=ctx.content_id,
                attraction_id=attraction["id"],
                strength=attraction.get("recommendation_strength", "worth-seeing")
            )
```

### 7.2 Chunking Strategy

```python
class TextChunker:
    """
    Intelligent text chunking for embedding generation.
    Uses semantic boundaries when possible.
    """
    
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: list = None
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or [
            "\n\n",  # Paragraph breaks
            "\n",    # Line breaks
            ". ",    # Sentences
            ", ",    # Clauses
            " "      # Words
        ]
    
    def chunk(self, text: str) -> list[dict]:
        """
        Split text into overlapping chunks.
        Returns list of {text, start_char, end_char}
        """
        chunks = []
        current_pos = 0
        
        while current_pos < len(text):
            # Find chunk end
            chunk_end = min(current_pos + self.chunk_size, len(text))
            
            # Try to break at semantic boundary
            if chunk_end < len(text):
                chunk_end = self._find_break_point(
                    text, 
                    current_pos, 
                    chunk_end
                )
            
            chunk_text = text[current_pos:chunk_end].strip()
            
            if chunk_text:
                chunks.append({
                    "text": chunk_text,
                    "start_char": current_pos,
                    "end_char": chunk_end
                })
            
            # Move position with overlap
            current_pos = chunk_end - self.chunk_overlap
            if current_pos <= chunks[-1]["start_char"] if chunks else 0:
                current_pos = chunk_end
        
        return chunks
    
    def _find_break_point(self, text: str, start: int, end: int) -> int:
        """Find the best semantic break point near end."""
        search_start = max(start, end - 200)  # Look back 200 chars max
        search_text = text[search_start:end]
        
        for separator in self.separators:
            last_sep = search_text.rfind(separator)
            if last_sep != -1:
                return search_start + last_sep + len(separator)
        
        return end
```

---

## 8. Query & Retrieval Layer

### 8.1 GraphRAG Query Engine

```python
class GraphRAGQueryEngine:
    """
    Hybrid query engine combining vector search and graph traversal.
    """
    
    def __init__(
        self,
        neo4j_client,
        supabase_client,
        embedding_client,
        llm_client
    ):
        self.neo4j = neo4j_client
        self.supabase = supabase_client
        self.embeddings = embedding_client
        self.llm = llm_client
    
    async def search_hotels(
        self,
        query: str,
        filters: dict = None,
        limit: int = 10
    ) -> SearchResponse:
        """
        Search for hotels using hybrid approach.
        
        1. Vector similarity on query
        2. Graph traversal for relationships
        3. Combine and rank results
        4. Generate synthesized response
        """
        start_time = time.time()
        
        # Step 1: Generate query embedding
        query_embedding = await self.embeddings.embed(query)
        
        # Step 2: Vector search for relevant content
        similar_content = await self.supabase.vector_search(
            table="summary_embeddings",
            embedding=query_embedding,
            limit=50,
            threshold=0.7
        )
        
        content_ids = [c["content_id"] for c in similar_content]
        
        # Step 3: Graph traversal for hotels mentioned in that content
        cypher_query = """
        MATCH (c:Content)-[r:REVIEWED]->(h:Hotel)
        WHERE c.id IN $content_ids
        WITH h, 
             COUNT(DISTINCT c) as mention_count,
             AVG(CASE r.sentiment 
                 WHEN 'positive' THEN 1.0 
                 WHEN 'neutral' THEN 0.5 
                 ELSE 0.0 END) as avg_sentiment,
             COLLECT(DISTINCT r.highlights) as all_highlights,
             COLLECT(DISTINCT {
                 content_id: c.id,
                 blogger_id: c.blogger_id,
                 sentiment: r.sentiment,
                 highlights: r.highlights
             }) as reviews
        RETURN h, mention_count, avg_sentiment, all_highlights, reviews
        ORDER BY mention_count DESC, avg_sentiment DESC
        LIMIT $limit
        """
        
        graph_results = await self.neo4j.execute(
            cypher_query,
            {"content_ids": content_ids, "limit": limit}
        )
        
        # Step 4: Apply additional filters
        if filters:
            graph_results = self._apply_filters(graph_results, filters)
        
        # Step 5: Enrich with blogger info
        enriched_results = await self._enrich_with_bloggers(graph_results)
        
        # Step 6: Generate synthesized response
        recommendations = [
            HotelRecommendation(
                hotel_id=r["h"]["id"],
                name=r["h"]["name"],
                location=f"{r['h']['city']}, {r['h']['country']}",
                blogger_mentions=r["mention_count"],
                average_sentiment=r["avg_sentiment"],
                highlights=self._flatten_highlights(r["all_highlights"]),
                source_contents=r["reviews"][:5]  # Top 5 reviews
            )
            for r in enriched_results
        ]
        
        return SearchResponse(
            query=query,
            results=recommendations,
            total_count=len(recommendations),
            search_time_ms=int((time.time() - start_time) * 1000)
        )
    
    async def get_hotel_insights(self, hotel_id: str) -> dict:
        """
        Get comprehensive blogger insights for a specific hotel.
        """
        cypher_query = """
        MATCH (h:Hotel {id: $hotel_id})
        OPTIONAL MATCH (c:Content)-[r:REVIEWED]->(h)
        OPTIONAL MATCH (b:Blogger)-[:CREATED]->(c)
        OPTIONAL MATCH (h)-[:LOCATED_IN]->(l:Location)
        OPTIONAL MATCH (h)-[sim:SIMILAR_TO]->(similar:Hotel)
        
        WITH h, l,
             COLLECT(DISTINCT {
                 content_id: c.id,
                 blogger_name: b.name,
                 blogger_credibility: b.credibility_score,
                 sentiment: r.sentiment,
                 highlights: r.highlights,
                 concerns: r.concerns,
                 visit_date: r.visit_date
             }) as reviews,
             COLLECT(DISTINCT {
                 id: similar.id,
                 name: similar.name,
                 similarity_score: sim.score
             }) as similar_hotels
        
        RETURN h as hotel, l as location, reviews, similar_hotels
        """
        
        result = await self.neo4j.execute_single(
            cypher_query,
            {"hotel_id": hotel_id}
        )
        
        # Aggregate insights
        reviews = result["reviews"]
        sentiment_breakdown = {
            "positive": len([r for r in reviews if r["sentiment"] == "positive"]),
            "neutral": len([r for r in reviews if r["sentiment"] == "neutral"]),
            "negative": len([r for r in reviews if r["sentiment"] == "negative"])
        }
        
        # Extract top highlights across all reviews
        all_highlights = []
        for r in reviews:
            all_highlights.extend(r.get("highlights", []))
        top_highlights = self._get_top_items(all_highlights, limit=10)
        
        return {
            "hotel": result["hotel"],
            "location": result["location"],
            "total_mentions": len(reviews),
            "sentiment_breakdown": sentiment_breakdown,
            "top_highlights": top_highlights,
            "blogger_reviews": sorted(
                reviews,
                key=lambda x: x.get("blogger_credibility", 0),
                reverse=True
            )[:10],
            "similar_hotels": result["similar_hotels"][:5]
        }
    
    async def explore_connections(
        self,
        start_entity: dict,
        relationship_types: list = None,
        depth: int = 2
    ) -> dict:
        """
        Explore graph connections from a starting entity.
        """
        entity_type = start_entity["type"].capitalize()
        entity_id = start_entity["id"]
        
        # Build dynamic Cypher based on allowed relationships
        rel_filter = ""
        if relationship_types:
            rel_filter = ":" + "|".join(relationship_types)
        
        cypher_query = f"""
        MATCH path = (start:{entity_type} {{id: $entity_id}})-[*1..{depth}]-(connected)
        WHERE start <> connected
        WITH connected, 
             LENGTH(path) as distance,
             [rel in relationships(path) | TYPE(rel)] as relationship_chain
        RETURN DISTINCT 
            labels(connected)[0] as entity_type,
            connected as entity,
            distance,
            relationship_chain
        ORDER BY distance, entity_type
        LIMIT 50
        """
        
        results = await self.neo4j.execute(
            cypher_query,
            {"entity_id": entity_id}
        )
        
        # Group by entity type
        grouped = {}
        for r in results:
            entity_type = r["entity_type"]
            if entity_type not in grouped:
                grouped[entity_type] = []
            grouped[entity_type].append({
                "entity": r["entity"],
                "distance": r["distance"],
                "path": r["relationship_chain"]
            })
        
        return {
            "start_entity": start_entity,
            "connections": grouped,
            "total_connected": len(results)
        }
```

### 8.2 Natural Language to Cypher

```python
class NL2CypherTranslator:
    """
    Translates natural language queries to Cypher.
    Uses LLM with structured prompting.
    """
    
    SCHEMA_CONTEXT = """
    Neo4j Graph Schema:
    
    Nodes:
    - Blogger(id, name, credibility_score)
    - Content(id, type, title, summary, themes[], sentiment)
    - Hotel(id, name, city, country, star_rating, price_tier)
    - Location(id, name, type)
    - Attraction(id, name, type, categories[])
    
    Relationships:
    - (Blogger)-[:CREATED]->(Content)
    - (Content)-[:REVIEWED {sentiment, highlights[], concerns[]}]->(Hotel)
    - (Content)-[:MENTIONS {context}]->(Location)
    - (Content)-[:RECOMMENDS {strength}]->(Attraction)
    - (Hotel)-[:LOCATED_IN]->(Location)
    - (Attraction)-[:LOCATED_IN]->(Location)
    - (Location)-[:PART_OF]->(Location)
    """
    
    async def translate(self, natural_query: str) -> str:
        """
        Convert natural language to Cypher query.
        """
        prompt = f"""
        {self.SCHEMA_CONTEXT}
        
        Translate the following natural language query to a Cypher query.
        Return ONLY the Cypher query, no explanation.
        
        Natural Language Query: {natural_query}
        
        Cypher Query:
        """
        
        response = await self.llm.complete(
            model="claude-sonnet-4-20250514",
            prompt=prompt,
            max_tokens=500
        )
        
        # Extract and validate Cypher
        cypher = self._extract_cypher(response)
        self._validate_cypher(cypher)
        
        return cypher
    
    def _validate_cypher(self, cypher: str):
        """Basic Cypher validation."""
        # Check for dangerous operations
        dangerous = ["DELETE", "DETACH", "DROP", "CREATE INDEX", "REMOVE"]
        for op in dangerous:
            if op in cypher.upper():
                raise ValueError(f"Dangerous operation not allowed: {op}")
        
        # Must be a read query
        if not any(cypher.upper().startswith(kw) for kw in ["MATCH", "OPTIONAL"]):
            raise ValueError("Query must start with MATCH")
```

---

## 9. Technology Stack

### 9.1 Complete Stack Overview

| Layer | Technology | Purpose | Why This Choice |
|-------|------------|---------|-----------------|
| **Compute** | Google Cloud Run | Serverless containers | Scale to zero, pay-per-use, easy deployment |
| **Queue** | Cloud Pub/Sub | Message queue | Native GCP integration, exactly-once delivery |
| **Jobs** | Cloud Run Jobs | Batch processing | Long-running tasks, sequential processing |
| **Object Storage** | Google Cloud Storage | Raw content storage | Durability, lifecycle policies, signed URLs |
| **Relational DB** | Supabase (PostgreSQL) | Operational data | Hosted Postgres, built-in auth, real-time |
| **Vector Store** | Supabase pgvector | Embeddings | Same DB as operational, reduces complexity |
| **Graph DB** | Neo4j AuraDB | Knowledge graph | Purpose-built for relationships, Cypher |
| **Cache** | Redis (Memorystore) | Query caching | Low latency, pub/sub for invalidation |
| **LLM** | Claude (Anthropic) | Summarization, NER | Best reasoning, structured output |
| **Embeddings** | OpenAI text-embedding-3-small | Vector embeddings | Cost-effective, good quality |
| **Transcription** | OpenAI Whisper | Video transcription | Accurate, multi-language |
| **Monitoring** | Cloud Monitoring + Logging | Observability | Native GCP integration |

### 9.2 Service Dependencies

```yaml
# docker-compose.yml (for local development)
version: '3.8'

services:
  ingestion-api:
    build: ./services/ingestion
    ports:
      - "8001:8000"
    environment:
      - GCS_BUCKET=letsbai-blogger-content-dev
      - PUBSUB_TOPIC=content-ingested-dev
      - SUPABASE_URL=${SUPABASE_URL}
      - SUPABASE_KEY=${SUPABASE_KEY}
    depends_on:
      - redis

  query-api:
    build: ./services/query
    ports:
      - "8002:8000"
    environment:
      - NEO4J_URI=${NEO4J_URI}
      - NEO4J_USER=${NEO4J_USER}
      - NEO4J_PASSWORD=${NEO4J_PASSWORD}
      - SUPABASE_URL=${SUPABASE_URL}
      - SUPABASE_KEY=${SUPABASE_KEY}
      - REDIS_URL=redis://redis:6379
    depends_on:
      - redis

  processing-worker:
    build: ./services/processing
    environment:
      - GCS_BUCKET=letsbai-blogger-content-dev
      - PUBSUB_SUBSCRIPTION=content-ingested-sub-dev
      - NEO4J_URI=${NEO4J_URI}
      - SUPABASE_URL=${SUPABASE_URL}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  neo4j:
    image: neo4j:5-community
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=neo4j/password
    volumes:
      - neo4j_data:/data

volumes:
  neo4j_data:
```

---

## 10. Deployment Architecture

### 10.1 GCP Infrastructure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              GCP PROJECT                                     │
│                         letsbai-production                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    VPC: letsbai-vpc                                  │   │
│  │                                                                      │   │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │   │
│  │  │ Cloud Run        │  │ Cloud Run        │  │ Cloud Run Jobs   │  │   │
│  │  │ ingestion-api    │  │ query-api        │  │ processing-worker│  │   │
│  │  │ (min: 0, max: 10)│  │ (min: 1, max: 20)│  │ (concurrency: 1) │  │   │
│  │  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘  │   │
│  │           │                     │                     │            │   │
│  │  ┌────────┴─────────────────────┴─────────────────────┴─────────┐  │   │
│  │  │                    VPC Connector                              │  │   │
│  │  └───────────────────────────┬───────────────────────────────────┘  │   │
│  │                              │                                      │   │
│  │  ┌──────────────────────────┴────────────────────────────────────┐  │   │
│  │  │                    Private Services                            │  │   │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │  │   │
│  │  │  │ Memorystore │  │ Cloud SQL   │  │ Private     │            │  │   │
│  │  │  │ (Redis)     │  │ (if needed) │  │ Endpoints   │            │  │   │
│  │  │  └─────────────┘  └─────────────┘  └─────────────┘            │  │   │
│  │  └───────────────────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Cloud Storage                                     │   │
│  │  ┌────────────────────────────────────────────────────────────┐     │   │
│  │  │ letsbai-blogger-content                                     │     │   │
│  │  │   /raw/     (Standard)                                      │     │   │
│  │  │   /processed/ (Standard)                                    │     │   │
│  │  │   /archive/   (Coldline, 90-day transition)                │     │   │
│  │  └────────────────────────────────────────────────────────────┘     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Pub/Sub                                           │   │
│  │  Topics: content-ingested, content-processed, content-failed        │   │
│  │  Subscriptions: processing-worker-sub (pull, exactly-once)          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    External Services                                 │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │   │
│  │  │ Supabase    │  │ Neo4j       │  │ Anthropic/  │                 │   │
│  │  │ (Postgres)  │  │ AuraDB      │  │ OpenAI APIs │                 │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 10.2 Terraform Configuration

```hcl
# main.tf

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  backend "gcs" {
    bucket = "letsbai-terraform-state"
    prefix = "blogger-knowledge-graph"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Cloud Storage Bucket
resource "google_storage_bucket" "blogger_content" {
  name     = "letsbai-blogger-content-${var.environment}"
  location = var.region
  
  uniform_bucket_level_access = true
  
  lifecycle_rule {
    condition {
      age = 90
      matches_prefix = ["raw/"]
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }
  
  lifecycle_rule {
    condition {
      age = 365
      matches_prefix = ["raw/"]
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }
}

# Pub/Sub Topics
resource "google_pubsub_topic" "content_ingested" {
  name = "content-ingested-${var.environment}"
}

resource "google_pubsub_topic" "content_processed" {
  name = "content-processed-${var.environment}"
}

resource "google_pubsub_topic" "content_failed" {
  name = "content-failed-${var.environment}"
}

# Pub/Sub Subscription with dead letter
resource "google_pubsub_subscription" "processing_worker" {
  name  = "processing-worker-sub-${var.environment}"
  topic = google_pubsub_topic.content_ingested.name
  
  ack_deadline_seconds = 600
  
  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.content_failed.id
    max_delivery_attempts = 3
  }
  
  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
}

# Cloud Run - Ingestion API
resource "google_cloud_run_v2_service" "ingestion_api" {
  name     = "ingestion-api-${var.environment}"
  location = var.region
  
  template {
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/letsbai/ingestion-api:${var.image_tag}"
      
      env {
        name  = "GCS_BUCKET"
        value = google_storage_bucket.blogger_content.name
      }
      env {
        name  = "PUBSUB_TOPIC"
        value = google_pubsub_topic.content_ingested.name
      }
      env {
        name = "SUPABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.supabase_url.secret_id
            version = "latest"
          }
        }
      }
      
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
    
    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }
  }
}

# Cloud Run Jobs - Processing Worker
resource "google_cloud_run_v2_job" "processing_worker" {
  name     = "processing-worker-${var.environment}"
  location = var.region
  
  template {
    template {
      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/letsbai/processing-worker:${var.image_tag}"
        
        env {
          name  = "GCS_BUCKET"
          value = google_storage_bucket.blogger_content.name
        }
        # ... other env vars
        
        resources {
          limits = {
            cpu    = "2"
            memory = "4Gi"
          }
        }
      }
      
      timeout = "3600s"  # 1 hour max
      max_retries = 1
    }
    
    task_count = 1
    parallelism = 1  # Sequential processing
  }
}

# Memorystore Redis
resource "google_redis_instance" "cache" {
  name           = "letsbai-cache-${var.environment}"
  tier           = "BASIC"
  memory_size_gb = 1
  region         = var.region
  
  authorized_network = google_compute_network.vpc.id
}

# VPC for private connectivity
resource "google_compute_network" "vpc" {
  name                    = "letsbai-vpc-${var.environment}"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name          = "letsbai-subnet-${var.environment}"
  ip_cidr_range = "10.0.0.0/24"
  region        = var.region
  network       = google_compute_network.vpc.id
}

# VPC Connector for Cloud Run
resource "google_vpc_access_connector" "connector" {
  name          = "letsbai-connector-${var.environment}"
  region        = var.region
  network       = google_compute_network.vpc.name
  ip_cidr_range = "10.8.0.0/28"
}
```

---

## 11. Security Considerations

### 11.1 Authentication & Authorization

```yaml
Security Layers:

1. API Authentication:
   - Firebase Auth / Supabase Auth for user authentication
   - JWT tokens for API requests
   - API keys for service-to-service communication

2. Blogger Verification:
   - Email verification required
   - Social media link verification
   - Manual approval for high-volume uploaders

3. Content Security:
   - Virus scanning on upload (Cloud Security Scanner)
   - Content type validation
   - File size limits enforced
   - Signed URLs for GCS access (time-limited)

4. Data Access:
   - Row-level security in Supabase
   - Neo4j role-based access control
   - Principle of least privilege for service accounts

5. Network Security:
   - VPC for internal services
   - Cloud Armor for DDoS protection
   - Private endpoints for databases
```

### 11.2 Service Account Permissions

```yaml
# Principle of least privilege

ingestion-service@project.iam.gserviceaccount.com:
  - storage.objects.create (blogger-content bucket)
  - pubsub.topics.publish (content-ingested topic)

processing-worker@project.iam.gserviceaccount.com:
  - storage.objects.get (blogger-content bucket)
  - storage.objects.create (blogger-content bucket)
  - pubsub.subscriptions.consume (processing-worker-sub)
  - secretmanager.secrets.access (API keys)

query-service@project.iam.gserviceaccount.com:
  - storage.objects.get (blogger-content bucket)
  - secretmanager.secrets.access (database credentials)
```

---

## 12. Scalability & Performance

### 12.1 Scaling Strategy

| Component | Scaling Model | Triggers |
|-----------|---------------|----------|
| Ingestion API | Horizontal (0-10) | Request count, CPU |
| Query API | Horizontal (1-20) | Request count, latency |
| Processing Worker | Sequential (1) | Queue depth |
| Supabase | Vertical | Connection count |
| Neo4j AuraDB | Vertical | Query latency |
| Redis | Vertical | Memory usage |

### 12.2 Performance Targets

```yaml
SLOs:

Upload Latency:
  - p50: < 500ms (file receipt acknowledgment)
  - p99: < 2s

Query Latency:
  - p50: < 200ms
  - p99: < 1s

Processing Time:
  - Document (< 10 pages): < 30s
  - Document (10-50 pages): < 2 min
  - Video (< 10 min): < 5 min

Availability:
  - API Uptime: 99.9%
  - Processing Success Rate: 98%
```

### 12.3 Caching Strategy

```python
class QueryCache:
    """
    Multi-layer caching for query results.
    """
    
    # Cache TTLs
    HOTEL_INSIGHTS_TTL = 3600  # 1 hour
    SEARCH_RESULTS_TTL = 300   # 5 minutes
    GRAPH_EXPLORATION_TTL = 1800  # 30 minutes
    
    async def get_or_compute(
        self,
        cache_key: str,
        compute_fn: callable,
        ttl: int
    ):
        # Try Redis cache first
        cached = await self.redis.get(cache_key)
        if cached:
            return json.loads(cached)
        
        # Compute result
        result = await compute_fn()
        
        # Cache result
        await self.redis.setex(
            cache_key,
            ttl,
            json.dumps(result)
        )
        
        return result
    
    def invalidate_hotel(self, hotel_id: str):
        """Invalidate all caches related to a hotel."""
        patterns = [
            f"hotel:{hotel_id}:*",
            f"search:*hotel*",  # Broad invalidation
        ]
        for pattern in patterns:
            self.redis.delete_pattern(pattern)
```

---

## 13. Cost Estimation

### 13.1 Monthly Cost Breakdown (Production)

| Service | Specification | Estimated Cost |
|---------|---------------|----------------|
| **Cloud Run - Ingestion** | 0-10 instances, ~100K requests/mo | $20-50 |
| **Cloud Run - Query** | 1-20 instances, ~1M requests/mo | $100-200 |
| **Cloud Run Jobs** | ~10K processing jobs/mo | $50-100 |
| **Cloud Storage** | 500GB raw + processed | $15-25 |
| **Pub/Sub** | ~50K messages/mo | $5-10 |
| **Memorystore Redis** | 1GB Basic | $35 |
| **Supabase** | Pro plan | $25 |
| **Neo4j AuraDB** | Professional (8GB) | $65 |
| **Claude API** | ~10K requests/mo | $100-300 |
| **OpenAI API** | Embeddings + Whisper | $50-100 |
| **Networking** | Egress, DNS | $20-30 |
| **Monitoring** | Cloud Monitoring | $20-30 |
| **TOTAL** | | **$500-900/mo** |

### 13.2 Cost Optimization Tips

1. **Use Cloud Run min instances = 0** for non-critical services
2. **Batch embedding requests** to reduce API calls
3. **Use caching aggressively** for repeat queries
4. **Implement content deduplication** before processing
5. **Use Coldline storage** for archived content
6. **Monitor LLM token usage** and optimize prompts

---

## 14. Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)
- [ ] Set up GCP project and Terraform
- [ ] Create GCS bucket with lifecycle policies
- [ ] Set up Pub/Sub topics and subscriptions
- [ ] Initialize Supabase project with schemas
- [ ] Set up Neo4j AuraDB instance
- [ ] Create base Docker images

### Phase 2: Ingestion (Weeks 3-4)
- [ ] Build Ingestion API (FastAPI)
- [ ] Implement file upload handler
- [ ] Implement URL scraping service
- [ ] Implement video download handler
- [ ] Deploy to Cloud Run
- [ ] Write integration tests

### Phase 3: Processing (Weeks 5-7)
- [ ] Build text extraction modules
- [ ] Implement LLM summarization pipeline
- [ ] Implement NER extraction pipeline
- [ ] Build entity resolution service
- [ ] Implement embedding generation
- [ ] Build Neo4j graph population
- [ ] Deploy processing worker

### Phase 4: Query Layer (Weeks 8-9)
- [ ] Build Query API (FastAPI)
- [ ] Implement hybrid search (vector + graph)
- [ ] Implement hotel insights endpoint
- [ ] Implement graph exploration endpoint
- [ ] Add caching layer
- [ ] Deploy to Cloud Run

### Phase 5: Polish & Launch (Weeks 10-12)
- [ ] Build admin dashboard
- [ ] Implement monitoring and alerting
- [ ] Performance testing and optimization
- [ ] Security audit
- [ ] Documentation
- [ ] Soft launch with beta bloggers

---

## Appendix A: Example Queries

### Find Hotels Mentioned by Multiple Bloggers

```cypher
MATCH (b:Blogger)-[:CREATED]->(c:Content)-[r:REVIEWED]->(h:Hotel)
WHERE r.sentiment = 'positive'
WITH h, COUNT(DISTINCT b) as blogger_count, 
     COLLECT(DISTINCT b.name) as bloggers,
     COLLECT(r.highlights) as all_highlights
WHERE blogger_count >= 3
RETURN h.name, h.city, blogger_count, bloggers, all_highlights
ORDER BY blogger_count DESC
LIMIT 10
```

### Find Hotels Near an Attraction

```cypher
MATCH (a:Attraction {name: 'Tanah Lot Temple'})-[:LOCATED_IN]->(l:Location)
MATCH (h:Hotel)-[:LOCATED_IN]->(l)
MATCH (c:Content)-[r:REVIEWED]->(h)
WHERE r.sentiment = 'positive'
RETURN h.name, h.price_tier, 
       COUNT(c) as review_count,
       AVG(CASE r.sentiment WHEN 'positive' THEN 5 WHEN 'neutral' THEN 3 ELSE 1 END) as avg_rating
ORDER BY avg_rating DESC, review_count DESC
LIMIT 5
```

### Content with Multiple Entity Types

```cypher
MATCH (c:Content)
WHERE EXISTS((c)-[:REVIEWED]->(:Hotel))
  AND EXISTS((c)-[:RECOMMENDS]->(:Attraction))
  AND EXISTS((c)-[:MENTIONS]->(:Location))
WITH c
MATCH (b:Blogger)-[:CREATED]->(c)
MATCH (c)-[:REVIEWED]->(h:Hotel)
MATCH (c)-[:RECOMMENDS]->(a:Attraction)
MATCH (c)-[:MENTIONS]->(l:Location)
RETURN c.title, b.name,
       COLLECT(DISTINCT h.name) as hotels,
       COLLECT(DISTINCT a.name) as attractions,
       COLLECT(DISTINCT l.name) as locations
LIMIT 20
```

---

## Appendix B: LLM Prompt Templates

### Full Summarization Prompt

```
You are a travel content analyst for LetsBai.ai, a travel planning platform.
Your task is to analyze travel blog content and extract structured insights.

CONTENT TO ANALYZE:
---
{extracted_text}
---

Provide your analysis in the following JSON format. Be thorough and extract
all relevant information. If information is not available, use null.

{
  "summary": "A 2-3 paragraph summary capturing the main experiences, 
              recommendations, and insights from this content. Write in 
              third person (e.g., 'The author visited...')",
              
  "key_themes": [
    "List 3-7 main themes or topics covered",
    "e.g., 'luxury accommodation', 'local cuisine', 'adventure activities'"
  ],
  
  "travel_context": {
    "trip_type": "solo | couple | family | group | business",
    "travel_style": "budget | mid-range | luxury | backpacker",
    "season_visited": "summer | winter | spring | fall | monsoon | dry season",
    "trip_duration": "X days/weeks (if mentioned)",
    "trip_purpose": "leisure | honeymoon | anniversary | adventure | wellness | cultural"
  },
  
  "sentiment_analysis": {
    "overall_tone": "positive | negative | mixed | neutral",
    "enthusiasm_level": "highly_enthusiastic | positive | measured | critical",
    "highlights": [
      "List specific things the author loved or highly recommended"
    ],
    "concerns": [
      "List any negative experiences, warnings, or criticisms"
    ]
  },
  
  "target_audience": "Description of who would benefit most from this content",
  
  "practical_value": {
    "has_budget_info": true/false,
    "has_itinerary": true/false,
    "has_booking_tips": true/false,
    "has_local_tips": true/false
  },
  
  "content_quality": {
    "depth": "superficial | moderate | detailed | comprehensive",
    "recency_indicators": "Any dates or time references that indicate when the trip occurred",
    "credibility_signals": "First-hand experience indicators, photos mentioned, specific details"
  }
}

Important:
- Extract information ONLY from the provided content
- Do not make assumptions or add information not present
- Use null for any fields where information is not available
- Keep the summary factual and based on the content
```

---

*Document Version: 1.0*
*Last Updated: February 2025*
*Next Review: After Phase 1 completion*
## Sub-Location Intelligence Integration (Phase 5)
- **Hierarchy Update**: Introduced `Destination -> Region -> SubLocation -> Attraction/Hotel`. 
- **Geo-Assignment**: Hotels are mapped to SubLocations at ingest using Shapely point-in-polygon logic with a nearest-centroid fallback.
- **Resolver Logic**: LangGraph agents now use a weighted dot-product scoring function (preference vector vs sub-location profile) to rank destinations and sub-locations BEFORE selecting individual hotels.
- **Empathy Layer**: Ranked sub-locations include LLM-generated honest tradeoffs formatted for ChatPlanning and Voice (Zara).
