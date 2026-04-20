-- Runs once on first container start (mounted into /docker-entrypoint-initdb.d/).
-- The postgis/postgis image already ships the extension; this guarantees it's enabled.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
