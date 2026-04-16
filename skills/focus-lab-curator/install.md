# Installing the Focus Lab Curator

The curator is a plain-markdown skill. It runs in any capable coding agent.

## Claude Code

Symlink the skill into your Claude Code skills folder:

```bash
mkdir -p ~/.claude/skills
ln -sfn "$(pwd)/skills/focus-lab-curator" ~/.claude/skills/focus-lab-curator
```

Then, from inside a pack folder (one that contains `posts.json`):

```bash
cd ~/Downloads/focus-lab-pack-2026-04-16
claude
```

In the Claude prompt, invoke the skill:

```
/focus-lab-curator
```

or just say *"curate this feed"* — the skill's description will match.

## Cursor

Copy `SKILL.md` into your workspace rules:

```bash
mkdir -p .cursor/rules
cp skills/focus-lab-curator/SKILL.md .cursor/rules/focus-lab-curator.md
```

Then open the pack folder in Cursor and ask the agent to *"curate this feed using the Focus Lab Curator skill"*.

## Codex / OpenAI Agents

Copy `SKILL.md` into your agent's instructions file, or pass it with `--instructions`:

```bash
codex --instructions skills/focus-lab-curator/SKILL.md
```

## Any other agent

Paste the contents of `SKILL.md` into your agent's system prompt. The skill is plain markdown plus a JSON contract — any capable agent can follow it.

---

## Where `goals.md` lives

- **Pack-local (preferred):** the curator writes `./goals.md` in the pack folder when you first run it. That file is what gets zipped and AirDropped with the pack.
- **User-global (fallback):** if you accept when prompted, a copy is also saved to `~/.focuslab/goals.md`. Future packs pick this up automatically when a pack-local `goals.md` is absent.

You can edit `goals.md` by hand at any time. Re-running the skill will pick up your edits.

---

## Output

The skill always writes **one file**: `posts.filtered.json`, next to `posts.json` in the pack folder.

Re-zip the pack folder after filtering:

```bash
cd ~/Downloads
zip -r focus-lab-pack-2026-04-16-curated.zip focus-lab-pack-2026-04-16/
```

Then AirDrop the zip to your phone and import it in the Focus Lab Feed viewer.
