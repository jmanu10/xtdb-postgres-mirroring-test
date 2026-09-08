CREATE TABLE IF NOT EXISTS "uc_bigint_array_null" (
    "id" BIGINT PRIMARY KEY,
    "_id" BIGINT GENERATED ALWAYS AS ("id") STORED,
    "values" BIGINT[]
);
ALTER TABLE "uc_bigint_array_null" REPLICA IDENTITY FULL;
