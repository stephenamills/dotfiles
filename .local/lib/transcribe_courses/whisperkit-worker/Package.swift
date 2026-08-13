// swift-tools-version: 6.0

import PackageDescription
import Foundation

// The worker builds against one clean local Argmax checkout.  The default is the
// pinned working copy; ARGMAX_OSS_SWIFT_PATH exists so the same source can build
// from a relocated checkout. The transcribe-courses package verifies that whatever path
// is used is checked out at ARGMAX_REQUIRED_REVISION with no local modifications,
// and folds both the path and the revision into the worker cache fingerprint.
let argmaxPath = Context.environment["ARGMAX_OSS_SWIFT_PATH"]
    ?? "../argmax-oss-swift"

let package = Package(
    name: "WhisperKitWorker",
    platforms: [
        .macOS(.v14)
    ],
    dependencies: [
        .package(name: "argmax-oss-swift", path: argmaxPath)
    ],
    targets: [
        .executableTarget(
            name: "whisperkit-worker",
            dependencies: [
                .product(name: "WhisperKit", package: "argmax-oss-swift")
            ]
        )
    ]
)
