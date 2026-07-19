const fs = require("fs");
const { JSDOM } = require("jsdom");

const html = fs.readFileSync(
  "/home/claude/Chinese_Study-main/pinyin-immersion-app/src/hw_component/index.html", "utf-8");

// Strip the CDN script tag (no network in jsdom) — we inject a stub instead.
const patched = html.replace(/<script src="https:\/\/cdn\.jsdelivr[^"]*"><\/script>/, "");

const dom = new JSDOM(patched, {
  url: "http://localhost/",
  runScripts: "dangerously",
  pretendToBeVisual: true,
  beforeParse(window) {
    // ---- capture protocol messages (parent === window in jsdom top frame)
    window.__messages = [];
    window.parent.postMessage = (msg) => window.__messages.push(msg);
    window.navigator.vibrate = () => {};
    window.speechSynthesis = { getVoices: () => [], cancel(){}, speak(){} };
    window.SpeechSynthesisUtterance = function(){};

    // ---- HanziWriter stub with drivable quiz callbacks
    window.__writers = [];
    window.HanziWriter = {
      loadCharacterData: (ch) => Promise.resolve({ strokes: new Array(ch === "习" ? 3 : 6) }),
      create: (target, ch, cfg) => {
        const w = {
          ch, cfg, quizOpts: null,
          animateCharacter(o) { setTimeout(() => o && o.onComplete && o.onComplete(), 0); },
          quiz(opts) { this.quizOpts = opts; },
          highlightStroke() {},
          cancelQuiz() {},
          // test drivers:
          driveCorrect(remaining) { this.quizOpts.onCorrectStroke && this.quizOpts.onCorrectStroke({ strokesRemaining: remaining }); },
          driveMistake() { this.quizOpts.onMistake && this.quizOpts.onMistake({}); },
          driveComplete(m) { this.quizOpts.onComplete && this.quizOpts.onComplete({ totalMistakes: m }); },
        };
        window.__writers.push(w);
        return w;
      },
    };
  },
});

const w = dom.window;
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const lastWriter = () => w.__writers[w.__writers.length - 1];
const valueMsgs = () => w.__messages.filter(m => m.type === "streamlit:setComponentValue");

function assert(cond, msg) { if (!cond) { console.error("❌ " + msg); process.exit(1); } console.log("  ✅ " + msg); }

(async () => {
  await sleep(20);
  assert(w.__messages.some(m => m.type === "streamlit:componentReady"),
         "sends componentReady on boot");
  assert(w.__messages.some(m => m.type === "streamlit:setFrameHeight"),
         "sends setFrameHeight");

  // ---- render a 2-char session: 习 is NEW, 惯 is REVIEW
  const session = {
    session_id: "sess-1",
    chars: [
      { character: "习", is_new: true,  stroke_count: 3, interval: 0, ease_factor: 2.5,
        review_count: 0, char_pinyin: "xí", word: "习惯", word_pinyin: "xí guàn",
        word_english: "habit / to be used to" },
      { character: "惯", is_new: false, stroke_count: 11, interval: 3, ease_factor: 2.5,
        review_count: 2, char_pinyin: "guàn", word: "习惯", word_pinyin: "xí guàn",
        word_english: "habit / to be used to" },
    ],
  };
  w.dispatchEvent(new w.MessageEvent("message", { data: { type: "streamlit:render", args: { session } } }));
  await sleep(30);

  // ---- THE BUG MATT REPORTED: answer must not be visible anywhere
  const visibleText = w.document.getElementById("app").textContent;
  assert(!visibleText.includes("习"), "target character 习 never appears as text (masked cue)");
  assert(w.document.querySelectorAll("#masked-word .blank").length === 1,
         "masked word shows a blank box for the target only (惯 visible as context)");
  assert(visibleText.includes("惯"), "sibling character 惯 IS visible as context");
  assert(visibleText.includes("xí") && visibleText.includes("habit"),
         "pinyin + meaning shown as the recall cue");

  // ---- NEW char ladder: watch phase auto-completes -> trace
  await sleep(30);   // animateCharacter fires async, then 500ms... stub uses real timers
  await sleep(600);
  assert(w.document.getElementById("chips").textContent.includes("TRACE"),
         "new char enters TRACE after the demo");
  let writer = lastWriter();
  assert(writer.cfg.showOutline === true, "trace phase shows the outline");

  // ---- THE OTHER BUG: ink colour must differ from stroke colour, on dark bg
  assert(writer.cfg.drawingColor && writer.cfg.strokeColor &&
         writer.cfg.drawingColor.toLowerCase() !== writer.cfg.strokeColor.toLowerCase(),
         `learner ink (${writer.cfg.drawingColor}) differs from completed strokes (${writer.cfg.strokeColor})`);
  assert(writer.cfg.drawingWidth >= 16, "ink is thick enough to see on a phone");

  // finish trace -> write phase
  writer.driveComplete(0);
  await sleep(600);
  assert(w.document.getElementById("chips").textContent.includes("WRITE FROM MEMORY"),
         "new char proceeds to blind WRITE");
  writer = lastWriter();
  assert(writer.cfg.showOutline === false, "write phase hides the outline");

  // write with 1 mistake -> grade should be Good(2) via quality mapping
  writer.driveMistake();
  writer.driveCorrect(2); writer.driveCorrect(1); writer.driveCorrect(0);
  writer.driveComplete(1);
  await sleep(50);
  let vals = valueMsgs();
  assert(vals.length >= 1, "result streamed after first character");
  let r0 = vals[vals.length - 1].value.results[0];
  assert(r0.character === "习" && r0.mistakes === 1 && r0.grade === 2,
         "new char, 1 mistake -> grade Good (matches engine mapping)");

  // tap to advance instantly
  w.document.getElementById("tap-next").onclick();
  await sleep(30);

  // ---- REVIEW char: straight to write
  assert(w.document.getElementById("chips").textContent.includes("REVIEW"),
         "review char goes straight to writing");
  const appText2 = w.document.getElementById("app").textContent;
  assert(!appText2.includes("惯"), "now 惯 is masked and 习 would be context");
  writer = lastWriter();

  // hint + clean strokes: hints count toward grade (0 mistakes + 1 hint -> Good)
  w.document.getElementById("btn-hint").click();
  writer.driveComplete(0);
  await sleep(50);
  vals = valueMsgs();
  const last = vals[vals.length - 1].value;
  const r1 = last.results[1];
  assert(r1.character === "惯" && r1.hints === 1 && r1.grade === 2,
         "review char, clean but 1 hint -> grade Good");

  // advance -> summary + done:true
  w.document.getElementById("tap-next").onclick();
  await sleep(30);
  vals = valueMsgs();
  const final = vals[vals.length - 1].value;
  assert(final.done === true && final.results.length === 2,
         "session end sends done:true with all results");
  assert(w.document.getElementById("summary").style.display !== "none",
         "summary screen shown");

  // ---- re-render with SAME session id must not reset state
  w.dispatchEvent(new w.MessageEvent("message", { data: { type: "streamlit:render", args: { session } } }));
  await sleep(20);
  assert(w.document.getElementById("summary").style.display !== "none",
         "re-render with same session_id keeps state (no remount reset)");

  console.log("\nALL COMPONENT TESTS PASS");
  process.exit(0);
})().catch(e => { console.error("HARNESS ERROR:", e); process.exit(1); });
