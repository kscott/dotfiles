#!/usr/bin/env node
'use strict';

/**
 * generate_summary_report.js
 *
 * Aggregates multiple weeks of archived metrics data into a trend-focused HTML
 * summary report. Designed to answer: "How has my team performed over the last
 * N weeks / sprint / quarter / year?"
 *
 * Data source: metrics_archive/ folder populated automatically by
 * generate_html_report.js each time a weekly report runs.
 *
 * What the summary shows:
 *   - Period overview stat cards (totals and averages across all weeks)
 *   - Trend line charts per metric, one line per person (meeting %, Jira velocity,
 *     PRs opened, Slack messages)
 *   - Period summary table — one row per person with period totals
 *   - Per-person expandable breakdown (weekly or monthly depending on --group-by)
 *
 * Usage:
 *   node generate_summary_report.js \
 *     --start    2026-01-01  \  (first day of the period to summarise)
 *     --end      2026-12-31  \  (last day)
 *     --config   /path/to/team_config.json \
 *     --data-dir /path/to/metrics_archive/ \
 *     --members  "Name One,Name Two"   (or ALL) \
 *     --out      /path/to/output/ \
 *     --group-by month           (optional: "week" [default] or "month")
 *
 * --group-by month: rolls up weekly data into monthly buckets, producing 12 clean
 * chart points for a full-year view instead of 52 crowded ones. Ideal for year-end
 * reviews, annual performance summaries, and planning-season reporting.
 *
 * The script discovers all metrics_<start>_to_<end>.json files in --data-dir
 * whose week start date falls within [--start, --end], then aggregates them.
 */

const fs   = require('fs');
const path = require('path');

// ── CLI parsing ───────────────────────────────────────────────────────────────
const args     = process.argv.slice(2);
const arg      = (flag) => { const i = args.indexOf(flag); return i !== -1 ? args[i + 1] : null; };
const die      = (msg)  => { console.error('\nERROR:', msg, '\n'); process.exit(1); };

const startDate  = arg('--start')    || die('--start YYYY-MM-DD required');
const endDate    = arg('--end')      || die('--end YYYY-MM-DD required');
const configPath = arg('--config')   || die('--config path required');
const dataDir    = arg('--data-dir') || die('--data-dir path required');
const membersArg = arg('--members')  || 'ALL';
const outDir     = arg('--out')      || die('--out path required');

const groupByRaw = (arg('--group-by') || 'week').toLowerCase().trim();
if (!['week', 'month'].includes(groupByRaw)) die('--group-by must be "week" or "month"');
const groupByMonth = (groupByRaw === 'month');

// ── Load config ───────────────────────────────────────────────────────────────
let config;
try { config = JSON.parse(fs.readFileSync(configPath, 'utf8')); }
catch (e) { die(`Cannot read config at ${configPath}: ${e.message}`); }

const squadName = config.squad_name || 'Squad';
const emName    = config.em_name    || 'Engineering Manager';
const squadSlug = squadName.replace(/\s+/g, '_').toUpperCase();

const allCfgMembers = Object.keys(config.members || {});
const members = membersArg.trim().toUpperCase() === 'ALL'
  ? allCfgMembers
  : membersArg.split(',').map(n => n.trim()).filter(Boolean);

// ── Discover archive files in range ──────────────────────────────────────────
function localDate(str) {
  const [y, m, d] = str.split('-').map(Number);
  return new Date(y, m - 1, d);
}

const rangeStart = localDate(startDate);
const rangeEnd   = localDate(endDate);

if (!fs.existsSync(dataDir)) die(`data-dir not found: ${dataDir}\nRun generate_html_report.js for at least one week first.`);

const archiveFiles = fs.readdirSync(dataDir)
  .filter(f => /^metrics_\d{4}-\d{2}-\d{2}_to_\d{4}-\d{2}-\d{2}\.json$/.test(f))
  .map(f => {
    const [, ws, we] = f.match(/metrics_(\d{4}-\d{2}-\d{2})_to_(\d{4}-\d{2}-\d{2})/) || [];
    return { file: f, weekStart: ws, weekEnd: we };
  })
  .filter(({ weekStart }) => {
    const ws = localDate(weekStart);
    return ws >= rangeStart && ws <= rangeEnd;
  })
  .sort((a, b) => a.weekStart.localeCompare(b.weekStart));

if (!archiveFiles.length) {
  die(`No archived weeks found in ${dataDir} between ${startDate} and ${endDate}.\n` +
      'Run generate_html_report.js for at least one week in this range first.');
}

console.log(`\nFound ${archiveFiles.length} week(s) in range:`);
archiveFiles.forEach(w => console.log(`  • ${w.weekStart} → ${w.weekEnd}`));

// ── Load each archive ─────────────────────────────────────────────────────────
const weeks = archiveFiles.map(({ file, weekStart, weekEnd }) => {
  try {
    const data = JSON.parse(fs.readFileSync(path.join(dataDir, file), 'utf8'));
    return { weekStart, weekEnd, data };
  } catch (e) {
    console.warn(`  ⚠️  Could not parse ${file}: ${e.message} — skipping`);
    return null;
  }
}).filter(Boolean);

// ── Helpers ───────────────────────────────────────────────────────────────────
const MONTHS_SHORT = ['Jan','Feb','Mar','Apr','May','Jun',
                      'Jul','Aug','Sep','Oct','Nov','Dec'];
const MONTHS_LONG  = ['January','February','March','April','May','June',
                      'July','August','September','October','November','December'];

function shortDate(str) {
  const d = localDate(str);
  return `${MONTHS_SHORT[d.getMonth()]} ${d.getDate()}`;
}

function periodLabel(s, e) {
  const sd = localDate(s), ed = localDate(e);
  if (sd.getFullYear() === ed.getFullYear()) {
    if (sd.getMonth() === ed.getMonth())
      return `${MONTHS_LONG[sd.getMonth()]} ${sd.getDate()}–${ed.getDate()}, ${ed.getFullYear()}`;
    return `${MONTHS_SHORT[sd.getMonth()]} ${sd.getDate()} – ${MONTHS_SHORT[ed.getMonth()]} ${ed.getDate()}, ${ed.getFullYear()}`;
  }
  return `${MONTHS_SHORT[sd.getMonth()]} ${sd.getDate()}, ${sd.getFullYear()} – ${MONTHS_SHORT[ed.getMonth()]} ${ed.getDate()}, ${ed.getFullYear()}`;
}

const esc = (s) => String(s ?? '')
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');

function mtgColor(pct) {
  if (pct >= 75) return '#EF4444';
  if (pct >= 50) return '#F59E0B';
  return '#10B981';
}

function initials(name) {
  return name.split(' ').map(w => w[0] ?? '').join('').slice(0, 2).toUpperCase();
}

const PALETTE = ['#3B82F6','#8B5CF6','#10B981','#F59E0B','#EF4444','#06B6D4','#EC4899','#84CC16'];

// ── Monthly bucketing ─────────────────────────────────────────────────────────
// monthKey(dateStr) → "2026-01" style key used for grouping
function monthKey(dateStr) {
  return dateStr.slice(0, 7); // "YYYY-MM"
}

// monthLabel(key, spanYears) → "Jan '26" when spanning years, else "January"
function monthLabel(key, spanYears) {
  const [y, m] = key.split('-').map(Number);
  return spanYears
    ? `${MONTHS_SHORT[m - 1]} '${String(y).slice(2)}`
    : MONTHS_LONG[m - 1];
}

// Build ordered monthly bucket keys from the discovered weeks array
function buildMonthBuckets(weeksArr) {
  const keys = [...new Set(weeksArr.map(w => monthKey(w.weekStart)))].sort();
  return keys;
}

// Aggregate an array of per-week data objects (from getMemberWeekData) into one
// synthetic "month" object suitable for the same downstream code.
function aggregateWeeks(weekDataArr) {
  const n = weekDataArr.length || 1;
  const totalMtgHrs   = weekDataArr.reduce((s, w) => s + w.cal.total_meeting_hours, 0);
  const totalAvailHrs = weekDataArr.reduce((s, w) => s + w.cal.available_hours, 0);
  const avgMtgPct     = Math.round(weekDataArr.reduce((s, w) => s + w.cal.meeting_pct, 0) / n);

  return {
    cal: {
      total_meeting_hours: +totalMtgHrs.toFixed(1),
      available_hours:     +totalAvailHrs.toFixed(1),
      meeting_pct:         avgMtgPct,
      avg_hrs_per_day:     +(totalMtgHrs / (n * 5)).toFixed(1),
      ooo_days:            weekDataArr.reduce((s, w) => s + w.cal.ooo_days, 0),
    },
    prs: {
      opened:            weekDataArr.flatMap(w => w.prs.opened),
      reviews_given:     weekDataArr.flatMap(w => w.prs.reviews_given),
      comments_received: weekDataArr.reduce((s, w) => s + (w.prs.comments_received || 0), 0),
    },
    jira: {
      assigned_total:   weekDataArr.reduce((s, w) => s + (w.jira.assigned_total || 0), 0),
      closed_this_week: weekDataArr.reduce((s, w) => s + w.jira.closed_this_week, 0),
      active:           weekDataArr.flatMap(w => w.jira.active || []),
      closed_tickets:   weekDataArr.flatMap(w => w.jira.closed_tickets || []),
    },
    slack: {
      total_messages: weekDataArr.reduce((s, w) => s + w.slack.total_messages, 0),
      per_channel:    [],   // channel breakdown not meaningful after aggregation
    },
    conf: {
      created:   weekDataArr.reduce((s, w) => s + w.conf.created, 0),
      updated:   weekDataArr.reduce((s, w) => s + w.conf.updated, 0),
      commented: weekDataArr.reduce((s, w) => s + w.conf.commented, 0),
      pages:     weekDataArr.flatMap(w => w.conf.pages || []),
    },
    oncall: { is_on_call: weekDataArr.some(w => w.oncall.is_on_call === true) },
    highlights: weekDataArr.flatMap(w => w.highlights || []),
    focus:      weekDataArr[weekDataArr.length - 1]?.focus || '',
    _weekCount: n,  // how many real weeks were rolled up
  };
}

// ── Build per-member, per-week data matrix ─────────────────────────────────────
// weekMatrix[memberName][weekIndex] = { cal, prs, jira, slack, conf, oncall, ... }
function getMemberWeekData(name, weekData) {
  const d   = (weekData.members || {})[name] || {};
  const cal = d.calendar   || {};
  return {
    cal: {
      total_meeting_hours: cal.total_meeting_hours ?? 0,
      available_hours:     cal.available_hours     ?? 0,
      meeting_pct:         cal.meeting_pct         ?? 0,
      avg_hrs_per_day:     cal.avg_hrs_per_day     ?? 0,
      ooo_days:            cal.ooo_days            ?? 0,
    },
    prs:    d.prs        || { opened: [], reviews_given: [], comments_received: 0 },
    jira:   d.jira       || { assigned_total: 0, closed_this_week: 0, active: [], closed_tickets: [] },
    slack:  d.slack      || { total_messages: 0, per_channel: [] },
    conf:   d.confluence || { created: 0, updated: 0, commented: 0, pages: [] },
    oncall: d.on_call    || { is_on_call: null },
    highlights: d.highlights || [],
    focus:      d.focus  || '',
  };
}

// monthBuckets: ordered array of "YYYY-MM" keys (used only when groupByMonth)
const monthBuckets = groupByMonth ? buildMonthBuckets(weeks) : [];

// spanYears: true when the period crosses a calendar year boundary
const spanYears = localDate(startDate).getFullYear() !== localDate(endDate).getFullYear();

const memberInfo = members.map((name, i) => {
  // Always build week-level raw data (used for period-level totals & stats)
  const weekData = weeks.map(w => getMemberWeekData(name, w.data));

  // Build "periods" — either weekly (default) or monthly buckets
  let periods, periodLabelsArr;
  if (groupByMonth) {
    periods = monthBuckets.map(mk => {
      const weekIdxs = weeks.reduce((acc, w, wi) => {
        if (monthKey(w.weekStart) === mk) acc.push(wi);
        return acc;
      }, []);
      return aggregateWeeks(weekIdxs.map(wi => weekData[wi]));
    });
    periodLabelsArr = monthBuckets.map(mk => monthLabel(mk, spanYears));
  } else {
    periods = weekData;
    periodLabelsArr = weeks.map(w => shortDate(w.weekStart));
  }

  return {
    name,
    role:     (config.members[name] || {}).role || 'Engineer',
    color:    PALETTE[i % PALETTE.length],
    initials: initials(name),
    weeks:    weekData,      // always raw weekly — used for period stats
    periods,                 // weekly OR monthly — used for charts & detail table
    periodLabels: periodLabelsArr,
  };
});

// ── Compute period totals and averages per member ──────────────────────────────
function periodStats(m) {
  const n = m.weeks.length || 1;
  return {
    totalMeetingHrs:  +(m.weeks.reduce((s, w) => s + w.cal.total_meeting_hours, 0)).toFixed(1),
    avgMeetingPct:    Math.round(m.weeks.reduce((s, w) => s + w.cal.meeting_pct, 0) / n),
    totalOoo:         m.weeks.reduce((s, w) => s + w.cal.ooo_days, 0),
    totalPrsOpened:   m.weeks.reduce((s, w) => s + w.prs.opened.length, 0),
    totalReviews:     m.weeks.reduce((s, w) => s + w.prs.reviews_given.length, 0),
    totalJiraClosed:  m.weeks.reduce((s, w) => s + w.jira.closed_this_week, 0),
    avgJiraClosed:    +(m.weeks.reduce((s, w) => s + w.jira.closed_this_week, 0) / n).toFixed(1),
    totalSlack:       m.weeks.reduce((s, w) => s + w.slack.total_messages, 0),
    avgSlack:         Math.round(m.weeks.reduce((s, w) => s + w.slack.total_messages, 0) / n),
    totalConfluence:  m.weeks.reduce((s, w) => s + w.conf.created + w.conf.updated + w.conf.commented, 0),
    onCallWeeks:      m.weeks.filter(w => w.oncall.is_on_call === true).length,
  };
}

memberInfo.forEach(m => { m.stats = periodStats(m); });

// ── Team-level period totals ───────────────────────────────────────────────────
const teamTotals = {
  totalMeetingHrs: +(memberInfo.reduce((s, m) => s + m.stats.totalMeetingHrs, 0)).toFixed(1),
  avgMeetingPct:   Math.round(memberInfo.reduce((s, m) => s + m.stats.avgMeetingPct, 0) / (memberInfo.length || 1)),
  totalPrsOpened:  memberInfo.reduce((s, m) => s + m.stats.totalPrsOpened, 0),
  totalReviews:    memberInfo.reduce((s, m) => s + m.stats.totalReviews, 0),
  totalJiraClosed: memberInfo.reduce((s, m) => s + m.stats.totalJiraClosed, 0),
  totalSlack:      memberInfo.reduce((s, m) => s + m.stats.totalSlack, 0),
  weeksIncluded:   weeks.length,
};

// ── Chart data ────────────────────────────────────────────────────────────────
// x-axis labels come from the first member's periodLabels (all members share the same)
const xLabels = memberInfo.length ? memberInfo[0].periodLabels : [];

// Build a short display name: first word + last-name initial (e.g. "Emily L.")
// This keeps chart legends concise while staying unique on teams with shared first names.
function shortName(fullName) {
  const parts = fullName.trim().split(/\s+/);
  if (parts.length === 1) return parts[0];
  return parts[0] + ' ' + parts[parts.length - 1][0].toUpperCase() + '.';
}

const chartData = {
  weekLabels: xLabels,   // kept as "weekLabels" key so chart JS doesn't need changing
  groupBy: groupByRaw,   // "week" | "month" — used for axis/tooltip labels in HTML
  members: memberInfo.map(m => ({
    name:        shortName(m.name),
    full:        m.name,
    color:       m.color,
    meetingPct:  m.periods.map(p => p.cal.meeting_pct),
    jiraClosed:  m.periods.map(p => p.jira.closed_this_week),
    prsOpened:   m.periods.map(p => p.prs.opened.length),
    reviews:     m.periods.map(p => p.prs.reviews_given.length),
    slackMsgs:   m.periods.map(p => p.slack.total_messages),
  })),
};

// ── HTML generators ───────────────────────────────────────────────────────────
function statCard(label, value, sub, extra) {
  return `<div class="sc ${extra || ''}">
    <div class="sc-val">${esc(value)}</div>
    <div class="sc-lbl">${esc(label)}</div>
    ${sub ? `<div class="sc-sub">${esc(sub)}</div>` : ''}
  </div>`;
}

function summaryTable() {
  const headers = ['Member','Avg Mtg %','Total PRs','Reviews','Jira Closed','Avg Slack/wk','OOO Days'];
  const rows = memberInfo.map(m => {
    const s = m.stats;
    return `<tr>
      <td><span class="avatar-sm" style="background:${m.color}">${m.initials}</span> ${esc(m.name)}</td>
      <td style="color:${mtgColor(s.avgMeetingPct)};font-weight:700">${s.avgMeetingPct}%</td>
      <td>${s.totalPrsOpened}</td>
      <td>${s.totalReviews}</td>
      <td>${s.totalJiraClosed}</td>
      <td>${s.avgSlack}</td>
      <td>${s.totalOoo}</td>
    </tr>`;
  }).join('');
  return `<div class="table-wrap">
    <table class="sum-table">
      <thead><tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;
}

function memberDetailCard(m) {
  const s = m.stats;
  const periodCount = m.periods.length;
  const periodNoun  = groupByMonth ? 'month' : 'week';

  const periodRows = m.periods.map((pd, i) => {
    const label = m.periodLabels[i] || '';
    const oooStr = pd.cal.ooo_days > 0 ? pd.cal.ooo_days + 'd' : '—';
    // For monthly view, show week count in the period column
    const periodCell = groupByMonth
      ? `${label}<small class="period-wk-count"> (${pd._weekCount ?? 1}w)</small>`
      : label;
    return `<tr>
      <td class="nw">${periodCell}</td>
      <td style="color:${mtgColor(pd.cal.meeting_pct)}">${pd.cal.meeting_pct}%</td>
      <td>${pd.cal.total_meeting_hours.toFixed(1)}h</td>
      <td>${pd.prs.opened.length}</td>
      <td>${pd.prs.reviews_given.length}</td>
      <td>${pd.jira.closed_this_week}</td>
      <td>${pd.jira.assigned_total}</td>
      <td>${pd.slack.total_messages}</td>
      <td>${oooStr}</td>
    </tr>`;
  }).join('');

  // Highlights: tagged with week date (weekly) or month name (monthly)
  const allHighlights = groupByMonth
    ? m.periods.flatMap((pd, i) =>
        (pd.highlights || []).map(h =>
          `<li><span class="wk-tag">${m.periodLabels[i]}</span>${esc(h)}</li>`))
    : weeks.flatMap((w, i) =>
        (m.weeks[i].highlights || []).map(h =>
          `<li><span class="wk-tag">${shortDate(w.weekStart)}</span>${esc(h)}</li>`));

  const breakdownTitle = groupByMonth ? 'Month-by-Month Breakdown' : 'Week-by-Week Breakdown';

  return `<div class="mc" id="mc-${esc(m.name.replace(/\s+/g,'-').toLowerCase())}">
  <div class="mc-head" style="border-left:4px solid ${m.color}">
    <div class="mc-identity">
      <div class="avatar" style="background:${m.color}">${m.initials}</div>
      <div>
        <div class="mc-name">${esc(m.name)}</div>
        <div class="mc-role">${esc(m.role)} · ${weeks.length} week${weeks.length !== 1 ? 's' : ''} · ${periodCount} ${periodNoun}${periodCount !== 1 ? 's' : ''}</div>
      </div>
      <div class="mc-quick">
        <span class="qs" style="color:${mtgColor(s.avgMeetingPct)}">${s.avgMeetingPct}% <small>avg meetings</small></span>
        <span class="qs">${s.totalJiraClosed} <small>Jira closed</small></span>
        <span class="qs">${s.totalPrsOpened} <small>PRs opened</small></span>
        <span class="qs">${s.totalReviews} <small>reviews</small></span>
      </div>
    </div>
  </div>
  <div class="mc-body">
    <details class="ds" open>
      <summary class="ds-sum">${breakdownTitle}
        <span class="ds-cnt">${periodCount} ${periodNoun}${periodCount !== 1 ? 's' : ''}</span>
      </summary>
      <div class="ds-body">
        <table class="dt">
          <thead><tr>
            <th>${groupByMonth ? 'Month' : 'Week'}</th>
            <th>Mtg %</th><th>Mtg Hrs</th>
            <th>PRs</th><th>Reviews</th><th>Jira ✓</th><th>Jira Active</th>
            <th>Slack</th><th>OOO</th>
          </tr></thead>
          <tbody>${periodRows}</tbody>
        </table>
      </div>
    </details>
    ${allHighlights.length ? `<details class="ds">
      <summary class="ds-sum">All Highlights
        <span class="ds-cnt">${allHighlights.length} items</span>
      </summary>
      <div class="ds-body"><ul class="hl-list">${allHighlights.join('')}</ul></div>
    </details>` : ''}
  </div>
</div>`;
}

// ── Build full HTML ───────────────────────────────────────────────────────────
const label = periodLabel(startDate, endDate);

function buildHTML() {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(squadName)} Summary — ${esc(label)}</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #F1F5F9; color: #0F172A; font-size: 14px; line-height: 1.5; }
.page-wrap { max-width: 1200px; margin: 0 auto; padding: 24px 20px 48px; }

/* Header */
.hdr { background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
       color: #fff; padding: 22px 28px; border-radius: 12px;
       display: flex; align-items: flex-start; justify-content: space-between;
       margin-bottom: 20px; gap: 12px; flex-wrap: wrap; }
.hdr-squad  { font-size: 22px; font-weight: 700; letter-spacing: -0.3px; }
.hdr-period { font-size: 13px; color: #94A3B8; margin-top: 3px; }
.hdr-em     { font-size: 12px; color: #64748B; margin-top: 2px; }
.hdr-right  { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }
.hdr-pill   { background: rgba(59,130,246,.2); color: #93C5FD; border-radius: 999px;
              font-size: 11px; font-weight: 600; padding: 3px 10px; white-space: nowrap; }
.btn-pdf    { background: #3B82F6; color: #fff; border: none; padding: 9px 18px;
              border-radius: 7px; font-size: 13px; font-weight: 600; cursor: pointer;
              white-space: nowrap; transition: background .15s; }
.btn-pdf:hover { background: #2563EB; }

/* Summary cards */
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
         gap: 12px; margin-bottom: 24px; }
.sc { background: #fff; border-radius: 10px; padding: 16px;
      border: 1px solid #E2E8F0; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.sc-val  { font-size: 28px; font-weight: 700; color: #1E293B; line-height: 1; }
.sc-lbl  { font-size: 11px; font-weight: 600; color: #64748B; text-transform: uppercase;
           letter-spacing: .5px; margin-top: 4px; }
.sc-sub  { font-size: 11px; color: #94A3B8; margin-top: 3px; }
.sc-ok   { border-top: 3px solid #10B981; }
.sc-warn { border-top: 3px solid #F59E0B; }
.sc-blue { border-top: 3px solid #3B82F6; }

/* Section headers */
.section-hdr { font-size: 11px; font-weight: 700; text-transform: uppercase;
               letter-spacing: .6px; color: #94A3B8; margin: 24px 0 12px;
               display: flex; align-items: center; gap: 8px; }
.section-hdr::after { content: ''; flex: 1; height: 1px; background: #E2E8F0; }

/* Charts */
.charts-grid { display: grid; grid-template-columns: repeat(2, 1fr);
               gap: 16px; margin-bottom: 24px; }
.chart-card  { background: #fff; border-radius: 10px; padding: 20px;
               border: 1px solid #E2E8F0; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.chart-title { font-size: 13px; font-weight: 700; color: #334155;
               text-transform: uppercase; letter-spacing: .4px; margin-bottom: 16px; }
.chart-sub   { font-size: 11px; color: #94A3B8; margin-top: -12px; margin-bottom: 14px; }
.chart-wrap  { position: relative; height: 240px; }

/* Summary table */
.table-wrap { overflow-x: auto; margin-bottom: 24px; }
.sum-table  { width: 100%; border-collapse: collapse; background: #fff;
              border-radius: 10px; overflow: hidden; border: 1px solid #E2E8F0;
              box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.sum-table th { background: #F1F5F9; font-size: 11px; font-weight: 700; text-transform: uppercase;
                letter-spacing: .4px; color: #475569; padding: 10px 14px;
                text-align: left; border-bottom: 1px solid #E2E8F0; }
.sum-table td { padding: 10px 14px; border-bottom: 1px solid #F8FAFC; color: #334155;
                font-size: 13px; vertical-align: middle; }
.sum-table tr:last-child td { border-bottom: none; }
.sum-table tr:hover td { background: #F8FAFC; }
.avatar-sm   { display: inline-flex; width: 24px; height: 24px; border-radius: 50%;
               align-items: center; justify-content: center; font-size: 9px;
               font-weight: 700; color: #fff; margin-right: 6px; vertical-align: middle; }

/* Member cards */
.members-grid { display: flex; flex-direction: column; gap: 16px; }
.mc { background: #fff; border-radius: 10px; border: 1px solid #E2E8F0;
      box-shadow: 0 1px 3px rgba(0,0,0,.06); overflow: hidden; }
.mc-head { padding: 16px 20px; background: #F8FAFC; border-bottom: 1px solid #E2E8F0; }
.mc-identity { display: flex; align-items: center; gap: 12px; }
.avatar { width: 40px; height: 40px; border-radius: 50%; display: flex;
          align-items: center; justify-content: center; font-size: 13px;
          font-weight: 700; color: #fff; flex-shrink: 0; }
.mc-name { font-size: 15px; font-weight: 700; color: #0F172A; }
.mc-role { font-size: 12px; color: #64748B; }
.mc-quick { display: flex; gap: 20px; margin-left: auto; flex-wrap: wrap; }
.qs { font-size: 16px; font-weight: 700; color: #1E293B; text-align: center; }
.qs small { display: block; font-size: 10px; font-weight: 400; color: #94A3B8;
            text-transform: uppercase; letter-spacing: .3px; }
.mc-body { padding: 16px 20px; display: flex; flex-direction: column; gap: 12px; }

/* Details */
.ds { border: 1px solid #E2E8F0; border-radius: 8px; overflow: hidden; }
.ds-sum { padding: 10px 14px; cursor: pointer; font-size: 13px; font-weight: 600;
          color: #334155; display: flex; align-items: center; gap: 8px; list-style: none;
          user-select: none; background: #F8FAFC; }
.ds-sum::-webkit-details-marker { display: none; }
.ds-sum::before { content: '▶'; font-size: 9px; color: #94A3B8; transition: transform .15s; }
details[open] > .ds-sum::before { transform: rotate(90deg); }
.ds-cnt { margin-left: auto; font-size: 11px; font-weight: 400; color: #94A3B8; }
.ds-body { padding: 14px; background: #fff; }

/* Data tables */
.dt { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.dt th { text-align: left; padding: 6px 10px; background: #F1F5F9; font-size: 11px;
         font-weight: 700; text-transform: uppercase; letter-spacing: .3px; color: #475569;
         border-bottom: 1px solid #E2E8F0; }
.dt td { padding: 7px 10px; border-bottom: 1px solid #F1F5F9; color: #334155; }
.dt tr:last-child td { border-bottom: none; }
.dt tr:hover td { background: #F8FAFC; }
.nw { white-space: nowrap; }

/* Highlights */
.hl-list  { padding-left: 18px; display: flex; flex-direction: column; gap: 5px; }
.hl-list li { font-size: 13px; color: #334155; }
.wk-tag { display: inline-block; background: #EFF6FF; color: #3B82F6; font-size: 10px;
          font-weight: 600; border-radius: 4px; padding: 1px 5px; margin-right: 6px;
          white-space: nowrap; }
.period-wk-count { font-size: 10px; color: #94A3B8; font-weight: 400; }

/* Footer */
.footer { text-align: center; font-size: 11px; color: #94A3B8; margin-top: 32px; }

/* Print */
@media print {
  @page { size: A4; margin: 15mm 12mm; }
  body { background: #fff; }
  .page-wrap { max-width: 100%; padding: 0; }
  .btn-pdf { display: none !important; }
  .hdr { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .charts-grid { grid-template-columns: repeat(2, 1fr); gap: 12px; }
  .chart-wrap { height: 200px; }
  .mc { break-inside: avoid; }
  .ds-body { display: block !important; }
}
</style>
</head>
<body>
<div class="page-wrap">

  <!-- Header -->
  <div class="hdr">
    <div>
      <div class="hdr-squad">${esc(squadName)} — Summary Report</div>
      <div class="hdr-period">${esc(label)}</div>
      <div class="hdr-em">${esc(emName)}</div>
    </div>
    <div class="hdr-right">
      <span class="hdr-pill">${weeks.length} week${weeks.length !== 1 ? 's' : ''} · ${groupByMonth ? monthBuckets.length + ' months · ' : ''}${members.length} member${members.length !== 1 ? 's' : ''}</span>
      <button class="btn-pdf" onclick="window.print()">⬇ Export PDF</button>
    </div>
  </div>

  <!-- Period overview cards -->
  <div class="cards">
    ${statCard('Total Meeting Hours', `${teamTotals.totalMeetingHrs}h`, `avg ${teamTotals.avgMeetingPct}% of capacity`, teamTotals.avgMeetingPct >= 50 ? 'sc-warn' : 'sc-ok')}
    ${statCard('PRs Opened', teamTotals.totalPrsOpened, `+ ${teamTotals.totalReviews} reviews given`, 'sc-blue')}
    ${statCard('Jira Tickets Closed', teamTotals.totalJiraClosed, `across ${weeks.length} weeks`, 'sc-ok')}
    ${statCard('Slack Messages', teamTotals.totalSlack, `${Math.round(teamTotals.totalSlack / (memberInfo.length || 1))} avg per person`)}
    ${statCard('Weeks Covered', weeks.length, `${shortDate(startDate)} – ${shortDate(endDate)}`)}
    ${statCard('Team Size', members.length, `${members.map(shortName).join(', ')}`)}
  </div>

  <!-- Trend charts -->
  <div class="section-hdr">Trends over time</div>
  <div class="charts-grid">
    <div class="chart-card">
      <div class="chart-title">📅 Meeting Load % — per ${groupByRaw}</div>
      <div class="chart-sub">% of available hours spent in meetings · green &lt;50% · amber 50–75% · red ≥75%${groupByMonth ? ' · monthly average' : ''}</div>
      <div class="chart-wrap"><canvas id="chartMtg"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">🎯 Jira Closed — per ${groupByRaw}</div>
      <div class="chart-sub">Tickets moved to Done/Closed ${groupByMonth ? 'per month' : 'each week'} per person</div>
      <div class="chart-wrap"><canvas id="chartJira"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">🔀 PRs Opened — per ${groupByRaw}</div>
      <div class="chart-sub">Pull requests created ${groupByMonth ? 'per month' : 'each week'} per person</div>
      <div class="chart-wrap"><canvas id="chartPRs"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">💬 Slack Messages — per ${groupByRaw}</div>
      <div class="chart-sub">Total messages sent ${groupByMonth ? 'per month' : 'each week'} per person</div>
      <div class="chart-wrap"><canvas id="chartSlack"></canvas></div>
    </div>
  </div>

  <!-- Period summary table -->
  <div class="section-hdr">Period summary</div>
  ${summaryTable()}

  <!-- Per-person breakdown -->
  <div class="section-hdr">Per-person detail</div>
  <div class="members-grid">
    ${memberInfo.map(memberDetailCard).join('\n\n')}
  </div>

  <div class="footer">
    Generated ${new Date().toLocaleString()} · ${esc(squadName)} · ${esc(emName)}
    · ${weeks.length} weeks (${shortDate(startDate)} – ${shortDate(endDate)})
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<script>
const D = ${JSON.stringify(chartData)};

Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
Chart.defaults.font.size   = 12;
Chart.defaults.color       = '#64748B';

const GRID = { color: '#F1F5F9', drawBorder: false };
const TICK  = { color: '#94A3B8' };

function lineDatasets(key) {
  return D.members.map(m => ({
    label:       m.name,
    data:        m[key],
    borderColor: m.color,
    backgroundColor: m.color + '20',
    tension:     0.35,
    pointRadius: 5,
    pointHoverRadius: 7,
    borderWidth: 2.5,
    fill:        false,
  }));
}

const sharedOptions = (yTitle, stepSize) => ({
  responsive:          true,
  maintainAspectRatio: false,
  interaction: { mode: 'index', intersect: false },
  plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, padding: 10 } } },
  scales: {
    x: { grid: GRID, ticks: TICK },
    y: {
      grid: GRID, ticks: { ...TICK, stepSize },
      title: { display: true, text: yTitle, color: '#94A3B8', font: { size: 11 } },
    },
  },
});

// Meeting % trend
new Chart(document.getElementById('chartMtg'), {
  type: 'line',
  data: { labels: D.weekLabels, datasets: lineDatasets('meetingPct') },
  options: {
    ...sharedOptions('% of capacity', 10),
    plugins: {
      ...sharedOptions('% of capacity', 10).plugins,
      annotation: undefined, // could add 50% reference line here in future
    },
    scales: {
      ...sharedOptions('% of capacity', 10).scales,
      y: {
        ...sharedOptions('% of capacity', 10).scales.y,
        min: 0, max: 100,
        ticks: { ...TICK, callback: v => v + '%', stepSize: 25 },
      },
    },
  },
});

// Jira closed trend
new Chart(document.getElementById('chartJira'), {
  type: 'line',
  data: { labels: D.weekLabels, datasets: lineDatasets('jiraClosed') },
  options: sharedOptions('Tickets closed', 1),
});

// PRs opened trend
new Chart(document.getElementById('chartPRs'), {
  type: 'line',
  data: { labels: D.weekLabels, datasets: lineDatasets('prsOpened') },
  options: sharedOptions('PRs opened', 1),
});

// Slack messages trend
new Chart(document.getElementById('chartSlack'), {
  type: 'line',
  data: { labels: D.weekLabels, datasets: lineDatasets('slackMsgs') },
  options: sharedOptions('Messages', 5),
});
</script>
</body>
</html>`;
}

// ── Write output ──────────────────────────────────────────────────────────────
fs.mkdirSync(outDir, { recursive: true });
const groupSuffix = groupByMonth ? '_monthly' : '';
const fileName = `${squadSlug}_Summary_${startDate}_to_${endDate}${groupSuffix}.html`;
const outPath  = path.join(outDir, fileName);
fs.writeFileSync(outPath, buildHTML(), 'utf8');

const xLabelStr = xLabels.join(', ');
console.log(`\n✅  Summary report written to: ${outPath}`);
console.log(`   Covers ${weeks.length} week(s)${groupByMonth ? ` rolled up into ${monthBuckets.length} month(s)` : ''}: ${xLabelStr}`);
console.log(`   Open in any browser — click "Export PDF" to save as PDF.\n`);
