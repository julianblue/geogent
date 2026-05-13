-- Runs once on first container start (placed in /docker-entrypoint-initdb.d/).
-- Mirrors scripts/db/init-postgis.sql so the Railway PostGIS service comes
-- up with the same extensions enabled as the local docker-compose stack.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
