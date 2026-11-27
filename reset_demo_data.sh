#!/usr/bin/env bash
# Deletes the three demo databases; each service re-seeds on the next start. Stop the services first.
cd "$(dirname "$0")"
rm -fv police-service/police.db judiciary-service/judiciary.db correctional-service/correctional.db
