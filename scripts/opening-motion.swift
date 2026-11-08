// Relay opening: code-native editorial motion, never a product recording.
import AppKit
import Foundation

let args = CommandLine.arguments
func option(_ name: String, _ fallback: String) -> String {
    guard let i = args.firstIndex(of: name), i+1 < args.count else { return fallback }
    return args[i+1]
}
let output = option("--output", "demo/opening-v2/visuals")
let cuesPath = option("--cues", "demo/opening-v2/visuals/motion-cues.json")
let mode = option("--mode", "preview")
let W: CGFloat = 1920, H: CGFloat = 1080
let fps: Int32 = 24
var cue: [String: Double] = ["problem":0,"teamchat":5.5,"harborcloud":10.2,"ownership":14.7,"manual":18.5,"relay":24.2,"agentOwn":27.2,"approval":30.2,"delivery":34.2,"transition":38.0,"end":39.5]
if FileManager.default.fileExists(atPath:cuesPath), let data=try? Data(contentsOf:URL(fileURLWithPath:cuesPath)), let obj=(try? JSONSerialization.jsonObject(with:data)) as? [String:Double] { cue.merge(obj) { _, new in new } }
try FileManager.default.createDirectory(atPath:output,withIntermediateDirectories:true)

func col(_ hex: UInt32, _ alpha: CGFloat = 1) -> NSColor { NSColor(calibratedRed:CGFloat((hex>>16)&255)/255,green:CGFloat((hex>>8)&255)/255,blue:CGFloat(hex&255)/255,alpha:alpha) }
let ink=col(0x202D45), muted=col(0x697282), paper=col(0xF8F7F3), line=col(0xDEDFDF)
let blue=col(0x235BD8), bluePale=col(0xE9EFFD), teal=col(0x24756A), tealPale=col(0xE6F1ED)
let red=col(0xA7463C), redPale=col(0xF9EAE6), green=col(0x247052), white=NSColor.white
var ctx: CGContext { NSGraphicsContext.current!.cgContext }
func clamp(_ x: Double) -> Double { max(0,min(1,x)) }
func ease(_ x: Double) -> Double { let x=clamp(x); return 1-pow(1-x,3) }
func on(_ t:Double,_ start:Double,_ d:Double=0.5)->Double { ease((t-start)/d) }
func between(_ t:Double,_ start:Double,_ end:Double)->Double { let fade=0.45; return on(t,start,fade)*(1-on(t,end,fade)) }
func alpha(_ a:Double,_ draw:()->Void) { guard a>0.0001 else{return};ctx.saveGState();ctx.setAlpha(CGFloat(a));draw();ctx.restoreGState() }
func shift(_ x:CGFloat,_ y:CGFloat,_ draw:()->Void) { ctx.saveGState();ctx.translateBy(x:x,y:-y);draw();ctx.restoreGState() }
func box(_ x:CGFloat,_ y:CGFloat,_ w:CGFloat,_ h:CGFloat,_ fill:NSColor,_ radius:CGFloat=12,_ border:NSColor?=nil) {
    let p=NSBezierPath(roundedRect:NSRect(x:x,y:H-y-h,width:w,height:h),xRadius:radius,yRadius:radius);fill.setFill();p.fill()
    if let border=border {border.setStroke();p.lineWidth=1.5;p.stroke()}
}
func circle(_ x:CGFloat,_ y:CGFloat,_ r:CGFloat,_ fill:NSColor,_ border:NSColor?=nil) {
    let p=NSBezierPath(ovalIn:NSRect(x:x-r,y:H-y-r,width:2*r,height:2*r));fill.setFill();p.fill();if let border=border{border.setStroke();p.lineWidth=2;p.stroke()}
}
func text(_ value:String,_ x:CGFloat,_ y:CGFloat,_ w:CGFloat,_ size:CGFloat,_ fill:NSColor=ink,_ weight:NSFont.Weight = .regular,_ h:CGFloat=150,_ align:NSTextAlignment = .left) {
    let p=NSMutableParagraphStyle();p.lineSpacing=6;p.alignment=align;p.lineBreakMode = .byWordWrapping
    (value as NSString).draw(in:NSRect(x:x,y:H-y-h,width:w,height:h),withAttributes:[.font:NSFont.systemFont(ofSize:size,weight:weight),.foregroundColor:fill,.paragraphStyle:p])
}
func stroke(_ pts:[CGPoint],_ color:NSColor,_ width:CGFloat=3,_ dash:[CGFloat]=[]) {
    guard let first=pts.first else{return};ctx.saveGState();ctx.setStrokeColor(color.cgColor);ctx.setLineWidth(width);ctx.setLineCap(.round);ctx.setLineJoin(.round);ctx.setLineDash(phase:0,lengths:dash);ctx.beginPath();ctx.move(to:CGPoint(x:first.x,y:H-first.y));for p in pts.dropFirst(){ctx.addLine(to:CGPoint(x:p.x,y:H-p.y))};ctx.strokePath();ctx.restoreGState()
}
func arrow(_ x:CGFloat,_ y:CGFloat,_ dx:CGFloat,_ color:NSColor,_ width:CGFloat=3) {
    stroke([CGPoint(x:x,y:y),CGPoint(x:x+dx,y:y)],color,width)
    let sign:CGFloat=dx>=0 ? 1 : -1;stroke([CGPoint(x:x+dx-14*sign,y:y-10),CGPoint(x:x+dx,y:y),CGPoint(x:x+dx-14*sign,y:y+10)],color,width)
}
func check(_ x:CGFloat,_ y:CGFloat,_ s:CGFloat,_ color:NSColor) { stroke([CGPoint(x:x,y:y+s*0.52),CGPoint(x:x+s*0.33,y:y+s*0.83),CGPoint(x:x+s,y:y)],color,4) }
func cross(_ x:CGFloat,_ y:CGFloat,_ s:CGFloat,_ color:NSColor) {stroke([CGPoint(x:x,y:y),CGPoint(x:x+s,y:y+s)],color,4);stroke([CGPoint(x:x+s,y:y),CGPoint(x:x,y:y+s)],color,4)}
func chatIcon(_ x:CGFloat,_ y:CGFloat,_ s:CGFloat,_ color:NSColor) {
    box(x,y,s,s*0.72,color,s*0.16);let p=NSBezierPath();p.move(to:NSPoint(x:x+s*0.2,y:H-y-s*0.63));p.line(to:NSPoint(x:x+s*0.2,y:H-y-s*0.93));p.line(to:NSPoint(x:x+s*0.48,y:H-y-s*0.66));p.close();color.setFill();p.fill()
    circle(x+s*0.3,y+s*0.36,s*0.045,white);circle(x+s*0.5,y+s*0.36,s*0.045,white);circle(x+s*0.7,y+s*0.36,s*0.045,white)
}
func cloudIcon(_ x:CGFloat,_ y:CGFloat,_ s:CGFloat,_ color:NSColor) {
    circle(x+s*0.25,y+s*0.5,s*0.23,color);circle(x+s*0.48,y+s*0.34,s*0.3,color);circle(x+s*0.75,y+s*0.51,s*0.24,color);box(x+s*0.2,y+s*0.48,s*0.62,s*0.27,color,s*0.1)
}
func person(_ x:CGFloat,_ y:CGFloat,_ scale:CGFloat,_ fill:NSColor,_ label:String?=nil) {
    circle(x,y,scale*0.5,fill);circle(x,y-scale*0.12,scale*0.12,white)
    let p=NSBezierPath();p.appendArc(withCenter:NSPoint(x:x,y:H-y-scale*0.24),radius:scale*0.23,startAngle:0,endAngle:180);p.close();white.setFill();p.fill()
    if let label=label{text(label,x-140,y+scale*0.65,280,27,ink,.medium,60,.center)}
}
func miniTag(_ label:String,_ x:CGFloat,_ y:CGFloat,_ width:CGFloat,_ fill:NSColor,_ color:NSColor,_ approved:Bool=false) {
    box(x,y,width,52,fill,8);if approved{check(x+16,y+15,23,color)}
    text(label,x+(approved ? 52:18),y+9,width-(approved ? 66:36),25,color,.semibold,45)
}
func footer() { text("ILLUSTRATIVE SCENARIO  ·  LIVE DEMO FOLLOWS",110,1016,1700,21,muted,.medium,38); }
func heading(_ eyebrow:String,_ title:String,_ t:Double,_ begin:Double) {
    let p=on(t,begin);alpha(p){shift(0,CGFloat(18*(1-p))){text(eyebrow,110,75,1700,25,blue,.semibold,45);text(title,110,142,1700,76,ink,.semibold,180)}}
}
func company(_ side:String,_ x:CGFloat,_ y:CGFloat,_ size:CGFloat=60) {
    if side=="TeamChat"{chatIcon(x,y+10,64,blue)}else{cloudIcon(x,y+4,70,teal)}
    text(side,x+92,y,650,size,ink,.semibold,90)
}

func hook(_ t:Double) {
    text("RELAY  /  THE CUSTOMER’S PROBLEM",110,76,1700,25,blue,.semibold,45)
    alpha(1-on(t,2.45,0.45)){text("An important message.",110,180,1700,100,ink,.semibold,180)}
    alpha(on(t,2.45,0.45)){text("It never arrives.",110,180,1700,108,ink,.semibold,180)}
    company("TeamChat",110,350,42)
    text("MESSAGING APP",110,440,700,23,muted,.semibold,50)
    let y:CGFloat=675
    stroke([CGPoint(x:280,y:y),CGPoint(x:1640,y:y)],line,3)
    person(280,y,116,blue,"You");person(1640,y,116,col(0x858B94),"Recipient")
    let travel=CGFloat(ease((t-0.35)/1.9));let px:CGFloat=400+500*travel
    box(px,y-86,500,125,white,12,line);chatIcon(px+22,y-55,55,blue)
    text("Please confirm the time.",px+104,y-56,370,31,ink,.medium,90)
    let fail=on(t,2.5,0.35)
    alpha(fail){circle(1400,y,33,redPale);cross(1387,y-13,26,red);text("Not received",1460,y+135,360,30,red,.semibold,60,.center)}
    alpha(on(t,3.1)){text("Someone is still waiting for your message.",110,880,1700,44,muted,.regular,90)}
}

func companies(_ t:Double) {
    let start=cue["teamchat"]!;heading("THE TWO COMPANIES","One message. Two companies behind it.",t,start)
    let p=on(t,start+0.1)
    alpha(p){shift(CGFloat(-25*(1-p)),0){
        company("TeamChat",140,390,70)
        text("Messaging app for\npeople and teams",140,488,680,43,ink,.regular,140)
        person(200,770,78,blue);person(320,770,78,col(0x7188BB));person(440,770,78,col(0x8D9BAB))
        chatIcon(560,714,90,blue)
    }}
    let c=on(t,cue["harborcloud"]!-0.5)
    alpha(c){shift(CGFloat(25*(1-c)),0){
        company("HarborCloud",1160,390,70)
        text("Cloud platform",1160,488,650,43,ink,.regular,100)
        cloudIcon(1260,684,220,teal)
        for n in 0..<3 {box(1520,718+CGFloat(n)*40,195,24,tealPale,5);circle(1540,730+CGFloat(n)*40,4,teal)}
    }}
    alpha(c){arrow(810,610,290,muted,3);text("Depends on",795,544,330,28,muted,.medium,50,.center)}
    alpha(on(t,start+1)){miniTag("Some messages aren’t arriving",140,880,610,redPale,red)}
}

func ownership(_ t:Double) {
    let start=cue["ownership"]!;heading("THE COORDINATION PROBLEM","Each team sees its own side.",t,start)
    let a=on(t,start);alpha(a){
        box(110,352,700,536,white,12,line);box(1110,352,700,536,white,12,line)
        company("TeamChat",150,388,53);company("HarborCloud",1150,388,53)
        text("Their own app systems",150,485,600,34,muted,.regular,65)
        text("Their own cloud systems",1150,485,600,34,muted,.regular,65)
        person(460,668,100,blue,"App engineers");person(1460,668,100,teal,"Cloud engineers")
        stroke([CGPoint(x:960,y:360),CGPoint(x:960,y:890)],line,2,[9,12])
        text("Separate\ncontrol",845,395,230,25,muted,.medium,100,.center)
    }
    let ms=cue["manual"]!, elapsed=max(0,t-ms), duration=3.1
    alpha(on(t,ms)){
        let phase=elapsed.truncatingRemainder(dividingBy:duration*2)
        let forward=phase<duration
        let progress=CGFloat(ease((forward ? phase : phase-duration)/duration))
        let x:CGFloat=forward ? 640+480*progress : 1120-480*progress
        box(x,816,330,62,forward ? bluePale:tealPale,10)
        text(forward ? "Question →" : "← Finding",x+25,829,290,29,forward ? blue:teal,.semibold,50)
        text("Questions and findings, back and forth.",110,925,1700,40,muted,.regular,70)
    }
}

func relay(_ t:Double) {
    let start=cue["relay"]!;heading("THE PROJECT","Relay",t,start)
    alpha(on(t,start+0.3)){text("Agents work together. Each company stays in control.",110,250,1700,44,muted,.regular,110)}
    let a=on(t,start+0.15)
    alpha(a){
        box(110,425,640,440,white,12,line);box(1170,425,640,440,white,12,line)
        company("TeamChat",150,458,47);company("HarborCloud",1210,458,47)
        text("Its own systems",150,542,500,30,muted,.regular,60);text("Its own systems",1210,542,500,30,muted,.regular,60)
        circle(430,680,62,bluePale);chatIcon(399,657,62,blue);text("AI agent",290,770,280,33,blue,.semibold,70,.center)
        circle(1490,680,62,tealPale);chatIcon(1459,657,62,teal);text("AI agent",1350,770,280,33,teal,.semibold,70,.center)
        stroke([CGPoint(x:505,y:680),CGPoint(x:1415,y:680)],line,3)
        box(828,625,264,110,ink,12);text("Switch",838,644,244,44,white,.semibold,75,.center)
        text("Connects the agents",765,567,390,25,muted,.medium,50,.center)
    }
    alpha(on(t,start+0.6)*(1-on(t,cue["delivery"]!-0.1))){text("MATTERMOST · THE TEAMS’ INCIDENT ROOM",110,928,1700,25,muted,.medium,55,.center)}
    let own=cue["agentOwn"]!;let pulse=CGFloat(0.45+0.15*sin((t-own)*2.8))
    alpha(on(t,own)){
        for x:CGFloat in [430,1490]{let p=NSBezierPath(ovalIn:NSRect(x:x-78,y:H-680-78,width:156,height:156));(x==430 ? blue:teal).withAlphaComponent(pulse).setStroke();p.lineWidth=2;p.stroke()}
    }
    let approved=on(t,cue["approval"]!+0.55)
    alpha(approved){miniTag("Owner approves",150,357,330,tealPale,green,true);miniTag("Owner approves",1210,357,330,tealPale,green,true)}
    let travelStart=cue["approval"]!+0.95
    alpha(on(t,travelStart)*(1-on(t,cue["delivery"]!-0.3))){
        let p=CGFloat(clamp((t-travelStart)/2.1));let x:CGFloat=520+820*p
        box(x-106,650,212,60,bluePale,8,white);text("Reviewed finding",x-100,666,200,22,blue,.semibold,38,.center)
    }
    // The finding passes behind the bridge; Switch's label remains readable.
    alpha(a){box(828,625,264,110,ink,12);text("Switch",838,644,244,44,white,.semibold,75,.center)}
    alpha(on(t,cue["delivery"]!-0.1)){
        box(460,900,1000,80,tealPale,10);check(490,923,36,green)
        text("Messages arrive again.",560,912,860,46,green,.semibold,70)
    }
    let tr=on(t,cue["transition"]!,0.35)
    alpha(tr){box(0,0,W,H,paper,0);text("Relay",110,76,1700,28,blue,.semibold,60);text("Here’s how.",110,375,1700,132,ink,.semibold,230);text("Two companies. One shared recovery.",110,660,1700,42,muted,.regular,100)}
}

func draw(_ t:Double) {
    box(0,0,W,H,paper,0)
    let team=cue["teamchat"]!, own=cue["ownership"]!, rel=cue["relay"]!
    alpha(1-on(t,team,0.5)){hook(t)}
    alpha(on(t,team,0.5)*(1-on(t,own,0.5))){companies(t)}
    alpha(on(t,own,0.5)*(1-on(t,rel,0.5))){ownership(t)}
    alpha(on(t,rel,0.5)){relay(t)}
    footer()
}

func preview(_ t:Double,_ name:String) throws {
    let bitmap=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:Int(W),pixelsHigh:Int(H),bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
    NSGraphicsContext.saveGraphicsState();NSGraphicsContext.current=NSGraphicsContext(bitmapImageRep:bitmap);draw(t);NSGraphicsContext.restoreGraphicsState()
    try bitmap.representation(using:.png,properties:[:])!.write(to:URL(fileURLWithPath:output+"/"+name+".png"))
}
let duration=cue["end"]!
let previewCues:[(String,Double)]=[("01-hook",0.8),("02-failed",min(cue["teamchat"]!-0.7,4.4)),("03-teamchat",cue["teamchat"]!+1.7),("04-two-companies",cue["harborcloud"]!+1.3),("05-boundaries",cue["ownership"]!+1.3),("06-manual",cue["manual"]!+2.2),("07-relay",cue["relay"]!+1.5),("08-agents",cue["agentOwn"]!+1),("09-approvals",cue["approval"]!+1.1),("10-delivery",cue["delivery"]!+1),("11-transition",min(duration-0.3,cue["transition"]!+0.65))]
if mode=="preview" {
    for (name,time) in previewCues {try preview(time,name)}
    let obj:[String:Any]=["kind":"Illustrative editorial vector motion; no reconstructed product UI","dimensions":[1920,1080],"fps":fps,"duration":duration,"cues":cue,"previews":previewCues.map{["file":$0.0+".png","time":$0.1]}]
    try JSONSerialization.data(withJSONObject:obj,options:[.prettyPrinted,.sortedKeys]).write(to:URL(fileURLWithPath:output+"/visual-manifest.json"))
    print("Prepared \(previewCues.count) editorial motion preview frames")
}
// Software encoding keeps this renderer independent of host hardware encoders.
// PNG frames go only to stdout; pipe directly to ffmpeg, never to a tool log.
if mode=="pipe" {
    let count=Int(ceil(duration*Double(fps)))
    for i in 0..<count {
        autoreleasepool {
            let bitmap=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:Int(W),pixelsHigh:Int(H),bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
            NSGraphicsContext.saveGraphicsState();NSGraphicsContext.current=NSGraphicsContext(bitmapImageRep:bitmap);draw(Double(i)/Double(fps));NSGraphicsContext.restoreGraphicsState()
            FileHandle.standardOutput.write(bitmap.representation(using:.png,properties:[:])!)
        }
    }
}
