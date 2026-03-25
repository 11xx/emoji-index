#!/usr/bin/awk -f
# Propagates merged keywords to ALL lines in a variant family (base + skin tones etc).
# Line count is preserved. Only the keywords field changes.
# Usage: awk -f propagate-keywords.awk emojis-full.txt

BEGIN { FS = " \\| " }

# --- Pass 1: collect keyword union per base-name key ---
FNR == NR {
    for (i = 1; i <= NF; i++) gsub(/^[[:space:]]+|[[:space:]]+$/, "", $i)

    name = $4
    kws  = $6

    base = name
    gsub(/: (light|medium-light|medium|medium-dark|dark) skin tone/, "", base)
    gsub(/: (red|curly|white|bald) hair/, "", base)
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", base)

    key = $2 SUBSEP $3 SUBSEP base

    n = split(kws, arr, /,[[:space:]]*/);
    for (i = 1; i <= n; i++) {
        kw = arr[i]
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", kw)
        if (kw != "" && !kw_seen[key, kw]) {
            kw_seen[key, kw] = 1
            merged[key] = (merged[key] == "") ? kw : merged[key] ", " kw
        }
    }
    next
}

# --- Pass 2: reprint every line with merged keywords injected ---
{
    for (i = 1; i <= NF; i++) gsub(/^[[:space:]]+|[[:space:]]+$/, "", $i)

    name = $4
    base = name
    gsub(/: (light|medium-light|medium|medium-dark|dark) skin tone/, "", base)
    gsub(/: (red|curly|white|bald) hair/, "", base)
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", base)

    key = $2 SUBSEP $3 SUBSEP base

    out = $1 " | " $2 " | " $3 " | " $4 " | " $5 " | " merged[key]
    if (NF >= 7) out = out " | " $7
    print out
}
