#!/usr/bin/env bash
set -eo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
stack="$here/../headless"

cd "$stack/omnetpp-6.4.0"
source setenv
cd "$stack/inet-4.7.0"
source setenv -f
cd "$stack/simu5g-1.8.0"
source setenv -f
cd "$here/src"

if command -v gmake >/dev/null 2>&1; then
  build_make=gmake
elif [[ -x /nix/store/4bm0xvf9jwvy4m2havzvr4y88fqmsar5-gnumake-4.2.1/bin/make ]]; then
  build_make=/nix/store/4bm0xvf9jwvy4m2havzvr4y88fqmsar5-gnumake-4.2.1/bin/make
else
  build_make=make
fi
"$build_make" -j4 MODE=release
