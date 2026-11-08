// Local editorial illustrations, deliberately distinct from product screenshots.
import AppKit
import Foundation

let output = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "demo/final/cards"
try FileManager.default.createDirectory(atPath: output, withIntermediateDirectories: true)
let W: CGFloat = 1920, H: CGFloat = 1080
func color(_ hex: UInt32) -> NSColor {
    NSColor(calibratedRed: CGFloat((hex >> 16) & 255)/255, green: CGFloat((hex >> 8) & 255)/255, blue: CGFloat(hex & 255)/255, alpha: 1)
}
let navy = color(0x202D45), blue = color(0x235BD8), muted = color(0x56637A), bg = color(0xF6F8FC)
func box(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat, _ fill: NSColor, radius: CGFloat = 16) {
    fill.setFill()
    NSBezierPath(roundedRect: NSRect(x:x,y:H-y-h,width:w,height:h),xRadius:radius,yRadius:radius).fill()
}
func text(_ value: String, _ x: CGFloat, _ y: CGFloat, _ w: CGFloat, size: CGFloat, fill: NSColor, bold: Bool = false, height: CGFloat = 180) {
    let paragraph = NSMutableParagraphStyle(); paragraph.lineSpacing = 10
    let attrs: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: size, weight: bold ? .semibold : .regular),
       .foregroundColor: fill, .paragraphStyle: paragraph]
    (value as NSString).draw(in:NSRect(x:x,y:H-y-height,width:w,height:height),withAttributes:attrs)
}
func base(_ section: String) {
    box(0,0,W,H,bg,radius:0)
    box(100,104,8,46,blue,radius:4)
    text("RELAY  /  " + section,130,100,1640,size:28,fill:blue,bold:true,height:60)
    text("Editorial explanation · Fictional companies · Actual local workflow follows",100,990,1720,size:24,fill:muted,height:50)
}
func save(_ name: String, _ draw: () -> Void) throws {
    let bitmap = NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:Int(W),pixelsHigh:Int(H),bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
    NSGraphicsContext.saveGraphicsState(); NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep:bitmap)
    draw()
    NSGraphicsContext.restoreGraphicsState()
    try bitmap.representation(using:.png,properties:[:])!.write(to:URL(fileURLWithPath:output+"/"+name+".png"))
}
try save("problem") {
    base("THE PROBLEM")
    text("Some messages arrive.\nOthers don’t.",100,225,1700,size:92,fill:navy,bold:true,height:300)
    box(100,660,800,150,.white)
    text("Customers need reliable delivery.",140,700,1500,size:40,fill:muted,height:100)
}
try save("two-companies") {
    base("THE PROBLEM")
    text("Two companies.\nOne customer problem.",100,210,1700,size:80,fill:navy,bold:true,height:260)
    box(100,600,710,215,.white); box(1110,600,710,215,.white)
    text("TeamChat",145,640,620,size:48,fill:navy,bold:true,height:80)
    text("Messaging application",145,722,620,size:32,fill:muted,height:65)
    text("HarborCloud",1155,640,620,size:48,fill:navy,bold:true,height:80)
    text("Cloud connection",1155,722,620,size:32,fill:muted,height:65)
    text("↔",875,648,210,size:76,fill:blue,bold:true,height:120)
}
try save("existing") {
    base("THE EXISTING SOLUTION")
    text("Engineers connect the dots.",100,225,1700,size:80,fill:navy,bold:true,height:180)
    box(100,510,500,190,.white); box(1320,510,500,190,.white)
    text("App team",145,550,420,size:44,fill:navy,bold:true,height:80)
    text("Cloud team",1365,550,420,size:44,fill:navy,bold:true,height:80)
    text("Questions\nEvidence\nUpdates",760,470,500,size:40,fill:blue,bold:true,height:250)
    text("→",635,550,120,size:60,fill:blue,height:100)
    text("→",1160,550,120,size:60,fill:blue,height:100)
    text("Dashboards and APIs help each team do its work.",100,815,1700,size:36,fill:muted,height:90)
}
try save("why") {
    base("WHY IT FALLS SHORT")
    text("One side can recover.\nThe customer can still be stuck.",100,220,1700,size:76,fill:navy,bold:true,height:260)
    box(100,600,815,210,.white); box(1005,600,815,210,.white)
    text("Cloud connection",145,640,725,size:40,fill:navy,bold:true,height:75)
    text("Healthy",145,720,725,size:40,fill:color(0x147D55),bold:true,height:70)
    text("Message delivery",1050,640,725,size:40,fill:navy,bold:true,height:75)
    text("Still unreliable",1050,720,725,size:40,fill:color(0xA85317),bold:true,height:70)
}
try save("closing") {
    box(0,0,W,H,bg,radius:0)
    box(100,104,8,46,blue,radius:4)
    text("RELAY",130,100,1640,size:28,fill:blue,bold:true,height:60)
    text("Two teams.\nOne recovery.",100,300,1700,size:110,fill:navy,bold:true,height:320)
    text("Coordinated through Switch · Inside Mattermost",100,760,1720,size:38,fill:muted,height:90)
    text("Fictional companies · Actual local services and live agents · Edited demonstration",100,990,1720,size:24,fill:muted,height:50)
}
print("Prepared five 1920×1080 editorial cards")
