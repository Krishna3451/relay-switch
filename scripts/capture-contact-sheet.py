"""Make an evidence contact sheet from unchanged native capture frames."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--capture-root',type=Path,default=Path('recording/native-take'))
a=p.parse_args()
root=a.capture_root.resolve()
markers=json.loads((root/'markers.json').read_text())
streams=['shared','teamchat','harborcloud']
frames={key:json.loads((root/key/'frames.json').read_text()) for key in streams}
moments=[('baseline',markers[0]['start']-1000 if markers else min(rows[0]['at'] for rows in frames.values())+5000)]
moments += [(m['stage'],m['completed_at']+1500) for m in markers if m.get('completed_at')]
moments.append(('final',max(rows[-1]['at'] for rows in frames.values())))
selected=[]
for row,(stage,at) in enumerate(moments):
    for column,stream in enumerate(streams):
        f=min(frames[stream],key=lambda f:abs(f['at']-at))
        image=(root/stream/f['file']).resolve()
        image.relative_to(root)
        selected.append({'row':row,'column':column,'stage':stage,'stream':stream,'at':f['at'],'file':str(image.relative_to(root))})
with tempfile.TemporaryDirectory(prefix='relay-contact-') as directory:
    listing=Path(directory)/'frames.ffconcat'
    lines=['ffconcat version 1.0']
    for s in selected:
        image=str(root/s['file']).replace("'","'\\''")
        lines.append("file '"+image+"'")
    listing.write_text('\n'.join(lines)+'\n')
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-safe','0','-f','concat','-i',str(listing),'-vf',f'scale=533:300:flags=lanczos,tile=3x{len(moments)}','-frames:v','1',str(root/'contact-sheet.png')],check=True)
(root/'contact-sheet-index.json').write_text(json.dumps({'columns':streams,'rows':[s for s,_ in moments],'source_frames':selected},indent=2)+'\n')
print(json.dumps({'sheet':str(root/'contact-sheet.png'),'rows':len(moments),'actual_frames':len(selected)}))
