import Foundation

// Archives complete ISO weeks out of session-log.md into monthly archive files.
// Each week is assigned to the month containing its Thursday (ISO 8601 convention).
// Runs headless via launchd; uses FileManager directly (no AppleScript/TCC dance —
// the previous python+osascript version couldn't reliably read the iCloud file
// from a background launchd process).

let home = FileManager.default.homeDirectoryForCurrentUser
let productivity = home.appendingPathComponent("Library/Mobile Documents/com~apple~CloudDocs/Productivity")
let sessionLog = productivity.appendingPathComponent("session-log.md")
let archiveDir = productivity.appendingPathComponent("Archive/session-logs")
let logPath = home.appendingPathComponent("logs/archive-session-log.log")

// MARK: - Date arithmetic (Julian Day Number based, timezone-independent)

func julianDayNumber(year: Int, month: Int, day: Int) -> Int {
    let a = (14 - month) / 12
    let y = year + 4800 - a
    let m = month + 12 * a - 3
    return day + (153 * m + 2) / 5 + 365 * y + y / 4 - y / 100 + y / 400 - 32045
}

func calendarDate(fromJDN jdn: Int) -> (Int, Int, Int) {
    let a = jdn + 32044
    let b = (4 * a + 3) / 146097
    let c = a - (146097 * b) / 4
    let d = (4 * c + 3) / 1461
    let e = c - (1461 * d) / 4
    let m = (5 * e + 2) / 153
    let day = e - (153 * m + 2) / 5 + 1
    let month = m + 3 - 12 * (m / 10)
    let year = 100 * b + d - 4800 + m / 10
    return (year, month, day)
}

func mondayOf(_ t: (Int, Int, Int)) -> (Int, Int, Int) {
    let jdn = julianDayNumber(year: t.0, month: t.1, day: t.2)
    let weekdayIndex = ((jdn % 7) + 7) % 7 // 0 = Monday
    return calendarDate(fromJDN: jdn - weekdayIndex)
}

func addDays(_ t: (Int, Int, Int), _ days: Int) -> (Int, Int, Int) {
    calendarDate(fromJDN: julianDayNumber(year: t.0, month: t.1, day: t.2) + days)
}

func archiveMonth(_ monday: (Int, Int, Int)) -> String {
    let thursday = addDays(monday, 3)
    return String(format: "%04d-%02d", thursday.0, thursday.1)
}

func ymdString(_ t: (Int, Int, Int)) -> String {
    String(format: "%04d-%02d-%02d", t.0, t.1, t.2)
}

func sameYMD(_ a: (Int, Int, Int), _ b: (Int, Int, Int)) -> Bool {
    a.0 == b.0 && a.1 == b.1 && a.2 == b.2
}

func todayYMD() -> (Int, Int, Int) {
    var cal = Calendar(identifier: .gregorian)
    cal.timeZone = TimeZone.current
    let comps = cal.dateComponents([.year, .month, .day], from: Date())
    return (comps.year!, comps.month!, comps.day!)
}

func parseYMD(_ s: String) -> (Int, Int, Int)? {
    let parts = s.split(separator: "-", omittingEmptySubsequences: false)
    guard parts.count == 3,
          parts[0].count == 4, parts[1].count == 2, parts[2].count == 2,
          let y = Int(parts[0]), let m = Int(parts[1]), let d = Int(parts[2]),
          (1...12).contains(m), (1...31).contains(d)
    else { return nil }
    return (y, m, d)
}

func parseHeaderDate(_ line: String) -> (Int, Int, Int)? {
    guard line.hasPrefix("## "), line.count >= 13 else { return nil }
    let start = line.index(line.startIndex, offsetBy: 3)
    let end = line.index(start, offsetBy: 10)
    return parseYMD(String(line[start..<end]))
}

// MARK: - Line handling (mirrors Python's splitlines(keepends=True))

func splitKeepingEnds(_ s: String) -> [String] {
    var result: [String] = []
    var current = ""
    for ch in s {
        current.append(ch)
        if ch == "\n" {
            result.append(current)
            current = ""
        }
    }
    if !current.isEmpty { result.append(current) }
    return result
}

// MARK: - Logging

func log(_ msg: String) {
    let line = "[\(ymdString(todayYMD()))] \(msg)\n"
    print(line, terminator: "")
    guard let data = line.data(using: .utf8) else { return }
    if FileManager.default.fileExists(atPath: logPath.path) {
        if let handle = try? FileHandle(forWritingTo: logPath) {
            defer { try? handle.close() }
            handle.seekToEndOfFile()
            handle.write(data)
        }
    } else {
        try? FileManager.default.createDirectory(
            at: logPath.deletingLastPathComponent(), withIntermediateDirectories: true)
        try? data.write(to: logPath)
    }
}

func trimLog() {
    guard let content = try? String(contentsOf: logPath, encoding: .utf8) else { return }
    let lines = splitKeepingEnds(content)
    if lines.count > 100 {
        try? lines.suffix(100).joined().write(to: logPath, atomically: true, encoding: .utf8)
    }
}

// MARK: - Failure notifications
//
// Mirrors backup-folder.py's notify_failure(): terminal-notifier first, falling
// back to osascript's "display notification" (a pure Notification Center call,
// not a file operation — unrelated to the iCloud TCC issue this tool works around).
// Both are timeout-bounded so a notification problem can never hang the job.

@discardableResult
func runProcessWithTimeout(_ path: String, arguments: [String], timeout: TimeInterval) -> Bool {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: path)
    process.arguments = arguments
    process.standardOutput = FileHandle.nullDevice
    process.standardError = FileHandle.nullDevice
    let semaphore = DispatchSemaphore(value: 0)
    process.terminationHandler = { _ in semaphore.signal() }
    do {
        try process.run()
    } catch {
        return false
    }
    if semaphore.wait(timeout: .now() + timeout) == .timedOut {
        process.terminate()
        return false
    }
    return process.terminationStatus == 0
}

func findTerminalNotifier() -> String? {
    for candidate in ["/opt/homebrew/bin/terminal-notifier", "/usr/local/bin/terminal-notifier"]
    where FileManager.default.isExecutableFile(atPath: candidate) {
        return candidate
    }
    return nil
}

func notifyFailure(_ msg: String) {
    let body = String(msg.replacingOccurrences(of: "\n", with: " ").prefix(240))
    if let tn = findTerminalNotifier() {
        let ok = runProcessWithTimeout(tn, arguments: [
            "-title", "Session Log Archive Failed",
            "-message", body,
            "-sound", "Basso",
            "-ignoreDnD",
            "-group", "session-log-archive-failure",
        ], timeout: 15)
        if ok { return }
    }
    let safe = body.replacingOccurrences(of: "\\", with: "").replacingOccurrences(of: "\"", with: "'")
    runProcessWithTimeout(
        "/usr/bin/osascript",
        arguments: ["-e", "display notification \"\(safe)\" with title \"Session Log Archive Failed\" sound name \"Basso\""],
        timeout: 15
    )
}

// MARK: - Args

let args = CommandLine.arguments
let dryRun = args.contains("--dry-run")
var sourceOverride: String? = nil
if let idx = args.firstIndex(of: "--source"), idx + 1 < args.count {
    sourceOverride = args[idx + 1]
}
if sourceOverride != nil && !dryRun {
    print("ERROR: --source is only valid with --dry-run")
    exit(1)
}

// MARK: - Main

func run() {
    trimLog()

    if dryRun { log("DRY RUN — no files will be modified") }

    let currentMonday = mondayOf(todayYMD())
    let currentMondayStr = ymdString(currentMonday)

    let readURL = sourceOverride.map { URL(fileURLWithPath: $0) } ?? sessionLog
    guard let content = try? String(contentsOf: readURL, encoding: .utf8), !content.isEmpty else {
        let msg = "session-log.md is empty or not accessible — nothing to archive"
        log(msg)
        if !dryRun { notifyFailure(msg) }
        return
    }
    let lines = splitKeepingEnds(content)
    if lines.isEmpty {
        log("session-log.md is empty or not accessible — nothing to archive")
        return
    }

    var splitIndex: Int? = nil
    for (i, line) in lines.enumerated() {
        if line.hasPrefix("## "), line.count >= 13 {
            let start = line.index(line.startIndex, offsetBy: 3)
            let end = line.index(start, offsetBy: 10)
            if String(line[start..<end]) >= currentMondayStr {
                splitIndex = i
                break
            }
        }
    }

    if splitIndex == 0 {
        log("No prior-week entries found — nothing to archive")
        return
    }

    let toArchive = splitIndex.map { Array(lines[0..<$0]) } ?? lines
    let newSession = splitIndex.map { Array(lines[$0...]) } ?? []

    struct WeekGroup { let monday: (Int, Int, Int); let month: String; let lines: [String] }
    var weeks: [WeekGroup] = []
    var currentWeekMonday: (Int, Int, Int)? = nil
    var currentWeekLines: [String] = []

    for line in toArchive {
        if let d = parseHeaderDate(line) {
            let wm = mondayOf(d)
            if currentWeekMonday == nil || !sameYMD(wm, currentWeekMonday!) {
                if !currentWeekLines.isEmpty, let cwm = currentWeekMonday {
                    weeks.append(WeekGroup(monday: cwm, month: archiveMonth(cwm), lines: currentWeekLines))
                }
                currentWeekMonday = wm
                currentWeekLines = []
            }
        }
        currentWeekLines.append(line)
    }
    if !currentWeekLines.isEmpty, let cwm = currentWeekMonday {
        weeks.append(WeekGroup(monday: cwm, month: archiveMonth(cwm), lines: currentWeekLines))
    }

    if weeks.isEmpty {
        log("No dateable entries found to archive")
        return
    }

    var byMonthOrder: [String] = []
    var byMonth: [String: [String]] = [:]
    for w in weeks {
        if byMonth[w.month] == nil {
            byMonth[w.month] = []
            byMonthOrder.append(w.month)
        }
        byMonth[w.month]!.append(contentsOf: w.lines)
    }

    for w in weeks {
        let entryCount = w.lines.filter { $0.hasPrefix("## ") }.count
        let first = w.lines.first(where: { $0.hasPrefix("## ") })?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? "?"
        let last = w.lines.last(where: { $0.hasPrefix("## ") })?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? "?"
        let archiveName = "session-log-\(w.month).md"
        log("  \(dryRun ? "[dry-run] " : "")week \(ymdString(w.monday)) → \(archiveName)  (\(entryCount) entries)")
        log("    first: \(first)")
        log("    last:  \(last)")
    }

    for month in byMonthOrder.sorted() {
        let monthLines = byMonth[month]!
        let archivePath = archiveDir.appendingPathComponent("session-log-\(month).md")
        if !dryRun {
            do {
                try FileManager.default.createDirectory(at: archiveDir, withIntermediateDirectories: true)
                var existing = ""
                if FileManager.default.fileExists(atPath: archivePath.path) {
                    existing = (try? String(contentsOf: archivePath, encoding: .utf8)) ?? ""
                }
                try (existing + monthLines.joined()).write(to: archivePath, atomically: true, encoding: .utf8)
                let entryCount = monthLines.filter { $0.hasPrefix("## ") }.count
                log("Wrote \(entryCount) entries to session-log-\(month).md")
            } catch {
                let msg = "ERROR: failed to write session-log-\(month).md — \(error)"
                log(msg)
                notifyFailure(msg)
                exit(1)
            }
        }
    }

    let retained = newSession.filter { $0.hasPrefix("## ") }.count
    log("  \(dryRun ? "[dry-run] " : "")retaining \(retained) entries in session-log.md")

    if !dryRun {
        do {
            try newSession.joined().write(to: sessionLog, atomically: true, encoding: .utf8)
        } catch {
            let msg = "ERROR: failed to write session-log.md back — \(error)"
            log(msg)
            notifyFailure(msg)
            exit(1)
        }
    }
}

run()
