#!/bin/bash
# Fetch Oceanside finance pages with browser headers
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
HDRS=(
  -A "$UA"
  -H "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
  -H "Accept-Language: en-US,en;q=0.9"
  -H "Sec-Fetch-Dest: document"
  -H "Sec-Fetch-Mode: navigate"
  -H "Sec-Fetch-Site: none"
  -H "Upgrade-Insecure-Requests: 1"
  --compressed
)
fetch() {
  curl -s -L "${HDRS[@]}" "$1" -o "$2"
}
export UA
export -f fetch
