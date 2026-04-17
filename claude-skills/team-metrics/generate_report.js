#!/usr/bin/env node
/**
 * Team Metrics Report Generator
 * ------------------------------------
 * Usage:
 *   node generate_report.js \
 *     --members "Engineer One,Engineer Two" \
 *     --start   2026-03-04 \
 *     --end     2026-03-10 \
 *     --data    /path/to/metrics_data.json \
 *     --out     /path/to/output/dir
 *
 * --members   Comma-separated names matching keys in team_config.json.
 *             Use "ALL" to include every member in the config.
 * --start     Week start date (YYYY-MM-DD, Monday)
 * --end       Week end date   (YYYY-MM-DD, Friday or last working day)
 * --data      Path to the JSON file Claude writes with collected metrics.
 *             See DATA FORMAT section at the bottom of this file.
 * --out       Output directory (default: same folder as this script).
 *
 * Exit codes: 0 = success, 1 = argument/validation error, 2 = write error
 */

'use strict';

// ─── DEPENDENCIES ────────────────────────────────────────────────────────────
const path = require('path');
const fs   = require('fs');

const DOCX_LOCAL    = path.resolve(__dirname, 'node_modules/docx');
const DOCX_FALLBACK = '/sessions/quirky-determined-ramanujan/node_modules/docx';
const DOCX_PATH     = fs.existsSync(DOCX_LOCAL) ? DOCX_LOCAL : DOCX_FALLBACK;
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, PageBreak, LevelFormat,
  TabStopType, TabStopPosition
} = require(DOCX_PATH);

// ─── CLI ARGS ────────────────────────────────────────────────────────────────
function parseArgs() {
  const args = process.argv.slice(2);
  const get  = (flag) => { const i = args.indexOf(flag); return i !== -1 ? args[i + 1] : null; };
  const members = get('--members');
  const start   = get('--start');
  const end     = get('--end');
  const data    = get('--data');
  const out     = get('--out') || __dirname;

  if (!members) die('--members required. E.g.: --members "Engineer One,Engineer Two" or --members ALL');
  if (!start)   die('--start required. E.g.: --start 2026-03-04');
  if (!end)     die('--end required. E.g.: --end 2026-03-10');
  if (!data)    die('--data required. Path to the JSON metrics file Claude generates.');
  if (!fs.existsSync(data)) die(`Data file not found: ${data}`);
  return { members, start, end, data, out };
}

function die(msg, code = 1) { console.error('❌  ' + msg); process.exit(code); }

// ─── DATE & NUMBER HELPERS ───────────────────────────────────────────────────
const MONTHS = ['January','February','March','April','May','June',
                'July','August','September','October','November','December'];

function parseDate(s) {
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function filingMonth(startStr, endStr) {
  const start = parseDate(startStr), end = parseDate(endStr);
  const counts = {};
  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    const dow = d.getDay();
    if (dow === 0 || dow === 6) continue;
    const key = `${d.getFullYear()}-${d.getMonth()}`;
    if (!counts[key]) counts[key] = { month: d.getMonth(), year: d.getFullYear(), n: 0 };
    counts[key].n++;
  }
  const best = Object.values(counts).sort((a, b) => b.n - a.n)[0];
  return { month: best.month, year: best.year, label: `${MONTHS[best.month]} ${best.year}` };
}

function workingDays(startStr, endStr) {
  const start = parseDate(startStr), end = parseDate(endStr);
  let n = 0;
  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    const dow = d.getDay();
    if (dow !== 0 && dow !== 6) n++;
  }
  return n;
}

function fmtDate(s) {
  const d = parseDate(s);
  return `${MONTHS[d.getMonth()].slice(0,3)} ${d.getDate()}`;
}

function weekLabel(startStr, endStr) {
  const s = parseDate(startStr), e = parseDate(endStr);
  const sm = MONTHS[s.getMonth()].slice(0,3), em = MONTHS[e.getMonth()].slice(0,3);
  if (s.getMonth() === e.getMonth())
    return `Week of ${sm} ${s.getDate()} \u2013 ${e.getDate()}, ${s.getFullYear()}`;
  return `Week of ${sm} ${s.getDate()} \u2013 ${em} ${e.getDate()}, ${s.getFullYear()}`;
}

function todayLabel() {
  const d = new Date();
  return `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
}

/** Format decimal hours → "3h 30min" or "3h" */
function fmtHours(h) {
  const hr = Math.floor(h), mn = Math.round((h - hr) * 60);
  if (mn > 0) return `${hr}h ${mn}min`;
  return `${hr}h`;
}

function pct(num, denom) {
  if (!denom) return '0%';
  return `${Math.round((num / denom) * 100)}%`;
}

// ─── COLORS ──────────────────────────────────────────────────────────────────
const C = {
  headerBlue:  "1F4E79", lightBlue:  "D0E4F5", midBlue:    "2E75B6",
  accentBlue:  "5B9BD5", white:      "FFFFFF", lightGray:  "F5F5F5",
  midGray:     "D9D9D9", darkText:   "1A1A1A", greenMuted: "E2EFDA",
  orangeMuted: "FCE4D6", weekBand:   "EAF2FB", greenDark:  "2E7D32",
  orangeDark:  "C55A11", purpleMuted:"EAE7F5", purpleDark: "5B2D8E",
  redMuted:    "FCE8E8", redDark:    "C62828", tealMuted:  "E0F4F1",
  tealDark:    "00695C",
};

const CONTENT_WIDTH = 9360; // US Letter 8.5" − 2×0.75" margins in DXA

// ─── DOCX PRIMITIVES ─────────────────────────────────────────────────────────
function bdr(color = C.midGray) {
  const b = { style: BorderStyle.SINGLE, size: 4, color };
  return { top: b, bottom: b, left: b, right: b };
}

function hCell(text, width, bg = C.headerBlue, fg = C.white) {
  return new TableCell({
    borders: bdr(C.accentBlue), width: { size: width, type: WidthType.DXA },
    shading: { fill: bg, type: ShadingType.CLEAR },
    margins: { top: 100, bottom: 100, left: 140, right: 140 },
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({ children: [
      new TextRun({ text, bold: true, color: fg, size: 20, font: "Arial" })
    ]})]
  });
}

function dCell(text, width, bg = C.white, bold = false, fg = C.darkText) {
  return new TableCell({
    borders: bdr(C.midGray), width: { size: width, type: WidthType.DXA },
    shading: { fill: bg, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 140, right: 140 },
    verticalAlign: VerticalAlign.TOP,
    children: [new Paragraph({ children: [
      new TextRun({ text: String(text ?? '—'), bold, color: fg, size: 19, font: "Arial" })
    ]})]
  });
}

function sp(before = 40, after = 40) {
  return new Paragraph({ spacing: { before, after }, children: [new TextRun("")] });
}

function bul(text, indent = 720) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { before: 40, after: 40 },
    children: [new TextRun({ text, size: 19, font: "Arial", color: C.darkText })]
  });
}

function lv(label, value, valColor = C.darkText) {
  return new Paragraph({
    spacing: { before: 60, after: 60 },
    children: [
      new TextRun({ text: `${label}: `, bold: true, size: 19, font: "Arial", color: C.midBlue }),
      new TextRun({ text: value, size: 19, font: "Arial", color: valColor }),
    ]
  });
}

function secHead(text, color = C.midBlue) {
  return new Paragraph({
    spacing: { before: 160, after: 60 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: C.accentBlue, space: 3 } },
    children: [new TextRun({ text, bold: true, size: 22, color, font: "Arial" })]
  });
}

function subHead(text) {
  return new Paragraph({
    spacing: { before: 100, after: 40 },
    children: [new TextRun({ text, bold: true, size: 20, color: C.midBlue, font: "Arial" })]
  });
}

function italicNote(text) {
  return new Paragraph({
    spacing: { before: 30, after: 30 },
    children: [new TextRun({ text, size: 17, font: "Arial", color: "808080", italics: true })]
  });
}

// ─── SUMMARY TABLE ───────────────────────────────────────────────────────────
function summaryTable(members, wdays) {
  // cols: Member | Mtg Hrs (%) | OOO | Jira Assigned | Jira Closed | PRs Opened | Reviews | Slack Msgs
  const cols = [2000, 1500, 560, 1100, 1100, 950, 1000, 1150];
  const hdrs = ["Team Member", "Meeting Hrs (%)", "OOO", "Jira Assigned", "Jira Closed", "PRs Opened", "Reviews Given", "Slack Msgs"];
  return new Table({
    width: { size: CONTENT_WIDTH, type: WidthType.DXA }, columnWidths: cols,
    rows: [
      new TableRow({ tableHeader: true, children: hdrs.map((h, i) => hCell(h, cols[i])) }),
      ...members.map((m, idx) => {
        const bg       = idx % 2 === 0 ? C.white : C.lightGray;
        const cal      = m.calendar || {};
        const mtgHrs   = cal.total_meeting_hours ?? 0;
        const availHrs = cal.available_hours ?? (wdays * 8);
        const mtgPct   = pct(mtgHrs, availHrs);
        const ooo      = cal.ooo_days ?? 0;
        const prs      = m.prs || {};
        const prCount  = (prs.opened || []).length;
        const revCount = (prs.reviews_given || []).length;
        const jira     = m.jira || {};
        const slk      = m.slack || {};
        return new TableRow({ children: [
          dCell(m.name,                                    cols[0], bg, true),
          dCell(`${fmtHours(mtgHrs)} (${mtgPct})`,        cols[1], bg),
          dCell(ooo > 0 ? `${ooo}d` : "—",               cols[2], ooo > 0 ? C.orangeMuted : bg, false, ooo > 0 ? C.orangeDark : C.darkText),
          dCell(jira.assigned_total ?? 0,                  cols[3], bg),
          dCell(jira.closed_this_week ?? 0,                cols[4], C.greenMuted, false, C.greenDark),
          dCell(prCount,                                   cols[5], bg, false, C.midBlue),
          dCell(revCount,                                  cols[6], bg, false, C.purpleDark),
          dCell(slk.total_messages ?? 0,                   cols[7], bg),
        ]});
      })
    ]
  });
}

// ─── EXEC SUMMARY ────────────────────────────────────────────────────────────
function weekExecSummary(members, wdays) {
  const totMtgHrs  = members.reduce((s,m) => s + (m.calendar?.total_meeting_hours ?? 0), 0);
  const totAvailHrs = members.reduce((s,m) => s + (m.calendar?.available_hours ?? wdays * 8), 0);
  const avgMtgPct  = pct(totMtgHrs, totAvailHrs);
  const totJiraAsgn = members.reduce((s,m) => s + (m.jira?.assigned_total ?? 0), 0);
  const totJiraCls  = members.reduce((s,m) => s + (m.jira?.closed_this_week ?? 0), 0);
  const totPRs      = members.reduce((s,m) => s + ((m.prs?.opened || []).length), 0);
  const totRevs     = members.reduce((s,m) => s + ((m.prs?.reviews_given || []).length), 0);
  const sc          = [1560, 1560, 1560, 1560, 1560, 1560];

  return [
    new Paragraph({
      spacing: { before: 120, after: 100 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: C.accentBlue, space: 4 } },
      children: [new TextRun({ text: "Weekly Summary", bold: true, size: 28, color: C.midBlue, font: "Arial" })]
    }),
    sp(40, 20),
    new Table({
      width: { size: CONTENT_WIDTH, type: WidthType.DXA }, columnWidths: sc,
      rows: [
        new TableRow({ children: [
          hCell("Total Mtg Hours", sc[0]), hCell("Team Mtg %",    sc[1]),
          hCell("Jira Assigned",   sc[2]), hCell("Jira Closed",   sc[3]),
          hCell("PRs Opened",      sc[4]), hCell("Reviews Given", sc[5]),
        ]}),
        new TableRow({ children: [
          dCell(fmtHours(totMtgHrs), sc[0], C.lightBlue,  true),
          dCell(avgMtgPct,           sc[1], C.lightBlue,  true),
          dCell(totJiraAsgn,         sc[2], C.lightBlue,  true),
          dCell(totJiraCls,          sc[3], C.greenMuted, true, C.greenDark),
          dCell(totPRs,              sc[4], C.lightBlue,  true, C.midBlue),
          dCell(totRevs,             sc[5], C.purpleMuted,true, C.purpleDark),
        ]}),
      ]
    }),
    sp(60, 40),
    new Paragraph({
      spacing: { before: 80, after: 60 },
      children: [new TextRun({ text: "Per-Member Overview", bold: true, size: 22, color: C.midBlue, font: "Arial" })]
    }),
    summaryTable(members, wdays),
    sp(80, 40),
  ];
}

// ─── WEEK DIVIDER ────────────────────────────────────────────────────────────
function weekDivider(label, wdays, memberCount, reportDate) {
  return [
    new Paragraph({ children: [new PageBreak()] }),
    new Paragraph({
      spacing: { before: 0, after: 0 },
      shading: { fill: C.headerBlue, type: ShadingType.CLEAR },
      children: [new TextRun({ text: "  " + label, bold: true, size: 36, color: C.white, font: "Arial" })]
    }),
    new Paragraph({
      spacing: { before: 0, after: 0 },
      shading: { fill: C.weekBand, type: ShadingType.CLEAR },
      children: [new TextRun({
        text: `  ${wdays} working days  ·  ${memberCount} team member${memberCount !== 1 ? 's' : ''}  ·  Report date: ${reportDate}`,
        size: 18, color: C.midBlue, font: "Arial"
      })]
    }),
    sp(80, 40),
  ];
}

// ─── JIRA TABLE ──────────────────────────────────────────────────────────────
function jiraTable(tickets, statusColors) {
  if (!tickets || tickets.length === 0) {
    return new Table({
      width: { size: CONTENT_WIDTH, type: WidthType.DXA }, columnWidths: [1400, 5560, 2400],
      rows: [
        new TableRow({ tableHeader: true, children: [
          hCell("Jira Key",[1400],C.midBlue), hCell("Summary",[5560],C.midBlue), hCell("Status",[2400],C.midBlue)
        ]}),
        new TableRow({ children: [
          dCell("—",1400,C.lightGray), dCell("None this period",5560,C.lightGray), dCell("—",2400,C.lightGray)
        ]})
      ]
    });
  }
  const cols = [1400, 5560, 2400];
  return new Table({
    width: { size: CONTENT_WIDTH, type: WidthType.DXA }, columnWidths: cols,
    rows: [
      new TableRow({ tableHeader: true, children: [
        hCell("Jira Key",cols[0],C.midBlue), hCell("Summary",cols[1],C.midBlue), hCell("Status",cols[2],C.midBlue)
      ]}),
      ...tickets.map((t, i) => {
        const bg = i % 2 === 0 ? C.white : C.lightGray;
        const isDone = /closed|done|won't do/i.test(t.status);
        const isActive = /progress|development|review|started/i.test(t.status);
        const sc  = isDone ? C.greenDark  : isActive ? C.orangeDark : C.darkText;
        const sbg = isDone ? C.greenMuted : isActive ? C.orangeMuted : bg;
        return new TableRow({ children: [
          dCell(t.key, cols[0], bg, true, C.midBlue),
          dCell(t.summary, cols[1], bg),
          dCell(t.status, cols[2], sbg, false, sc),
        ]});
      })
    ]
  });
}

// ─── PR TABLE ────────────────────────────────────────────────────────────────
function prTable(prs, cols4) {
  // cols4: [num_w, title_w, repo_w, status_w]
  if (!prs || prs.length === 0) {
    return new Table({
      width: { size: CONTENT_WIDTH, type: WidthType.DXA }, columnWidths: cols4,
      rows: [
        new TableRow({ tableHeader: true, children: cols4.map((w,i) => hCell(["PR #","Title","Date","Status"][i],w,C.midBlue)) }),
        new TableRow({ children: cols4.map(w => dCell("—",w,C.lightGray)) })
      ]
    });
  }
  return new Table({
    width: { size: CONTENT_WIDTH, type: WidthType.DXA }, columnWidths: cols4,
    rows: [
      new TableRow({ tableHeader: true, children: [
        hCell("PR #",    cols4[0],C.midBlue), hCell("Title", cols4[1],C.midBlue),
        hCell("Date",    cols4[2],C.midBlue), hCell("Status",cols4[3],C.midBlue),
      ]}),
      ...prs.map((p, i) => {
        const bg = i % 2 === 0 ? C.white : C.lightGray;
        const merged = /merged/i.test(p.status);
        return new TableRow({ children: [
          dCell(`#${p.num}`,  cols4[0], bg, true, C.midBlue),
          dCell(p.title,      cols4[1], bg),
          dCell(p.date,       cols4[2], bg),
          dCell(p.status,     cols4[3], merged ? C.greenMuted : C.lightBlue, false, merged ? C.greenDark : C.midBlue),
        ]});
      })
    ]
  });
}

function reviewTable(reviews) {
  if (!reviews || reviews.length === 0) return null;
  const cols = [1200, 5460, 2700];
  return new Table({
    width: { size: CONTENT_WIDTH, type: WidthType.DXA }, columnWidths: cols,
    rows: [
      new TableRow({ tableHeader: true, children: [
        hCell("PR #",cols[0],C.purpleDark), hCell("Title",cols[1],C.purpleDark), hCell("Date / Repo",cols[2],C.purpleDark)
      ]}),
      ...reviews.map((r, i) => {
        const bg = i % 2 === 0 ? C.white : C.lightGray;
        return new TableRow({ children: [
          dCell(`#${r.pr}`, cols[0], bg, true, C.purpleDark),
          dCell(r.title,    cols[1], bg),
          dCell(`${r.date}${r.repo ? '  ·  ' + r.repo.split('/').pop() : ''}`, cols[2], bg),
        ]});
      })
    ]
  });
}

// ─── CONFLUENCE TABLE ────────────────────────────────────────────────────────
function confluenceTable(pages) {
  if (!pages || pages.length === 0) return null;
  const cols = [5000, 2500, 1860];
  return new Table({
    width: { size: CONTENT_WIDTH, type: WidthType.DXA }, columnWidths: cols,
    rows: [
      new TableRow({ tableHeader: true, children: [
        hCell("Page Title",cols[0],C.tealDark), hCell("Action",cols[1],C.tealDark), hCell("Date",cols[2],C.tealDark)
      ]}),
      ...pages.map((p, i) => {
        const bg = i % 2 === 0 ? C.white : C.lightGray;
        const actColor = p.action === 'created' ? C.greenDark : p.action === 'commented' ? C.midBlue : C.darkText;
        return new TableRow({ children: [
          dCell(p.title,  cols[0], bg),
          dCell(p.action, cols[1], bg, false, actColor),
          dCell(p.date,   cols[2], bg),
        ]});
      })
    ]
  });
}

// ─── MEMBER SECTION ──────────────────────────────────────────────────────────
function memberSection(m, wdays) {
  const cal    = m.calendar || {};
  const prs    = m.prs      || {};
  const jira   = m.jira     || {};
  const slk    = m.slack    || {};
  const conf   = m.confluence || {};
  const oncall = m.on_call  || {};

  const mtgHrs    = cal.total_meeting_hours ?? 0;
  const availHrs  = cal.available_hours     ?? (wdays * 8);
  const mtgPctVal = Math.round((mtgHrs / (availHrs || 1)) * 100);
  const avgHrsDy  = cal.avg_hrs_per_day ?? 0;
  const ooo       = cal.ooo_days ?? 0;

  const prsOpened  = prs.opened        || [];
  const revsGiven  = prs.reviews_given || [];
  const prComments = prs.comments_received ?? 0;
  const prSource   = prs.source || "unknown";

  const jiraAssigned = jira.assigned_total  ?? 0;
  const jiraClosed   = jira.closed_this_week ?? 0;
  const jiraActive   = jira.active          || [];
  const jiraClosedTix = jira.closed_tickets || [];
  const allJiraTix   = [...jiraActive, ...jiraClosedTix];

  const slkTotal  = slk.total_messages ?? 0;
  const slkChans  = slk.per_channel    || [];
  const slkWindow = slk.active_window  || null;

  const confCreated   = conf.created   ?? 0;
  const confUpdated   = conf.updated   ?? 0;
  const confCommented = conf.commented ?? 0;
  const confPages     = conf.pages     || [];

  // ── Header banner ────────────────────────────────────────────────────────
  const onCallBadge = oncall.is_on_call
    ? new TextRun({ text: "  🔔 ON-CALL", bold: true, size: 20, color: C.redDark, font: "Arial" })
    : null;

  const headerChildren = [
    new TextRun({ text: `  ${m.name}`, bold: true, size: 30, color: C.white, font: "Arial" }),
    new TextRun({ text: `  ·  ${m.role}`, size: 20, color: "BDD7EE", font: "Arial" }),
  ];
  if (onCallBadge) headerChildren.push(onCallBadge);

  // ── 4-column stat card ────────────────────────────────────────────────────
  const qc = [2340, 2340, 2340, 2340];
  const oooStr    = ooo > 0 ? `  ·  OOO: ${ooo}d` : '';
  const mtgStr    = `${fmtHours(mtgHrs)}  ·  ${mtgPctVal}% of ${fmtHours(availHrs)}${oooStr}`;
  const jiraStr   = `${jiraAssigned} assigned  ·  ${jiraClosed} closed`;
  const prStr     = `${prsOpened.length} opened  ·  ${revsGiven.length} reviewed`;
  const slkStr    = `${slkTotal} messages  ·  ${slkChans.length} channel${slkChans.length !== 1 ? 's' : ''}`;

  const statCard = new Table({
    width: { size: CONTENT_WIDTH, type: WidthType.DXA }, columnWidths: qc,
    rows: [
      new TableRow({ children: [
        hCell(`📅 ${mtgStr}`, qc[0], C.lightBlue, C.midBlue),
        hCell(`📋 ${jiraStr}`,        qc[1], C.lightBlue, C.midBlue),
        hCell(`🔀 ${prStr}`,          qc[2], C.lightBlue, C.midBlue),
        hCell(`💬 ${slkStr}`,         qc[3], C.lightBlue, C.midBlue),
      ]})
    ]
  });

  const elements = [
    new Paragraph({
      pageBreakBefore: true, spacing: { before: 0, after: 0 },
      shading: { fill: C.midBlue, type: ShadingType.CLEAR },
      children: headerChildren
    }),
    sp(80, 40),
    statCard,
    sp(60, 40),

    // ── Highlights ────────────────────────────────────────────────────────
    secHead("Key Highlights"),
    ...(m.highlights || []).map(bul),
    sp(40, 20),

    // ── Meetings ──────────────────────────────────────────────────────────
    secHead("Meetings"),
    lv("Total hours in meetings", fmtHours(mtgHrs)),
    lv("Available hours this week", `${fmtHours(availHrs)}  (${(wdays - ooo)} working days × 8h)`),
    lv("Meetings as % of available", `${mtgPctVal}%`),
    lv("Avg hours/day in meetings", `${fmtHours(avgHrsDy)}/day`),
    ...(ooo > 0 ? [lv("Out-of-office days", `${ooo} day${ooo > 1 ? 's' : ''}`, C.orangeDark)] : []),
    sp(40, 20),

    // ── GitHub PRs ────────────────────────────────────────────────────────
    secHead("GitHub Pull Requests"),
    ...(prSource !== 'github' ? [italicNote(`Source: ${prSource === 'gmail+slack' ? 'Inferred from Gmail notifications + Slack' : prSource === 'slack' ? 'Inferred from Slack messages' : 'Inferred'}`)] : []),
    sp(20, 0),
    subHead(`PRs Opened / Created  (${prsOpened.length})`),
    prTable(prsOpened, [900, 5260, 1400, 1800]),
    sp(40, 20),
    subHead(`Reviews Given  (${revsGiven.length})`),
    ...(revsGiven.length > 0 ? [reviewTable(revsGiven)] : [italicNote("No reviews recorded this week.")]),
    sp(40, 20),
    lv("PR Comments Received", `${prComments}`, C.darkText),
    sp(40, 20),

    // ── Jira ──────────────────────────────────────────────────────────────
    secHead("Jira"),
    lv("Tickets assigned",        String(jiraAssigned)),
    lv("Tickets closed this week", String(jiraClosed), C.greenDark),
    sp(40, 20),
  ];

  if (allJiraTix.length > 0) {
    elements.push(jiraTable(allJiraTix));
    elements.push(sp(40, 20));
  }

  // ── Slack ─────────────────────────────────────────────────────────────────
  elements.push(secHead("Slack Activity"));
  elements.push(lv("Total messages sent", String(slkTotal)));
  if (slkWindow) elements.push(lv("Active time window", slkWindow, "595959"));

  if (slkChans.length > 0) {
    elements.push(sp(20, 20));
    elements.push(subHead("Messages by channel"));
    const chanCols = [4000, 5360];
    const chanTable = new Table({
      width: { size: CONTENT_WIDTH, type: WidthType.DXA }, columnWidths: chanCols,
      rows: [
        new TableRow({ tableHeader: true, children: [
          hCell("Channel", chanCols[0], C.midBlue), hCell("Messages", chanCols[1], C.midBlue)
        ]}),
        ...slkChans.map((c, i) => {
          const bg = i % 2 === 0 ? C.white : C.lightGray;
          return new TableRow({ children: [
            dCell(c.channel, chanCols[0], bg),
            dCell(String(c.count), chanCols[1], bg),
          ]});
        })
      ]
    });
    elements.push(chanTable);
  }
  elements.push(sp(40, 20));

  // ── Confluence ────────────────────────────────────────────────────────────
  elements.push(secHead("Confluence"));
  elements.push(lv("Pages created",    String(confCreated),   confCreated   > 0 ? C.greenDark : C.darkText));
  elements.push(lv("Pages updated",    String(confUpdated),   confUpdated   > 0 ? C.midBlue   : C.darkText));
  elements.push(lv("Pages commented",  String(confCommented), confCommented > 0 ? C.midBlue   : C.darkText));
  if (confPages.length > 0) {
    elements.push(sp(20, 20));
    elements.push(confluenceTable(confPages));
  }
  elements.push(sp(40, 20));

  // ── On-Call ───────────────────────────────────────────────────────────────
  elements.push(secHead("PagerDuty / On-Call"));
  if (oncall.is_on_call === true) {
    elements.push(lv("On-call this week", "YES", C.redDark));
    if (oncall.source) elements.push(italicNote(`Source: ${oncall.source}`));
  } else if (oncall.is_on_call === false) {
    elements.push(lv("On-call this week", "No", C.darkText));
    if (oncall.source) elements.push(italicNote(`Source: ${oncall.source}`));
  } else {
    elements.push(italicNote("On-call status could not be determined (no PagerDuty connector; Calendar/Slack check found no indication)."));
  }
  elements.push(sp(40, 20));

  // ── Current Focus ─────────────────────────────────────────────────────────
  elements.push(secHead("Current Focus"));
  elements.push(new Paragraph({
    spacing: { before: 40, after: 40 },
    children: [new TextRun({ text: m.focus || "—", size: 19, font: "Arial", color: C.darkText, italics: true })]
  }));

  return elements;
}

// ─── COVER PAGE ───────────────────────────────────────────────────────────────
function coverPage(monthLabel, squadName, emName) {
  return [
    sp(1440, 80),
    new Paragraph({ alignment: AlignmentType.CENTER, children: [
      new TextRun({ text: squadName, bold: true, size: 64, color: C.headerBlue, font: "Arial" })
    ]}),
    new Paragraph({ alignment: AlignmentType.CENTER, children: [
      new TextRun({ text: "Team Metrics — " + monthLabel, size: 40, color: C.midBlue, font: "Arial" })
    ]}),
    sp(80, 80),
    new Paragraph({ alignment: AlignmentType.CENTER,
      border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: C.accentBlue, space: 6 } },
      children: [new TextRun({ text: "Running monthly record  ·  Most recent week first", size: 22, color: "595959", font: "Arial", italics: true })]
    }),
    sp(80, 60),
    new Paragraph({ alignment: AlignmentType.CENTER, children: [
      new TextRun({ text: `Prepared for: ${emName}`, size: 22, color: "595959", font: "Arial", italics: true })
    ]}),
    sp(40, 40),
    new Paragraph({ alignment: AlignmentType.CENTER, children: [
      new TextRun({ text: `Last updated: ${todayLabel()}`, size: 20, color: "808080", font: "Arial" })
    ]}),
    sp(200, 0),
  ];
}

// ─── DOCUMENT ASSEMBLY ───────────────────────────────────────────────────────
function buildDoc(monthLabel, allWeeks, squadName, emName) {
  const children = [
    ...coverPage(monthLabel, squadName, emName),
    ...allWeeks.flatMap(week => [
      ...weekDivider(week.label, week.workingDays, week.members.length, week.reportDate),
      ...weekExecSummary(week.members, week.workingDays),
      ...week.members.flatMap(m => memberSection(m, week.workingDays)),
    ])
  ];

  return new Document({
    numbering: {
      config: [{ reference: "bullets", levels: [{
        level: 0, format: LevelFormat.BULLET, text: "•",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } }
      }]}]
    },
    styles: {
      default: { document: { run: { font: "Arial", size: 20, color: C.darkText } } },
      paragraphStyles: [
        { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal",
          run: { size: 30, bold: true, font: "Arial", color: C.white },
          paragraph: { spacing: { before: 0, after: 0 }, outlineLevel: 0 } },
        { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal",
          run: { size: 24, bold: true, font: "Arial", color: C.midBlue },
          paragraph: { spacing: { before: 120, after: 60 }, outlineLevel: 1 } },
      ]
    },
    sections: [{
      properties: {
        page: { size: { width: 12240, height: 15840 },
                margin: { top: 1080, right: 1080, bottom: 1080, left: 1080 } }
      },
      headers: { default: new Header({ children: [new Paragraph({
        tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
        border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: C.accentBlue, space: 4 } },
        children: [
          new TextRun({ text: `${squadName} — ${monthLabel}`, bold: true, size: 18, color: C.midBlue, font: "Arial" }),
          new TextRun({ text: "\tMonthly Metrics Record", size: 18, color: "808080", font: "Arial" }),
        ]
      })] }) },
      footers: { default: new Footer({ children: [new Paragraph({
        tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
        border: { top: { style: BorderStyle.SINGLE, size: 6, color: C.midGray, space: 4 } },
        children: [
          new TextRun({ text: "Confidential — Internal Use Only", size: 16, color: "808080", font: "Arial", italics: true }),
          new TextRun({ text: "\tPage ", size: 16, color: "808080", font: "Arial" }),
          new TextRun({ children: [PageNumber.CURRENT], size: 16, color: "808080", font: "Arial" }),
          new TextRun({ text: " of ", size: 16, color: "808080", font: "Arial" }),
          new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16, color: "808080", font: "Arial" }),
        ]
      })] }) },
      children
    }]
  });
}

// ─── MAIN ────────────────────────────────────────────────────────────────────
async function main() {
  const { members: memberArg, start, end, data: dataPath, out: outDir } = parseArgs();

  const configPath = path.join(__dirname, 'team_config.json');
  if (!fs.existsSync(configPath)) die(`team_config.json not found at: ${configPath}`);
  const config    = JSON.parse(fs.readFileSync(configPath,  'utf8'));
  const inputData = JSON.parse(fs.readFileSync(dataPath,    'utf8'));

  const allNames    = Object.keys(config.members);
  const wantedNames = memberArg.toUpperCase() === 'ALL'
    ? allNames
    : memberArg.split(',').map(n => n.trim());

  for (const name of wantedNames) {
    if (!config.members[name]) die(`Unknown member: "${name}". Valid names: ${allNames.join(', ')}`);
  }

  const wdays   = workingDays(start, end);
  const members = wantedNames.map(name => {
    const d = inputData.members[name];
    if (!d) die(`No data found for "${name}" in ${dataPath}.`);
    return { name, role: config.members[name].role, ...d };
  });

  const squadName = config.squad_name || "Squad";
  const emName    = config.em_name    || "Engineering Manager";
  const squadSlug = squadName.replace(/\s+/g, '_').toUpperCase();

  const { label: monthLabel, month, year } = filingMonth(start, end);
  const fileName  = `${squadSlug}_Team_Metrics_${MONTHS[month]}_${year}.docx`;
  const outPath   = path.join(outDir, fileName);
  const sidecarPath = outPath.replace('.docx', '_weeks.json');

  const newWeek = { label: weekLabel(start, end), workingDays: wdays, reportDate: todayLabel(), members };

  let existingWeeks = [];
  if (fs.existsSync(sidecarPath)) {
    existingWeeks = JSON.parse(fs.readFileSync(sidecarPath, 'utf8'));
    existingWeeks = existingWeeks.filter(w => w.label !== newWeek.label);
  }

  const allWeeks = [newWeek, ...existingWeeks];
  fs.writeFileSync(sidecarPath, JSON.stringify(allWeeks, null, 2));

  const doc = buildDoc(monthLabel, allWeeks, squadName, emName);
  const buf = await Packer.toBuffer(doc);
  fs.writeFileSync(outPath, buf);

  const action = existingWeeks.length > 0 ? 'Appended to' : 'Created';
  console.log(`✅  ${action}: ${outPath}`);
  console.log(`   Weeks in file : ${allWeeks.length} (${allWeeks.map(w => w.label).join(' | ')})`);
  console.log(`   Size          : ${(buf.length / 1024).toFixed(1)} KB`);
  console.log(`   Sidecar       : ${sidecarPath}`);
}

main().catch(e => { console.error('❌', e.message); process.exit(2); });

/*
 * ─── DATA FORMAT ─────────────────────────────────────────────────────────────
 * Claude writes a JSON file matching this structure before calling this script.
 *
 * {
 *   "members": {
 *     "Engineer One": {
 *       "calendar": {
 *         "total_meeting_hours": 10.5,
 *         "available_hours": 40,
 *         "meeting_pct": 26,
 *         "avg_hrs_per_day": 2.1,
 *         "ooo_days": 0
 *       },
 *       "prs": {
 *         "opened": [
 *           { "num": "1918", "title": "Add flightId to event", "date": "Mar 2",
 *             "repo": "yourorg/your-repo", "status": "Open" }
 *         ],
 *         "reviews_given": [
 *           { "pr": "1887", "title": "New purchaser audience type", "date": "Feb 26",
 *             "repo": "yourorg/your-repo" }
 *         ],
 *         "comments_received": 3,
 *         "source": "gmail+slack"
 *       },
 *       "jira": {
 *         "assigned_total": 6,
 *         "closed_this_week": 2,
 *         "active": [
 *           { "key": "PROJ-101", "summary": "Implement resource lookup", "status": "In Progress" }
 *         ],
 *         "closed_tickets": [
 *           { "key": "PROJ-95", "summary": "Add input validation to POST handler", "status": "Done" }
 *         ]
 *       },
 *       "slack": {
 *         "total_messages": 20,
 *         "per_channel": [
 *           { "channel": "#enablement-apis", "count": 12 },
 *           { "channel": "#client_apis_engineering", "count": 8 }
 *         ],
 *         "active_window": "9:15am – 6:30pm"
 *       },
 *       "confluence": {
 *         "created": 0,
 *         "updated": 1,
 *         "commented": 0,
 *         "pages": [
 *           { "title": "Flight API Design Doc", "action": "updated", "date": "Feb 27" }
 *         ]
 *       },
 *       "on_call": {
 *         "is_on_call": false,
 *         "source": "calendar"
 *       },
 *       "highlights": [
 *         "Opened PR #1918 adding flightId to event protobuf definitions",
 *         "Reviewed PR #1887 (new purchaser audience type) with detailed feedback"
 *       ],
 *       "focus": "Completing Flight API protobuf definitions and event emission pipeline"
 *     }
 *   }
 * }
 */
