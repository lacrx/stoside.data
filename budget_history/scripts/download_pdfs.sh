#!/bin/bash
# Download PDFs via curl (urllib gets 403 from Akamai edge)
set -u
cd "$(dirname "$0")/.."

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

ok=0
fail=0
skip=0
fails=()

# jq would be cleaner but Python is available
python -c "
import json
for r in json.load(open('inventory.json')):
    print(r['doc_id'] + '\t' + r['url'] + '\t' + r['local_path'])
" | tr -d '\r' | while IFS=$'\t' read -r doc_id url local_path; do
    # Defensive: strip any stray trailing whitespace / CR that leaks into the path
    local_path="${local_path%$'\r'}"
    local_path="${local_path%% }"
    if [ -s "$local_path" ]; then
        skip=$((skip+1))
        continue
    fi
    # Run in foreground, capture HTTP status
    http_code=$(curl -s -o "$local_path" -w "%{http_code}" -L \
        -A "$UA" \
        -H "Accept: application/pdf,*/*;q=0.9" \
        -H "Accept-Language: en-US,en;q=0.9" \
        -H "Accept-Encoding: gzip, deflate, br" \
        -H "Referer: https://www.ci.oceanside.ca.us/government/financial-services" \
        -H "Sec-Fetch-Dest: document" \
        -H "Sec-Fetch-Mode: navigate" \
        -H "Sec-Fetch-Site: same-origin" \
        -H "Upgrade-Insecure-Requests: 1" \
        --compressed \
        "$url")
    if [ "$http_code" = "200" ] && [ -s "$local_path" ]; then
        size=$(stat -c%s "$local_path" 2>/dev/null || wc -c < "$local_path")
        ok=$((ok+1))
        printf "OK   %-10s %-15s %s\n" "$doc_id" "$(numfmt --to=iec "$size" 2>/dev/null || echo "${size}B")" "$local_path"
    else
        rm -f "$local_path"
        fail=$((fail+1))
        echo "FAIL $doc_id code=$http_code $url"
    fi
    sleep 0.4
done

echo "done"
