import Foundation
import Vision
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

// Usage: ocr.swift <image-path>
// Outputs TSV: x<TAB>y<TAB>w<TAB>h<TAB>confidence<TAB>text  (pixel coords, origin top-left)

guard CommandLine.arguments.count >= 2 else {
    FileHandle.standardError.write("usage: ocr.swift <image>\n".data(using: .utf8)!)
    exit(1)
}
let path = CommandLine.arguments[1]
let url = URL(fileURLWithPath: path)

guard let src = CGImageSourceCreateWithURL(url as CFURL, nil),
      let cg = CGImageSourceCreateImageAtIndex(src, 0, [kCGImageSourceShouldCache: false] as CFDictionary) else {
    FileHandle.standardError.write("cannot load image\n".data(using: .utf8)!)
    exit(2)
}
let imgW = cg.width
let imgH = cg.height
FileHandle.standardError.write("IMAGE\t\(imgW)\t\(imgH)\n".data(using: .utf8)!)

let request = VNRecognizeTextRequest { (req, err) in
    if let err = err {
        FileHandle.standardError.write("vision error: \(err)\n".data(using: .utf8)!)
        exit(3)
    }
}
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false
request.recognitionLanguages = ["zh-Hans", "zh-Hant", "en-US"]

let handler = VNImageRequestHandler(cgImage: cg, options: [:])
try? handler.perform([request])

let results = request.results ?? []
for obs in results {
    guard let cand = obs.topCandidates(1).first else { continue }
    let bb = obs.boundingBox
    // Vision: normalized, origin bottom-left
    let x = bb.origin.x * CGFloat(imgW)
    let w = bb.width * CGFloat(imgW)
    let h = bb.height * CGFloat(imgH)
    let yTop = (1.0 - bb.origin.y - bb.height) * CGFloat(imgH)
    let text = cand.string.replacingOccurrences(of: "\n", with: " ")
    let conf = Int(round(cand.confidence * 100))
    print("\(Int(round(x)))\t\(Int(round(yTop)))\t\(Int(round(w)))\t\(Int(round(h)))\t\(conf)\t\(text)")
}
