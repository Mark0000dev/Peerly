\set ON_ERROR_STOP on
SET statement_timeout = '30s';
SET lock_timeout = '2s';
SET timezone = 'UTC';
SET extra_float_digits = 3;
BEGIN ISOLATION LEVEL REPEATABLE READ;
\if :{?backup_snapshot}
SET TRANSACTION SNAPSHOT :'backup_snapshot';
\endif
-- Session-local helper only; rollback removes it. No product schema writes.
CREATE FUNCTION pg_temp.peerly_inventory() RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE
    item record;
    measured jsonb;
    inventory jsonb := '{}'::jsonb;
    total_tables integer := 0;
BEGIN
    FOR item IN SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename LOOP
        total_tables := total_tables + 1;
        IF total_tables > 256 THEN RAISE EXCEPTION 'table_bound'; END IF;
        EXECUTE format(
            'SELECT jsonb_build_object(''rows'', count(*), ''sha256'', '
            'encode(sha256(convert_to(coalesce(string_agg(d, '''' ORDER BY d COLLATE "C"), ''''), '
            '''UTF8'')), ''hex'')) FROM '
            '(SELECT encode(sha256(convert_to(to_jsonb(t)::text, ''UTF8'')), ''hex'') d '
            'FROM (SELECT * FROM public.%I LIMIT 10001) t) bounded', item.tablename)
            INTO measured;
        IF (measured->>'rows')::integer > 10000 THEN RAISE EXCEPTION 'row_bound'; END IF;
        inventory := inventory || jsonb_build_object(item.tablename, measured);
    END LOOP;
    RETURN inventory;
END $$;
WITH retained AS (
    SELECT p.upload_id AS id, p.id AS attempt, u.source_size, u.source_digest,
           p.display_size, p.display_digest
    FROM photo_processing_attempts p JOIN photo_uploads u ON u.id=p.upload_id
    WHERE p.outcome='ready'
    UNION ALL
    SELECT p.image_id, p.id, u.source_size, u.source_digest, p.display_size, p.display_digest
    FROM chat_image_attempts p JOIN chat_image_preparations u ON u.id=p.image_id
    WHERE p.outcome='ready'
), objects AS (
    SELECT 'retained/'||id||'/'||attempt||'/original' AS key,
           source_size AS size, encode(source_digest,'hex') AS sha256 FROM retained
    UNION ALL
    SELECT 'retained/'||id||'/'||attempt||'/photo.jpg', display_size,
           encode(display_digest,'hex') FROM retained
), broken AS (
    SELECT count(*) AS n FROM photos p LEFT JOIN photo_revisions r
      ON (r.account_id,r.version)=(p.account_id,p.current_version) WHERE r.account_id IS NULL
    UNION ALL
    SELECT count(*) FROM photo_revisions r LEFT JOIN photo_upload_revisions u
      ON (u.account_id,u.upload_id,u.version,u.state)=
         (r.account_id,r.upload_id,r.upload_version,'ready')
      LEFT JOIN photo_processing_attempts a ON (a.upload_id,a.id)=(u.upload_id,u.attempt_id)
      WHERE u.upload_id IS NULL OR a.id IS NULL OR a.outcome<>'ready'
    UNION ALL
    SELECT count(*) FROM messages m LEFT JOIN chat_image_revisions r
      ON (r.account_id,r.conversation_id,r.client_message_id,r.image_id,r.version,r.attempt_id,r.state)=
         (m.author_id,m.conversation_id,m.client_message_id,m.image_id,m.image_version,m.image_attempt_id,'ready')
      LEFT JOIN chat_image_attempts a ON (a.image_id,a.id)=(r.image_id,r.attempt_id)
      WHERE m.image_id IS NOT NULL AND (r.image_id IS NULL OR a.id IS NULL OR a.outcome<>'ready')
)
SELECT jsonb_build_object(
    'format', 1,
    'heads', (SELECT jsonb_agg(version_num ORDER BY version_num) FROM alembic_version),
    'tables', pg_temp.peerly_inventory(),
    'broken_relationships', (SELECT sum(n) FROM broken),
    'unvalidated_constraints', (SELECT count(*) FROM pg_constraint c JOIN pg_namespace n
        ON n.oid=c.connamespace WHERE n.nspname='public' AND NOT c.convalidated),
    'disabled_triggers', (SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND t.tgenabled='D'),
    'objects', (SELECT coalesce(jsonb_agg(to_jsonb(o) ORDER BY key),'[]'::jsonb)
        FROM (SELECT * FROM objects ORDER BY key LIMIT 20001) o)
);
ROLLBACK;
