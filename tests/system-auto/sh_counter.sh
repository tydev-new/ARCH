#!/bin/sh
counter=0
while [ $counter -lt 6000 ]; do
    ts=$(date "+%Y-%m-%d %H:%M:%S")
    #echo "[$ts] Counter: $counter"
    echo "[$ts] $counter" >> sh_counter_output.txt
    counter=$((counter+1))
    sleep 3
done