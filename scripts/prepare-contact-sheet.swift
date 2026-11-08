import AppKit
import Foundation
let root = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "demo/final/qa"
let url = URL(fileURLWithPath:root+"/frame-index.json")
let data = try JSONSerialization.jsonObject(with:Data(contentsOf:url)) as! [String:Any]
let shots = data["shots"] as! [[String:Any]]
let columns = 4, cellW = 480, cellH = 318, header = 70
let rows = Int(ceil(Double(shots.count)/Double(columns)))
let width = columns*cellW, height = rows*cellH+header
let bitmap = NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:width,pixelsHigh:height,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
NSGraphicsContext.saveGraphicsState();NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep:bitmap)
NSColor.white.setFill();NSRect(x:0,y:0,width:width,height:height).fill()
func label(_ text:String,_ x:Int,_ y:Int,_ w:Int,_ size:CGFloat) {
 let p=NSMutableParagraphStyle();p.lineBreakMode = .byTruncatingTail
 (text as NSString).draw(in:NSRect(x:x,y:height-y-42,width:w,height:40),withAttributes:[.font:NSFont.systemFont(ofSize:size),.foregroundColor:NSColor.darkGray,.paragraphStyle:p])
}
label("Relay — actual final-video frames at spoken cues",20,15,width-40,26)
let project = FileManager.default.currentDirectoryPath
for (index,shot) in shots.enumerated() {
 let x=(index%columns)*cellW,y=header+(index/columns)*cellH
 let path=project+"/"+(shot["file"] as! String)
 let image=NSImage(contentsOfFile:path)!
 image.draw(in:NSRect(x:x+4,y:height-y-270,width:cellW-8,height:266))
 let t=shot["time"] as! Double
 label(String(format:"%02d · %.2fs · %@",index+1,t,shot["label"] as! String),x+10,y+270,cellW-20,14)
}
NSGraphicsContext.restoreGraphicsState()
try bitmap.representation(using:.jpeg,properties:[.compressionFactor:0.9])!.write(to:URL(fileURLWithPath:root+"/contact-sheet.jpg"))
print("Prepared actual-frame QA contact sheet")
