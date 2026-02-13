-- Migration: Create sync_log table for rate limiting manual refresh
-- Date: January 30, 2026
-- Purpose: Track manual sync attempts to prevent abuse (limit 3 per day)

CREATE TABLE IF NOT EXISTS public.sync_log (
    id SERIAL PRIMARY KEY,
    triggered_at TIMESTAMPTZ DEFAULT NOW(),
    triggered_by TEXT,  -- user name who triggered
    status TEXT DEFAULT 'started',  -- started, success, failed
    message TEXT
);

-- Enable RLS
ALTER TABLE public.sync_log ENABLE ROW LEVEL SECURITY;

-- Policy: Allow read access
CREATE POLICY "Allow read access to sync_log"
ON public.sync_log
FOR SELECT
USING (true);

-- Policy: Allow insert for service role
CREATE POLICY "Service role insert sync_log"
ON public.sync_log
FOR INSERT
TO service_role
WITH CHECK (true);

-- Policy: Allow update for service role
CREATE POLICY "Service role update sync_log"
ON public.sync_log
FOR UPDATE
TO service_role
USING (true)
WITH CHECK (true);

-- Index for efficient daily count queries
CREATE INDEX idx_sync_log_triggered_at ON public.sync_log(triggered_at);

-- Function to check if sync is allowed (max 3 per day)
CREATE OR REPLACE FUNCTION check_sync_allowed()
RETURNS TABLE (allowed BOOLEAN, count_today INT, message TEXT)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    today_count INT;
    max_per_day INT := 3;
BEGIN
    SELECT COUNT(*) INTO today_count
    FROM sync_log
    WHERE triggered_at >= CURRENT_DATE
    AND triggered_at < CURRENT_DATE + INTERVAL '1 day';

    IF today_count >= max_per_day THEN
        RETURN QUERY SELECT FALSE, today_count, 'Limite atteinte (3 par jour)'::TEXT;
    ELSE
        RETURN QUERY SELECT TRUE, today_count, NULL::TEXT;
    END IF;
END;
$$;
