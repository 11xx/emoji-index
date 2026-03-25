#!/usr/bin/awk -f
# Usage: awk -f add-codepoints.awk emoji-test.txt emojis.txt > emojis-new.txt

# Pass 1: build emoji → formatted codepoints map from emoji-test.txt
FNR == NR {
  if (/^[[:space:]]*#/ || /^[[:space:]]*$/) next
  if (!/; fully-qualified/) next

  # codepoints: everything left of the semicolon
  semi = index($0, ";")
  cp_raw = substr($0, 1, semi - 1)
  gsub(/[[:space:]]+/, " ", cp_raw)
  gsub(/^ | $/, "", cp_raw)

  # emoji glyph: first token after "# "
  hash = index($0, "# ")
  rest = substr($0, hash + 2)
  split(rest, tok, " ")
  emoji_char = tok[1]

  # format as U+XXXX U+XXXX ...
  n = split(cp_raw, parts, " ")
  fmt = ""
  for (i = 1; i <= n; i++)
    if (parts[i] ~ /^[0-9A-F]+$/)
      fmt = fmt (fmt ? " " : "") "U+" parts[i]

  codepoints[emoji_char] = fmt
  next
}

# Pass 2: emojis.txt — append codepoints field
{
  pipe = index($0, " | ")
  if (pipe == 0) { print; next }

  emoji_char = substr($0, 1, pipe - 1)

  if (emoji_char in codepoints)
    print $0 " | " codepoints[emoji_char]
  else {
    print $0 " | ?"    # flag unmatched so they're easy to grep later
  }
}
