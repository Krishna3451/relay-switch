#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p demo/final-v3/visuals
swift -module-cache-path /private/tmp/relay-privacy-swift-cache scripts/privacy-video-motion.swift --mode preview
swift -module-cache-path /private/tmp/relay-privacy-swift-cache scripts/privacy-video-motion.swift --mode pipe |
  ffmpeg -hide_banner -loglevel error -y -f image2pipe -framerate 24 -vcodec png -i pipe:0 -an -c:v libx264 -threads 4 -preset fast -crf 18 -pix_fmt yuv420p -movflags +faststart demo/final-v3/visuals/film-silent.mp4
