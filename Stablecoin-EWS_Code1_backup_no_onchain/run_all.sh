#!/usr/bin/env bash
# Ban BACKUP khong on-chain (Code 1, Nhom 4) cho macOS/Linux.
# Mac dinh OFFLINE (chi dung cache data/raw). Tai lai tu nguon: ./run_all.sh refresh
set -e
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8
python3 -m pip install -r requirements.txt
if [ "$1" = "refresh" ]; then
  python3 -m src.data.build_panel --version v1 --refresh
else
  python3 -m src.data.build_panel --version v1 --offline
fi
python3 -m pytest -q
echo "XONG. Ket qua: data/processed/panel.parquet, outputs/tables/, outputs/appendix/"
