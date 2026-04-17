#!/usr/bin/env node
'use strict';

/**
 * parse_standup.js
 *
 * Parses an Obsidian standup markdown file and extracts per-person bullet
 * summaries for a given date range. Merges results into metrics_data.json.
 *
 * Handles the free-form formats found in ENBL Standup 2026.md:
 *   - Erin             (name on own line, sub-bullets follow with indentation)
 *   Erin -             (name + dash, content on same line)
 *   - Erin - content   (bullet + name + dash + content)
 *   Emily. -           (name with trailing period)
 *   Erin               (bare name, indented content follows)
 *
 * Usage:
 *   node parse_standup.js \
 *     --config  /path/to/team_config.json \
 *     --file    /path/to/standup.md \
 *     --members "Name One,Name Two"  (or "ALL") \
 *     --start   2026-03-09 \
 *     --end     2026-03-13 \
 *     --out     /path/to/metrics_data.json
 */

const fs   = require('fs');
const path = require('path');

// ── CLI parsing ───────────────────────────────────────────────────────────────
const args = process.argv.slice(2);
const arg  = (flag) => { const i = args.indexOf(flag); return i !== -1 ? args[i + 1] : null; };
const die  = (msg)  => { console.error('\nERROR:', msg, '\n'); process.exit(1); };

const configPath  = arg('--config')  || die('--config <path> is required');
const standupFile = arg('--file')    || die('--file <path> is required');
const membersArg  = arg('--members') || die('--members "Name,Name" or "ALL" is required');
const startDate   = arg('--start')   || die('--start YYYY-MM-DD is required');
const endDate     = arg('--end')     || die('--end YYYY-MM-DD is required');
const outPath     = arg('--out')     || die('--out <path> is required');

// ── Load config ───────────────────────────────────────────────────────────────
let config;
try { config = JSON.parse(fs.readFileSync(configPath, 'utf8')); }
catch (e) { die(`Could not read config: ${e.message}`); }

const allMembers = Object.keys(config.members || {});
const members = membersArg.trim().toUpperCase() === 'ALL'
  ? allMembers
  : membersArg.split(',').map(n => n.trim()).filter(Boolean);

// ── Load standup file ─────────────────────────────────────────────────────────
let content;
try { content = fs.readFileSync(standupFile, 'utf8'); }
catch (e) { die(`Could not read standup file: ${e.message}`); }

// ── Date helpers ──────────────────────────────────────────────────────────────
const rangeStart = new Date(startDate + 'T00:00:00');
const rangeEnd   = new Date(endDate   + 'T23:59:59');

function parseStandupDate(str) {
  // Matches MM/DD or MM/DD/YY or MM/DD/YYYY at start of trimmed line
  const m = str.trim().match(/^(\d{1,2})\/(\d{1,2})(?:\/(\d{2,4}))?$/);
  if (!m) return null;
  const month = parseInt(m[1]) - 1;
  const day   = parseInt(m[2]);
  const year  = m[3] ? (m[3].length === 2 ? 2000 + parseInt(m[3]) : parseInt(m[3])) : 2026;
  const d = new Date(year, month, day);
  return isNaN(d.getTime()) ? null : d;
}

function fmtDate(d) {
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// ── Build first-name → full-name lookup ───────────────────────────────────────
// Also handle known nickname variants (e.g. "Nikkii", "AK" for Ananya)
const firstToFull = {};
for (const name of members) {
  const first = name.split(' ')[0].toLowerCase();
  firstToFull[first] = name;
}

function matchPersonName(text) {
  // Strip leading bullet characters
  const stripped = text.replace(/^[-*•]\s*/, '').trim();

  for (const [first, full] of Object.entries(firstToFull)) {
    // Pattern: FirstName optionally followed by period, then optional dash/colon/space
    const re = new RegExp(`^(${first})\\.?\\s*[-:]?(.*)$`, 'i');
    const m  = stripped.match(re);
    if (m) {
      return { name: full, rest: m[2].trim() };
    }
    // Also try full name match
    const fullRe = new RegExp(`^(${full.replace(/\s+/, '\\s+')})\\.?\\s*[-:]?(.*)$`, 'i');
    const fm = stripped.match(fullRe);
    if (fm) {
      return { name: full, rest: fm[2].trim() };
    }
  }
  return null;
}

// ── Split file into date-labelled sections ────────────────────────────────────
const lines = content.split('\n');
const sections = []; // { date, dateStr, startIdx, endIdx }

for (let i = 0; i < lines.length; i++) {
  const trimmed = lines[i].trim().replace(/^#+\s*/, '').replace(/^-+\s*/, '');
  const d = parseStandupDate(trimmed);
  if (d) {
    sections.push({ date: d, dateStr: fmtDate(d), startIdx: i + 1 });
  }
}
for (let i = 0; i < sections.length - 1; i++) {
  sections[i].endIdx = sections[i + 1].startIdx - 1;
}
if (sections.length > 0) {
  sections[sections.length - 1].endIdx = lines.length - 1;
}

const relevantSections = sections.filter(s => s.date >= rangeStart && s.date <= rangeEnd);

console.log(`\n━━ Standup Parser ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
console.log(`File    : ${standupFile}`);
console.log(`Range   : ${startDate} → ${endDate}`);
console.log(`Sections: ${relevantSections.length > 0
  ? relevantSections.map(s => s.dateStr).join(', ')
  : '(none found in range)'}`);

// ── Parse per-person bullets within a section ─────────────────────────────────
function parseSectionForPerson(sectionLines) {
  // Returns: { memberFullName -> [bullet string] }
  const result = {};
  let currentPerson = null;
  let currentBullets = [];

  function flush() {
    if (currentPerson && currentBullets.length > 0) {
      if (!result[currentPerson]) result[currentPerson] = [];
      result[currentPerson].push(...currentBullets);
    }
    currentPerson = null;
    currentBullets = [];
  }

  for (const rawLine of sectionLines) {
    const trimmed = rawLine.trim();
    if (!trimmed) continue;

    // Detect indentation level (tabs or spaces)
    const indentMatch = rawLine.match(/^(\s+)/);
    const indentLen   = indentMatch ? indentMatch[1].replace(/\t/g, '    ').length : 0;

    // Check if this line starts a new person
    const personMatch = matchPersonName(trimmed);

    if (personMatch) {
      flush();
      currentPerson = personMatch.name;
      // If there's content on the same line after the name, add it as first bullet
      const rest = personMatch.rest.replace(/^[-:]\s*/, '').trim();
      if (rest) currentBullets.push(rest);

    } else if (currentPerson) {
      // Continuation line — only include if it looks like a sub-bullet or detail
      // (indented, or starts with a bullet char)
      const isBullet   = /^[-*•]/.test(trimmed);
      const isIndented  = indentLen >= 1;

      if (isBullet || isIndented) {
        const cleaned = trimmed.replace(/^[-*•\t]+\s*/, '').trim();
        if (cleaned && !cleaned.match(/^[-=]{3,}$/)) {
          currentBullets.push(cleaned);
        }
      } else {
        // Non-indented, non-bullet, non-person line — treat as end of this person's block
        flush();
      }
    }
    // Lines before any person match (general meeting notes, Ananya updates, etc.) are skipped
  }
  flush();
  return result;
}

// ── Collect all standup entries per member ────────────────────────────────────
const standupByMember = {}; // fullName -> [{ date, bullets }]
for (const name of members) standupByMember[name] = [];

for (const section of relevantSections) {
  const sectionLines = lines.slice(section.startIdx, section.endIdx + 1);
  const entries      = parseSectionForPerson(sectionLines);

  for (const [memberName, bullets] of Object.entries(entries)) {
    if (standupByMember[memberName] !== undefined && bullets.length > 0) {
      standupByMember[memberName].push({
        date:    section.dateStr,
        bullets: bullets.map(b => b.trim()).filter(Boolean),
      });
    }
  }
}

// ── Report ────────────────────────────────────────────────────────────────────
console.log('\nEntries found:');
for (const [name, days] of Object.entries(standupByMember)) {
  const total = days.reduce((s, d) => s + d.bullets.length, 0);
  console.log(`  ${name}: ${days.length} day(s), ${total} bullet(s)`);
  if (process.env.DEBUG) {
    for (const d of days) {
      console.log(`    ${d.date}:`);
      for (const b of d.bullets) console.log(`      - ${b}`);
    }
  }
}

// ── Merge into metrics_data.json ──────────────────────────────────────────────
let metricsData = { members: {} };
if (fs.existsSync(outPath)) {
  try { metricsData = JSON.parse(fs.readFileSync(outPath, 'utf8')); }
  catch (e) { console.warn(`Warning: could not parse ${outPath}, starting fresh.`); }
}
if (!metricsData.members) metricsData.members = {};

for (const name of members) {
  if (!metricsData.members[name]) metricsData.members[name] = {};
  metricsData.members[name].standup = standupByMember[name];
}

fs.writeFileSync(outPath, JSON.stringify(metricsData, null, 2), 'utf8');
console.log(`\n✅  Standup data written to ${outPath}`);
console.log(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n`);
