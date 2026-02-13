-- Migration: Add password_prefix column for fast login lookup
-- Date: 2026-01-29
-- Purpose: Store SHA256 prefix of password for O(1) lookup instead of O(n) bcrypt checks

-- Step 1: Add password_prefix column
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_prefix TEXT;

-- Step 2: Create index for fast lookup
CREATE INDEX IF NOT EXISTS idx_users_password_prefix ON users(password_prefix);

-- Step 3: Add comment for documentation
COMMENT ON COLUMN users.password_prefix IS 'First 16 chars of SHA256(password) for fast lookup. Login flow: query by prefix (instant), then bcrypt verify (single check).';
