#!/bin/zsh
cd "${0:A:h}/.."
python3 scripts/package_demo.py
if [[ $? -ne 0 ]]; then
  echo '整理失败，请保留窗口中的错误信息。'
  exit 1
fi
open dist
