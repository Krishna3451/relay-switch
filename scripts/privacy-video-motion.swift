// Privacy-centered Relay film. Editorial illustrations + unchanged native capture excerpts.
import AppKit
import Foundation
let args=CommandLine.arguments
func option(_ name:String,_ fallback:String)->String { guard let i=args.firstIndex(of:name),i+1<args.count else{return fallback};return args[i+1] }
let root=option("--root",FileManager.default.currentDirectoryPath)
let output=option("--output","demo/final-v3/visuals")
let mode=option("--mode","preview")
let planPath=option("--plan","demo/final-v3/privacy-edit-plan.json")
let plan=try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:planPath))) as! [String:Any]
let cue=plan["cues"] as! [String:Double]
let clips=plan["clips"] as! [[String:Any]]
let duration=plan["duration"] as! Double
let frameCount=plan["frameCount"] as! Int
let W:CGFloat=1920,H:CGFloat=1080
let fps:Int32=24
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

let images=NSCache<NSString,NSImage>()
images.countLimit=8
func original(_ path:String)->NSImage {
    if let value=images.object(forKey:path as NSString){return value}
    let value=NSImage(contentsOfFile:root+"/"+path)!
    images.setObject(value,forKey:path as NSString)
    return value
}
func capture(_ path:String,_ destination:NSRect,_ roi:NSRect?=nil) {
    let image=original(path)
    let source=roi ?? NSRect(x:0,y:0,width:1600,height:900)
    let from=NSRect(x:source.minX,y:900-source.minY-source.height,width:source.width,height:source.height)
    let to=NSRect(x:destination.minX,y:H-destination.minY-destination.height,width:destination.width,height:destination.height)
    ctx.saveGState();NSBezierPath(rect:to).addClip()
    image.draw(in:to,from:from,operation:.sourceOver,fraction:1,respectFlipped:false,hints:[.interpolation:NSImageInterpolation.high])
    ctx.restoreGState()
}
func frame(_ clip:[String:Any],_ t:Double)->String {
    let rows=clip["frames"] as! [[String:Any]],elapsed=max(0,t-(clip["start"] as! Double))
    return (rows.last(where:{($0["offset"] as! Double)<=elapsed}) ?? rows[0])["path"] as! String
}
func lockMark(_ x:CGFloat,_ y:CGFloat) {
    let p=NSBezierPath();p.appendArc(withCenter:NSPoint(x:x+18,y:H-y-19),radius:13,startAngle:0,endAngle:180)
    muted.setStroke();p.lineWidth=3;p.stroke();box(x,y+18,36,29,bluePale,5,line);circle(x+18,y+31,3,blue)
}
func note(_ title:String,_ detail:String,_ y:CGFloat,_ color:NSColor=blue,_ fill:NSColor=bluePale) {
    box(90,y,760,100,fill,10);text(title,115,y+15,710,31,color,.semibold,50)
    text(detail,115,y+59,710,22,muted,.regular,43)
}
func sourceFooter(_ label:String="Recorded UI · editorial zooms and highlights") {
    box(0,1037,W,43,paper,0);text(label,90,1049,1740,17,muted,.medium,30)
}
func recordedHeader(_ label:String,_ eyebrow:String="ACTUAL MATTERMOST RECORDING") {
    box(0,0,W,112,paper,0)
    if !eyebrow.isEmpty && eyebrow != "ACTUAL MATTERMOST RECORDING" {text(eyebrow,90,16,1740,19,blue,.semibold,35)}
    text(label,90,45,1740,40,ink,.semibold,62)
}

func intro(_ t:Double) {
    if t<cue["companies"]! {
        text("RELAY / THE CUSTOMER’S PROBLEM",110,76,1700,25,blue,.semibold,45)
        text(t<2.0 ? "An important message." : "It never arrives.",110,180,1700,t<2 ? 100:108,ink,.semibold,180)
        company("TeamChat",110,350,42);text("MESSAGING APP",110,440,700,23,muted,.semibold,50)
        let y:CGFloat=675;stroke([CGPoint(x:280,y:y),CGPoint(x:1640,y:y)],line,3)
        person(280,y,116,blue,"You");person(1640,y,116,col(0x858B94),"Recipient")
        let px:CGFloat=400+500*CGFloat(ease((t-0.25)/1.6))
        box(px,y-86,500,125,white,12,line);chatIcon(px+22,y-55,55,blue);text("Please confirm the time.",px+104,y-56,370,31,ink,.medium,90)
        alpha(on(t,2.0,0.3)){circle(1400,y,33,redPale);cross(1387,y-13,26,red);text("Not received",1460,y+135,360,30,red,.semibold,60,.center)}
    } else if t<cue["privacy"]! {
        heading("THE TWO COMPANIES","One customer problem. Two owners.",t,cue["companies"]!)
        company("TeamChat",140,370,70);text("Messaging app for\npeople and teams",140,475,680,43,ink,.regular,140)
        person(200,750,78,blue);person(320,750,78,col(0x7188BB));person(440,750,78,col(0x8D9BAB));chatIcon(560,694,90,blue)
        alpha(on(t,cue["companies"]!+2.5)){company("HarborCloud",1160,370,70);text("Cloud platform",1160,475,650,43,ink,.regular,100);cloudIcon(1260,664,220,teal);arrow(810,610,290,muted,3);text("Depends on",795,544,330,28,muted,.medium,50,.center)}
        miniTag("Some messages aren’t arriving",140,885,610,redPale,red)
    } else if t<cue["relay"]! {
        heading("WHY COLLABORATION TAKES WORK","You can’t just send every log.",t,cue["privacy"]!)
        box(110,365,770,520,white,12,line);text("Private records",150,395,680,42,ink,.semibold,80)
        lockMark(770,397)
        box(150,505,690,82,redPale,8);text("Customer information",175,525,630,31,red,.medium,60)
        box(150,610,690,82,redPale,8);text("Private system details",175,630,630,31,red,.medium,60)
        box(150,715,690,110,bluePale,8);text("Relevant incident finding",175,735,630,31,blue,.semibold,60);text("Prepared for the owner to review",175,780,630,23,muted,.regular,45)
        text("Prepare evidence.\nReview what can leave.\nAsk the next question.",1080,390,740,48,ink,.medium,290)
        alpha(on(t,cue["manual"]!)){arrow(895,770,160,blue,4);box(1100,755,620,90,tealPale,10);text("Reviewed finding →",1130,776,560,34,teal,.semibold,60)}
        text("Illustration of information logs can contain; no real customer records are shown.",110,937,1700,23,muted,.regular,60)
    } else if t<cue["transition"]! {
        heading("THE PROJECT","Relay",t,cue["relay"]!)
        text("Agents investigate. People control sharing and changes.",110,250,1700,43,muted,.regular,110)
        box(110,425,640,440,white,12,line);box(1170,425,640,440,white,12,line)
        company("TeamChat",150,458,47);company("HarborCloud",1210,458,47)
        text("Its own systems",150,542,500,30,muted,.regular,60);text("Its own systems",1210,542,500,30,muted,.regular,60)
        circle(430,680,62,bluePale);chatIcon(399,657,62,blue);text("AI agent",290,770,280,33,blue,.semibold,70,.center)
        circle(1490,680,62,tealPale);chatIcon(1459,657,62,teal);text("AI agent",1350,770,280,33,teal,.semibold,70,.center)
        stroke([CGPoint(x:505,y:680),CGPoint(x:1415,y:680)],line,3)
        box(828,625,264,110,ink,12);text("Switch",838,644,244,44,white,.semibold,75,.center)
        text("Connects the agents",765,567,390,25,muted,.medium,50,.center)
        alpha(on(t,cue["shareControl"]!)){miniTag("Owner reviews",150,357,330,tealPale,green,true);miniTag("Owner reviews",1210,357,330,tealPale,green,true)}
        let p=CGFloat(clamp((t-cue["shareControl"]!)/2.2))
        alpha(on(t,cue["shareControl"]!)*(1-on(t,cue["outcome"]!))){box(530+800*p-105,650,210,60,bluePale,8);text("Reviewed finding",536+800*p-105,666,198,22,blue,.semibold,40,.center)}
        box(828,625,264,110,ink,12);text("Switch",838,644,244,44,white,.semibold,75,.center)
        if t>=cue["outcome"]! {box(380,905,1160,82,tealPale,10);check(410,927,35,green);text("Do the messages actually arrive?",480,918,1010,43,green,.semibold,70)}
        else{text("MATTERMOST · THE TEAMS’ INCIDENT ROOM",110,938,1700,25,muted,.medium,55,.center)}
    } else {
        text("Relay",110,76,1700,28,blue,.semibold,60);text("Here’s how.",110,375,1700,132,ink,.semibold,230)
        text("Two companies. One shared recovery.",110,660,1700,42,muted,.regular,100)
    }
    text("ILLUSTRATIVE SCENARIO · RECORDED WORKING DEMO FOLLOWS",110,1017,1700,19,muted,.medium,38)
}

let exactQuestion=plan["exactQuestion"] as! String
func focused(_ clip:[String:Any],_ t:Double) {
    let mode=clip["mode"] as! String,path=frame(clip,t)
    recordedHeader(clip["label"] as! String)
    let roi=NSRect(x:1134,y:205,width:462,height:565)
    capture(path,NSRect(x:1030,y:175,width:786,height:847),roi)
    box(1027,172,792,853,NSColor.clear,8,line)
    switch mode {
    case "diagnosis":
        text("Investigate the app’s own evidence.",90,215,790,57,ink,.semibold,200)
        note("Connection failures","Actual timeouts in TeamChat’s own observations",475)
        note("Failed message-server starts","The app still has work to recover",605)
        text("A focused finding is prepared for review.",90,800,780,35,muted,.regular,130)
    case "private-context":
        text("Detailed diagnostics stay private.",90,190,790,55,ink,.semibold,190)
        lockMark(95,408);text("TeamChat agent’s private context",155,410,720,31,blue,.semibold,65)
        text("Detailed connection-check events\nComplete server-start records\nFull diagnostic history",95,495,780,37,muted,.regular,190)
        box(90,740,790,210,bluePale,10);text("Prepared for owner review",115,765,740,33,blue,.semibold,65)
        text("A short incident finding and focused question, prepared for the owner to review.",115,822,730,29,ink,.regular,120)
    case "approve-share":
        text("Maya reviews the finding.",90,180,790,54,ink,.semibold,160)
        text("EXACT QUESTION INSIDE THAT FINDING",90,365,790,22,blue,.semibold,50)
        box(90,425,790,330,bluePale,10);text(exactQuestion,115,448,740,31,ink,.medium,290)
        note("Share with HarborCloud","Maya’s actual approval reply in this thread.",805,teal,tealPale)
        text("The full reviewed finding is released, including this question and cited incident references.",90,930,790,22,muted,.regular,80)
    case "cloud-plan","cloud-approve":
        text("HarborCloud controls the cloud change.",90,215,790,55,ink,.semibold,200)
        note("Proposed: more connection capacity","Six concurrent requests, for this route only",480)
        note("Leo’s approval is required","The agent cannot authorize its own change",620,teal,tealPale)
        text(mode=="cloud-approve" ? "Watch the actual approval arrive →" : "The proposed change is still awaiting review.",90,820,790,34,muted,.regular,120)
    case "app-plan","app-approve":
        text("TeamChat controls its own recovery.",90,215,790,55,ink,.semibold,200)
        note("Recover failed message-service parts","Keep working servers; replace failed starts",480)
        note("Maya’s approval is required","A separate owner decision for the app",620,teal,tealPale)
        text(mode=="app-approve" ? "The actual owner reply authorizes this plan →" : "The cloud result gives TeamChat the missing context.",90,820,790,34,muted,.regular,130)
    case "app-result","app-shared":
        text("The approved recovery runs.",90,215,790,55,ink,.semibold,200)
        note("App recovery executed","Measured delivery, not an approval-only status",480,teal,tealPale)
        note("Result reviewed and shared","Both teams receive the measured outcome",620)
    case "retry","retry-result":
        text("Recover the earlier failed message.",90,215,790,55,ink,.semibold,200)
        note("Same original ID and text","This is the request that genuinely failed earlier",480)
        note(mode=="retry" ? "Maya requests the retry" : "Delivered once",mode=="retry" ? "Actual reply in the failed-message thread" : "The repeated identical request is deduplicated",620,teal,tealPale)
    default:break
    }
    sourceFooter("Actual Mattermost recording · editorial zooms and highlights")
}

func trace(_ clip:[String:Any],_ t:Double) {
    recordedHeader("The same approved finding reaches HarborCloud","SELECTIVE SHARING · RECORDED PRIVATE REVIEW → RECORDED SHARED THREAD")
    text("TeamChat · private review",80,135,800,30,blue,.semibold,55)
    text("Both teams · shared incident",1040,135,800,30,teal,.semibold,55)
    capture(plan["comparisonPrivate"] as! String,NSRect(x:80,y:195,width:800,height:513),NSRect(x:1135,y:225,width:460,height:295))
    capture(frame(clip,t),NSRect(x:1040,y:195,width:800,height:609),NSRect(x:1135,y:405,width:460,height:350))
    // Boxes mark the same focused question within the whole approved finding.
    alpha(on(t,(clip["start"] as! Double)+0.55)){
        let p=NSBezierPath(rect:NSRect(x:198,y:H-410-152,width:654,height:152));blue.setStroke();p.lineWidth=3;p.stroke()
        let q=NSBezierPath(rect:NSRect(x:1158,y:H-420-152,width:654,height:152));blue.setStroke();q.lineWidth=3;q.stroke()
    }
    arrow(905,475,95,blue,4);text("Switch",895,400,130,27,blue,.semibold,60,.center)
    box(80,780,800,170,bluePale,10);lockMark(110,809)
    text("Detailed diagnostics stay private.",170,805,665,31,blue,.semibold,95)
    text("The approved finding and its evidence references cross. The full diagnostic record stays with TeamChat’s agent.",110,881,720,23,ink,.regular,70)
    box(1040,835,800,115,tealPale,10);text("HarborCloud’s agent starts investigating.",1070,855,740,31,teal,.semibold,90)
    sourceFooter("Editorial comparison of successive captured moments · highlighted text is unchanged")
}

func measured(_ clip:[String:Any],_ t:Double) {
    let mode=clip["mode"] as! String
    capture(frame(clip,t),NSRect(x:0,y:0,width:W,height:H))
    recordedHeader(clip["label"] as! String,mode.hasPrefix("ending") ? "":"ACTUAL MATTERMOST RECORDING")
    if mode.hasPrefix("ending") {
        box(0,112,W,925,paper,0)
        if mode=="ending-control" {
            capture(frame(clip,t),NSRect(x:1030,y:190,width:790,height:824),NSRect(x:1135,y:290,width:460,height:480))
        } else {
            text("The recorded closing check",1030,255,790,39,ink,.semibold,100)
            capture(frame(clip,t),NSRect(x:1030,y:395,width:790,height:275),NSRect(x:1135,y:610,width:460,height:160))
            text("After the earlier-message retry",1030,755,790,33,green,.semibold,95)
            text("Actual shared incident post",1030,825,790,25,muted,.regular,60)
        }
    }
    box(50,185,770,790,paper,12,line)
    if mode=="partial" {
        text("The cloud is healthy.\nMessages still fail.",90,220,680,51,ink,.semibold,185)
        box(90,440,680,135,tealPale,10);text("Cloud connection",120,460,600,27,teal,.medium,55);text("6/6 passed",120,505,600,50,green,.semibold,80)
        box(90,605,680,165,redPale,10);text("Customer messages",120,625,600,27,red,.medium,55);text("15/24 arrived",120,673,600,50,red,.semibold,80)
        text("Messages are still failing.",90,860,680,36,red,.semibold,80)
    } else if mode=="test" {
        text("Test the customer’s actual outcome.",90,220,680,51,ink,.semibold,190)
        text("24/24",90,455,680,135,green,.semibold,200)
        text("messages arrived",90,650,680,47,green,.medium,90)
        text("The same 24-message workload.\nThis result was recorded before the retry.",90,790,680,29,muted,.regular,135)
    } else {
        text("Controlled collaboration.\nVerified recovery.",90,220,680,49,ink,.semibold,190)
        let labels=["Owner-reviewed findings","Separately approved changes","A shared incident record"]
        for (i,label) in labels.enumerated(){check(95,470+CGFloat(i)*80,28,green);text(label,145,456+CGFloat(i)*80,600,31,ink,.medium,70)}
        box(90,755,680,185,tealPale,10);text("24/24 delivered",120,775,620,45,green,.semibold,85);text("Earlier failed message recovered once.",120,849,620,28,green,.medium,85)
    }
    sourceFooter("Editorial result labels reproduce the actual recorded checks · no new service run")
}

func draw(_ t:Double) {
    box(0,0,W,H,paper,0)
    if t<cue["report"]! {intro(t);return}
    if t>=cue["closing"]! {
        text("RELAY",110,90,1700,30,blue,.semibold,60)
        text("Two teams.\nOne recovery.",110,285,1700,120,ink,.semibold,350)
        text("Controlled sharing. Approved changes. Verified delivery.",110,760,1700,40,muted,.regular,115)
        text("Fictional companies · scripted presenter inputs · actual local agents and recorded checks",110,1005,1700,19,muted,.regular,45)
        return
    }
    guard let clip=clips.first(where:{t>=($0["start"] as! Double) && t<($0["end"] as! Double)}) else{return}
    let mode=clip["mode"] as! String
    if mode=="wide" {capture(frame(clip,t),NSRect(x:0,y:0,width:W,height:H));recordedHeader(clip["label"] as! String);sourceFooter()}
    else if mode=="trace-share" {trace(clip,t)}
    else if ["partial","test","ending-control","ending-result"].contains(mode) {measured(clip,t)}
    else {focused(clip,t)}
}

func bitmap(_ t:Double)->NSBitmapImageRep {
    let b=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:Int(W),pixelsHigh:Int(H),bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
    NSGraphicsContext.saveGraphicsState();NSGraphicsContext.current=NSGraphicsContext(bitmapImageRep:b);draw(t);NSGraphicsContext.restoreGraphicsState();return b
}
let previews:[(String,Double)]=[("01-hook",1.0),("02-companies",cue["companies"]!+3.3),("03-private-records",cue["privacy"]!+2.2),("04-review-gate",cue["manual"]!+3.2),("05-relay",cue["shareControl"]!+1.2),("06-private-context",cue["privateContext"]!+3.0),("07-owner-share",cue["approveShare"]!+3.8),("08-same-finding",cue["sharedQuestion"]!+3.8),("09-cloud-approval",cue["cloudApprove"]!+1.8),("10-partial",cue["partial"]!+4.0),("11-app-approval",cue["appApprove"]!+1.5),("12-all-pass",cue["test"]!+2.2),("13-retry",cue["retryResult"]!+2.0),("14-governance",cue["endingResult"]!+2.0)]
if mode=="preview" {
    for (name,time) in previews {try bitmap(time).representation(using:.png,properties:[:])!.write(to:URL(fileURLWithPath:output+"/"+name+".png"))}
    let value:[String:Any]=["duration":duration,"frameCount":frameCount,"fps":fps,"previews":previews.map{["file":$0.0+".png","time":$0.1]},"disclosure":plan["disclosure"]!]
    try JSONSerialization.data(withJSONObject:value,options:[.prettyPrinted,.sortedKeys]).write(to:URL(fileURLWithPath:output+"/visual-manifest.json"))
    print("Prepared \(previews.count) privacy-film previews")
} else if mode=="pipe" {
    for i in 0..<frameCount {autoreleasepool{FileHandle.standardOutput.write(bitmap(Double(i)/Double(fps)).representation(using:.png,properties:[:])!)}}
}

