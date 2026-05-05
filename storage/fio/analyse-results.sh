#!/usr/bin/env bash

if [ $# -ne 1 ]; then
    echo "Usage: $0 <fio_output.log>"
    exit 1
fi

LOG="$1"

printf "%-10s %-10s %-10s %-15s %-20s %-10s\n" \
       "TEST" "JOB" "RW" "AVG_LATENCY" "BANDWIDTH" "IOPS"
printf "%-10s %-10s %-10s %-15s %-20s %-10s\n" \
       "----------" "----------" "----------" "---------------" "--------------------" "----------"

awk '
/Running test=/ {
    match($0, /test='\''([^'\'']+)'\''/, t)
    test=t[1]
}

/job=/ {
    match($0, /job='\''([^'\'']+)'\''/, j)
    job=j[1]
}

/^[[:space:]]*read:/ {
    rw="READ"
    match($0, /IOPS=([^,]+)/, i)
    match($0, /BW=([^ ]+)/, b)
    iops[rw]=i[1]
    bw[rw]=b[1]
}

/^[[:space:]]*write:/ {
    rw="WRITE"
    match($0, /IOPS=([^,]+)/, i)
    match($0, /BW=([^ ]+)/, b)
    iops[rw]=i[1]
    bw[rw]=b[1]
}

/avg=/ && /^ *lat / {
    match($0, /avg=([0-9.]+)/, l)
    latency=l[1]

    if ($0 ~ /usec/) latency=latency " us"
    else if ($0 ~ /msec/) latency=latency " ms"
    else if ($0 ~ /nsec/) latency=latency " ns"

    # Save latency per rw mode if available, else generic
    if (rw != "") lat[rw]=latency
}

/Run status group/ {
    if ("READ" in iops) {
        printf "%-10s %-10s %-10s %-15s %-20s %-10s\n",
               test, job, "READ", lat["READ"], bw["READ"], iops["READ"]
    }
    if ("WRITE" in iops) {
        printf "%-10s %-10s %-10s %-15s %-20s %-10s\n",
               test, job, "WRITE", lat["WRITE"], bw["WRITE"], iops["WRITE"]
    }

    delete iops
    delete bw
    delete lat
    rw=""
}
' "$LOG"
