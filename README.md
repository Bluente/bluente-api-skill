# Bluente Translate API — Agent Skill

An [Agent Skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) that teaches coding agents (Claude Code, Codex, Cursor and others) how to integrate with **Bluente's document-translation API** correctly: upload, wait for processing, start the translation, poll or use a webhook, and download the result — plus error codes, translation options, glossaries and InDesign (IDML) translation.

Full API documentation: https://www.bluente.com/docs

## What's inside

```
bluente-translate-api/
├── SKILL.md                      # Core flow and the gotchas (loaded when the skill triggers)
├── references/
│   ├── endpoints.md              # Every endpoint, parameters, response shapes
│   ├── errors.md                 # Error codes, task statuses, retry rules
│   ├── options.md                # Bilingual, scanned/OCR, table layout enhancement, download conversion
│   ├── file-types-and-idml.md    # Supported files and IDML rules
│   ├── webhooks.md               # Webhook payload and safe handling
│   └── glossary.md               # Custom glossary upload/list/update/delete
└── examples/
    ├── translate.sh              # bash + curl + jq
    ├── translate.py              # Python + requests
    └── translate.ts              # TypeScript, Node.js 18+ (no dependencies)
```

## Install

### Claude Code

Copy the skill folder into your personal skills directory (all projects):

```bash
git clone https://github.com/Bluente/bluente-api-skill.git
mkdir -p ~/.claude/skills
cp -r bluente-api-skill/bluente-translate-api ~/.claude/skills/
```

or into one project (shared with everyone who works on that repo):

```bash
mkdir -p .claude/skills
cp -r bluente-api-skill/bluente-translate-api .claude/skills/
```

Claude Code picks it up automatically and uses it when you work with the Bluente API.

### Other agents

The skill is plain Markdown plus example scripts, so any agent can use it:

- **Agents that support the Agent Skills format** — copy `bluente-translate-api/` into that agent's skills directory (see its documentation).
- **Agents with project rules or instruction files** (for example `AGENTS.md` or editor rule files) — copy the folder into your repo and add a line such as: *"When working with the Bluente API, read `bluente-translate-api/SKILL.md` and follow it."*
- **Anything else** — paste `SKILL.md` into the conversation, and point the agent at the `references/` file it needs.

## Using the examples

All examples read the API key from the `BLUENTE_API_KEY` environment variable. Create a key at https://translate.bluente.com/apikeys.

```bash
export BLUENTE_API_KEY=sk-...

./bluente-translate-api/examples/translate.sh contract.docx en fr ./out
python3 bluente-translate-api/examples/translate.py contract.docx en fr ./out
npx tsx bluente-translate-api/examples/translate.ts contract.docx en fr ./out
```

> Running an example starts a real translation and **uses credits** on the account that owns the key.

> Creating a new API key **expires that user's previous keys.** Use a separate Bluente user per environment or integration.

## License

MIT — see [LICENSE](LICENSE).
