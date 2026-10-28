#!/bin/zsh
cd "${0:A:h}"
open 'http://localhost:4175/'
python3 -m backend.local_recognition
