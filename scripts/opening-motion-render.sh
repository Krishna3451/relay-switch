#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
cues="${1:-demo/opening-v2/voice-cues.json}"
visuals="${2:-demo/opening-v2/visuals}"
mkdir -p "$visuals"
swift -module-cache-path /private/tmp/relay-opening-swift-cache scripts/opening-motion.swift --mode preview --cues "$cues" --output "$visuals"
swift -module-cache-path /private/tmp/relay-opening-swift-cache scripts/opening-motion.swift --mode pipe --cues "$cues" --output "$visuals" |
  "${FFMPEG:-ffmpeg}" -hide_banner -loglevel error -y -f image2pipe -framerate 24 -vcodec png -i pipe:0 -an -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -movflags +faststart "$visuals/opening-silent.mp4"
