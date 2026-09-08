CREATE TABLE IF NOT EXISTS "uc_jsonb_top_level_null" (
    "id" BIGINT PRIMARY KEY,
    "_id" BIGINT GENERATED ALWAYS AS ("id") STORED,
    "payload" JSONB
);
ALTER TABLE "uc_jsonb_top_level_null" REPLICA IDENTITY FULL;
