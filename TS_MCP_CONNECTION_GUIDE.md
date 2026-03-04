# TypeScript Mobile MCP Connection Guide

This repository branch is TypeScript-first and follows the latest `mobile-mcp` structure.
Use this file as the single source of truth for AI agents when connecting MCP.

## 1) Quick MCP Registration (Recommended)

Use npm package directly:

```json
{
  "mcpServers": {
    "mobile-mcp": {
      "command": "npx",
      "args": ["-y", "@mobilenext/mobile-mcp@latest"]
    }
  }
}
```

## 2) Local Branch Registration (for this repository)

When you want to run this checked-out branch directly:

### Build first

```bash
npm install
npm run build
```

### MCP config (local binary)

```json
{
  "mcpServers": {
    "mobile-mcp-local": {
      "command": "node",
      "args": ["/Users/kimkitae/Documents/appium-mcp/lib/index.js", "--stdio"]
    }
  }
}
```

## 3) Agent CLI Examples

### Claude Code

```bash
claude mcp add mobile-mcp -- npx -y @mobilenext/mobile-mcp@latest
```

### Codex CLI

```bash
codex mcp add mobile-mcp npx "@mobilenext/mobile-mcp@latest"
```

### Cursor (command mode)
- Command: `npx`
- Args: `-y @mobilenext/mobile-mcp@latest`

## 4) AI Operation Rules (Performance/Cost)

- Prefer `mobile_list_elements_on_screen` first.
- Use screenshot tools only when element tree is insufficient.
- Avoid repeatedly calling both elements + screenshot in the same step unless strictly needed.
- For text fields, clear existing value before typing when supported.
- For drag/drop, prefer element-driven flows rather than fixed coordinates.

## 5) Runtime Prerequisites

- Node.js 18+
- Android Platform Tools (`adb`)
- Xcode command-line tools (for iOS/simulator workflows on macOS)
- WebDriverAgent / iOS tunnel setup when required by your environment

