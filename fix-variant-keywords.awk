#!/usr/bin/awk -f
# Fixes variant-keyword contamination (skin tones, hair styles).
# Shared pool = union of all family keywords MINUS variant-specific descriptors.
# Each line then gets only its own specific descriptor appended.
# Usage: awk -f fix-variant-keywords.awk emojis-full.txt emojis-full.txt

BEGIN { FS = " \\| " }

# Returns 1 if a keyword is a variant-specific descriptor to strip from shared pool
function is_variant_kw(kw,    l) {
  l = tolower(kw)
  # full skin tone phrases
  if (l ~ /^(light|medium-light|medium|medium-dark|dark) skin tone$/) return 1
  if (l == "skin tone") return 1
  # standalone fragments produced when model split the phrases
  if (l == "skin" || l == "tone") return 1
  # standalone modifier words that only make sense as skin/hair descriptors
  if (l == "medium-light" || l == "medium-dark") return 1
  # hair style descriptors
  if (l ~ /^(red|curly|white|bald) hair$/) return 1
  if (l == "hair style" || l == "hair type") return 1
  return 0
}

# Returns the variant-specific keyword for this name, or "" for base
function variant_descriptor(name,    l) {
  l = tolower(name)
  if (l ~ /: light skin tone$/)        return "light skin tone"
  if (l ~ /: medium-light skin tone$/) return "medium-light skin tone"
  if (l ~ /: medium skin tone$/)       return "medium skin tone"
  if (l ~ /: medium-dark skin tone$/)  return "medium-dark skin tone"
  if (l ~ /: dark skin tone$/)         return "dark skin tone"
  if (l ~ /: red hair$/)               return "red hair"
  if (l ~ /: curly hair$/)             return "curly hair"
  if (l ~ /: white hair$/)             return "white hair"
  if (l ~ /: bald$/)                   return "bald"
  return ""
}

function base_name(name,    b) {
  b = name
  gsub(/: (light|medium-light|medium|medium-dark|dark) skin tone/, "", b)
  gsub(/: (red|curly|white|bald) hair/, "", b)
  gsub(/: bald/, "", b)
  gsub(/^[[:space:]]+|[[:space:]]+$/, "", b)
  return b
}

# --- Pass 1: build clean shared keyword pool per family ---
FNR == NR {
  for (i = 1; i <= NF; i++) gsub(/^[[:space:]]+|[[:space:]]+$/, "", $i)

  key = $2 SUBSEP $3 SUBSEP base_name($4)

  n = split($6, arr, /,[[:space:]]*/);
  for (i = 1; i <= n; i++) {
    kw = arr[i]
    gsub(/^[[:space:]]+|[[:space:]]+$/, "", kw)
    if (kw == "" || is_variant_kw(kw)) next
    if (!kw_seen[key, kw]) {
      kw_seen[key, kw] = 1
      shared[key] = (shared[key] == "") ? kw : shared[key] ", " kw
    }
  }
  next
}

# --- Pass 2: reprint every line with corrected keywords ---
{
  for (i = 1; i <= NF; i++) gsub(/^[[:space:]]+|[[:space:]]+$/, "", $i)

  key = $2 SUBSEP $3 SUBSEP base_name($4)

  kws = shared[key]

  # append only this line's own descriptor (empty string for base emoji)
  vd = variant_descriptor($4)
  if (vd != "") kws = kws ", " vd

  out = $1 " | " $2 " | " $3 " | " $4 " | " $5 " | " kws
  if (NF >= 7) out = out " | " $7
  print out
}
