#!/bin/bash

set -u

if [ "$LIVE" = "true" ]; then
    git fetch --all
    git reset --hard origin/master
    docker build -t hdb_scraper .
fi

rm -f data/bidadari_2.log

docker run --rm -v `pwd`/data:/app/data hdb_scraper

cat data/bidadari_2.log

if grep --quiet "^###OK###$" data/bidadari_2.log; then
    # If there is any changes to the data scraped
    if [[ $(git diff data/bidadari_2.csv) ]]; then
        git add data/bidadari_2.*
        git commit -m "Updated bidadari feb data on `date`"
        if [ "$LIVE" = "true" ]; then
            git push
        fi
    else
        echo "No change in data"
        git checkout -- data/bidadari_2.*
    fi
else
    echo "Data scrape failed"
    git checkout -- data/bidadari_2.*
fi
