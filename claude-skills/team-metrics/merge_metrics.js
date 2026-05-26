#!/usr/bin/env node
/**
 * merge_metrics.js
 *
 * Combines per-source files into the final metrics_data.json and (on a
 * fully-successful merge) deletes the per-source files.
 *
 * Each data source owns a file named metrics_data.<source>.json in the same
 * directory as the merged target. Expected sources:
 *
 *   - metrics_data.calendar.json   (members[name].calendar)
 *   - metrics_data.atlassian.json  (members[name].jira, .confluence)
 *   - metrics_data.github.json     (members[name].prs)
 *   - metrics_data.pagerduty.json  (members[name].on_call)
 *   - metrics_data.slack.json      (members[name].slack, optionally
 *                                   .partial_absences, .weekend_activity)
 *
 * Validation (all required for a "complete and successful" merge):
 *   - All five source files exist and parse as JSON
 *   - Each source has matching week.start / week.end
 *   - Every member listed in team_config.json appears in every source file
 *
 * On success → write target, delete the five source files.
 * On any failure → write whatever could be merged, print a clear list of
 * what's missing, and leave the source files in place for inspection /
 * re-run.
 *
 * ── USAGE ────────────────────────────────────────────────────────────────────
 *
 *   node merge_metrics.js \
 *     --config  /path/to/team_config.json \
 *     --target  /path/to/metrics_data.json
 *
 *   # optional override for source directory (defaults to dir of --target)
 *   node merge_metrics.js ... --source-dir /path/to/sources
 *
 *   # skip cleanup even on a fully-successful merge (useful for debugging)
 *   node merge_metrics.js ... --no-cleanup
 */

const fs   = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const arg  = (flag) => { const i = args.indexOf(flag); return i !== -1 ? args[i + 1] : null; };
const flag = (name) => args.includes(name);
const die  = (msg)  => { console.error('\nERROR:', msg, '\n'); process.exit(1); };

const configPath = arg('--config') || die('--config <path> is required');
const targetPath = arg('--target') || die('--target <path> is required');
const sourceDir  = arg('--source-dir') || path.dirname(targetPath);
const noCleanup  = flag('--no-cleanup');

let config;
try { config = JSON.parse(fs.readFileSync(configPath, 'utf8')); }
catch (e) { die(`Could not read config at ${configPath}: ${e.message}`); }

const expectedMembers = Object.keys(config.members || {});
if (expectedMembers.length === 0) die('No members found in team_config.json');

// Source spec: which fields each source contributes per member.
const SOURCES = [
  { name: 'calendar',  fields: ['calendar'] },
  { name: 'atlassian', fields: ['jira', 'confluence'] },
  { name: 'github',    fields: ['prs'] },
  { name: 'pagerduty', fields: ['on_call'] },
  { name: 'slack',     fields: ['slack', 'partial_absences', 'weekend_activity'] },
];

console.log('\n━━ Merge Metrics ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
console.log(`Target     : ${targetPath}`);
console.log(`Source dir : ${sourceDir}`);
console.log(`Members    : ${expectedMembers.length}`);
console.log('───────────────────────────────────────────────────────────────');

// ── Load every available source ─────────────────────────────────────────────
const loaded   = {};   // source name → parsed JSON
const problems = [];   // list of { source, problem } describing why merge isn't complete

for (const src of SOURCES) {
  const srcPath = path.join(sourceDir, `metrics_data.${src.name}.json`);
  if (!fs.existsSync(srcPath)) {
    problems.push({ source: src.name, problem: `source file missing (${srcPath})` });
    continue;
  }
  try {
    loaded[src.name] = JSON.parse(fs.readFileSync(srcPath, 'utf8'));
    console.log(`  ✓ ${src.name.padEnd(10)} loaded from ${path.basename(srcPath)}`);
  } catch (e) {
    problems.push({ source: src.name, problem: `failed to parse: ${e.message}` });
  }
}

// ── Validate week consistency ───────────────────────────────────────────────
let canonicalWeek = null;
for (const [name, data] of Object.entries(loaded)) {
  const wk = data.week || {};
  if (!wk.start || !wk.end) {
    problems.push({ source: name, problem: 'missing week.start / week.end' });
    continue;
  }
  if (!canonicalWeek) {
    canonicalWeek = { start: wk.start, end: wk.end };
  } else if (wk.start !== canonicalWeek.start || wk.end !== canonicalWeek.end) {
    problems.push({
      source: name,
      problem: `week mismatch: ${wk.start}…${wk.end} vs canonical ${canonicalWeek.start}…${canonicalWeek.end}`,
    });
  }
}

// ── Validate every configured member appears in every loaded source ─────────
for (const [name, data] of Object.entries(loaded)) {
  const got = new Set(Object.keys(data.members || {}));
  const missing = expectedMembers.filter(m => !got.has(m));
  if (missing.length) {
    problems.push({ source: name, problem: `missing members: ${missing.join(', ')}` });
  }
}

// ── Build merged output from whatever loaded successfully ───────────────────
const merged = {
  week: canonicalWeek || { start: null, end: null },
  members: {},
};
for (const m of expectedMembers) merged.members[m] = {};

for (const src of SOURCES) {
  const data = loaded[src.name];
  if (!data) continue;
  for (const m of expectedMembers) {
    const slice = (data.members || {})[m];
    if (!slice) continue;
    for (const field of src.fields) {
      if (slice[field] !== undefined) merged.members[m][field] = slice[field];
    }
  }
}

// ── Write merged target ─────────────────────────────────────────────────────
fs.mkdirSync(path.dirname(targetPath), { recursive: true });
fs.writeFileSync(targetPath, JSON.stringify(merged, null, 2), 'utf8');

// ── Report and cleanup ──────────────────────────────────────────────────────
if (problems.length === 0) {
  console.log(`\n✅  Merge complete: ${targetPath}`);
  if (noCleanup) {
    console.log('   (--no-cleanup set, leaving source files in place)');
  } else {
    console.log('   Cleaning up source files…');
    for (const src of SOURCES) {
      const srcPath = path.join(sourceDir, `metrics_data.${src.name}.json`);
      try {
        fs.unlinkSync(srcPath);
        console.log(`     deleted ${path.basename(srcPath)}`);
      } catch (e) {
        console.warn(`     ⚠️  could not delete ${path.basename(srcPath)}: ${e.message}`);
      }
    }
  }
  console.log('');
  process.exit(0);
}

// Incomplete or failed validation → leave source files in place.
console.warn('\n⚠️  Merge incomplete. Source files left in place. Issues:');
for (const p of problems) {
  console.warn(`     [${p.source}] ${p.problem}`);
}
console.warn(`\n   Partial merge written to ${targetPath}.`);
console.warn(`   Fix the issues above, re-run the relevant fetcher(s), then re-run merge_metrics.js.\n`);
process.exit(1);
