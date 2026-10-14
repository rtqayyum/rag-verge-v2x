#!/usr/bin/env bash
set -eo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
stack="$here/../headless"
model="$here/src"

cd "$stack/omnetpp-6.4.0"
source setenv
cd "$stack/inet-4.7.0"
source setenv -f
cd "$stack/simu5g-1.8.0"
source setenv -f
cd "$here/scenario"

config="${1:-Risk}"
repetition="${2:-0}"
ini_file="${V2X_INI:-$here/scenario/tasks.ini}"
opp_run \
  -l "$INET_ROOT/src/INET" \
  -l "$SIMU5G_ROOT/src/simu5g" \
  -l "$model/out/clang-release/v2xmodel" \
  -n "$model:$SIMU5G_ROOT/simulations:$SIMU5G_ROOT/emulation:$SIMU5G_ROOT/src:$INET_ROOT/src" \
  -u Cmdenv -f "$ini_file" -c "$config" -r "$repetition"
