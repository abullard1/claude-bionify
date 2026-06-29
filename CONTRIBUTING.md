# Contributing to claude-bionify

Thanks for your interest in improving claude-bionify. Issues and pull requests are welcome.

## Development setup

claude-bionify has no runtime dependencies. For development you need Python 3.10+ and the test tools:

```shell
git clone https://github.com/abullard1/claude-bionify.git
cd claude-bionify
python3 -m venv .venv
.venv/bin/pip install pytest pytest-cov ruff
```

Run the plugin against your working copy without installing it:

```shell
claude --plugin-dir ./plugins/claude-bionify
```

## Before you open a pull request

CI gates on these three checks, so run them locally first:

```shell
.venv/bin/python -m pytest tests/                                   # tests (80%+ coverage)
.venv/bin/ruff check plugins/claude-bionify/scripts tests assets    # lint
claude plugin validate ./plugins/claude-bionify --strict            # manifest
```

## Project layout

- `plugins/claude-bionify/scripts/` holds the plugin code:
  - `settings.py` is the single source of truth for every option.
  - `core.py` is the pure formatting logic (no I/O).
  - `bionify.py` is the MessageDisplay hook, `control.py` is the `/claude-bionify:set` CLI, and `overrides.py` is the shared override store.
- `tests/test_bionify.py` covers all of the above.
- `assets/` holds the README images and `generate_themes.py`.

## Common changes

**Adding or changing a setting.** Add a typed field to `Style` and one `Setting` row in `settings.py`, then mirror it in `plugin.json`'s `userConfig`. The `TestManifestConsistency` test fails if the two drift, so keep their defaults and bounds in sync.

**Changing a theme.** Edit the JSON in `plugins/claude-bionify/themes/`, then regenerate the gallery so CI stays green:

```shell
python assets/generate_themes.py
```

## Commit messages

Follow Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `ci:`.

## Code style

Keep functions small and the formatting core free of I/O. Comments should explain why, not restate what. `ruff` enforces the lint rules.
