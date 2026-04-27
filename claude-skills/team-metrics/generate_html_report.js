#!/usr/bin/env node
'use strict';

/**
 * generate_html_report.js
 *
 * Generates a self-contained HTML weekly team metrics report with embedded
 * Chart.js visualizations and one-click PDF export (via browser print dialog).
 * No npm dependencies — uses only Node.js built-ins.
 * Requires internet access to load Chart.js from CDN when the report is opened.
 *
 * Usage:
 *   node generate_html_report.js \
 *     --members "Name One,Name Two"   (or ALL) \
 *     --start   2026-02-23 \
 *     --end     2026-03-06 \
 *     --data    /path/to/metrics_data.json \
 *     --config  /path/to/team_config.json \
 *     --out     /path/to/output/
 */

const fs   = require('fs');
const path = require('path');

// ── CLI parsing ───────────────────────────────────────────────────────────────
const args = process.argv.slice(2);
const arg  = (flag) => { const i = args.indexOf(flag); return i !== -1 ? args[i + 1] : null; };
const die  = (msg)  => { console.error('\nERROR:', msg, '\n'); process.exit(1); };

const membersArg = arg('--members') || die('--members required');
const startDate  = arg('--start')   || die('--start required');
const endDate    = arg('--end')     || die('--end required');
const dataPath   = arg('--data')    || die('--data required');
const configPath = arg('--config')  || die('--config required');
const outDir     = arg('--out')     || die('--out required');

// ── Load data ─────────────────────────────────────────────────────────────────
let config, rawData;
try { config  = JSON.parse(fs.readFileSync(configPath,  'utf8')); }
catch (e) { die(`Cannot read config at ${configPath}: ${e.message}`); }
try { rawData = JSON.parse(fs.readFileSync(dataPath, 'utf8')); }
catch (e) { die(`Cannot read data at ${dataPath}: ${e.message}`); }

const squadName = config.squad_name || 'Squad';
const emName    = config.em_name    || 'Engineering Manager';
const squadSlug = squadName.replace(/\s+/g, '_').toUpperCase();

const allCfgMembers = Object.keys(config.members || {});
const members = membersArg.trim().toUpperCase() === 'ALL'
  ? allCfgMembers
  : membersArg.split(',').map(n => n.trim()).filter(Boolean);

for (const m of members) {
  if (!config.members[m]) die(`Member "${m}" not found in team_config.json`);
}

// ── Date helpers ──────────────────────────────────────────────────────────────
const MONTHS_LONG  = ['January','February','March','April','May','June',
                      'July','August','September','October','November','December'];
const MONTHS_SHORT = ['Jan','Feb','Mar','Apr','May','Jun',
                      'Jul','Aug','Sep','Oct','Nov','Dec'];

function localDate(str) {
  const [y, m, d] = str.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function workingDays(s, e) {
  let n = 0;
  for (let d = localDate(s); d <= localDate(e); d.setDate(d.getDate() + 1)) {
    const day = d.getDay();
    if (day !== 0 && day !== 6) n++;
  }
  return n;
}

function weekLabel(s, e) {
  const sd = localDate(s), ed = localDate(e);
  const sm = MONTHS_SHORT[sd.getMonth()], em_ = MONTHS_SHORT[ed.getMonth()];
  if (sd.getMonth() === ed.getMonth())
    return `${sm} ${sd.getDate()}–${ed.getDate()}, ${ed.getFullYear()}`;
  return `${sm} ${sd.getDate()} – ${em_} ${ed.getDate()}, ${ed.getFullYear()}`;
}

const wdays = workingDays(startDate, endDate);
const label = weekLabel(startDate, endDate);

// ── Process member data ────────────────────────────────────────────────────────
function getMember(name) {
  const d   = (rawData.members || {})[name] || {};
  const cfg = (config.members  || {})[name] || {};
  const cal = d.calendar   || {};
  return {
    name,
    role:       cfg.role || 'Engineer',
    cal: {
      total_meeting_hours: cal.total_meeting_hours ?? 0,
      available_hours:     cal.available_hours     ?? wdays * 8,
      meeting_pct:         cal.meeting_pct         ?? 0,
      avg_hrs_per_day:     cal.avg_hrs_per_day     ?? 0,
      ooo_days:            cal.ooo_days            ?? 0,
    },
    prs:    {
      opened:           (d.prs?.opened           || []),
      updated:          (d.prs?.updated          || []),
      reviews_given:    (d.prs?.reviews_given    || []),
      commits_pushed:   (d.prs?.commits_pushed   ?? 0),
      prs_merged:       (d.prs?.prs_merged       ?? (d.prs?.opened || []).filter(p => p.status === 'Merged').length),
      comments_received:(d.prs?.comments_received ?? 0),
      source:           (d.prs?.source           || 'unknown'),
    },
    jira:   d.jira       || { assigned_total: 0, closed_this_week: 0, points_this_week: 0, active: [], closed_tickets: [] },
    slack:  d.slack      || { total_messages: 0, per_channel: [], active_window: '—' },
    conf:   d.confluence || { created: 0, updated: 0, commented: 0, pages: [] },
    oncall: d.on_call    || { is_on_call: null, source: 'unknown' },
    partial_absences: d.partial_absences || [],
    highlights: d.highlights || [],
    focus:      d.focus      || '',
    standup:    d.standup    || [],
  };
}

const memberList = members.map(getMember);

// Per-person chart colors (stable across renders)
const PALETTE = ['#3B82F6','#8B5CF6','#10B981','#F59E0B','#EF4444','#06B6D4','#EC4899','#84CC16'];
memberList.forEach((m, i) => { m._color = PALETTE[i % PALETTE.length]; });

// Parse "20+" (or any count value) to a number for arithmetic/charting.
// Display values are kept as-is; only use this for math.
const numCount = (v) => parseInt(v) || 0;

// ── Team totals ────────────────────────────────────────────────────────────────
const sum = (fn) => memberList.reduce((s, m) => s + (fn(m) || 0), 0);
// Parse slack message counts — "20+" is treated as 20 (numeric floor)
const parseSlack = (v) => parseInt(String(v)) || 0;
const slackCapped = memberList.some(m => String(m.slack.total_messages).includes('+'));

const totals = {
  meetingHrs:   +(sum(m => m.cal.total_meeting_hours)).toFixed(1),
  avgMtgPct:    Math.round(sum(m => m.cal.meeting_pct) / memberList.length),
  prsOpened:    sum(m => m.prs.opened.length),
  prsUpdated:   sum(m => m.prs.updated.length),
  prsMerged:    sum(m => m.prs.prs_merged),
  reviewsGiven: sum(m => m.prs.reviews_given.length),
  commitsPushed: sum(m => m.prs.commits_pushed),
  commentsRec:  sum(m => m.prs.comments_received),
  jiraAssigned: sum(m => m.jira.assigned_total),
  jiraClosed:   sum(m => m.jira.closed_this_week),
  jiraPoints:   sum(m => m.jira.points_this_week ?? 0),
  slackMsgs:    sum(m => numCount(m.slack.total_messages)),
  oooDays:      sum(m => m.cal.ooo_days),
  partialAbsences: sum(m => m.partial_absences.length),
  onCall:       memberList.filter(m => m.oncall.is_on_call === true).map(m => m.name.split(' ')[0]),
};

// ── Helpers ────────────────────────────────────────────────────────────────────
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

function statusBadge(status) {
  const map = { merged: 'badge-merged', open: 'badge-open', closed: 'badge-closed',
                done: 'badge-done', 'in progress': 'badge-inprog', 'in review': 'badge-review',
                created: 'badge-created', updated: 'badge-updated', commented: 'badge-commented' };
  const cls = map[(status || '').toLowerCase()] || 'badge-neutral';
  return `<span class="badge ${cls}">${esc(status)}</span>`;
}

// ── Table generators ───────────────────────────────────────────────────────────
function prTable(prs) {
  if (!prs.length) return '<p class="empty">No PRs this week</p>';
  return `<table class="dt"><thead><tr>
    <th>#</th><th>Title</th><th>Repo</th><th>Date</th><th>Status</th>
  </tr></thead><tbody>${prs.map(p => `<tr>
    <td class="mono">#${esc(p.num)}</td>
    <td>${esc(p.title)}</td>
    <td class="mono sm">${esc(p.repo)}</td>
    <td class="nw">${esc(p.date)}</td>
    <td>${statusBadge(p.status)}</td>
  </tr>`).join('')}</tbody></table>`;
}

function reviewTable(reviews) {
  if (!reviews.length) return '<p class="empty">No reviews this week</p>';
  return `<table class="dt"><thead><tr>
    <th>PR #</th><th>Title</th><th>Repo</th>
  </tr></thead><tbody>${reviews.map(r => `<tr>
    <td class="mono">#${esc(r.pr)}</td>
    <td>${esc(r.title)}</td>
    <td class="mono sm">${esc(r.repo)}</td>
  </tr>`).join('')}</tbody></table>`;
}

function jiraTable(tickets, label) {
  if (!tickets.length) return `<p class="empty">No ${label} tickets</p>`;
  const showPts = tickets.some(t => t.points != null);
  return `<table class="dt"><thead><tr>
    <th>Key</th><th>Summary</th><th>Status</th>${showPts ? '<th class="ta-r">Pts</th>' : ''}
  </tr></thead><tbody>${tickets.map(t => `<tr>
    <td class="mono nw"><a href="${esc(t.url)}" target="_blank">${esc(t.key)}</a></td>
    <td>${esc(t.summary)}</td>
    <td>${statusBadge(t.status)}</td>
    ${showPts ? `<td class="ta-r nw">${t.points != null ? t.points : '—'}</td>` : ''}
  </tr>`).join('')}</tbody></table>`;
}

function channelTable(channels) {
  if (!channels.length) return '<p class="empty">No Slack data this week</p>';
  const sorted = [...channels].sort((a,b) => numCount(b.count) - numCount(a.count));
  return `<table class="dt"><thead><tr><th>Channel</th><th>Messages</th></tr></thead>
  <tbody>${sorted.map(c => `<tr>
    <td class="mono">${esc(c.channel)}${c.summary ? `<br><span style="font-family:sans-serif;font-size:0.78em;font-weight:normal;color:#666;">${esc(c.summary)}</span>` : ''}</td><td>${c.count}</td>
  </tr>`).join('')}</tbody></table>`;
}

function standupSection(days) {
  if (!days || days.length === 0) return '<p class="empty">No standup entries for this period</p>';
  return days.map(d => `
    <div class="su-day">
      <div class="su-date">${esc(d.date)}</div>
      <ul class="su-list">${d.bullets.map(b => `<li>${esc(b)}</li>`).join('')}</ul>
    </div>`).join('');
}

function confluenceTable(pages) {
  if (!pages.length) return '<p class="empty">No Confluence activity this week</p>';
  return `<table class="dt"><thead><tr><th>Page</th><th>Action</th><th>Date</th></tr></thead>
  <tbody>${pages.map(p => `<tr>
    <td>${esc(p.title)}</td><td>${statusBadge(p.action)}</td><td class="nw">${esc(p.date)}</td>
  </tr>`).join('')}</tbody></table>`;
}

// ── Per-member card HTML ────────────────────────────────────────────────────────
function memberCard(m) {
  const onCallBadge = m.oncall.is_on_call === true
    ? '<span class="badge badge-oncall">🔔 On-Call</span>'
    : m.oncall.is_on_call === null ? '<span class="badge badge-neutral">On-Call: ?</span>' : '';
  const oooBadge = m.cal.ooo_days > 0
    ? `<span class="badge badge-ooo">OOO ${m.cal.ooo_days}d</span>` : '';
  const absenceBadge = m.partial_absences.length > 0
    ? `<span class="badge badge-absence">⚠️ ${m.partial_absences.length} partial${m.partial_absences.length > 1 ? '' : ''}</span>` : '';

  const highlights = m.highlights.length
    ? `<ul class="hl-list">${m.highlights.map(h => `<li>${esc(h)}</li>`).join('')}</ul>`
    : '<p class="empty">No highlights recorded</p>';

  return `<div class="mc" id="mc-${esc(m.name.replace(/\s+/g,'-').toLowerCase())}">
  <div class="mc-head" style="border-left:4px solid ${m._color}">
    <div class="mc-identity">
      <div class="avatar" style="background:${m._color}">${initials(m.name)}</div>
      <div>
        <div class="mc-name">${esc(m.name)}</div>
        <div class="mc-role">${esc(m.role)}</div>
      </div>
      <div class="mc-badges">${onCallBadge}${oooBadge}${absenceBadge}</div>
    </div>
    <div class="mc-stats">
      <div class="mcs"><span class="mcs-v" style="color:${mtgColor(m.cal.meeting_pct)}">${m.cal.meeting_pct}%</span><span class="mcs-l">in meetings</span></div>
      <div class="mcs"><span class="mcs-v">${m.cal.total_meeting_hours.toFixed(1)}h</span><span class="mcs-l">meeting hrs</span></div>
      <div class="mcs"><span class="mcs-v">${m.prs.opened.length}</span><span class="mcs-l">PRs opened</span></div>
      <div class="mcs"><span class="mcs-v">${m.prs.updated.length}</span><span class="mcs-l">PRs updated</span></div>
      <div class="mcs"><span class="mcs-v">${m.prs.prs_merged}</span><span class="mcs-l">PRs merged</span></div>
      <div class="mcs"><span class="mcs-v">${m.prs.reviews_given.length}</span><span class="mcs-l">approved</span></div>
      <div class="mcs"><span class="mcs-v">${m.prs.commits_pushed}</span><span class="mcs-l">commits</span></div>
      <div class="mcs"><span class="mcs-v">${m.jira.closed_this_week}</span><span class="mcs-l">Jira closed</span></div>
      <div class="mcs"><span class="mcs-v">${m.jira.points_this_week ?? 0}</span><span class="mcs-l">pts closed</span></div>
      <div class="mcs"><span class="mcs-v">${m.jira.assigned_total}</span><span class="mcs-l">Jira active</span></div>
      <div class="mcs"><span class="mcs-v">${m.slack.total_messages}</span><span class="mcs-l">Slack msgs</span></div>
    </div>
  </div>
  <div class="mc-body">
    <div class="sec-block">
      <div class="sec-title">Highlights &amp; Focus</div>
      ${highlights}
      ${m.focus ? `<p class="focus-line">🎯 ${esc(m.focus)}</p>` : ''}
    </div>

    <details class="ds" open>
      <summary class="ds-sum">Standups
        <span class="ds-cnt">${m.standup.length} day(s) captured</span>
      </summary>
      <div class="ds-body su-wrap">${standupSection(m.standup)}</div>
    </details>

    <details class="ds" open>
      <summary class="ds-sum">GitHub PRs
        <span class="ds-cnt">${m.prs.opened.length} opened · ${m.prs.updated.length} updated · ${m.prs.prs_merged} merged · ${m.prs.reviews_given.length} approved · ${m.prs.commits_pushed} commits · ${m.prs.comments_received} comments</span>
      </summary>
      <div class="ds-body">
        <div class="gh-stats-row">
          <div class="gh-stat"><span class="gh-stat-v">${m.prs.opened.length}</span><span class="gh-stat-l">Opened</span></div>
          <div class="gh-stat"><span class="gh-stat-v">${m.prs.updated.length}</span><span class="gh-stat-l">Updated (WIP)</span></div>
          <div class="gh-stat"><span class="gh-stat-v">${m.prs.prs_merged}</span><span class="gh-stat-l">Merged</span></div>
          <div class="gh-stat"><span class="gh-stat-v">${m.prs.reviews_given.length}</span><span class="gh-stat-l">Approved</span></div>
          <div class="gh-stat"><span class="gh-stat-v">${m.prs.commits_pushed}</span><span class="gh-stat-l">Commits</span></div>
          <div class="gh-stat"><span class="gh-stat-v">${m.prs.comments_received}</span><span class="gh-stat-l">Comments Recv'd</span></div>
        </div>
        <div class="sub-lbl mt">PRs Opened</div>${prTable(m.prs.opened)}
        <div class="sub-lbl mt">PRs Updated (WIP — pushed to this week, opened prior)</div>${prTable(m.prs.updated)}
        <div class="sub-lbl mt">Reviews Given</div>${reviewTable(m.prs.reviews_given)}
        <div class="src-note">Source: ${esc(m.prs.source)}</div>
      </div>
    </details>

    <details class="ds" open>
      <summary class="ds-sum">Jira Tickets
        <span class="ds-cnt">${m.jira.assigned_total} active · ${m.jira.closed_this_week} closed (${m.jira.points_this_week ?? 0} pts)</span>
      </summary>
      <div class="ds-body">
        <div class="sub-lbl">In Progress / In Review</div>${jiraTable(m.jira.active, 'active')}
        <div class="sub-lbl mt">Closed This Week</div>${jiraTable(m.jira.closed_tickets, 'closed')}
      </div>
    </details>

    <details class="ds">
      <summary class="ds-sum">Slack
        <span class="ds-cnt">${m.slack.total_messages} messages · ${esc(m.slack.active_window)}</span>
      </summary>
      <div class="ds-body">
        ${channelTable(m.slack.per_channel)}
        <div class="src-note">Active window = earliest–latest message (proxy for time on Slack).</div>
      </div>
    </details>

    ${m.partial_absences.length > 0 ? `
    <details class="ds ds-absence" open>
      <summary class="ds-sum">⚠️ Partial Absences
        <span class="ds-cnt">${m.partial_absences.length} reported via #content_squad</span>
      </summary>
      <div class="ds-body">
        <table class="dt"><thead><tr><th>Date</th><th>Note</th></tr></thead>
        <tbody>${m.partial_absences.map(a => `<tr><td class="nw">${esc(a.date)}</td><td>${esc(a.note)}</td></tr>`).join('')}</tbody>
        </table>
        <div class="src-note">Detected from Slack messages in #content_squad. Does not affect capacity math.</div>
      </div>
    </details>` : ''}

    <details class="ds">
      <summary class="ds-sum">Confluence
        <span class="ds-cnt">${m.conf.created} created · ${m.conf.updated} updated · ${m.conf.commented} commented</span>
      </summary>
      <div class="ds-body">${confluenceTable(m.conf.pages)}</div>
    </details>

    <details class="ds">
      <summary class="ds-sum">Meetings
        <span class="ds-cnt">${m.cal.total_meeting_hours.toFixed(1)}h of ${m.cal.available_hours}h available · avg ${m.cal.avg_hrs_per_day.toFixed(1)}h/day</span>
      </summary>
      <div class="ds-body">
        <div class="mtg-grid">
          <div class="mg-item"><div class="mg-val">${m.cal.total_meeting_hours.toFixed(1)}h</div><div class="mg-lbl">Total hrs</div></div>
          <div class="mg-item"><div class="mg-val">${m.cal.available_hours}h</div><div class="mg-lbl">Available</div></div>
          <div class="mg-item"><div class="mg-val" style="color:${mtgColor(m.cal.meeting_pct)}">${m.cal.meeting_pct}%</div><div class="mg-lbl">Meeting load</div></div>
          <div class="mg-item"><div class="mg-val">${m.cal.avg_hrs_per_day.toFixed(1)}h</div><div class="mg-lbl">Avg / day</div></div>
          <div class="mg-item"><div class="mg-val">${m.cal.ooo_days}</div><div class="mg-lbl">OOO days</div></div>
        </div>
      </div>
    </details>
  </div>
</div>`;
}

// ── Chart data (serialised into HTML) ─────────────────────────────────────────
const chartPayload = {
  labels:      memberList.map(m => m.name.split(' ')[0]),
  fullLabels:  memberList.map(m => m.name),
  colors:      memberList.map(m => m._color),
  meetings: {
    hours:     memberList.map(m => +m.cal.total_meeting_hours.toFixed(1)),
    deepWork:  memberList.map(m => +(m.cal.available_hours - m.cal.total_meeting_hours).toFixed(1)),
    pct:       memberList.map(m => m.cal.meeting_pct),
    barColors: memberList.map(m => mtgColor(m.cal.meeting_pct)),
  },
  prs: {
    opened:  memberList.map(m => m.prs.opened.length),
    reviews: memberList.map(m => m.prs.reviews_given.length),
  },
  jira: {
    assigned: memberList.map(m => m.jira.assigned_total),
    closed:   memberList.map(m => m.jira.closed_this_week),
  },
  slack: {
    messages: memberList.map(m => numCount(m.slack.total_messages)),
    colors:   memberList.map(m => m._color),
  },
};

// ── Summary card HTML ─────────────────────────────────────────────────────────
function statCard(label, value, sub, colorClass) {
  return `<div class="sc ${colorClass || ''}">
    <div class="sc-val">${esc(value)}</div>
    <div class="sc-lbl">${esc(label)}</div>
    ${sub ? `<div class="sc-sub">${esc(sub)}</div>` : ''}
  </div>`;
}

const summaryCards = [
  statCard('Team Meeting Hours', `${totals.meetingHrs}h`, `avg ${totals.avgMtgPct}% of capacity`, totals.avgMtgPct >= 50 ? 'sc-warn' : 'sc-ok'),
  statCard('PRs Opened', totals.prsOpened, `+ ${totals.prsUpdated} updated (WIP)`),
  statCard('PRs Merged', totals.prsMerged, `${totals.commitsPushed} commits pushed`),
  statCard('PR Reviews Given', totals.reviewsGiven, `${totals.commentsRec} comments received`),
  statCard('Jira Closed', totals.jiraClosed, `${totals.jiraPoints} pts · ${totals.jiraAssigned} active`),
  statCard('Slack Messages', totals.slackMsgs, `across ${memberList.length} members`),
  statCard('OOO Days', totals.oooDays, totals.oooDays > 0 ? 'capacity reduced' : 'full team available'),
  statCard('Partial Absences', totals.partialAbsences, totals.partialAbsences > 0 ? 'sick / partial day — see member cards' : 'none reported', totals.partialAbsences > 1 ? 'sc-warn' : ''),
  statCard('On-Call', totals.onCall.length > 0 ? totals.onCall.join(', ') : 'None', totals.onCall.length > 0 ? 'this week' : ''),
].join('\n');

// ── Build the complete HTML document ──────────────────────────────────────────
function buildHTML() {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(squadName)} Metrics — Week of ${esc(label)}</title>
<style>
/* ── Reset & base ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #F1F5F9; color: #0F172A; font-size: 14px; line-height: 1.5; }
a { color: #3B82F6; text-decoration: none; }

/* ── Layout ── */
.page-wrap { max-width: 1200px; margin: 0 auto; padding: 24px 20px 48px; }

/* ── Header ── */
.hdr { background: #1E293B; color: #fff; padding: 20px 28px; border-radius: 12px;
       display: flex; align-items: center; justify-content: space-between;
       margin-bottom: 20px; gap: 12px; flex-wrap: wrap; }
.hdr-left { display: flex; flex-direction: column; gap: 3px; }
.hdr-squad { font-size: 22px; font-weight: 700; letter-spacing: -0.3px; }
.hdr-week  { font-size: 13px; color: #94A3B8; }
.hdr-em    { font-size: 12px; color: #64748B; margin-top: 2px; }
.btn-pdf { background: #3B82F6; color: #fff; border: none; padding: 9px 18px;
           border-radius: 7px; font-size: 13px; font-weight: 600; cursor: pointer;
           white-space: nowrap; transition: background .15s; }
.btn-pdf:hover { background: #2563EB; }

/* ── Summary cards ── */
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
         gap: 12px; margin-bottom: 24px; }
.sc { background: #fff; border-radius: 10px; padding: 16px;
      border: 1px solid #E2E8F0; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.sc-val  { font-size: 28px; font-weight: 700; color: #1E293B; line-height: 1; }
.sc-lbl  { font-size: 11px; font-weight: 600; color: #64748B; text-transform: uppercase;
           letter-spacing: .5px; margin-top: 4px; }
.sc-sub  { font-size: 11px; color: #94A3B8; margin-top: 3px; }
.sc-ok   { border-top: 3px solid #10B981; }
.sc-warn { border-top: 3px solid #F59E0B; }

/* ── Charts ── */
.charts-grid { display: grid; grid-template-columns: repeat(2, 1fr);
               gap: 16px; margin-bottom: 24px; }
.chart-card { background: #fff; border-radius: 10px; padding: 20px;
              border: 1px solid #E2E8F0; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
.chart-title { font-size: 13px; font-weight: 700; color: #334155;
               text-transform: uppercase; letter-spacing: .4px; margin-bottom: 16px; }
.chart-wrap { position: relative; height: 220px; }

/* ── Member cards ── */
.members-section { display: flex; flex-direction: column; gap: 16px; }
.mc { background: #fff; border-radius: 10px; border: 1px solid #E2E8F0;
      box-shadow: 0 1px 3px rgba(0,0,0,.06); overflow: hidden; }
.mc-head { padding: 16px 20px; background: #F8FAFC; border-bottom: 1px solid #E2E8F0; }
.mc-identity { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.avatar { width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center;
          justify-content: center; font-size: 13px; font-weight: 700; color: #fff;
          flex-shrink: 0; }
.mc-name  { font-size: 15px; font-weight: 700; color: #0F172A; }
.mc-role  { font-size: 12px; color: #64748B; }
.mc-badges { display: flex; gap: 6px; flex-wrap: wrap; margin-left: auto; }
.mc-stats { display: flex; flex-wrap: wrap; gap: 6px; }
.mcs { display: flex; flex-direction: column; align-items: center; min-width: 64px;
       background: #fff; border: 1px solid #E2E8F0; border-radius: 7px; padding: 8px 10px; }
.mcs-v { font-size: 18px; font-weight: 700; color: #1E293B; line-height: 1; }
.mcs-l { font-size: 10px; color: #94A3B8; text-transform: uppercase; letter-spacing: .3px;
          margin-top: 3px; white-space: nowrap; }

/* ── Member body ── */
.mc-body { padding: 16px 20px; display: flex; flex-direction: column; gap: 12px; }
.sec-block { }
.sec-title { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .5px;
             color: #64748B; margin-bottom: 8px; }

/* ── Details / collapsible ── */
.ds { border: 1px solid #E2E8F0; border-radius: 8px; overflow: hidden; }
.ds-sum { padding: 10px 14px; cursor: pointer; font-size: 13px; font-weight: 600;
          color: #334155; display: flex; align-items: center; gap: 8px; list-style: none;
          user-select: none; background: #F8FAFC; }
.ds-sum::-webkit-details-marker { display: none; }
.ds-sum::before { content: '▶'; font-size: 9px; color: #94A3B8; transition: transform .15s; }
details[open] > .ds-sum::before { transform: rotate(90deg); }
.ds-cnt { margin-left: auto; font-size: 11px; font-weight: 400; color: #94A3B8; }
.ds-body { padding: 14px; background: #fff; }
.sub-lbl { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .4px;
           color: #64748B; margin-bottom: 8px; }

/* ── Standups ── */
.su-wrap { display: flex; flex-direction: column; gap: 10px; }
.su-day { border-left: 3px solid #E2E8F0; padding-left: 12px; }
.su-date { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .4px;
           color: #64748B; margin-bottom: 4px; }
.su-list { margin: 0; padding-left: 16px; }
.su-list li { font-size: 13px; color: #334155; line-height: 1.55; margin-bottom: 2px; }
.mt { margin-top: 14px; }

/* ── Tables ── */
.dt { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.dt th { text-align: left; padding: 6px 10px; background: #F1F5F9; font-size: 11px;
         font-weight: 700; text-transform: uppercase; letter-spacing: .3px; color: #475569;
         border-bottom: 1px solid #E2E8F0; }
.dt td { padding: 7px 10px; border-bottom: 1px solid #F1F5F9; color: #334155; }
.dt tr:last-child td { border-bottom: none; }
.dt tr:hover td { background: #F8FAFC; }
.mono { font-family: 'SFMono-Regular', Consolas, monospace; }
.sm   { font-size: 11px; }
.nw   { white-space: nowrap; }
.empty { color: #94A3B8; font-size: 12.5px; padding: 4px 0; }

/* ── Badges ── */
.badge { display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 999px;
         font-size: 11px; font-weight: 600; }
.badge-open     { background: #EFF6FF; color: #2563EB; }
.badge-merged   { background: #EDE9FE; color: #7C3AED; }
.badge-closed   { background: #FEF2F2; color: #DC2626; }
.badge-done     { background: #ECFDF5; color: #059669; }
.badge-inprog   { background: #EFF6FF; color: #2563EB; }
.badge-review   { background: #FFF7ED; color: #C2410C; }
.badge-created  { background: #ECFDF5; color: #059669; }
.badge-updated  { background: #EFF6FF; color: #2563EB; }
.badge-commented{ background: #FFF7ED; color: #C2410C; }
.badge-oncall   { background: #FEF9C3; color: #854D0E; }
.badge-ooo      { background: #F1F5F9; color: #475569; }
.badge-absence  { background: #FEF3C7; color: #92400E; }
.ta-r           { text-align: right; font-variant-numeric: tabular-nums; }
.ds-absence > summary { color: #92400E; }
.badge-neutral  { background: #F1F5F9; color: #64748B; }

/* ── Highlights & focus ── */
.hl-list { padding-left: 18px; display: flex; flex-direction: column; gap: 4px; }
.hl-list li { font-size: 13px; color: #334155; }
.focus-line { font-size: 12.5px; color: #475569; margin-top: 8px;
              padding: 8px 12px; background: #F0FDF4; border-radius: 6px;
              border-left: 3px solid #10B981; }

/* ── Meeting grid ── */
.mtg-grid { display: flex; gap: 10px; flex-wrap: wrap; }
.mg-item  { background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 7px;
            padding: 10px 14px; min-width: 80px; text-align: center; }
.mg-val   { font-size: 20px; font-weight: 700; color: #1E293B; }
.mg-lbl   { font-size: 10px; color: #94A3B8; text-transform: uppercase; letter-spacing: .3px;
            margin-top: 2px; }

/* ── GitHub stats row (per-person mini summary) ── */
.gh-stats-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
.gh-stat { background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px;
           padding: 10px 16px; text-align: center; min-width: 90px; flex: 1; }
.gh-stat-v { display: block; font-size: 22px; font-weight: 700; color: #1E293B; }
.gh-stat-l { display: block; font-size: 10px; font-weight: 600; text-transform: uppercase;
             letter-spacing: .4px; color: #64748B; margin-top: 2px; }

/* ── Source note ── */
.src-note { font-size: 11px; color: #94A3B8; margin-top: 8px; font-style: italic; }

/* ── Footer ── */
.footer { text-align: center; font-size: 11px; color: #94A3B8; margin-top: 32px; }

/* ── Print / PDF ── */
@media print {
  @page { size: A4; margin: 15mm 12mm; }
  body { background: #fff; font-size: 12px; }
  .page-wrap { max-width: 100%; padding: 0; }
  .btn-pdf { display: none !important; }
  .hdr { background: #1E293B !important; -webkit-print-color-adjust: exact;
         print-color-adjust: exact; border-radius: 0; margin: 0 0 16px; }
  .chart-wrap { height: 180px; }
  .charts-grid { grid-template-columns: repeat(2, 1fr); gap: 12px; }
  .mc { break-inside: avoid; page-break-inside: avoid; }
  .ds-body { display: block !important; }
  details { open: true; }
}
</style>
</head>
<body>
<div class="page-wrap">

  <!-- Header -->
  <div class="hdr">
    <div class="hdr-left">
      <div class="hdr-squad">${esc(squadName)} — Weekly Metrics</div>
      <div class="hdr-week">Week of ${esc(label)}</div>
      <div class="hdr-em">${esc(emName)}</div>
    </div>
    <button class="btn-pdf" onclick="window.print()">⬇ Export PDF</button>
  </div>

  <!-- Summary cards -->
  <div class="cards">
    ${summaryCards}
  </div>

  <!-- Charts -->
  <div class="charts-grid">
    <div class="chart-card">
      <div class="chart-title">📅 Meeting Load</div>
      <div class="chart-wrap"><canvas id="chartMeetings"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">🔀 GitHub Activity</div>
      <div class="chart-wrap"><canvas id="chartPRs"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">🎯 Jira Velocity</div>
      <div class="chart-wrap"><canvas id="chartJira"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">💬 Slack Messages</div>
      <div class="chart-wrap"><canvas id="chartSlack"></canvas></div>
    </div>
  </div>

  <!-- Per-person sections -->
  <div class="members-section">
    ${memberList.map(memberCard).join('\n\n')}
  </div>

  <div class="footer">
    Generated ${new Date().toLocaleString()} · ${esc(squadName)} Team Metrics · ${esc(emName)}
  </div>
</div>

${chartJsScript()}
<script>
const D = ${JSON.stringify(chartPayload)};

Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
Chart.defaults.font.size   = 12;
Chart.defaults.color       = '#64748B';

const GRID = { color: '#F1F5F9', drawBorder: false };
const TICK = { color: '#94A3B8' };

// ── Chart 1: Meeting Load (stacked bar: meetings + deep work) ─────────────────
new Chart(document.getElementById('chartMeetings'), {
  type: 'bar',
  data: {
    labels: D.labels,
    datasets: [
      {
        label: 'Meeting Hrs',
        data:  D.meetings.hours,
        backgroundColor: D.meetings.barColors,
        borderRadius: 4,
        borderSkipped: false,
      },
      {
        label: 'Deep Work Hrs',
        data:  D.meetings.deepWork,
        backgroundColor: '#E2E8F0',
        borderRadius: 4,
        borderSkipped: false,
      },
    ],
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: 'bottom', labels: { boxWidth: 10, padding: 10 } },
      tooltip: {
        callbacks: {
          afterBody(ctx) {
            const i = ctx[0].dataIndex;
            return [\`Meeting load: \${D.meetings.pct[i]}%\`];
          }
        }
      },
    },
    scales: {
      x: { stacked: true, grid: GRID, ticks: TICK },
      y: {
        stacked: true,
        grid: GRID, ticks: TICK,
        title: { display: true, text: 'Hours', color: '#94A3B8', font: { size: 11 } },
      },
    },
  },
});

// ── Chart 2: GitHub PRs opened vs reviews given ───────────────────────────────
new Chart(document.getElementById('chartPRs'), {
  type: 'bar',
  data: {
    labels: D.labels,
    datasets: [
      { label: 'PRs Opened',    data: D.prs.opened,  backgroundColor: '#3B82F6', borderRadius: 4 },
      { label: 'Reviews Given', data: D.prs.reviews, backgroundColor: '#10B981', borderRadius: 4 },
    ],
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, padding: 10 } } },
    scales: {
      x: { grid: GRID, ticks: TICK },
      y: { grid: GRID, ticks: { ...TICK, stepSize: 1 },
           title: { display: true, text: 'Count', color: '#94A3B8', font: { size: 11 } } },
    },
  },
});

// ── Chart 3: Jira assigned vs closed ─────────────────────────────────────────
new Chart(document.getElementById('chartJira'), {
  type: 'bar',
  data: {
    labels: D.labels,
    datasets: [
      { label: 'Active / Assigned', data: D.jira.assigned, backgroundColor: '#F59E0B', borderRadius: 4 },
      { label: 'Closed This Week',  data: D.jira.closed,   backgroundColor: '#10B981', borderRadius: 4 },
    ],
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, padding: 10 } } },
    scales: {
      x: { grid: GRID, ticks: TICK },
      y: { grid: GRID, ticks: { ...TICK, stepSize: 1 },
           title: { display: true, text: 'Tickets', color: '#94A3B8', font: { size: 11 } } },
    },
  },
});

// ── Chart 4: Slack messages (horizontal bar, sorted high→low) ─────────────────
const slackOrder = D.labels
  .map((l, i) => ({ l, v: D.slack.messages[i], c: D.colors[i] }))
  .sort((a, b) => b.v - a.v);
new Chart(document.getElementById('chartSlack'), {
  type: 'bar',
  data: {
    labels: slackOrder.map(x => x.l),
    datasets: [{
      label: 'Messages',
      data:  slackOrder.map(x => x.v),
      backgroundColor: slackOrder.map(x => x.c),
      borderRadius: 4,
    }],
  },
  options: {
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { grid: GRID, ticks: { ...TICK, stepSize: 5 },
           title: { display: true, text: 'Messages', color: '#94A3B8', font: { size: 11 } } },
      y: { grid: { display: false }, ticks: TICK },
    },
  },
});
</script>
</body>
</html>`;
}

// ── Load Chart.js (local install preferred; CDN fallback) ─────────────────────
function chartJsScript() {
  const localPath = path.join(__dirname, 'node_modules/chart.js/dist/chart.umd.min.js');
  try {
    const src = fs.readFileSync(localPath, 'utf8');
    return `<script>${src}</script>`;
  } catch (_) {
    return `<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>`;
  }
}

// ── Write output ──────────────────────────────────────────────────────────────
fs.mkdirSync(outDir, { recursive: true });
const fileName = `${squadSlug}_Metrics_Week_${startDate}_to_${endDate}.html`;
const outPath  = path.join(outDir, fileName);
fs.writeFileSync(outPath, buildHTML(), 'utf8');

// ── Archive raw data for later use by generate_summary_report.js ──────────────
// Each week's data is saved as metrics_archive/metrics_<start>_to_<end>.json
// so the summary report can aggregate trends across multiple weeks.
const archiveDir  = path.join(outDir, 'metrics_archive');
fs.mkdirSync(archiveDir, { recursive: true });
const archiveData = { _week: { start: startDate, end: endDate }, ...rawData };
const archivePath = path.join(archiveDir, `metrics_${startDate}_to_${endDate}.json`);
fs.writeFileSync(archivePath, JSON.stringify(archiveData, null, 2), 'utf8');

console.log(`\n✅  Report written to: ${outPath}`);
console.log(`   Data archived to:   ${archivePath}`);
console.log(`   Open in any browser — click "Export PDF" to save as PDF.\n`);
