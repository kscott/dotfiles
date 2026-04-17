#!/usr/bin/env node
'use strict';

/**
 * fetch_github_metrics.js
 *
 * Fetches GitHub PR metrics for team members and writes only the "prs" section
 * of metrics_data.json (all other sections are left untouched).
 *
 * ── THREE MODES (tried in order) ─────────────────────────────────────────────
 *
 * 1. GH CLI MODE (primary — recommended for Ibotta)
 *    Uses the `gh` CLI authenticated to github.com/Ibotta.
 *    Requires: `gh auth login` has been run (once). No token in config needed.
 *    To set up: gh auth login   (one-time, or: gh auth login --hostname github.ibotta.com)
 *    Skipped if `gh` is not installed or not authenticated.
 *
 * 2. CANVAS MODE (fallback — reads the GitHub Activity bot canvas from Slack)
 *    a) From a local markdown file (recommended when running via Claude MCP):
 *         node fetch_github_metrics.js --canvas-content /tmp/canvas.md ...
 *    b) Directly from Slack API (requires a Slack user token):
 *         node fetch_github_metrics.js --canvas-id F0AM48B3GGH ...
 *
 * 2. GITHUB API MODE (fallback — only works for github.com public/org repos)
 *    Uses a Personal Access Token to search github.com. Need to do extra manual athorization for the SSO layer.
 *
 * ── USAGE ────────────────────────────────────────────────────────────────────
 *
 *   # Auto mode (gh CLI first, then canvas, then API)
 *   node fetch_github_metrics.js \
 *     --config  /path/to/team_config.json \
 *     --members "Name One,Name Two"  (or "ALL") \
 *     --start   2026-03-09 \
 *     --end     2026-03-13 \
 *     --out     /path/to/metrics_data.json
 *
 *   # Force canvas mode (skip gh CLI check)
 *   node fetch_github_metrics.js ... --canvas-content /tmp/canvas.md
 *
 *   # Force GitHub API mode (skip gh CLI and canvas)
 *   node fetch_github_metrics.js ... --no-gh-cli --no-canvas
 */

const https        = require('https');
const fs           = require('fs');
const path         = require('path');
const { execSync } = require('child_process');

// ── CLI parsing ───────────────────────────────────────────────────────────────
const args = process.argv.slice(2);
const arg  = (flag) => { const i = args.indexOf(flag); return i !== -1 ? args[i + 1] : null; };
const flag = (name) => args.includes(name);
const die  = (msg)  => { console.error('\nERROR:', msg, '\n'); process.exit(1); };

const configPath    = arg('--config')         || die('--config <path>  is required');
const membersArg    = arg('--members')        || die('--members "Name One,Name Two" or "ALL"  is required');
const startDate     = arg('--start')          || die('--start YYYY-MM-DD  is required');
const endDate       = arg('--end')            || die('--end YYYY-MM-DD  is required');
const outPath       = arg('--out')            || die('--out <path>  is required');
const canvasContent = arg('--canvas-content');
const canvasId      = arg('--canvas-id');
const slackTokenArg = arg('--slack-token');
const noGhCli       = flag('--no-gh-cli');
const noCanvas      = flag('--no-canvas');

// ── Load config ───────────────────────────────────────────────────────────────
let config;
try { config = JSON.parse(fs.readFileSync(configPath, 'utf8')); }
catch (e) { die(`Could not read config at ${configPath}: ${e.message}`); }

const allMembers = Object.keys(config.members || {});
const members = membersArg.trim().toUpperCase() === 'ALL'
  ? allMembers
  : membersArg.split(',').map(n => n.trim()).filter(Boolean);

for (const m of members) {
  if (!config.members[m])         die(`Member "${m}" not found in team_config.json`);
  if (!config.members[m].github)  die(`Member "${m}" has no "github" field in config`);
}

const githubOrg = config.github_org || 'Ibotta';

// ── gh CLI availability check ─────────────────────────────────────────────────
function isGhCliAuthenticated() {
  try {
    const out = execSync('gh auth status 2>&1', { encoding: 'utf8', timeout: 8000 });
    return out.includes('Logged in');
  } catch (e) {
    const combined = (e.stdout || '') + (e.stderr || '') + (e.message || '');
    return combined.includes('Logged in');
  }
}

// ── Determine mode ────────────────────────────────────────────────────────────
const effectiveCanvasId = canvasId || config.gh_metrics_canvas_id || null;
const slackToken = slackTokenArg || process.env.SLACK_TOKEN || config.slack_token || null;

const useGhCli      = !noGhCli && !canvasContent && isGhCliAuthenticated();
const useCanvasFile = !useGhCli && !noCanvas && !!canvasContent;
const useCanvasSlack= !useGhCli && !noCanvas && !canvasContent && !!effectiveCanvasId && !!slackToken;
const useGithubApi  = !useGhCli && !useCanvasFile && !useCanvasSlack;

// ── Helpers ───────────────────────────────────────────────────────────────────
function shortDate(isoStr) {
  if (!isoStr) return '';
  return new Date(isoStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function repoFromUrl(url) {
  return (url || '').replace('https://api.github.com/repos/', '');
}

// ── gh CLI mode ───────────────────────────────────────────────────────────────
function sleepSync(ms) {
  execSync(`sleep ${ms / 1000}`);
}

function ghExecJson(cmdArgs) {
  try {
    const out = execSync(`gh ${cmdArgs}`, { encoding: 'utf8', timeout: 30000 });
    return JSON.parse(out);
  } catch (e) {
    return null;
  }
}

function ghExecLines(cmdArgs) {
  // Returns array of parsed JSON lines (for --jq that emits one object per line)
  try {
    const out = execSync(`gh ${cmdArgs}`, { encoding: 'utf8', timeout: 30000 });
    return out.trim().split('\n').filter(Boolean).map(line => {
      try { return JSON.parse(line); } catch { return null; }
    }).filter(Boolean);
  } catch (e) {
    return [];
  }
}

function fetchMemberGhCli(displayName) {
  const handle = config.members[displayName].github;
  const dateRange = `${startDate}..${endDate}`;

  console.log(`\n  → ${displayName} (@${handle})`);

  // PRs created this week by this author
  const openedRaw = ghExecJson(
    `search prs --author=${handle} --owner=${githubOrg} ` +
    `--created "${dateRange}" ` +
    `--json number,title,state,url,repository,createdAt,commentsCount -L 50`
  ) || [];

  // PRs merged this week by this author (may include PRs created before this week)
  const mergedRaw = ghExecJson(
    `search prs --author=${handle} --owner=${githubOrg} ` +
    `--merged --merged-at "${dateRange}" ` +
    `--json number,title,url,repository -L 50`
  ) || [];

  const mergedNums = new Set(mergedRaw.map(p => String(p.number)));

  const opened = openedRaw.map(pr => ({
    num:    `#${pr.number}`,
    title:  pr.title,
    date:   shortDate(pr.createdAt),
    repo:   pr.repository?.nameWithOwner || '',
    status: mergedNums.has(String(pr.number)) ? 'Merged'
          : pr.state === 'MERGED'             ? 'Merged'
          : pr.state === 'CLOSED'             ? 'Closed'
          :                                     'Open',
    url:    pr.url,
  }));

  sleepSync(2000);

  // PRs updated this week (WIP carry-overs: authored by person, updated this week, created BEFORE this week)
  const updatedRaw = ghExecLines(
    `api -X GET "search/issues" ` +
    `-f q="type:pr author:${handle} org:${githubOrg} ` +
    `updated:${dateRange} created:<${startDate}" ` +
    `--jq '.items[] | {number,title,state,html_url,repository_url,updated_at}'`
  );

  const updated = updatedRaw.map(pr => ({
    num:    `#${pr.number}`,
    title:  pr.title,
    date:   shortDate(pr.updated_at),
    repo:   repoFromUrl(pr.repository_url),
    status: pr.state === 'closed' ? 'Closed' : 'Open',
    url:    pr.html_url,
  }));

  sleepSync(2000);

  // PRs reviewed by this person this week (updated during the range, not authored by them)
  const reviewsRaw = ghExecLines(
    `api -X GET "search/issues" ` +
    `-f q="type:pr reviewed-by:${handle} org:${githubOrg} ` +
    `updated:${dateRange} -author:${handle}" ` +
    `--jq '.items[] | {number,title,state,html_url,repository_url}'`
  );

  const reviews_given = reviewsRaw.map(pr => ({
    pr:    `#${pr.number}`,
    title: pr.title,
    date:  '',
    repo:  repoFromUrl(pr.repository_url),
    url:   pr.html_url,
  }));

  sleepSync(2000);

  // Commits pushed this week (via GitHub commit search API)
  const commitsResult = ghExecJson(
    `api -X GET "search/commits" ` +
    `-H "Accept: application/vnd.github.cloak-preview+json" ` +
    `-f q="author:${handle} org:${githubOrg} committer-date:${startDate}..${endDate}"`
  );
  const commits_pushed = commitsResult?.total_count || 0;

  // PRs merged this week (authored by this person)
  const prs_merged = [
    ...opened.filter(p => p.status === 'Merged'),
    ...updated.filter(p => p.status === 'Merged'),
  ].length;

  // Comments received = sum of comments on PRs opened this week
  const comments_received = openedRaw.reduce((sum, pr) => sum + (pr.commentsCount || 0), 0);

  console.log(`     PRs opened: ${opened.length}`);
  console.log(`     PRs updated (WIP): ${updated.length}`);
  console.log(`     PRs merged (this week): ${prs_merged}`);
  console.log(`     Reviews given: ${reviews_given.length}`);
  console.log(`     Commits pushed: ${commits_pushed}`);
  console.log(`     Comments received: ${comments_received}`);

  return { opened, updated, reviews_given, commits_pushed, prs_merged, comments_received, source: 'gh-cli' };
}

// ── Generic HTTPS GET helper ──────────────────────────────────────────────────
function httpsGet(hostname, urlPath, headers) {
  return new Promise((resolve, reject) => {
    const req = https.request({ hostname, path: urlPath, method: 'GET', headers }, res => {
      let body = '';
      res.on('data', c => body += c);
      res.on('end', () => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          try { resolve(JSON.parse(body)); }
          catch { resolve(body); }
        } else {
          const parsed = (() => { try { return JSON.parse(body); } catch { return {}; } })();
          reject(new Error(`HTTP ${res.statusCode} on ${urlPath}: ${parsed.message || body.slice(0, 200)}`));
        }
      });
    });
    req.on('error', reject);
    req.end();
  });
}

function downloadUrl(url, token) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const req = https.request({
      hostname: parsed.hostname,
      path:     parsed.pathname + parsed.search,
      method:   'GET',
      headers:  { 'Authorization': `Bearer ${token}`, 'User-Agent': 'team-metrics/1.0' },
    }, res => {
      if (res.statusCode === 301 || res.statusCode === 302) {
        return downloadUrl(res.headers.location, token).then(resolve).catch(reject);
      }
      let body = '';
      res.on('data', c => body += c);
      res.on('end', () => resolve(body));
    });
    req.on('error', reject);
    req.end();
  });
}

// ── Slack canvas fetcher ──────────────────────────────────────────────────────
async function fetchCanvasFromSlack(fileId, token) {
  console.log(`  Fetching canvas ${fileId} from Slack API…`);
  const info = await httpsGet('slack.com', `/api/files.info?file=${fileId}`, {
    'Authorization': `Bearer ${token}`,
    'User-Agent':    'team-metrics/1.0',
  });
  if (!info.ok) throw new Error(`Slack files.info error: ${info.error || JSON.stringify(info)}`);
  const file = info.file;
  const downloadLink = file.url_private_download || file.url_private;
  if (!downloadLink) throw new Error('Canvas file has no url_private — check token scopes (needs files:read)');
  const markdown = await downloadUrl(downloadLink, token);
  if (!markdown || typeof markdown !== 'string') throw new Error('Canvas download returned empty or non-text content');
  return markdown;
}

// ── Canvas markdown parser ────────────────────────────────────────────────────
function parseCanvasMarkdown(markdown, memberList, cfg) {
  const handleToName = {};
  for (const name of memberList) {
    const handle = cfg.members[name]?.github;
    if (handle) handleToName[handle.toLowerCase()] = name;
  }

  const results = {};
  const sectionSplit = markdown.split(/(?=^## )/m);

  for (const section of sectionSplit) {
    const headingMatch = section.match(/^## .+?—\s*`([^`]+)`/m);
    if (!headingMatch) continue;
    const handle = headingMatch[1].toLowerCase().trim();
    const displayName = handleToName[handle];
    if (!displayName) continue;

    const rows = {};
    const tableRowRe = /^\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|/gm;
    let m;
    const durationPRs = [];
    while ((m = tableRowRe.exec(section)) !== null) {
      const metric  = m[1].trim();
      const count   = m[2].trim();
      const details = m[3].trim();
      if (metric === 'Metric') continue;
      if (metric.startsWith('PR Duration')) {
        const prMatches = [...(m[0].matchAll(/https?:\/\/github\.com\/([^/]+\/[^/]+)\/pull\/(\d+)/g))];
        for (const pm of prMatches) durationPRs.push({ repo: pm[1], num: pm[2] });
      } else {
        rows[metric] = { count, details };
      }
    }

    const allPRsInSection = new Map();
    const urlRe = /https?:\/\/github\.com\/([^/]+\/[^/]+)\/pull\/(\d+)/g;
    let um;
    while ((um = urlRe.exec(section)) !== null) {
      const repo = um[1]; const num = um[2];
      if (!allPRsInSection.has(num)) allPRsInSection.set(num, { repo, num });
    }

    const mergedNums = new Set();
    const mergedDetails = (rows['PRs Merged/Closed']?.details || '') + ' ' + (rows['PRs Merged/Closed']?.count || '');
    for (const [, prNum] of mergedDetails.matchAll(/\/pull\/(\d+)/g)) mergedNums.add(prNum);

    const openedNums = new Set();
    const openedDetails = rows['PRs Opened']?.details || '';
    for (const [, prNum] of openedDetails.matchAll(/\/pull\/(\d+)/g)) openedNums.add(prNum);
    for (const { num: dNum } of durationPRs) openedNums.add(dNum);

    const openedCount = parseInt(rows['PRs Opened']?.count) || 0;

    const dateNearPR = (prNum) => {
      const re = new RegExp(`/pull/${prNum}[^\\n]*?\\(([A-Z][a-z]+ \\d+)\\)`);
      const dm = section.match(re);
      return dm ? dm[1] : null;
    };

    const opened = [];
    for (const num of openedNums) {
      const info = allPRsInSection.get(num);
      if (!info) continue;
      const status = mergedNums.has(num) ? 'Merged' : 'Open';
      const date   = dateNearPR(num);
      opened.push({ num: `#${num}`, title: `PR #${num}`, date: date || '', repo: info.repo, status });
    }

    const approvalsDetails = rows['Approvals']?.details || '';
    const approvalsCount   = parseInt(rows['Approvals']?.count) || 0;
    const reviews_given = [];
    for (const [, repo, num] of approvalsDetails.matchAll(/https?:\/\/github\.com\/([^/]+\/[^/]+)\/pull\/(\d+)/g)) {
      reviews_given.push({ pr: `#${num}`, title: `PR #${num}`, date: '', repo });
    }

    const comments_received = parseInt(rows['Comments']?.count) || 0;

    console.log(`     PRs opened: ${opened.length} (canvas count: ${openedCount})`);
    console.log(`     Reviews/approvals: ${reviews_given.length} (canvas count: ${approvalsCount})`);
    console.log(`     Comments received: ${comments_received}`);

    results[displayName] = { opened, updated: [], reviews_given, commits_pushed: 0, prs_merged: opened.filter(p => p.status === 'Merged').length, comments_received, source: 'slack-canvas' };
  }

  return results;
}

// ── GitHub API helpers (last-resort fallback) ──────────────────────────────────
const sleep = ms => new Promise(r => setTimeout(r, ms));
const RATE_DELAY_MS = 2500;

function githubGet(apiPath, token) {
  return httpsGet('api.github.com', apiPath, {
    'User-Agent':           'team-metrics-skill/1.0',
    'Authorization':        `Bearer ${token}`,
    'Accept':               'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
  });
}

function prStatus(item) {
  if (item.pull_request?.merged_at) return 'Merged';
  if (item.state === 'closed')       return 'Closed';
  return 'Open';
}

async function fetchMemberGithubApi(displayName, token) {
  const handle = config.members[displayName].github;
  console.log(`\n  → ${displayName} (@${handle})`);

  const openedQ = encodeURIComponent(`is:pr author:${handle} created:${startDate}..${endDate}`);
  let openedRaw;
  try {
    openedRaw = await githubGet(`/search/issues?q=${openedQ}&sort=created&order=desc&per_page=100`, token);
  } catch (e) {
    console.warn(`    ⚠️  Could not fetch opened PRs: ${e.message}`);
    openedRaw = { items: [] };
  }
  await sleep(RATE_DELAY_MS);

  const opened = (openedRaw.items || []).map(pr => ({
    num:    String(pr.number),
    title:  pr.title,
    date:   shortDate(pr.created_at),
    repo:   repoFromUrl(pr.repository_url),
    status: prStatus(pr),
  }));
  const comments_received = (openedRaw.items || []).reduce((sum, pr) => sum + (pr.comments || 0), 0);

  const reviewedQ = encodeURIComponent(`is:pr reviewed-by:${handle} updated:${startDate}..${endDate} -author:${handle}`);
  let reviewedRaw;
  try {
    reviewedRaw = await githubGet(`/search/issues?q=${reviewedQ}&sort=updated&order=desc&per_page=100`, token);
  } catch (e) {
    console.warn(`    ⚠️  Could not fetch reviewed PRs: ${e.message}`);
    reviewedRaw = { items: [] };
  }
  await sleep(RATE_DELAY_MS);

  const reviews_given = (reviewedRaw.items || []).map(pr => ({
    pr:    String(pr.number),
    title: pr.title,
    date:  shortDate(pr.updated_at),
    repo:  repoFromUrl(pr.repository_url),
  }));

  // PRs updated this week (WIP carry-overs: created before range, updated during range)
  const updatedQ = encodeURIComponent(`is:pr author:${handle} updated:${startDate}..${endDate} created:<${startDate}`);
  let updatedRaw;
  try {
    updatedRaw = await githubGet(`/search/issues?q=${updatedQ}&sort=updated&order=desc&per_page=100`, token);
  } catch (e) {
    console.warn(`    ⚠️  Could not fetch updated PRs: ${e.message}`);
    updatedRaw = { items: [] };
  }
  await sleep(RATE_DELAY_MS);

  const updated = (updatedRaw.items || []).map(pr => ({
    num:    `#${pr.number}`,
    title:  pr.title,
    date:   shortDate(pr.updated_at),
    repo:   repoFromUrl(pr.repository_url),
    status: prStatus(pr),
    url:    pr.html_url,
  }));

  // Commits pushed via search API
  let commits_pushed = 0;
  try {
    const commitSearch = await githubGet(
      `/search/commits?q=${encodeURIComponent(`author:${handle} org:${githubOrg} committer-date:${startDate}..${endDate}`)}`,
      token,
      { 'Accept': 'application/vnd.github.cloak-preview+json' }
    );
    commits_pushed = commitSearch?.total_count || 0;
  } catch (e) {
    console.warn(`    ⚠️  Could not fetch commit count: ${e.message}`);
  }
  await sleep(RATE_DELAY_MS);

  const prs_merged = [
    ...(openedRaw.items || []).filter(p => p.pull_request?.merged_at),
    ...(updatedRaw.items || []).filter(p => p.pull_request?.merged_at),
  ].length;

  console.log(`     PRs opened: ${opened.length}`);
  console.log(`     PRs updated (WIP): ${updated.length}`);
  console.log(`     PRs merged: ${prs_merged}`);
  console.log(`     PRs reviewed: ${reviews_given.length}`);
  console.log(`     Commits pushed: ${commits_pushed}`);
  console.log(`     Comments received: ${comments_received}`);

  return { opened, updated, reviews_given, commits_pushed, prs_merged, comments_received, source: 'github-api' };
}

// ── Main ──────────────────────────────────────────────────────────────────────
async function main() {
  const mode = useGhCli       ? `gh CLI (github.com/${githubOrg})`
             : useCanvasFile  ? 'Canvas (file)'
             : useCanvasSlack ? 'Canvas (Slack API)'
             :                  'GitHub API (fallback)';

  console.log(`\n━━ GitHub Metrics Fetch ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
  console.log(`Mode    : ${mode}`);
  console.log(`Org     : ${githubOrg}`);
  console.log(`Members : ${members.join(', ')}`);
  console.log(`Range   : ${startDate} → ${endDate}`);
  console.log(`Output  : ${outPath}`);
  console.log(`─────────────────────────────────────────────────────────────`);

  if (!useGhCli && !canvasContent) {
    console.warn('\n⚠️  gh CLI not available or not authenticated.');
    console.warn('   Run: gh auth login');
    console.warn('   This is the recommended way to get accurate PR data for Ibotta.\n');
  }

  // Load existing metrics_data.json
  let metricsData = { members: {} };
  if (fs.existsSync(outPath)) {
    try {
      metricsData = JSON.parse(fs.readFileSync(outPath, 'utf8'));
      console.log(`\nLoaded existing metrics_data.json (will merge prs section only).`);
    } catch (e) {
      console.warn(`\nWarning: could not parse ${outPath}, starting with empty data.`);
    }
  }
  if (!metricsData.members) metricsData.members = {};

  // ── GH CLI MODE (primary) ─────────────────────────────────────────────────
  if (useGhCli) {
    for (let i = 0; i < members.length; i++) {
      const name = members[i];
      if (!metricsData.members[name]) metricsData.members[name] = {};
      metricsData.members[name].prs = fetchMemberGhCli(name);
      if (i < members.length - 1) sleepSync(3000);
    }

  // ── CANVAS MODES (secondary) ──────────────────────────────────────────────
  } else if (useCanvasFile || useCanvasSlack) {
    let markdown;
    if (useCanvasFile) {
      console.log(`\nReading canvas content from file: ${canvasContent}`);
      try { markdown = fs.readFileSync(canvasContent, 'utf8'); }
      catch (e) { die(`Could not read canvas file ${canvasContent}: ${e.message}`); }
    } else {
      try { markdown = await fetchCanvasFromSlack(effectiveCanvasId, slackToken); }
      catch (e) { die(`Failed to fetch canvas from Slack: ${e.message}`); }
    }

    console.log(`\nParsing canvas markdown (${markdown.length} chars)…`);
    const canvasResults = parseCanvasMarkdown(markdown, members, config);

    let found = 0;
    for (const name of members) {
      console.log(`\n  → ${name} (@${config.members[name].github})`);
      if (canvasResults[name]) {
        found++;
        if (!metricsData.members[name]) metricsData.members[name] = {};
        metricsData.members[name].prs = canvasResults[name];
      } else {
        console.warn(`    ⚠️  Not found in canvas — skipping PR data for ${name}`);
        if (!metricsData.members[name]) metricsData.members[name] = {};
        metricsData.members[name].prs = {
          opened: [], reviews_given: [], comments_received: 0,
          source: 'slack-canvas', _note: 'Member not found in canvas this week',
        };
      }
    }

    if (found === 0) {
      console.warn('\n⚠️  No members matched in the canvas. Check that github handles in');
      console.warn('   team_config.json match the canvas (e.g. "witygass" not "Tyler Gassman").');
    }

  // ── GITHUB API MODE (last resort) ─────────────────────────────────────────
  } else {
    const token = config.github_token;
    if (!token || token.startsWith('<')) {
      die('No data source available.\n' +
          '  Best option : run `gh auth login` to use the gh CLI (works for github.com/Ibotta)\n' +
          '  Or          : set gh_metrics_canvas_id + slack_token in team_config.json\n' +
          '  Or          : set github_token in team_config.json (only works for public github.com repos)');
    }
    console.warn('\n⚠️  Running in GitHub REST API fallback mode.');
    console.warn('   Note: this only works for public github.com repos.');
    console.warn('   Run `gh auth login` for accurate Ibotta data.\n');

    for (const name of members) {
      if (!metricsData.members[name]) metricsData.members[name] = {};
      metricsData.members[name].prs = await fetchMemberGithubApi(name, token);
    }
  }

  // Write back
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(metricsData, null, 2), 'utf8');
  console.log(`\n━━ Done ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
  console.log(`✅  GitHub metrics written to ${outPath}\n`);
}

main().catch(err => {
  console.error('\nFATAL:', err.message);
  process.exit(1);
});
