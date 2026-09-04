CREATE TABLE IF NOT EXISTS "uc_text_array" (
    "id" BIGINT PRIMARY KEY,
    "_id" BIGINT GENERATED ALWAYS AS ("id") STORED,
    "values" TEXT[]
);
ALTER TABLE "uc_text_array" REPLICA IDENTITY FULL;
