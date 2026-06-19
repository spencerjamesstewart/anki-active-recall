# Recall Box

A type-your-answer-before-reveal box for the Anki reviewer.

Recall Box injects a free-text answer box directly under the question. You type
your answer (or your reasoning), press **Cmd/Ctrl + Return** to flip the card,
and your typed answer is shown **directly above the real answer** — so you
self-check against what you actually committed to, instead of the
"yeah, I basically knew that" fluency illusion.

There is **no auto-grading or diffing**. That's deliberate: synonyms and phrasing
make text matching brittle, and self-grading is the correct active-recall loop.
You are the judge.

## Features

- Free-text answer box under the question, autofocused.
- **Cmd/Ctrl + Return** reveals the answer; your typed text appears above it.
- Multi-line answers: `Enter` / `Shift+Enter` insert a newline; only
  Cmd/Ctrl+Return submits.
- Reviewer shortcuts stay out of your way while typing — `Space`, `Enter`, and
  digits `1–4` go into the box and never reveal or grade the card. After reveal,
  grading shortcuts work normally.
- Styling matches a dark deck aesthetic (560px wide, Georgia, teal accent).
- Skips cards that already use `{{type:Field}}` so you never get two input boxes.

## Requirements

- Anki **23.10+**. Developed and tested on **25.09.x** (Qt6 / Chromium).
- Desktop only (Anki add-ons don't run on AnkiMobile / AnkiDroid).

## Installation

### From source (development)

Symlink the package into your Anki add-ons folder, then restart Anki:

```bash
# macOS
ln -s "$(pwd)/recall_box" \
  "$HOME/Library/Application Support/Anki2/addons21/recall_box"
```

Edit files in this repo and restart Anki to pick up changes. To uninstall,
remove the symlink (this does not touch the repo):

```bash
rm "$HOME/Library/Application Support/Anki2/addons21/recall_box"
```

### As an installable `.ankiaddon`

Build a package and install it via **Tools → Add-ons → Install from file…**
(zip the package *contents*, not the folder):

```bash
cd recall_box
zip -r ../recall_box.ankiaddon . -x '__pycache__/*' '*.pyc' 'meta.json'
cd ..
```

## Usage

1. Start reviewing. A text box appears under the question, ready for input.
2. Type your answer.
3. Press **Cmd/Ctrl + Return** to reveal. Your answer shows above the real one.
4. Grade as usual with `1–4` or `Space`.

*Optional:* press `Esc` to blur the box and restore normal `Space`-to-reveal.

## How it works

Recall Box lives **inside the reviewer card webview** (not a Qt dock), because
the box must sit in the card's own content flow.

- `gui_hooks.card_will_show` appends the textarea + key-capture JS on the
  question, and inserts the typed-answer block after Anki's `<hr id=answer>`
  separator on the answer.
- `gui_hooks.webview_did_receive_js_message` receives the typed text from JS and
  round-trips it through a Python module global, so it survives the
  question → answer re-render (webview JS state is lost on re-render). It then
  calls `mw.reviewer._showAnswer()`.

See [`docs/recall-box-addon-brief.md`](docs/recall-box-addon-brief.md) for the
full design rationale and acceptance criteria.

## Scope

**v1 (current):** front-side textarea, Cmd/Ctrl+Return reveal, typed answer shown
above the real answer, keyboard capture, dark styling.

**Not included (by design):** auto-grading / diffing, persisting answers across
sessions, per-deck enable/disable, a config UI, mobile.

## License

MIT — see [LICENSE](LICENSE).
