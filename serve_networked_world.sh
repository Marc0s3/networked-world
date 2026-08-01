#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
echo "Starting Networked World v1.0.1 Professional Atlas..."
python3 server.py --port 0
