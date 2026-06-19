"""Recall Box — type-your-answer-before-reveal box for the Anki reviewer.

Injects a free-text answer box directly under the question in the reviewer card
webview. The user types an answer, presses Cmd/Ctrl+Return to flip the card, and
the reveal shows the typed answer directly above the real answer. No grading.

Architecture (see recall-box-addon-brief.md):
  * card_will_show(text, card, kind) injects the textarea on the question and
    prepends the "Your answer" block on the answer.
  * webview_did_receive_js_message receives the typed text + reveal command.
  * _typed_answer (module global) round-trips the text across the
    question -> answer re-render (webview JS state is lost on re-render).

Target: Anki 25.09.x (Qt6 / Chromium 122). Hook signatures and
mw.reviewer._showAnswer() confirmed against that build.
"""

from __future__ import annotations

import html
import re
from urllib.parse import unquote

from aqt import gui_hooks, mw
from aqt.reviewer import Reviewer

# The current card's typed answer. Round-trips question -> answer via Python
# because the webview's JS state is destroyed when the answer template renders.
_typed_answer: str = ""

# pycmd prefix used by the injected JS to send the typed text back to Python.
_REVEAL_CMD = "recallbox:reveal:"

# If the rendered question already contains Anki's {{type:Field}} input we skip
# injection rather than stack two answer boxes. (Documented v1 choice.)
_TYPE_INPUT_MARKER = 'id="typeans"'

# Marker so we never inject our box twice into the same render.
_BOX_MARKER = "recallbox-textarea"


def _question_html() -> str:
    """Textarea + key-capture JS appended under the question."""
    return """
<div id="recallbox-wrap">
  <textarea id="recallbox-textarea" rows="4" spellcheck="false"
            placeholder="Type your answer, then press Cmd/Ctrl+Return to reveal..."
            autocomplete="off" autocorrect="off" autocapitalize="off"></textarea>
</div>
<style>
  #recallbox-wrap { max-width: 560px; margin: 14px auto 0; }
  #recallbox-textarea {
    width: 100%;
    box-sizing: border-box;
    min-height: 4.5em;
    padding: 10px 12px;
    font-family: Georgia, serif;
    font-size: 0.9em;
    line-height: 1.5;
    color: #dddddd;
    background: #2a2a2a;
    border: 1px solid #444;
    border-radius: 6px;
    resize: vertical;
    outline: none;
  }
  #recallbox-textarea:focus { border-color: #6ecfcf; }
  #recallbox-textarea::placeholder { color: #777; }
</style>
<script>
(function () {
  var ta = document.getElementById("recallbox-textarea");
  if (!ta) return;
  var boxFocused = false;
  var revealed = false;

  function isReveal(e) {
    return (e.ctrlKey || e.metaKey) && (e.key === "Enter" || e.key === "Return");
  }
  function isSpaceOrEnter(e) {
    return e.key === " " || e.key === "Spacebar" ||
           e.key === "Enter" || e.key === "Return";
  }

  function reveal() {
    if (revealed) return;
    revealed = true;
    var value = ta.value;
    cleanup();
    pycmd("%REVEAL_CMD%" + encodeURIComponent(value));
  }

  function cleanup() {
    boxFocused = false;
    if (window.__recallBoxDocHandler) {
      document.removeEventListener("keydown", window.__recallBoxDocHandler, true);
      window.__recallBoxDocHandler = null;
    }
    try { ta.blur(); } catch (e) {}
  }

  // Authority for reveal keys (Space/Enter), capture phase, so Anki's
  // document-level / Qt shortcut handlers never see them while the box is
  // focused. Default actions (typing space, inserting newline) are preserved
  // because we do NOT preventDefault on plain keys.
  function onDocKeydown(e) {
    if (!boxFocused) return;
    if (isReveal(e)) {
      e.preventDefault();
      e.stopPropagation();
      reveal();
      return;
    }
    if (isSpaceOrEnter(e)) {
      e.stopPropagation();
    }
  }

  // Defense for every other key (digits 1-4, etc.): keep it inside the box and
  // out of Anki's handlers, while preserving normal editing.
  ta.addEventListener("keydown", function (e) {
    if (isReveal(e)) {
      e.preventDefault();
      reveal();
      return;
    }
    e.stopPropagation();
  });

  ta.addEventListener("focus", function () { boxFocused = true; });
  ta.addEventListener("blur", function () { boxFocused = false; });

  // Esc: blur the box so normal Space-to-reveal works again (optional nicety).
  ta.addEventListener("keyup", function (e) {
    if (e.key === "Escape") { boxFocused = false; ta.blur(); }
  });

  // Remove any stale handler from a prior render before installing ours.
  if (window.__recallBoxDocHandler) {
    document.removeEventListener("keydown", window.__recallBoxDocHandler, true);
  }
  window.__recallBoxDocHandler = onDocKeydown;
  document.addEventListener("keydown", onDocKeydown, true);

  // Autofocus the box once the card has settled.
  setTimeout(function () { ta.focus(); }, 50);
})();
</script>
""".replace("%REVEAL_CMD%", _REVEAL_CMD)


def _answer_html(typed: str) -> str:
    """The "Your answer" block prepended above the real answer."""
    if typed.strip():
        body = html.escape(typed).replace("\n", "<br>")
    else:
        body = '<span class="recallbox-empty">(no answer entered)</span>'
    return """
<div id="recallbox-yours">
  <div class="recallbox-label">Your answer</div>
  <div class="recallbox-body">%BODY%</div>
</div>
<style>
  #recallbox-yours {
    max-width: 560px;
    margin: 10px auto;
    padding: 12px 14px;
    text-align: left;
    font-family: Georgia, serif;
    color: #dddddd;
    background: #2a2a2a;
    border: 1px solid #444;
    border-left: 3px solid #6ecfcf;
    border-radius: 6px;
  }
  #recallbox-yours .recallbox-label {
    font-size: 0.7em;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #6ecfcf;
    margin-bottom: 6px;
  }
  #recallbox-yours .recallbox-body {
    font-size: 0.9em;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
  }
  #recallbox-yours .recallbox-empty { color: #777; font-style: italic; }
</style>
""".replace("%BODY%", body)


def on_card_will_show(text: str, card, kind: str) -> str:
    """Inject on the question; prepend the typed answer on the answer.

    Gated strictly on the reviewer kinds so the card-layout editor, preview, and
    browser are untouched.
    """
    global _typed_answer

    if kind == "reviewQuestion":
        # Clear stale text from the previous card so nothing leaks across cards
        # (rapid switching / undo).
        _typed_answer = ""
        if _TYPE_INPUT_MARKER in text or _BOX_MARKER in text:
            # Card uses {{type:Field}} (or we somehow already injected); leave it
            # alone to avoid a double input box.
            return text
        return text + _question_html()

    if kind == "reviewAnswer":
        block = _answer_html(_typed_answer)
        # The answer-side HTML is the full card: repeated question +
        # <hr id=answer> + the real answer. Insert our block right after that
        # separator so it sits below the question but above the answer. Fall
        # back to prepending if the separator isn't present.
        m = re.search(r'<hr\b[^>]*\bid\s*=\s*["\']?answer["\']?[^>]*>',
                      text, re.IGNORECASE)
        if m:
            return text[:m.end()] + block + text[m.end():]
        return block + text

    return text


def on_js_message(handled, message: str, context):
    """Receive the typed text + reveal command from the reviewer webview."""
    global _typed_answer

    if not isinstance(context, Reviewer):
        return handled
    if not message.startswith(_REVEAL_CMD):
        return handled

    _typed_answer = unquote(message[len(_REVEAL_CMD):])

    # Flip to the answer side. _showAnswer() is private but stable on 25.09.x;
    # guard on state so a stray message can't double-fire.
    if mw.reviewer.state == "question":
        mw.reviewer._showAnswer()

    return (True, None)


gui_hooks.card_will_show.append(on_card_will_show)
gui_hooks.webview_did_receive_js_message.append(on_js_message)
