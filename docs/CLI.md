# Command line

Hermes Life OS installs one command per job. The two you will use most:

| Command | What it does |
| --- | --- |
| `hermes-life-os` | The agent: `--mode onboard`, `morning`, `chat` and more. Needs a language model (Ollama, Anthropic, OpenAI or OpenRouter). |
| `hermes-life-os-tool` | Every tool from the shell. No language model and no API key. |

Both accept `--version` and `--profile <name>` (or `LIFE_OS_PROFILE`).

## hermes-life-os-tool

```bash
hermes-life-os-tool list                       # every tool with a one-line description
hermes-life-os-tool list --match library       # only tools that mention "library"
hermes-life-os-tool show add_task              # description, parameters, an example
hermes-life-os-tool run add_task text="Pay rent" due=friday priority=high minutes=45
hermes-life-os-tool run get_priorities
hermes-life-os-tool run plan_my_day apply=true
hermes-life-os-tool run export_calendar
```

### Passing arguments

- `key=value` pairs: a value is read as JSON when it parses (`minutes=45` is a number,
  `done=true` is a boolean, `tags='["home","urgent"]'` is a list) and as plain text otherwise
  (`due=friday`).
- `--json '{"text": "Pay rent"}'` passes a whole JSON object; `--json -` reads it from standard
  input. Pairs given as well override the same keys in the JSON.
- On Windows `cmd`, JSON needs double quotes escaped; the `key=value` form avoids that.

### Exit status

`0` when the tool ran (its own message, including "not added: ..." problems, is printed as
usual), `1` for an unknown tool or arguments that are not `key=value` or valid JSON.

### Scripting examples

```bash
# a morning shortcut: today's agenda and the plan, no AI involved
hermes-life-os-tool run get_today_agenda
hermes-life-os-tool run plan_my_day

# capture from anywhere (a shell alias or an automation app)
hermes-life-os-tool run add_to_inbox text="look into cello lessons"

# refresh a calendar file every night (cron)
0 23 * * * hermes-life-os-tool run export_calendar days=60
```

The full list of tools is in [TOOLS.md](TOOLS.md).
