#!/bin/bash

HOST=xo-db
PORT=5432

echo "Waiting for database at $HOST:$PORT to be available..."

check="nc -z $HOST $PORT"

while ! $check; do
  sleep 1
done

echo "Database is up! Starting the application..."
./manage.py makemigrations xo_game
./manage.py migrate

exec "$@"