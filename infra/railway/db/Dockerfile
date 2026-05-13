# PostGIS container for the geogent Railway deployment.
#
# Railway's managed Postgres add-on does NOT include the PostGIS extension,
# so we deploy our own based on the official postgis image. Volumes attached
# in the Railway dashboard will persist /var/lib/postgresql/data.

FROM postgis/postgis:16-3.4

# Ensure the PostGIS extensions exist on first cluster init.
COPY init-postgis.sql /docker-entrypoint-initdb.d/10-init-postgis.sql

EXPOSE 5432
