# Build Brief — Anki "Active Recall" Add-on

*Type-your-answer-before-reveal box for the Anki reviewer. Hand-off spec for Claude Code.*

## One-liner

Inject a free-text answer box directly under the question in the reviewer. The user types their answer (or their reasoning), hits **Cmd/Ctrl + Return** to flip the card, and the reveal shows the user's typed answer **directly above the real answer**. No grading, no diffing — pure self-checked active recall.

## Why it's built this way

The benefit of writing an answer before revealing isn't the medium — it's that you're forced to commit to a **complete, externalized answer** before seeing the truth, which defeats the "yeah, I basically knew that" fluency illusion. So the design is **commit → reveal → self-compare**, with the human as judge. **Do not auto-grade or diff free text** — synonyms and phrasing make that brittle, and self-grading is the correct active-recall loop. (This is the software version of the existing write-it-down study habit.)

---

## Architecture — note: NOT a Qt dock

Unlike the existing **Ask** and **Medical Pronunciation Lookup** add-ons (persistent Qt docks alongside the card), this one lives **inside the reviewer card webview**, because the box must sit under the question text in the card's own flow. Inject via the card-render hook; round-trip the typed text to Python via a JS bridge command so it survives the question→answer re-render (webview JS state is lost on re-render).

Components:

1. **Python — `gui_hooks.card_will_show(text, card, kind)`**
   - `kind == "reviewQuestion"`: append the `<textarea>` + JS to the card HTML.
   - `kind == "reviewAnswer"`: prepend the stored typed-answer block above the answer.
2. **Python — `gui_hooks.webview_did_receive_js_message(handled, message, context)`**: receive the typed text + reveal command from JS (check `context` is the `Reviewer`).
3. **Module global `_typed_answer`** (the current card's text), cleared on each new question render so nothing stale leaks.

## Lifecycle

1. **Question renders** → inject `<textarea>` under the question, autofocus it, attach the keydown capture, bind Cmd/Ctrl+Enter.
2. **User types freely** (any keys). Cmd/Ctrl+Enter → JS sends `pycmd("recallbox:reveal:" + encodeURIComponent(value))`.
3. **Python message handler** → store value in `_typed_answer`, then call `mw.reviewer._showAnswer()`.
4. **Answer renders** → `card_will_show` (reviewAnswer) prepends a "Your answer:" block containing `_typed_answer`, above the real answer. The textarea is gone (answer template re-render). **Focus returns to the reviewer body** so 1–4 / Space grade normally.
5. **Next question** → `_typed_answer` cleared, repeat.

---

## THE gotcha: keyboard capture (this is the crux)

**Problem:** Anki's reviewer shortcuts stay live while the webview has focus. If keystrokes leak past the box, typing can trigger reviewer actions — Space/Enter reveals; 1–4 grade the card. (e.g. typing "3 mg" could silently grade the card "Good.")

**Scoping insight that de-risks this:** the box is on the **question side only**. The grading keys (1–4) are **inert in the question state** — they only do anything *after* reveal, by which point the box is gone. So on the front, the **only** shortcut that can misfire is **Space / Enter (reveal)**. That is the one key behavior we must intercept. Grading-key leakage is a non-issue here.

**Required handling:**

- JS `keydown` listener on the textarea: call `e.stopPropagation()` for all keys so they don't bubble to Anki's document-level handlers.
- Preserve normal editing: plain **Enter** and **Shift+Enter** insert a newline (just don't `preventDefault` them).
- **Cmd/Ctrl+Enter**: `e.preventDefault(); reveal();`
- **Belt-and-suspenders:** also add a **document-level** `keydown` listener in the **capture phase** that, while the box is focused, swallows Space and Enter so they can't reach Anki even if Qt's routing differs from plain DOM bubbling. Track focus with focus/blur on the textarea.
- **Fallback if keys still leak** (single-key `QShortcut`s can bypass the DOM on some Qt builds): bridge focus/blur to Python and temporarily disable the reviewer shortcuts while the box is focused — e.g. monkeypatch `mw.reviewer._shortcutKeys` to return `[]` when the box is active and re-apply on blur/reveal. **Try the pure-JS path first; only add the Python shortcut-disable if leakage is actually observed.**

**Autofocus caveat:** autofocusing the box means Space no longer reveals while typing (intended — reveal is now Cmd/Ctrl+Enter). *Optional nicety:* Esc blurs the box and restores normal Space-to-reveal.

**After reveal:** blur/remove the textarea and return focus to the reviewer body so grading shortcuts (1–4, Space) work as usual. **If you skip this, the card can't be graded.**

---

## Edge cases

- **Empty box** on Cmd/Enter (or a normal "Show Answer" click): reveal normally; show "(no answer entered)" or omit the block.
- **Multi-line answers:** textarea; Cmd/Ctrl+Enter submits, Enter/Shift+Enter = newline.
- **Cards already using `{{type:Field}}`:** possible double input box / conflict. Detect (template contains `{{type:` or the rendered HTML already has Anki's type input) and either skip injection or coexist deliberately — pick one and document it.
- **Cloze cards:** box still useful for typing reasoning; keep it generic, no grading. Watch for visual overlap with cloze styling.
- **True/False cards** (e.g. the somatic-nerve / Nm-receptor card): encourage typing the *reason*, not just the verdict — but that's user behavior, not enforced. Box stays a plain textarea.
- **Only inject in the reviewer:** gate on `kind` being `reviewQuestion`/`reviewAnswer`. Do **not** inject in the card-layout editor, preview, or browser, or you'll break those views.
- **Rapid card switching / undo:** clear `_typed_answer` on every new question render so a previous answer never shows.
- **HTML-escape the typed answer** before injecting it into the answer HTML (user text may contain `<`, `&`, etc.).

## Styling

Match the existing dark theme / visual standards. Textarea: dark background, readable text, subtle border, full card width, a few rows tall, deck font. The "Your answer:" block on the back: visually distinct (muted label + boxed), clearly separated, sitting above the real answer.

## v1 scope

**In:** front-side textarea, Cmd/Ctrl+Enter reveal, typed answer shown above the real answer, key capture, dark styling.

**Out (later):** auto-grading/diffing (deliberately excluded), logging/persisting answers across sessions for review, per-deck enable/disable, a config UI, mobile (add-ons are desktop-only).

## Acceptance criteria

1. On any card, a text box appears under the question, autofocused.
2. Typing any character — including Space, digits 1–4, and Enter (newline) — stays in the box and never triggers reveal or grading.
3. Cmd/Ctrl+Return reveals the answer and shows exactly what was typed, above the real answer.
4. After reveal, 1–4 and Space grade the card normally (focus released).
5. The next card starts with an empty box; no answer text carries over.
6. Card-layout editor, preview, and browser are unaffected.

## Verify against the installed Anki

`mw.reviewer._showAnswer()` is private, and the `card_will_show` / `webview_did_receive_js_message` signatures can shift between Anki versions. Confirm exact names against the installed version and the current add-on hook reference (the `gui_hooks` module / "Add-on hooks" docs) before relying on them.
