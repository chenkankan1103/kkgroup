#!/bin/bash
curl -v -s -o response.html -w '%{http_code}' \
  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36' \
  -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8' \
  -H 'Accept-Language: zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7' \
  -H 'Accept-Encoding: gzip, deflate, br, zstd' \
  -H 'Origin: https://ani.gamer.com.tw' \
  -H 'Connection: keep-alive' \
  -H 'Referer: https://ani.gamer.com.tw/' \
  -H 'Sec-CH-UA: "Not/A;Brand";v="99", "Google Chrome";v="130", "Chromium";v="130"' \
  -H 'Sec-CH-UA-Mobile: ?0' \
  -H 'Sec-CH-UA-Platform: "Windows"' \
  -H 'Sec-CH-UA-Bitness: "64"' \
  -H 'Sec-CH-UA-Arch: "x86_64"' \
  -H 'Sec-CH-UA-Full-Version: "130.0.0.0"' \
  -H 'Sec-CH-UA-Platform-Version: "10.0.0"' \
  -H 'Sec-CH-UA-Model: ""' \
  -H 'Sec-Fetch-Dest: document' \
  -H 'Sec-Fetch-Mode: navigate' \
  -H 'Sec-Fetch-Site: same-origin' \
  -H 'Sec-Fetch-User: ?1' \
  -H 'Upgrade-Insecure-Requests: 1' \
  -H 'Cache-Control: max-age=0' \
  https://ani.gamer.com.tw/
cat response.html | head -100