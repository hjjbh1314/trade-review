# iFinD enrichment (optional)

Trade Review uses [iFinD MCP](https://10jqka.com.cn/) as an **optional**
natural-language enrichment layer for A-share snapshots. Without it, the app
falls back to a locally-composed summary built from akshare numbers — you do
not need iFinD to use the app.

## When you'd want this

iFinD adds a richer Chinese-language paragraph the AI coach can quote from
when reviewing your A-share trade. If you don't have an iFinD subscription,
skip this file entirely.

## Configuration

Pick one of the two:

**A. Environment variable (recommended)** — add to `.env`:

```bash
IFIND_AUTH_TOKEN="your-ifind-mcp-token"
```

**B. Config file** — create `ifind_mcp_config.json` in the repo root:

```json
{ "auth_token": "your-ifind-mcp-token" }
```

`IFIND_AUTH_TOKEN` takes precedence if both exist.

## Optional knobs

| Var | Default | Effect |
|---|---|---|
| `IFIND_VERIFY_SSL` | `false` | Verify TLS on calls to the iFinD MCP endpoint |
| `IFIND_TIMEOUT_SECONDS` | `30` | Per-request timeout in seconds |

## Verify

```bash
./start.sh
# look for: "iFinD client ready" in the log
```

If iFinD is not configured the log line is silent — and `enrich_with_ifind_text`
returns None so the rest of the request flows normally.

## Security

iFinD tokens are tied to a paid subscription. Never commit your `.env` or
`ifind_mcp_config.json` (both are already gitignored). If you accidentally
expose a token, rotate it in the iFinD console immediately.
