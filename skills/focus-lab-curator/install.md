# Installing the Focus Lab Curator

The curator is a plain-markdown skill. It runs in any capable coding agent.

The desktop app sets this up for you automatically when you bootstrap a workspace — `<workspace>/skills/focus-lab-curator/` and a `.claude/skills/focus-lab-curator` symlink are both created. The notes below cover manual setups (other agents, hand-rolled workspaces).

## Claude Code

If your workspace was bootstrapped by the app, you're done. Otherwise:

```bash
mkdir -p ~/.claude/skills
ln -sfn "$(pwd)/skills/focus-lab-curator" ~/.claude/skills/focus-lab-curator
```

From the workspace root:

```bash
cd ~/Focus\ Lab\ Feed     # or wherever your workspace lives
claude
```

In the Claude prompt, invoke the skill:

```
/focus-lab-curator
```

or just say *"curate the latest feed"* — the skill's description will match.

## Cursor

Copy `SKILL.md` into your workspace rules:

```bash
mkdir -p .cursor/rules
cp skills/focus-lab-curator/SKILL.md .cursor/rules/focus-lab-curator.md
```

Then open the workspace folder in Cursor and ask the agent to *"curate the latest collection job using the Focus Lab Curator skill"*.

## Codex / OpenAI Agents

Copy `SKILL.md` into your agent's instructions file, or pass it with `--instructions`:

```bash
codex --instructions skills/focus-lab-curator/SKILL.md
```

## Any other agent

Paste the contents of `SKILL.md` into your agent's system prompt. The skill is plain markdown plus a JSON contract — any capable agent can follow it.

---

## Where `goals.md` lives

`<workspace>/goals.md` — one file at the workspace root, shared by every job. The curator reads it on every run, so edits take effect on the next curation.

If `goals.md` is missing or essentially empty, the skill runs a short interview (5 questions) and writes one for you. You can edit by hand at any time.

---

## Publishing to your phone (optional)

With publishing configured, every curation ends by uploading the feed to a
Cloudflare R2 bucket — so your phone scrolls a URL instead of importing zip packs.

One-time setup (~10 minutes):

1. Create a Cloudflare account and enable **R2** (asks for a credit card; the
   free tier is 10 GB storage with zero egress fees — nothing is charged under it).
2. Create a bucket (e.g. `focus-lab-feed`) and enable **public access** via its
   `r2.dev` subdomain (bucket → Settings → Public access). Note the
   `https://pub-….r2.dev` URL.
3. Create an R2 API token (**Object Read & Write**, scoped to that bucket).
4. Write `<workspace>/publish.env`:

```
R2_ENDPOINT=https://<account_id>.r2.cloudflarestorage.com
R2_BUCKET=focus-lab-feed
R2_ACCESS_KEY_ID=<access key id>
R2_SECRET_ACCESS_KEY=<secret access key>
PUBLIC_BASE_URL=https://pub-xxxxxxxx.r2.dev
# optional (defaults shown):
# MAX_VIDEO_MB=50
# DAILY_BUDGET_MB=500
# RETENTION_DAYS=14
```

That's all — the uploader talks to R2's S3 API with Python's standard library,
so there is nothing to install.

From then on the curator publishes automatically after each filter and reports
your feed URL: `PUBLIC_BASE_URL/index.html`. Bookmark it on your phone's home
screen.

How it stays inside the free tier: media uploads in score order until
`DAILY_BUDGET_MB` is spent; videos over `MAX_VIDEO_MB` (and all YouTube videos)
become tap-through links to the original post; days older than `RETENTION_DAYS`
are pruned. Worst case ≈ 500 MB × 14 days = 7 GB.

**Privacy note:** an `r2.dev` public bucket is reachable by anyone who has the
URL (it's unguessable, but it is public). For real access control, put the
bucket behind a custom domain and enable Cloudflare Access on it (free for
personal use). Keep `publish.env` out of git — it holds your R2 secret.

Preview without uploading:

```bash
python3 skills/focus-lab-curator/publish.py --dry-run
python3 -m http.server 8899 -d publish_preview   # then open :8899/index.html
```

---

## Output

The skill always writes **one file** per job:

```
<workspace>/data/<date>/<job_id>/posts.filtered.json
```

It contains every kept post (across all platforms in that job, ranked by score) plus a compact audit log of what was dropped and why. The Focus Lab Feed app's **AI Curation** tab picks it up automatically.
