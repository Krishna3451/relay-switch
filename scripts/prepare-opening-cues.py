"""Map approved opening sentences to the actual narration's character timings."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'demo/opening-v2'
provider = json.loads((OUT / 'provider-alignment.json').read_text())
alignment = provider.get('normalized_alignment') or provider['alignment']
characters = alignment['characters']
starts = alignment['character_start_times_seconds']
mapped, indices = [], []
for index, character in enumerate(characters):
    for letter in character.casefold():
        if letter.isalnum():
            mapped.append(letter)
            indices.append(index)
full = ''.join(mapped)
anchors = {
    'problem': 'You send an important message',
    'teamchat': 'This is happening on TeamChat',
    'harborcloud': 'TeamChat relies on HarborCloud',
    'ownership': 'Each team can investigate only its own systems',
    'manual': 'Engineers pass questions and findings back and forth',
    'relay': 'Relay brings their agents together through Switch',
    'agentOwn': 'Each agent investigates its own side',
    'approval': 'People approve what gets shared and changed',
    'delivery': 'Both teams check that messages are arriving again',
    'transition': 'Here’s how',
}
cues = {}
for key, anchor in anchors.items():
    target = ''.join(c for c in anchor.casefold() if c.isalnum())
    position = full.find(target)
    if position < 0 or full.find(target, position + 1) >= 0:
        raise ValueError('Missing or ambiguous opening anchor: ' + key)
    cues[key] = starts[indices[position]]
manifest = json.loads((OUT / 'narration-manifest.json').read_text())
cues['end'] = manifest['audio_seconds']
if not 35 <= cues['end'] <= 40:
    raise ValueError('Actual approved opening narration is outside 35–40 seconds')
if list(cues.values()) != sorted(cues.values()):
    raise ValueError('Opening cue order differs from approved narration')
(OUT / 'voice-cues.json').write_text(json.dumps(cues, indent=2) + '\n')
print(json.dumps(cues, indent=2))
