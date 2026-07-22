#!/bin/bash
set -e

echo "Running Silver Layer Scripts..."
for f in /docker-entrypoint-initdb.d/silver/*.sql; do
    echo "Running $f"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f "$f"
done

echo "Running Gold Layer Scripts..."
for f in /docker-entrypoint-initdb.d/gold/*.sql; do
    echo "Running $f"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f "$f"
done
