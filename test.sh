#!/usr/bin/env bash
# 執行單元測試。優先使用 conda env `business` 的 python（已裝好本專案所需套件），
# 找不到就退回 PATH 上的 python3。
set -euo pipefail

PYTHON_BIN="${DOCQA_PYTHON:-/home/jj/miniconda3/envs/business/bin/python}"

if [ ! -x "$PYTHON_BIN" ]; then
    echo "找不到 $PYTHON_BIN，改用 PATH 上的 python3" >&2
    PYTHON_BIN="python3"
fi

cd "$(dirname "${BASH_SOURCE[0]}")"

exec "$PYTHON_BIN" -m pytest tests/ -v
