// Create Constraints to ensure uniqueness and fast lookups
CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT claim_id_unique IF NOT EXISTS FOR (c:Claim) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT content_id_unique IF NOT EXISTS FOR (c:Content) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT alias_name_unique IF NOT EXISTS FOR (a:Alias) REQUIRE a.normalized_name IS UNIQUE;
CREATE CONSTRAINT hotel_id_unique IF NOT EXISTS FOR (h:Hotel) REQUIRE h.id IS UNIQUE;
CREATE CONSTRAINT attraction_id_unique IF NOT EXISTS FOR (a:Attraction) REQUIRE a.id IS UNIQUE;
CREATE CONSTRAINT topic_id_unique IF NOT EXISTS FOR (t:Topic) REQUIRE t.id IS UNIQUE;

// Create Vector Indexes for Similarity Search (1024-dim NVIDIA nv-embedqa-e5-v5 embeddings)
CREATE VECTOR INDEX entity_embeddings IF NOT EXISTS FOR (e:Entity) ON (e.embedding)
OPTIONS {indexConfig: {
 `vector.dimensions`: 1024,
 `vector.similarity_function`: 'cosine'
}};

CREATE VECTOR INDEX alias_embeddings IF NOT EXISTS FOR (a:Alias) ON (a.embedding)
OPTIONS {indexConfig: {
 `vector.dimensions`: 1024,
 `vector.similarity_function`: 'cosine'
}};

CREATE VECTOR INDEX claim_embeddings IF NOT EXISTS FOR (c:Claim) ON (c.embedding)
OPTIONS {indexConfig: {
 `vector.dimensions`: 1024,
 `vector.similarity_function`: 'cosine'
}};

// SubLocation Integration Constraints
// Identity is the deterministic Entity `id` (see structured_entity_id), NOT the
// name: distinct places legitimately share a name ("North Shore" on O'ahu AND
// Kaua'i), so name-uniqueness on these labels is WRONG and would reject the
// second "North Shore". Uniqueness is enforced by entity_id_unique on (:Entity id).

// Vector Index for SubLocations (optional for semantic search later)
CREATE VECTOR INDEX sublocation_embeddings IF NOT EXISTS FOR (s:SubLocation) ON (s.embedding)
OPTIONS {indexConfig: {
 `vector.dimensions`: 1024,
 `vector.similarity_function`: 'cosine'
}};
