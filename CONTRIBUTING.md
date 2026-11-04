# Contributing to Eyemarchy

Thanks for helping. Small, focused pull requests are the easiest to review.

## Develop

1. Fork the repository and install your fork as the plugin (remove the
   installed copy first with `omarchy plugin remove io.github.harold15000.eyemarchy`):

   ```bash
   omarchy plugin add https://github.com/<you>/eyemarchy --enable
   cd ~/.config/omarchy/plugins/io.github.harold15000.eyemarchy
   git switch -c my-change
   ```

2. Edit. Scripts in `scripts/` are read fresh every time they run. After
   changing a QML or JS file run `omarchy restart shell`: a running service
   plugin is not reloaded on save.
3. Watch the log for warnings: `journalctl --user -f | grep -i eyemarchy`.
4. `omarchy-shell eyemarchy demo on` fills the cards with sample data, and
   `omarchy-shell eyemarchy press Down` (or `Left`, `Return`, `Comma`…) drives the
   keyboard from a script. `omarchy-shell eyemarchy state` prints the internal state.

## Test

```bash
python3 -m unittest discover -s tests      # collectors, against fake /proc and /sys
node --test tests/*.mjs                    # settings, translations, demo data
omarchy plugin validate .                  # the manifest, as the shell checks it
```

Run them before opening a pull request.

## Screenshots

`.github/capture.sh` makes the README captures on a real Omarchy machine. It
switches themes on screen for about two minutes and restores your theme,
wallpaper and workspace at the end. You never need it to use the plugin.

## Layout

| File | |
|---|---|
| `Desktop.qml` | The service: state, settings, keyboard navigation, IPC and one window per screen |
| `ClockCard.qml`, `AgentsCard.qml`, `MediaCard.qml`, `SystemCard.qml` | The cards |
| `SettingsCard.qml` | The settings panel |
| `Settings.js` | Defaults and validation of every setting |
| `I18n.js` | Interface text |
| `Demo.js` | Sample data for `demo on` |
| `scripts/agents.py` | Finds the agents and their state |
| `scripts/stats.py` | CPU, memory, GPU, disks, fans, battery, network |
| `scripts/top.py` | Which apps use the most CPU or RAM |
| `scripts/act.py` | Focus a window, attach a session, close an app |

The scripts only use the Python standard library and print one JSON object.

## Add a language

Copy the `en` block in `I18n.js`, translate it, and add the code to
`LANGUAGES`. Keep the `%1` placeholders. The tests check that no key is missing.

## Add an agent

Add one line to `PROCESS_AGENTS` in `scripts/agents.py` (group id, label,
program names) and, if it can run over SSH, to `REMOTE_NAMES`. If the agent
writes a status file with a real "waiting for you" state, a dedicated reader
like `claude_code()` is even better. Add a test in `tests/test_agents.py`.

## Ground rules

- No network access and no new dependencies.
- Never read conversation content.
- Anything that closes or signals a process goes through `act.py` and its checks.
