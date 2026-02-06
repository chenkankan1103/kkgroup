#!/bin/bash

echo "測試 API 端點..."
echo ""

# 測試 /api/health
echo "1️⃣ 測試 /api/health"
curl -s http://localhost:5000/api/health | head -c 200
echo ""
echo ""

# 測試 /api/export 的響應大小
echo "2️⃣ 測試 /api/export 的大小"
SIZE=$(curl -s http://localhost:5000/api/export | wc -c)
echo "響應大小: $SIZE bytes"
echo ""

# 測試 /api/export 的前幾行
echo "3️⃣ 測試 /api/export 的內容 (前 300 字符)"
curl -s http://localhost:5000/api/export | head -c 300
echo "..."
