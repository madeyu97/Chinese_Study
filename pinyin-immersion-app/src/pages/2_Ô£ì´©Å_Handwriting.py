# src/pages/2_✍️_Handwriting.py
"""
Handwriting drill page.

Three functionally distinct modes:
  - Trace:  outline visible during quiz (easiest)
  - Guided: animation plays first, then quiz WITHOUT outline (medium)
  - Memory: no animation, quiz WITHOUT outline (hardest)

Freehand drawing canvas overlay lets you practice freely with S-Pen / finger
/ mouse outside of quiz mode. Pressure-sensitive line width on S-Pen.

Settings:
  - 🤖 Auto-grade & advance: applies SRS grade from mistake count automatically
  - 🎨 Keep freehand visible during quiz: don't wipe your practice strokes
    when starting a quiz — useful as a self-reference layer
"""

import streamlit as st
import streamlit.components.v1 as components
import json

from db_manager import (
    get_handwriting_session,
    update_handwriting_progress,
    get_handwriting_stats,
)

st.set_page_config(page_title="Handwriting Drill", page_icon="✍️", layout="centered")
st.title("✍️ Handwriting Drill")

MODE_LABELS = {
    "trace":  "✏️ Trace (easiest)",
    "guided": "👀 Guided (medium)",
    "memory": "🧠 Memory (hardest)",
}
GRADE_NAMES = ["Again", "Hard", "Good", "Easy"]


def mistakes_to_grade(mistakes: int) -> int:
    if mistakes == 0:
        return 3
    if mistakes == 1:
        return 2
    if mistakes <= 3:
        return 1
    return 0


# ----------------------------------------------------------------------
# SESSION INIT
# ----------------------------------------------------------------------
if 'hw_batch' not in st.session_state:
    with st.spinner("Pulling characters from your studying + mastered vocabulary…"):
        st.session_state.hw_batch = get_handwriting_session(new_count=5)
    st.session_state.hw_index = 0

if 'hw_mode' not in st.session_state:
    st.session_state.hw_mode = "trace"

if 'hw_auto_grade' not in st.session_state:
    st.session_state.hw_auto_grade = True

if 'hw_keep_freehand' not in st.session_state:
    st.session_state.hw_keep_freehand = False

# ----------------------------------------------------------------------
# QUIZ RESULT INTAKE (from iframe via URL query params)
# ----------------------------------------------------------------------
incoming_ts = st.query_params.get("hw_ts")
incoming_mistakes = st.query_params.get("hw_mistakes")
incoming_char = st.query_params.get("hw_char")

if incoming_ts and incoming_mistakes is not None and incoming_char:
    last_processed = st.session_state.get("hw_last_processed_ts")
    if incoming_ts != last_processed:
        st.session_state.hw_last_processed_ts = incoming_ts
        st.session_state.hw_pending_mistakes = int(incoming_mistakes)
        st.session_state.hw_pending_char = incoming_char

        if st.session_state.hw_auto_grade:
            batch = st.session_state.hw_batch
            idx = st.session_state.hw_index
            if idx < len(batch) and batch[idx]["character"] == incoming_char:
                mistakes = int(incoming_mistakes)
                grade = mistakes_to_grade(mistakes)
                update_handwriting_progress(incoming_char, grade, batch[idx])
                st.session_state.hw_last_result = {
                    "char": incoming_char, "mistakes": mistakes, "grade": grade,
                }
                st.session_state.hw_index += 1
                st.session_state.pop("hw_pending_mistakes", None)
                st.session_state.pop("hw_pending_char", None)

        st.query_params.clear()
        st.rerun()

# ----------------------------------------------------------------------
# SIDEBAR
# ----------------------------------------------------------------------
with st.sidebar:
    st.header("✍️ Handwriting Progress")
    hw_stats = get_handwriting_stats()
    st.metric("Unique chars in your vocab", hw_stats['total_chars_available'])
    st.markdown("---")
    if hw_stats['total_chars_available'] > 0:
        st.write(f"**👀 Not yet practiced:** {hw_stats['unseen']}")
        st.progress(hw_stats['unseen'] / hw_stats['total_chars_available'])
        st.write(f"**✏️ Practiced:** {hw_stats['practiced']}")
        st.progress(hw_stats['practiced'] / hw_stats['total_chars_available'])
        st.write(f"**🏆 Mastered:** {hw_stats['mastered']}")
        st.progress(hw_stats['mastered'] / hw_stats['total_chars_available'])
        st.caption("Mastered = pushed 21+ days into the future.")

    st.markdown("---")
    st.subheader("⚙️ Settings")
    st.session_state.hw_auto_grade = st.checkbox(
        "🤖 Auto-grade & advance",
        value=st.session_state.hw_auto_grade,
        help="When ON, the SRS grade is applied automatically from HanziWriter's mistake count and the next character loads."
    )
    st.session_state.hw_keep_freehand = st.checkbox(
        "🎨 Keep freehand visible during quiz",
        value=st.session_state.hw_keep_freehand,
        help="When ON, your S-Pen practice strokes stay on the canvas when you start a quiz, so you can reference them. When OFF, the canvas auto-clears. The Clear button always works manually."
    )
    if st.button("🔄 Rebuild today's batch", use_container_width=True):
        for k in ('hw_batch', 'hw_index', 'hw_pending_mistakes', 'hw_pending_char', 'hw_last_result'):
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()

# ----------------------------------------------------------------------
# EMPTY / DONE STATES
# ----------------------------------------------------------------------
batch = st.session_state.hw_batch

if not batch:
    st.info(
        "No characters available to practice yet. Study some vocabulary on "
        "the **Pinyin Immersion** page first."
    )
    st.stop()

if st.session_state.hw_index >= len(batch):
    st.success("🎉 Done with today's batch!")
    st.balloons()
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("➕ Drill 5 more", use_container_width=True):
            extras = get_handwriting_session(new_count=5)
            already_done = {c['character'] for c in batch}
            new_extras = [c for c in extras if c['character'] not in already_done]
            if new_extras:
                st.session_state.hw_batch.extend(new_extras[:5])
                st.rerun()
            else:
                st.info("No more characters available right now.")
    with col_b:
        if st.button("🏁 Done for today", type="primary", use_container_width=True):
            st.stop()
    st.stop()

current = batch[st.session_state.hw_index]
char = current['character']

last_result = st.session_state.get("hw_last_result")
if last_result:
    st.success(
        f"✅ Last char **{last_result['char']}**: "
        f"{last_result['mistakes']} mistake(s) → graded **{GRADE_NAMES[last_result['grade']]}**"
    )
    st.session_state.pop("hw_last_result", None)

st.progress(st.session_state.hw_index / len(batch))
status_tag = "🆕 NEW" if current['is_new'] else "🔁 REVIEW"
st.caption(
    f"Character {st.session_state.hw_index + 1} of {len(batch)}  ·  {status_tag}  ·  "
    f"{current['stroke_count']} strokes  ·  appears in {current['personal_freq']} "
    f"of your vocab words"
)

st.markdown(
    f"<div style='text-align:center; font-size:96px; line-height:1; "
    f"margin: 8px 0 12px; font-family: serif;'>{char}</div>",
    unsafe_allow_html=True,
)

mode_keys = list(MODE_LABELS.keys())
selected_mode = st.radio(
    "Difficulty mode",
    options=mode_keys,
    format_func=lambda k: MODE_LABELS[k],
    horizontal=True,
    index=mode_keys.index(st.session_state.hw_mode),
    key="hw_mode_selector",
)
if selected_mode != st.session_state.hw_mode:
    st.session_state.hw_mode = selected_mode
    st.rerun()

mode_descriptions = {
    "trace": "Outline visible throughout. Trace over the lines.",
    "guided": "Watch the stroke order animation, then write WITHOUT the outline.",
    "memory": "No outline, no demo. Write from memory.",
}
st.caption(f"_{mode_descriptions[selected_mode]}_")

# ======================================================================
# HANZIWRITER + FREEHAND CANVAS COMPONENT
# ======================================================================
HANZI_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<style>
  body {
    margin: 0; padding: 16px; font-family: -apple-system, sans-serif;
    text-align: center; background: #fafafa;
    user-select: none; -webkit-user-select: none;
  }
  #char-container {
    position: relative;
    display: inline-block;
    width: 360px;
    height: 360px;
    background: #fff;
    border: 2px dashed #bbb;
    border-radius: 12px;
    touch-action: none;
  }
  #char-target {
    position: absolute;
    top: 0; left: 0;
    width: 360px;
    height: 360px;
  }
  #freehand-canvas {
    position: absolute;
    top: 0; left: 0;
    pointer-events: none;
    touch-action: none;
    background: transparent;
  }
  .controls {
    margin-top: 16px;
    display: flex;
    gap: 8px;
    justify-content: center;
    flex-wrap: wrap;
  }
  button {
    padding: 12px 18px;
    cursor: pointer;
    font-size: 15px;
    border-radius: 8px;
    border: 1px solid #555;
    background: #fff;
    min-width: 140px;
    min-height: 48px;
    font-weight: 500;
  }
  button:active { background: #eee; transform: scale(0.98); }
  button.primary {
    background: #ff4b4b; color: white; border-color: #ff4b4b;
  }
  button.active {
    background: #2c7be5; color: white; border-color: #2c7be5;
  }
  #status {
    margin-top: 14px; min-height: 32px; color: #333;
    font-size: 16px; padding: 8px;
    transition: all 0.2s;
  }
  #status.success { color: #1a7f1a; font-weight: 600; }
  #status.mistake { color: #c52525; }
  .legend { font-size: 13px; color: #888; margin-top: 6px; }
</style>
</head>
<body>
  <div id="char-container">
    <div id="char-target"></div>
    <canvas id="freehand-canvas" width="360" height="360"></canvas>
  </div>

  <div class="controls">
    <button id="demo-btn" onclick="showDemo()">▶️ Show Strokes</button>
    <button id="freehand-btn" onclick="toggleFreehand()">✏️ Free Practice</button>
    <button id="quiz-btn" class="primary" onclick="startQuiz()">✍️ Start Quiz</button>
    <button id="clear-btn" onclick="clearFreehand()">🗑 Clear</button>
  </div>
  <p id="status">Ready. Try Free Practice with your pen, or Start Quiz when ready.</p>
  <p class="legend">S-Pen pressure varies line width. The app auto-grades during Start Quiz.</p>

  <script src="https://cdn.jsdelivr.net/npm/hanzi-writer@3.5/dist/hanzi-writer.min.js"></script>
  <script>
    const CHAR = "__CHAR__";
    const MODE = "__MODE__";
    const AUTO_GRADE = __AUTO_GRADE__;
    const KEEP_FREEHAND = __KEEP_FREEHAND__;

    let writer = null;
    let resultSent = false;
    let freehandActive = false;
    let drawing = false;
    let lastX = 0, lastY = 0;

    const fhCanvas = document.getElementById('freehand-canvas');
    const fhCtx = fhCanvas.getContext('2d');

    function setStatus(msg, cls) {
      const el = document.getElementById('status');
      el.innerHTML = msg;
      el.className = cls || '';
    }

    // ----------------------------------------------------------------
    // FREEHAND DRAWING
    // ----------------------------------------------------------------
    function getCanvasPos(e) {
      const rect = fhCanvas.getBoundingClientRect();
      return {
        x: (e.clientX - rect.left) * (fhCanvas.width / rect.width),
        y: (e.clientY - rect.top) * (fhCanvas.height / rect.height),
      };
    }

    fhCanvas.addEventListener('pointerdown', (e) => {
      if (!freehandActive) return;
      e.preventDefault();
      drawing = true;
      const pos = getCanvasPos(e);
      lastX = pos.x; lastY = pos.y;
      const pressure = e.pressure > 0 ? e.pressure : 0.5;
      fhCtx.beginPath();
      fhCtx.arc(lastX, lastY, (1 + pressure * 4), 0, Math.PI * 2);
      fhCtx.fillStyle = '#222';
      fhCtx.fill();
    });

    fhCanvas.addEventListener('pointermove', (e) => {
      if (!drawing || !freehandActive) return;
      e.preventDefault();
      const pos = getCanvasPos(e);
      const pressure = e.pressure > 0 ? e.pressure : 0.5;
      fhCtx.strokeStyle = '#222';
      fhCtx.lineWidth = 2 + pressure * 6;
      fhCtx.lineCap = 'round';
      fhCtx.lineJoin = 'round';
      fhCtx.beginPath();
      fhCtx.moveTo(lastX, lastY);
      fhCtx.lineTo(pos.x, pos.y);
      fhCtx.stroke();
      lastX = pos.x; lastY = pos.y;
    });

    function stopDrawing() { drawing = false; }
    fhCanvas.addEventListener('pointerup', stopDrawing);
    fhCanvas.addEventListener('pointerleave', stopDrawing);
    fhCanvas.addEventListener('pointercancel', stopDrawing);

    function clearFreehand() {
      fhCtx.clearRect(0, 0, fhCanvas.width, fhCanvas.height);
      if (freehandActive) {
        setStatus('Canvas cleared. Keep practicing.', '');
      }
    }

    function toggleFreehand() {
      freehandActive = !freehandActive;
      const btn = document.getElementById('freehand-btn');
      if (freehandActive) {
        fhCanvas.style.pointerEvents = 'auto';
        btn.textContent = '⏹ Stop Practice';
        btn.classList.add('active');
        setStatus('Free practice mode — write with your S-Pen. Tap Clear to wipe, Start Quiz when ready.', '');
      } else {
        fhCanvas.style.pointerEvents = 'none';
        btn.textContent = '✏️ Free Practice';
        btn.classList.remove('active');
        setStatus('Ready.', '');
      }
    }

    // ----------------------------------------------------------------
    // HANZIWRITER MODES
    // ----------------------------------------------------------------
    function baseConfig(overrides) {
      const cfg = {
        width: 360,
        height: 360,
        padding: 10,
        showCharacter: false,
        strokeAnimationSpeed: 1,
        delayBetweenStrokes: 120,
        strokeColor: '#222',
        outlineColor: '#888',
      };
      return Object.assign(cfg, overrides || {});
    }

    function createWriter(overrides) {
      document.getElementById('char-target').innerHTML = '';
      writer = HanziWriter.create('char-target', CHAR, baseConfig(overrides));
    }

    function showDemo() {
      resultSent = false;
      if (freehandActive) toggleFreehand();
      if (!KEEP_FREEHAND) clearFreehand();
      createWriter({ showOutline: true });
      writer.animateCharacter({
        onComplete: () => setStatus('Animation done. Try Free Practice or Start Quiz.', '')
      });
      setStatus('Watching stroke order…', '');
    }

    function quizOpts() {
      const opts = {
        highlightOnComplete: true,
        onMistake: (info) => {
          setStatus(
            `Stroke ${info.strokeNum + 1}: ${info.mistakesOnStroke} mistake(s)`,
            'mistake'
          );
        },
        onCorrectStroke: (info) => {
          setStatus(
            `Stroke ${info.strokeNum + 1} ✓ — ${info.strokesRemaining} to go`,
            'success'
          );
        },
        onComplete: (summary) => {
          setStatus(
            `<strong>✅ Done!</strong> Total mistakes: ${summary.totalMistakes}` +
            (AUTO_GRADE ? '<br>Saving result…' : '<br>Pick a grade below.'),
            'success'
          );
          if (AUTO_GRADE && !resultSent) {
            resultSent = true;
            setTimeout(() => sendResult(summary.totalMistakes), 1400);
          }
        }
      };
      if (MODE === 'trace') {
        opts.leniency = 1.5;
        opts.showHintAfterMisses = 2;
      } else if (MODE === 'guided') {
        opts.leniency = 1.2;
        opts.showHintAfterMisses = 2;
      } else {
        opts.leniency = 1.0;
        opts.showHintAfterMisses = 3;
      }
      return opts;
    }

    async function startQuiz() {
      // Disable freehand input mode (but optionally keep the drawings)
      if (freehandActive) toggleFreehand();
      if (!KEEP_FREEHAND) clearFreehand();
      resultSent = false;

      // GUIDED mode: animation first, then quiz without outline
      if (MODE === 'guided') {
        createWriter({ showOutline: true });
        setStatus("Watch carefully — you'll write this from memory next.", "");
        await new Promise(resolve => {
          writer.animateCharacter({ onComplete: resolve });
        });
        await new Promise(r => setTimeout(r, 600));
      }

      if (MODE === 'trace') {
        createWriter({ showOutline: true });
        setStatus('Trace each stroke. The app is watching.', '');
      } else {
        createWriter({ showOutline: false });
        setStatus(
          MODE === 'guided'
            ? 'Now write it from what you just saw.'
            : 'Write the character from memory.',
          ''
        );
      }
      writer.quiz(quizOpts());
    }

    function sendResult(mistakes) {
      try {
        const parentUrl = new URL(window.parent.location.href);
        parentUrl.searchParams.set('hw_mistakes', mistakes);
        parentUrl.searchParams.set('hw_char', CHAR);
        parentUrl.searchParams.set('hw_ts', Date.now());
        window.parent.location.href = parentUrl.toString();
      } catch (e) {
        setStatus(
          `<strong>⚠️ Auto-grade failed.</strong> You had ${mistakes} mistake(s). Pick a grade below manually.`,
          'mistake'
        );
      }
    }

    window.addEventListener('load', () => {
      const initialConfig = (MODE === 'trace') ? { showOutline: true } : { showOutline: false };
      createWriter(initialConfig);
      if (MODE === 'memory') {
        setStatus('Memory mode — write from memory with Start Quiz, or try Free Practice first.', '');
      }
    });
  </script>
</body>
</html>
"""

char_for_js = json.dumps(char)[1:-1]
auto_grade_js = "true" if st.session_state.hw_auto_grade else "false"
keep_freehand_js = "true" if st.session_state.hw_keep_freehand else "false"
hanzi_html = (HANZI_TEMPLATE
              .replace("__CHAR__", char_for_js)
              .replace("__MODE__", st.session_state.hw_mode)
              .replace("__AUTO_GRADE__", auto_grade_js)
              .replace("__KEEP_FREEHAND__", keep_freehand_js))

components.html(hanzi_html, height=640, scrolling=False)

# ----------------------------------------------------------------------
# MANUAL GRADE BUTTONS
# ----------------------------------------------------------------------
st.markdown("---")

pending = st.session_state.get("hw_pending_mistakes")
if pending is not None and not st.session_state.hw_auto_grade:
    suggested = mistakes_to_grade(pending)
    st.info(
        f"📊 HanziWriter detected **{pending} mistake(s)**. "
        f"Suggested grade: **{GRADE_NAMES[suggested]}**."
    )
else:
    suggested = None

st.markdown("#### Grade (manual override available):")
st.caption(
    "With auto-grade ON, this auto-fills when you finish a quiz. "
    "You can always tap a button here to override."
)

cols = st.columns(4)
labels_compact = [
    ("Again", "Forgot"),
    ("Hard",  "Struggled"),
    ("Good",  "Solid"),
    ("Easy",  "Confident"),
]
for i, (col, (head, sub)) in enumerate(zip(cols, labels_compact)):
    with col:
        btn_type = "primary" if i == suggested else "secondary"
        if st.button(f"**{head}**\n\n{sub}", use_container_width=True,
                     key=f"hw_grade_{i}", type=btn_type):
            update_handwriting_progress(char, i, current)
            st.session_state.hw_last_result = {
                "char": char,
                "mistakes": pending if pending is not None else -1,
                "grade": i,
            }
            st.session_state.hw_index += 1
            st.session_state.pop("hw_pending_mistakes", None)
            st.session_state.pop("hw_pending_char", None)
            st.rerun()

with st.expander("⏭️ Skip this character (no SRS update)"):
    if st.button("Skip without grading"):
        st.session_state.hw_index += 1
        st.session_state.pop("hw_pending_mistakes", None)
        st.session_state.pop("hw_pending_char", None)
        st.rerun()
