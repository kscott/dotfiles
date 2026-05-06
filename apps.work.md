# Manual App Installs — Work Mac

Apps that can't be installed via Homebrew. Review and install these after running install.sh.

## Direct Download

- iTerm2 — install from Ibotta Self-Service app

## Claude Code Plugins

Run after `install.sh` and `gh auth login`:

```
claude plugin add marketplace anthropics/claude-plugins-official
claude plugin add marketplace ibotta/claude-plugins
claude plugin install slack@claude-plugins-official
claude plugin install swift-lsp@claude-plugins-official
claude plugin install pagerduty-api@ibotta
claude plugin install google-workspace@ibotta
claude plugin install cli-skills@ibotta
claude plugin install jira-advisor@ibotta
claude plugin install atlassian-api@ibotta
claude plugin install jira-breakdown@ibotta
```

Then re-auth each plugin that requires it (Atlassian, Google, Slack).

## System Preferences / One-time setup

- Sign in to iCloud (for session log sync)
- System Settings → Keyboard → Key Repeat: fastest, Delay: shortest
