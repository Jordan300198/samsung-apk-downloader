#!/bin/bash
# Samsung APK Downloader — Quick Start
# Usage: ./start.sh [port]

PORT=${1:-5050}
cd "$(dirname "$0")"
echo "🚀 Samsung APK Downloader — Web Platform"
echo "   http://localhost:$PORT"
echo ""
python app.py 2>&1
