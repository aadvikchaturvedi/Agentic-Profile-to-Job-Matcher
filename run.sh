#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "=== 1. Install dependencies ==="
pip install -r requirements.txt
pip install mypy pytest pytest-asyncio

echo ""
echo "=== 2. Install Playwright browsers ==="
playwright install chromium 2>/dev/null || true

echo ""
echo "=== 3. mypy check ==="
python -m mypy backend/ --ignore-missing-imports || true

echo ""
echo "=== 4. Run tests ==="
python -m pytest backend/tests/ -v 2>/dev/null || python -m unittest discover -s backend/tests -v

echo ""
echo "=== Done ==="
