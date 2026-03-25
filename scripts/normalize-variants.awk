#!/usr/bin/awk -f
# Single-pass variant normaliser:
#   - Merges keyword union across all family members
#   - Strips variant-specific terms (skin tone, hair) from shared pool
#   - Injects only each line's own descriptor at the end of keywords
#   - Normalises label: base emoji's label is used for all variants
#
# Usage: awk -f normalise-variants.awk emojis-full.txt emojis-full.txt > emojis-out.txt

BEGIN { FS = " \\| " }

function trim(s) { gsub(/^[[:space:]]+|[[:space:]]+$/, "", s); return s }

function is_variant_kw(kw,    l) {
  l = tolower(kw)
  if (l ~ /^(light|medium-light|medium|medium-dark|dark) skin tone$/) return 1
  if (l == "skin tone" || l == "skin" || l == "tone")                 return 1
  if (l == "medium-light" || l == "medium-dark")                      return 1
  if (l ~ /^(red|curly|white|bald) hair$/)                            return 1
  if (l == "hair style" || l == "hair type")                          return 1
  return 0
}

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
  return trim(b)
}

function is_base(name) {
  return (variant_descriptor(name) == "")
}

# --- Pass 1: build shared keyword pool and capture base label per family ---
FNR == NR {
  for (i = 1; i <= NF; i++) $i = trim($i)

  key = $2 SUBSEP $3 SUBSEP base_name($4)

  # capture label from base emoji only (no variant suffix in name)
  if (is_base($4) && !(key in base_label))
    base_label[key] = $5

  n = split($6, arr, /,[[:space:]]*/);
  for (i = 1; i <= n; i++) {
    kw = trim(arr[i])
    if (kw == "" || is_variant_kw(kw)) next
    if (!kw_seen[key, kw]) {
      kw_seen[key, kw] = 1
      shared[key] = (shared[key] == "") ? kw : shared[key] ", " kw
    }
  }
  next
}

# --- Pass 2: reprint with normalised label + corrected keywords ---
{
  for (i = 1; i <= NF; i++) $i = trim($i)

  key = $2 SUBSEP $3 SUBSEP base_name($4)

  # use base label; fall back to this line's own label if family has no base
  label = (key in base_label) ? base_label[key] : $5

  kws = shared[key]
  vd  = variant_descriptor($4)
  if (vd != "") kws = kws ", " vd

  out = $1 " | " $2 " | " $3 " | " $4 " | " label " | " kws
  if (NF >= 7) out = out " | " $7
  print out
}
