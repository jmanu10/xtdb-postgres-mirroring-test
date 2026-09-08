CREATE TABLE IF NOT EXISTS "uc_jsonb_big_integers" (
    "id" BIGINT PRIMARY KEY,
    "_id" BIGINT GENERATED ALWAYS AS ("id") STORED,
    "payload" JSONB
);
ALTER TABLE "uc_jsonb_big_integers" REPLICA IDENTITY FULL;
