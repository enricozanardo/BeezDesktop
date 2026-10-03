#!/usr/bin/env bash
# GTK / WebKit packages required by Toga on Ubuntu 24.04+.
# Run with sudo on the operator workstation.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y \
  libgirepository1.0-dev \
  libcairo2-dev \
  libpango1.0-dev \
  libwebkit2gtk-4.1-dev \
  gir1.2-webkit2-4.1 \
  python3-gi \
  python3-gi-cairo \
  pkg-config
echo "Toga Linux GUI dependencies installed."
