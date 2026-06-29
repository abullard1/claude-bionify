## Summary

<!-- What does this change, and why? -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Refactor / internal

## Checklist

- [ ] `pytest tests/` passes (coverage stays at 80%+)
- [ ] `ruff check plugins/claude-bionify/scripts tests assets` is clean
- [ ] `claude plugin validate ./plugins/claude-bionify --strict` passes
- [ ] If I changed a setting, `plugin.json` and `settings.py` stay in sync
- [ ] If I changed a theme, I ran `python assets/generate_themes.py`
- [ ] Docs updated if behavior changed
