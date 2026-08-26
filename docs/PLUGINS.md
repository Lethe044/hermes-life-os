# Writing a Hermes Life OS plugin

Hermes' tool set (`remember`, `log_sleep`, `detect_patterns`, ...) is not
closed - you can add your own tools without touching a single line of the
core codebase, and without maintaining a fork. Drop a Python file in a
folder, and Hermes picks it up on next start.

## Quick start

```bash
mkdir -p ~/.hermes/life-os/plugins
cp demo/plugins_examples/dice.py ~/.hermes/life-os/plugins/
python demo/demo_life_os.py --mode chat
# "roll a d20 for me"
```

`python demo/plugins.py` on its own lists every plugin Hermes currently
sees, the tools each one contributes, and any load warnings - run it any
time you want to sanity-check a new plugin before firing up the full CLI.

## The plugin contract

A plugin is a normal `.py` file that defines two things:

```python
TOOLS = [
    {"type": "function", "function": {
        "name": "my_tool",
        "description": "What it does, written for the LLM to read.",
        "parameters": {"type": "object", "properties": {
            "some_arg": {"type": "string"},
        }, "required": ["some_arg"]},
    }},
]

def dispatch(name, inp):
    if name == "my_tool":
        return f"Did the thing with {inp['some_arg']}"
    return None  # not one of ours - let Hermes keep looking
```

- `TOOLS` uses the exact same schema as `demo/tools.py`'s own `TOOLS` list
  (OpenAI function-calling format) - copy an existing entry as a template.
- `dispatch(name, inp)` is called for every tool call Hermes doesn't
  recognize as a built-in. Return a string result if you handle `name`,
  or `None` to let Hermes try the next plugin.
- Optional `PLUGIN_NAME = "my-plugin"` - shown in listings and in any
  error messages. Defaults to the filename without `.py`.

That's the whole API. No base class, no registration call, no imports
from `demo/` required (though your plugin *can* import `storage` to read
or write profile data - see `plugins_examples/screen_time.py`).

## Where plugins live

Default: `~/.hermes/life-os/plugins/*.py` - a sibling of your profile
data, so it isn't wiped by `--fresh` and isn't tied to any one profile.
Override the location with `LIFE_OS_PLUGINS_DIR` if you'd rather keep
plugins in, say, a version-controlled dotfiles repo:

```bash
export LIFE_OS_PLUGINS_DIR=~/dotfiles/hermes-plugins
```

Files starting with `_` are ignored (handy for a work-in-progress
`_scratch.py`, or a helper module a real plugin imports internally).

## Reading/writing your own data

Plugins can persist state exactly the way the built-in trackers do -
`plugins_examples/screen_time.py` is a complete example: it writes to
`storage.HERMES_DIR / "plugin_screen_time.json"`, which automatically
points at whichever profile is currently active (multi-user setups
included - see `docs/MULTI_USER.md`). Import `storage` *inside* your
functions rather than at module top-level if you want to always see the
currently-active profile rather than whatever was active when your
module was first imported.

## Calling other tools

Need to reuse existing logic (e.g. write to long-term memory from your
plugin)? Import directly from `storage` or `patterns`, the same modules
`demo/tools.py` itself uses:

```python
def dispatch(name, inp):
    if name == "log_and_remember":
        import storage
        storage.write_memory({"type": "note", "content": inp["text"]})
        return "Logged."
    return None
```

## Safety notes

- Plugins run with full Python privileges in this process, exactly like
  any script you'd run yourself. Only install plugins you wrote or trust
  - the same rule as `pip install`.
- A plugin that fails to import (syntax error, missing dependency,
  exception at import time) is skipped and reported; it never crashes
  the rest of Hermes.
- A plugin tool name that collides with a **built-in** tool name is
  dropped; built-ins always win, so a bad or malicious plugin can never
  shadow core functionality like `remember` or `log_sleep`.
- Two plugins defining the same tool name: the first one loaded
  (alphabetical by filename) wins, and the collision is reported so it's
  easy to notice.

## Sharing a plugin with others

A plugin is just one `.py` file - share it as a gist, a PR into
`demo/plugins_examples/`, or its own tiny repo people `curl`/copy into
their `plugins/` folder. There's no packaging step required, though
nothing stops you from publishing one on PyPI if you want auto-updates;
Hermes doesn't care where the file came from, only that it's in the
plugins directory.

If you think a plugin would be broadly useful, open a PR adding it to
`demo/plugins_examples/` - see `CONTRIBUTING.md`.
