# Strip Windows carriage returns if present
{ sub(/\r$/, "") }

/^# group:/ {
  sub(/^# group: /, "")
  group = $0
  next
}

/^# subgroup:/ {
  sub(/^# subgroup: /, "")
  subgroup = $0
  next
}

# Process only fully-qualified sequences to ensure proper rendering
/ ; fully-qualified/ {
  # Split the line at the '#' character where the emoji and name reside
  split($0, parts, "# ")
  if ("" == parts[2]) next

  # Split the remaining string by spaces: [Emoji, Version, NamePart1, NamePart2...]
  split(parts[2], subparts, " ")
  emoji = subparts[1]

  # Reconstruct the name, skipping the emoji and version number
  name = ""
  for (i = 3; i <= length(subparts); i++) {
    name = name (i == 3 ? "" : " ") subparts[i]
  }

  # Output strictly formatted fields separated by a pipe
  printf "%s | %s | %s | %s\n", emoji, group, subgroup, name
}
