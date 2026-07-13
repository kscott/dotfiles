// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "archive-session-log",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "archive-session-log",
            path: "Sources/archive-session-log"
        )
    ]
)
