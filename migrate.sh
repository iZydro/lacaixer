#!/bin/bash

echo "select * from plans" | sqlite3 src/database.db | while read l
do
    id=$(echo ${l} | cut -d "|" -f1)
    ts=$(echo ${l} | cut -d "|" -f2)
    pa=$(echo ${l} | cut -d "|" -f3)

    echo "${id} ${ts} ${pa}"

    aws dynamodb put-item \
        --table-name lacaixer \
        --item '{"id": {"S": "'${id}'"}, "timestamp": {"N": "'${ts}'"}, "parts": {"N": "'${pa}'"}}'

done
