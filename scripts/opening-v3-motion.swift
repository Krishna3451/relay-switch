// Relay v3: vivid editorial animation. Every scene is an illustration, not product UI.
import AppKit
import Foundation

let args=CommandLine.arguments
func opt(_ key:String,_ fallback:String)->String {guard let i=args.firstIndex(of:key),i+1<args.count else{return fallback};return args[i+1]}
let output=opt("--output","demo/opening-v3/visuals"), mode=opt("--mode","preview")
let cuePath=opt("--cues","demo/opening-v3/voice-cues.json")
let W:CGFloat=1920,H:CGFloat=1080,fps=24
let cue=(try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:cuePath)))) as! [String:Double]
try FileManager.default.createDirectory(atPath:output,withIntermediateDirectories:true)
func c(_ h:UInt32,_ a:CGFloat=1)->NSColor {NSColor(calibratedRed:CGFloat((h>>16)&255)/255,green:CGFloat((h>>8)&255)/255,blue:CGFloat(h&255)/255,alpha:a)}
let navy=c(0x080E27),deep=c(0x101537),blue=c(0x365CFF),cyan=c(0x36DFFC),violet=c(0x9457FF),coral=c(0xFF725E),yellow=c(0xFFD45C),mint=c(0x73F3BD),white=NSColor.white,soft=c(0xBDD0F4)
var ctx:CGContext{NSGraphicsContext.current!.cgContext}
func clamp(_ p:Double)->Double{max(0,min(1,p))}
func ease(_ p:Double)->Double{let q=clamp(p);return 1-pow(1-q,3)}
func smooth(_ p:Double)->Double{let q=clamp(p);return q*q*(3-2*q)}
func on(_ t:Double,_ s:Double,_ d:Double=0.45)->Double{ease((t-s)/d)}
func point(_ x:CGFloat,_ y:CGFloat)->CGPoint{CGPoint(x:x,y:H-y)}
func layer(_ a:Double=1,_ draw:()->Void){guard a>0.0001 else{return};ctx.saveGState();ctx.setAlpha(CGFloat(a));ctx.beginTransparencyLayer(auxiliaryInfo:nil);ctx.setAlpha(1);draw();ctx.endTransparencyLayer();ctx.restoreGState()}
func move(_ x:CGFloat=0,_ y:CGFloat=0,_ draw:()->Void){ctx.saveGState();ctx.translateBy(x:x,y:-y);draw();ctx.restoreGState()}
func turn(_ x:CGFloat,_ y:CGFloat,_ radians:CGFloat,_ scale:CGFloat=1,_ draw:()->Void){ctx.saveGState();ctx.translateBy(x:x,y:H-y);ctx.rotate(by:-radians);ctx.scaleBy(x:scale,y:scale);ctx.translateBy(x:-x,y:-(H-y));draw();ctx.restoreGState()}
func shadow(_ color:NSColor,_ blur:CGFloat=35,_ draw:()->Void){ctx.saveGState();ctx.setShadow(offset:CGSize(width:0,height:-15),blur:blur,color:color.cgColor);draw();ctx.restoreGState()}
func rect(_ x:CGFloat,_ y:CGFloat,_ w:CGFloat,_ h:CGFloat,_ color:NSColor,_ r:CGFloat=20,_ border:NSColor?=nil,_ line:CGFloat=1){let p=NSBezierPath(roundedRect:NSRect(x:x,y:H-y-h,width:w,height:h),xRadius:r,yRadius:r);color.setFill();p.fill();if let border=border{border.setStroke();p.lineWidth=line;p.stroke()}}
func circle(_ x:CGFloat,_ y:CGFloat,_ r:CGFloat,_ color:NSColor,_ border:NSColor?=nil,_ width:CGFloat=2){let p=NSBezierPath(ovalIn:NSRect(x:x-r,y:H-y-r,width:r*2,height:r*2));color.setFill();p.fill();if let border=border{border.setStroke();p.lineWidth=width;p.stroke()}}
func line(_ pts:[CGPoint],_ color:NSColor,_ width:CGFloat=3,_ dash:[CGFloat]=[]){guard let first=pts.first else{return};ctx.saveGState();ctx.setStrokeColor(color.cgColor);ctx.setLineWidth(width);ctx.setLineCap(.round);ctx.setLineJoin(.round);ctx.setLineDash(phase:0,lengths:dash);ctx.beginPath();ctx.move(to:point(first.x,first.y));for p in pts.dropFirst(){ctx.addLine(to:point(p.x,p.y))};ctx.strokePath();ctx.restoreGState()}
func text(_ s:String,_ x:CGFloat,_ y:CGFloat,_ w:CGFloat,_ size:CGFloat,_ color:NSColor=white,_ weight:NSFont.Weight = .semibold,_ h:CGFloat=170,_ align:NSTextAlignment = .left){let p=NSMutableParagraphStyle();p.alignment=align;p.lineSpacing=3;p.lineBreakMode = .byWordWrapping;(s as NSString).draw(in:NSRect(x:x,y:H-y-h,width:w,height:h),withAttributes:[.font:NSFont.systemFont(ofSize:size,weight:weight),.foregroundColor:color,.paragraphStyle:p])}
func glow(_ x:CGFloat,_ y:CGFloat,_ r:CGFloat,_ color:NSColor,_ strength:CGFloat=0.4){let gradient=NSGradient(starting:color.withAlphaComponent(strength),ending:color.withAlphaComponent(0))!;gradient.draw(fromCenter:NSPoint(x:x,y:H-y),radius:0,toCenter:NSPoint(x:x,y:H-y),radius:r,options:[])}
func gradient(_ a:NSColor,_ b:NSColor,_ angle:CGFloat=0){NSGradient(starting:a,ending:b)!.draw(in:NSRect(x:0,y:0,width:W,height:H),angle:angle)}
func curve(_ a:CGPoint,_ b:CGPoint,_ d:CGPoint,_ e:CGPoint,_ color:NSColor,_ width:CGFloat=5){ctx.saveGState();ctx.setStrokeColor(color.cgColor);ctx.setLineWidth(width);ctx.setLineCap(.round);ctx.beginPath();ctx.move(to:point(a.x,a.y));ctx.addCurve(to:point(e.x,e.y),control1:point(b.x,b.y),control2:point(d.x,d.y));ctx.strokePath();ctx.restoreGState()}
func bezier(_ a:CGPoint,_ b:CGPoint,_ d:CGPoint,_ e:CGPoint,_ p:CGFloat)->CGPoint{let q=1-p;return CGPoint(x:q*q*q*a.x+3*q*q*p*b.x+3*q*p*p*d.x+p*p*p*e.x,y:q*q*q*a.y+3*q*q*p*b.y+3*q*p*p*d.y+p*p*p*e.y)}
func particles(_ t:Double,_ a:CGPoint,_ b:CGPoint,_ d:CGPoint,_ e:CGPoint,_ color:NSColor,_ speed:Double=0.3,_ count:Int=7){curve(a,b,d,e,color.withAlphaComponent(0.25),5);for i in 0..<count{let p=CGFloat((t*speed+Double(i)/Double(count)).truncatingRemainder(dividingBy:1));let v=bezier(a,b,d,e,p);circle(v.x,v.y,9,color.withAlphaComponent(0.12));circle(v.x,v.y,4,color)}}
func check(_ x:CGFloat,_ y:CGFloat,_ size:CGFloat,_ color:NSColor=navy){line([CGPoint(x:x,y:y+size*0.5),CGPoint(x:x+size*0.32,y:y+size*0.82),CGPoint(x:x+size,y:y)],color,5)}
func cross(_ x:CGFloat,_ y:CGFloat,_ s:CGFloat,_ color:NSColor=white){line([CGPoint(x:x,y:y),CGPoint(x:x+s,y:y+s)],color,6);line([CGPoint(x:x+s,y:y),CGPoint(x:x,y:y+s)],color,6)}
func bubbleIcon(_ x:CGFloat,_ y:CGFloat,_ s:CGFloat,_ color:NSColor=white,_ dots:NSColor=blue){rect(x,y,s,s*0.72,color,s*0.22);let p=NSBezierPath();p.move(to:NSPoint(x:x+s*0.18,y:H-y-s*0.6));p.line(to:NSPoint(x:x+s*0.18,y:H-y-s*0.95));p.line(to:NSPoint(x:x+s*0.5,y:H-y-s*0.65));p.close();color.setFill();p.fill();for v:CGFloat in [0.28,0.5,0.72]{circle(x+s*v,y+s*0.36,s*0.045,dots)}}
func cloud(_ x:CGFloat,_ y:CGFloat,_ s:CGFloat,_ color:NSColor){circle(x+s*0.24,y+s*0.52,s*0.23,color);circle(x+s*0.48,y+s*0.32,s*0.3,color);circle(x+s*0.75,y+s*0.5,s*0.24,color);rect(x+s*0.18,y+s*0.47,s*0.65,s*0.29,color,s*0.1)}
func pill(_ s:String,_ x:CGFloat,_ y:CGFloat,_ w:CGFloat,_ color:NSColor,_ ink:NSColor=navy,_ size:CGFloat=28){rect(x,y,w,54,color,27);text(s,x+20,y+9,w-40,size,ink,.bold,45,.center)}
func portrait(_ x:CGFloat,_ y:CGFloat,_ scale:CGFloat,_ color:NSColor,_ facing:CGFloat=1){
    // A warm, illustrated person rather than an anonymous node.
    circle(x,y,scale*0.62,color.withAlphaComponent(0.15))
    let torso=NSBezierPath(roundedRect:NSRect(x:x-scale*0.55,y:H-y-scale*0.61,width:scale*1.1,height:scale*0.75),xRadius:scale*0.3,yRadius:scale*0.3);color.setFill();torso.fill()
    circle(x,y-scale*0.22,scale*0.34,c(0xF3BD9C));circle(x-scale*0.04,y-scale*0.39,scale*0.32,navy)
    rect(x-scale*0.29,y-scale*0.39,scale*0.62,scale*0.26,navy,scale*0.08)
    circle(x+facing*scale*0.14,y-scale*0.22,scale*0.025,navy)
    line([CGPoint(x:x+facing*scale*0.08,y:y-scale*0.06),CGPoint(x:x+facing*scale*0.22,y:y-scale*0.06)],navy,2)
}
func phone(_ x:CGFloat,_ y:CGFloat,_ w:CGFloat,_ t:Double,_ failed:Bool=true){turn(x,y,0,w/450){phoneBase(x,y,t,failed)}}
func phoneBase(_ x:CGFloat,_ y:CGFloat,_ t:Double,_ failed:Bool){let w:CGFloat=450,h=w*1.55
    shadow(c(0x000000,0.4),45){rect(x,y,w,h,c(0x15224C),w*0.1,c(0x7D96F9),3)}
    rect(x+11,y+11,w-22,h-22,c(0xF2F6FF),w*0.085)
    rect(x+w*0.33,y+21,w*0.34,15,navy,8)
    ctx.saveGState();let screen=NSBezierPath(roundedRect:NSRect(x:x+11,y:H-y-h+11,width:w-22,height:h-22),xRadius:w*0.085,yRadius:w*0.085);screen.addClip()
    rect(x+12,y+70,w-24,95,blue,w*0.02);bubbleIcon(x+38,y+96,45,white,blue);text("TeamChat",x+100,y+91,w-130,w*0.07,white,.bold,60)
    portrait(x+w/2,y+245,w*0.16,blue)
    text("Waiting for your message",x+25,y+324,w-50,w*0.052,navy,.semibold,75,.center)
    for i in 0..<3{rect(x+38,y+405+CGFloat(i)*54,w-76,32,c(0xDCE5FA),15)}
    let blink=CGFloat(0.4+0.6*(0.5+0.5*sin(t*3)))
    for i in 0..<3{circle(x+w*0.43+CGFloat(i)*w*0.07,y+h-83,6,blue.withAlphaComponent(blink))}
    if !failed{rect(x+32,y+380,w-64,160,mint,25);text("Please confirm\nthe time.",x+55,y+404,w-110,w*0.063,navy,.bold,110);check(x+w-90,y+548,27,mint)}
    ctx.restoreGState()
}
func grid(_ t:Double){for row in 0..<12{for col in 0..<23{let x=CGFloat(col)*88+CGFloat(sin(t*0.1)*18),y=CGFloat(row)*88+52;circle(x,y,1.2,white.withAlphaComponent(0.1))}}}
func footer(){text("ILLUSTRATIVE SCENARIO · LIVE DEMO FOLLOWS",74,1023,1500,20,white.withAlphaComponent(0.5),.medium,35)}
func base(_ t:Double,_ a:NSColor=navy,_ b:NSColor=deep){gradient(a,b,-30);glow(1510+CGFloat(sin(t*0.17)*110),210,780,violet,0.3);glow(130,880,700,blue,0.25);grid(t)}

func hook(_ t:Double){
    base(t)
    glow(1450,550,650,blue,0.4)
    let fail=on(t,2.4,0.22)
    layer(1-fail){text("Your message.",80,105,1100,150,white,.black,240)}
    layer(fail){text("Never\nreceived.",80,95,1100,142,coral,.black,380)}
    pill("TEAMCHAT · MESSAGING APP",86,495,490,blue,white,26)
    let angle=CGFloat(-0.1+0.015*sin(t*1.4))
    turn(1480,570,angle){phone(1200,190,450,t)}
    // The foreground message sweeps toward the recipient, then stalls and shakes.
    let p=ease((t-0.05)/2.1), shake=fail*0.5*sin(t*46)
    let mx=CGFloat(110+710*p+shake*7), my=CGFloat(760-120*p)
    turn(mx+330,my+80,CGFloat(-0.06+0.03*p)){
        shadow(c(0x000000,0.3),35){rect(mx,my,640,170,yellow,34)}
        bubbleIcon(mx+26,my+42,68,navy,yellow)
        text("Please confirm the time.",mx+119,my+52,490,40,navy,.bold,90)
    }
    layer(fail){shadow(coral.withAlphaComponent(0.4),40){circle(1428,656,65,coral)};cross(1406,634,44);pill("NOT RECEIVED",1350,880,330,coral,navy,28)}
    layer(on(t,3.2)){text("Someone is still waiting.",85,921,1180,44,soft,.medium,80)}
}

func companies(_ t:Double){
    let cloudStart=cue["harborcloud"]!, split=on(t,cloudStart-0.35,0.65)
    gradient(c(0x153CF4),c(0x3A1D8B),-25);glow(1300,420,850,cyan,0.16);grid(t)
    let x=CGFloat(84-55*split)
    let titleSize=CGFloat(132-40*split)
    text("TeamChat",x,107,1050,titleSize,white,.black,190)
    text("Messaging app for\npeople and teams",x+5,280,820,48,white,.medium,150)
    layer(1-split){
        let py=CGFloat(235+sin(t*1.7)*16)
        turn(1450,570,CGFloat(0.08+sin(t)*0.018)){phone(1220,py,420,t)}
        for i in 0..<3{let px=CGFloat(145+i*225),dy=CGFloat(sin(t*1.7+Double(i))*12);portrait(px,715+dy,115,[cyan,yellow,coral][i])}
        pill("Some messages aren’t arriving",92,895,700,coral,navy,31)
    }
    layer(split){
        let drift=CGFloat(30*(1-split))
        move(drift,0){
            text("HarborCloud",1110,140,760,87,white,.black,150)
            text("Cloud platform",1115,260,700,48,cyan,.medium,100)
            shadow(cyan.withAlphaComponent(0.35),60){cloud(1200,390,415,cyan)}
            for i in 0..<3{let y:CGFloat=650+CGFloat(i)*65;rect(1190,y,490,46,c(0x1B194A),14,c(0xA494FF),1.5);circle(1220,y+23,7,mint);line([CGPoint(x:1260,y:y+23),CGPoint(x:1500,y:y+23)],violet,5);for n in 0..<3{circle(1600+CGFloat(n)*20,y+23,4,cyan)}}
        }
        turn(405,704,-0.05){phone(235,435,300,t)}
        particles(t,CGPoint(x:575,y:650),CGPoint(x:850,y:420),CGPoint(x:950,y:480),CGPoint(x:1220,y:580),yellow,0.3,5)
        pill("DEPENDS ON",750,529,315,yellow,navy,26)
        text("People send messages.",75,920,760,35,white,.medium,70)
        text("Cloud infrastructure delivers them.",1090,920,790,35,white,.medium,70)
    }
}

func systems(_ t:Double){
    base(t,c(0x09132E),c(0x271247))
    let manual=on(t,cue["manual"]!,0.4)
    glow(260,675,540,blue,0.4);glow(1650,675,540,violet,0.4)
    layer(1-manual){text("Two teams.\nSeparate systems.",88,82,1680,105,white,.black,270)}
    layer(manual){text("Back.",88,83,900,145,cyan,.black,200);move(CGFloat(38*(1-manual)),0){text("And forth.",545,245,1280,135,yellow,.black,210)}}
    let y:CGFloat=690
    portrait(270,y,150,blue);portrait(1660,y,150,violet,-1)
    text("TeamChat",88,868,630,47,white,.bold,90)
    text("App engineers",88,930,630,29,soft,.medium,60)
    text("HarborCloud",1280,868,600,47,white,.bold,90,.right)
    text("Cloud engineers",1280,930,600,29,soft,.medium,60,.right)
    line([CGPoint(x:960,y:390),CGPoint(x:960,y:930)],white.withAlphaComponent(0.2),2,[10,16])
    layer(1-manual){pill("Own app access",120,440,460,blue,white,31);pill("Own cloud access",1305,440,485,violet,white,31)}
    layer(manual){
        let elapsed=t-cue["manual"]!
        let labels=["Question","Finding","Follow-up"]
        let colors=[yellow,cyan,coral]
        for i in 0..<3 {
            let p=CGFloat((elapsed*0.25+Double(i)*0.32).truncatingRemainder(dividingBy:1))
            let forward=i != 1
            let x:CGFloat=forward ? 430+850*p:1280-850*p
            let y:CGFloat=510+CGFloat(i)*105+CGFloat(sin(t*2+Double(i))*8)
            shadow(c(0x000000,0.22),20){rect(x,y,350,78,colors[i],22)}
            text(labels[i]+(forward ? "  →":"  ←"),x+20,y+18,310,34,navy,.bold,60,.center)
        }
    }
}

func agent(_ x:CGFloat,_ y:CGFloat,_ color:NSColor,_ t:Double,_ label:String){
    let pulse=CGFloat(0.5+0.5*sin(t*2.8))
    glow(x,y,240,color,0.28)
    circle(x,y,120,color.withAlphaComponent(0.18),color,3)
    circle(x,y,140+pulse*12,NSColor.clear,color.withAlphaComponent(0.25),2)
    shadow(color.withAlphaComponent(0.3),40){rect(x-82,y-67,164,138,color,42)}
    rect(x-57,y-38,114,67,navy,24)
    for d:CGFloat in [-25,25]{circle(x+d,y-5,10,white)}
    line([CGPoint(x:x-25,y:y+48),CGPoint(x:x+25,y:y+48)],navy,5)
    text(label,x-310,y+180,620,42,white,.bold,100,.center)
}

func project(_ t:Double){
    let start=cue["relay"]!
    base(t,c(0x07192B),c(0x29185C));glow(960,570,730,violet,0.35)
    let entrance=on(t,start,0.6), settled=on(t,start+0.9,0.7)
    let scale=CGFloat(1.25-0.25*entrance)
    turn(960,520,0,scale){
        text("Relay",80,55,1600,CGFloat(154-40*settled),white,.black,230)
        layer(settled){text("Two agents. One shared recovery.",84,215,1750,47,soft,.medium,100)}
    }
    let left=CGPoint(x:375,y:590), right=CGPoint(x:1545,y:590)
    particles(t,CGPoint(x:510,y:570),CGPoint(x:700,y:400),CGPoint(x:810,y:500),CGPoint(x:885,y:570),cyan,0.5,6)
    particles(t,CGPoint(x:1035,y:570),CGPoint(x:1220,y:350),CGPoint(x:1410,y:500),CGPoint(x:1410,y:570),violet,0.5,6)
    agent(left.x,left.y,cyan,t,"TeamChat agent")
    agent(right.x,right.y,violet,t+0.8,"HarborCloud agent")
    shadow(violet.withAlphaComponent(0.65),60){rect(755,462,410,205,c(0x34205D),46,violet,3)}
    text("Switch",775,500,370,87,white,.black,130,.center)
    text("CONNECTS THE AGENTS",690,698,540,25,soft,.bold,60,.center)
    let own=on(t,cue["agentOwn"]!,0.35)
    layer(own*(1-on(t,cue["delivery"]!,0.4))){pill("Own app systems",112,862,525,c(0x124A66),cyan,30);pill("Own cloud systems",1283,862,525,c(0x402565),c(0xD6B6FF),30)}
    let approved=on(t,cue["approval"]!,0.4)
    layer(approved){
        for x:CGFloat in [375,1545]{
            shadow(yellow.withAlphaComponent(0.24),25){pill("Owner approval",x-205,340,410,yellow,navy,32)}
            circle(x+210,366,28,mint);check(x+197,353,26)
        }
    }
    layer(on(t,cue["approval"]!+0.6,0.25)*(1-on(t,cue["delivery"]!-0.1,0.2))){
        let p=CGFloat(clamp((t-cue["approval"]!-0.6)/1.8));let x:CGFloat=500+920*p
        shadow(yellow.withAlphaComponent(0.3),20){rect(x-150,600,300,68,yellow,22)}
        text("Reviewed finding",x-135,615,270,27,navy,.bold,50,.center)
    }
    let delivery=on(t,cue["delivery"]!,0.4)
    layer(delivery){
        shadow(mint.withAlphaComponent(0.25),45){rect(395,825,1130,135,mint,38)}
        check(435,863,52)
        text("Messages arrive again.",525,853,930,61,navy,.black,100)
    }
    layer(1-delivery){text("MATTERMOST · THE TEAMS’ INCIDENT ROOM",80,967,1770,23,soft,.semibold,45,.center)}
    let tr=on(t,cue["transition"]!,0.25)
    layer(tr){
        gradient(blue,violet,-20);glow(1510,400,800,cyan,0.3)
        let p=on(t,cue["transition"]!,0.5)
        move(CGFloat(-70*(1-p)),0){text("Here’s how.",90,350,1740,170,white,.black,300)}
        text("Relay  /  Built with Switch",98,100,1700,35,white,.bold,70)
    }
}

func draw(_ t:Double){
    let tc=cue["teamchat"]!,own=cue["ownership"]!,rel=cue["relay"]!
    base(t)
    layer(1-on(t,tc,0.45)){hook(t)}
    layer(on(t,tc,0.45)*(1-on(t,own,0.45))){move(CGFloat(55*(1-on(t,tc,0.5))),0){companies(t)}}
    layer(on(t,own,0.45)*(1-on(t,rel,0.35))){systems(t)}
    layer(on(t,rel,0.35)){project(t)}
    footer()
}

func image(_ t:Double)->NSBitmapImageRep {let bitmap=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:Int(W),pixelsHigh:Int(H),bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!;NSGraphicsContext.saveGraphicsState();NSGraphicsContext.current=NSGraphicsContext(bitmapImageRep:bitmap);draw(t);NSGraphicsContext.restoreGraphicsState();return bitmap}
let previews:[(String,Double)]=[("01-hook",0.8),("02-failure",3.4),("03-teamchat",6.6),("04-companies",10.9),("05-boundaries",14.6),("06-manual",19.0),("07-relay",24.3),("08-agents",27.1),("09-approval",29.6),("10-delivery",33.0),("11-transition",35.4)]
if mode=="preview"{for(name,time)in previews{try image(time).representation(using:.png,properties:[:])!.write(to:URL(fileURLWithPath:output+"/"+name+".png"))};let manifest:[String:Any]=["kind":"Vivid editorial motion illustration, not captured product UI","fps":fps,"dimensions":[1920,1080],"duration":cue["end"]!,"cues":cue,"previews":previews.map{["file":$0.0+".png","time":$0.1]}];try JSONSerialization.data(withJSONObject:manifest,options:[.prettyPrinted,.sortedKeys]).write(to:URL(fileURLWithPath:output+"/visual-manifest.json"));print("Prepared \(previews.count) vivid motion previews")}
if mode=="pipe"{for i in 0..<Int(ceil(cue["end"]!*Double(fps))){autoreleasepool{FileHandle.standardOutput.write(image(Double(i)/Double(fps)).representation(using:.png,properties:[:])!)}}}
