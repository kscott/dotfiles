#!/usr/bin/env node
'use strict';

/**
 * generate_md_report.js
 *
 * Generates a Markdown weekly team metrics report from metrics_data.json.
 * No npm dependencies — uses only Node.js built-ins.
 *
 * Usage:
 *   node generate_md_report.js \
 *     --members "Name One,Name Two"   (or ALL) \
 *     --start   2026-03-16 \
 *     --end     2026-03-20 \
 *     --data    /path/to/metrics_data.json \
 *     --config  /path/to/team_config.json \
 *     --out     /path/to/output/
 */

const fs   = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const arg  = (flag) => { const i = args.indexOf(flag); return i !== -1 ? args[i + 1] : null; };
const die  = (msg)  => { console.error('\nERROR:', msg, '\n'); process.exit(1); };

const membersArg = arg('--members') || die('--members required');
const startDate  = arg('--start')   || die('--start required');
const endDate    = arg('--end')     || die('--end required');
const dataPath   = arg('--data')    || die('--data required');
const configPath = arg('--config')  || die('--config required');
const outDir     = arg('--out')     || die('--out required');

let config, rawData;
try { config  = JSON.parse(fs.readFileSync(configPath,  'utf8')); }
catch (e) { die(`Cannot read config: ${e.message}`); }
try { rawData = JSON.parse(fs.readFileSync(dataPath, 'utf8')); }
catch (e) { die(`Cannot read data: ${e.message}`); }

const squadName    = config.squad_name    || 'Squad';
const emName       = config.em_name       || 'Engineering Manager';
const atlassianUrl = config.atlassian_base_url || 'https://your-org.atlassian.net';
const squadSlug    = squadName.replace(/\s+/g, '_').toUpperCase();

const allCfgMembers = Object.keys(config.members || {});
const members = membersArg.trim().toUpperCase() === 'ALL'
  ? allCfgMembers
  : membersArg.split(',').map(n => n.trim()).filter(Boolean);

for (const m of members) {
  if (!config.members[m]) die(`Member "${m}" not found in team_config.json`);
}

// ── Date formatting ────────────────────────────────────────────────────────────
const MONTHS_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const MONTHS_LONG  = ['January','February','March','April','May','June',
                      'July','August','September','October','November','December'];

function parseDate(s) { const [y,m,d] = s.split('-').map(Number); return new Date(y, m-1, d); }
function fmtShort(s)  { const d = parseDate(s); return `${MONTHS_SHORT[d.getMonth()]} ${d.getDate()}`; }
function fmtLong(s)   { const d = parseDate(s); return `${MONTHS_LONG[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`; }

const startFmt = fmtShort(startDate);
const endFmt   = fmtShort(endDate);
const startLong = fmtLong(startDate);

// ── Helpers ────────────────────────────────────────────────────────────────────
function count(n) { return (typeof n === 'string' || n > 0) ? n : 0; }

function memberSection(name) {
  const d   = (rawData.members || {})[name] || {};
  const cfg = config.members[name] || {};
  const role = cfg.role || '';

  const cal  = d.calendar  || {};
  const prs  = d.prs       || {};
  const jira = d.jira      || {};
  const slk  = d.slack     || {};
  const conf = d.confluence || {};
  const oc   = d.on_call   || {};

  const lines = [];

  lines.push(`## ${name}`);
  if (role) lines.push(`*${role}*`);
  lines.push('');

  // Focus
  if (d.focus) {
    lines.push(`**Focus:** ${d.focus}`);
    lines.push('');
  }

  // Highlights
  if (d.highlights && d.highlights.length) {
    lines.push('**Highlights**');
    for (const h of d.highlights) lines.push(`- ${h}`);
    lines.push('');
  }

  // GitHub PRs
  const opened  = prs.opened  || [];
  const reviews = prs.reviews_given || [];
  if (opened.length || reviews.length) {
    lines.push('**GitHub**');
    if (opened.length) {
      lines.push(`- PRs opened: ${opened.length}`);
      for (const pr of opened) {
        lines.push(`  - [${pr.repo}#${pr.num}](https://github.com/${pr.repo}/pull/${pr.num}) ${pr.title} *(${pr.status}, ${pr.date})*`);
      }
    } else {
      lines.push('- PRs opened: 0');
    }
    lines.push(`- Reviews given: ${reviews.length}`);
    for (const r of reviews) {
      lines.push(`  - [${r.repo}#${r.pr}](https://github.com/${r.repo}/pull/${r.pr}) ${r.title} *(${r.date})*`);
    }
    lines.push('');
  }

  // Jira
  const active  = jira.active  || [];
  const closed  = jira.closed_tickets || [];
  lines.push('**Jira**');
  lines.push(`- Assigned: ${jira.assigned_total || 0}  |  Closed this week: ${jira.closed_this_week || 0}`);
  if (closed.length) {
    lines.push('- Closed:');
    for (const t of closed) lines.push(`  - [${t.key}](${atlassianUrl}/browse/${t.key}) ${t.summary}`);
  }
  if (active.length) {
    lines.push('- Active:');
    for (const t of active) lines.push(`  - [${t.key}](${atlassianUrl}/browse/${t.key}) ${t.summary} — *${t.status}*`);
  }
  lines.push('');

  // Slack
  const totalMsg = slk.total_messages;
  if (totalMsg !== undefined) {
    lines.push('**Slack**');
    lines.push(`- Messages: ${count(totalMsg)}`);
    const channels = (slk.per_channel || []).filter(c => c.count && c.count !== 0);
    for (const c of channels) {
      lines.push(`  - ${c.channel}: ${count(c.count)}`);
    }
    if (slk._note) lines.push(`  - *${slk._note}*`);
    lines.push('');
  }

  // Calendar
  if (cal.total_meeting_hours && cal.total_meeting_hours > 0) {
    lines.push('**Meetings**');
    lines.push(`- ${cal.total_meeting_hours}h in meetings (${cal.meeting_pct}% of ${cal.available_hours}h available)`);
    if (cal.ooo_days > 0) lines.push(`- OOO: ${cal.ooo_days} day(s)`);
    lines.push('');
  }

  return lines.join('\n');
}

// ── Build document ─────────────────────────────────────────────────────────────
const sections = [];

sections.push(`# ${squadName} Squad — Weekly Metrics`);
sections.push(`**Week of ${startFmt} – ${endFmt}**  |  ${emName}`);
sections.push('');
sections.push('---');
sections.push('');

// Team summary table
const tableRows = members.map(name => {
  const d    = (rawData.members || {})[name] || {};
  const prs  = d.prs  || {};
  const jira = d.jira || {};
  const slk  = d.slack || {};
  const prCount  = (prs.opened || []).length;
  const revCount = (prs.reviews_given || []).length;
  const closed   = jira.closed_this_week || 0;
  const active   = jira.assigned_total   || 0;
  const msgs     = count(slk.total_messages !== undefined ? slk.total_messages : '—');
  return `| ${name} | ${prCount} | ${revCount} | ${closed} | ${active} | ${msgs} |`;
});

sections.push('## Team Summary');
sections.push('');
sections.push('| Name | PRs | Reviews | Closed | Active Jira | Slack Msgs |');
sections.push('|---|---|---|---|---|---|');
sections.push(...tableRows);
sections.push('');
sections.push('---');
sections.push('');

// Per-member sections
for (const name of members) {
  sections.push(memberSection(name));
  sections.push('---');
  sections.push('');
}

const md = sections.join('\n');

// ── Write output ──────────────────────────────────────────────────────────────
const filename = `${squadSlug}_Metrics_Week_${startDate}_to_${endDate}.md`;
const outPath  = path.join(outDir, filename);
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(outPath, md, 'utf8');

// Also write to metrics_archive/
const archiveDir  = path.join(path.dirname(dataPath.startsWith('/') ? dataPath : path.join(process.cwd(), dataPath)), '..', 'metrics_archive');
const resolvedArchive = path.resolve(path.dirname(configPath), 'metrics_archive');
const archivePath = path.join(resolvedArchive, `metrics_${startDate}_to_${endDate}.md`);
try {
  fs.mkdirSync(resolvedArchive, { recursive: true });
  fs.writeFileSync(archivePath, md, 'utf8');
} catch (e) { /* non-fatal */ }

console.log(`✅  Markdown report: ${filename}`);
console.log(`   Archived to:     metrics_archive/metrics_${startDate}_to_${endDate}.md`);
