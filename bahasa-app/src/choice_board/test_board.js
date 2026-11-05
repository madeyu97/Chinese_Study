// Tests for the quiz answer cards. Run: node test_board.js  (needs jsdom)
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const html = fs.readFileSync(path.join(__dirname, "index.html"), "utf-8");
let failed = 0;
function check(name, cond) { console.log((cond ? "  ✅ " : "  ❌ ") + name); if (!cond) failed++; }

function board() {
  const dom = new JSDOM(html, {
    runScripts: "dangerously", pretendToBeVisual: true,
    beforeParse(window) {
      window.__messages = [];
      window.parent.postMessage = (msg) => window.__messages.push(msg);
    },
  });
  const w = dom.window;
  w.render = (args, theme) => w.dispatchEvent(new w.MessageEvent("message",
    { data: { type: "streamlit:render", args, theme: theme || { base: "light" } } }));
  w.values = () => w.__messages.filter((m) => m.type === "streamlit:setComponentValue").map((m) => m.value);
  w.cards = () => Array.from(w.document.querySelectorAll(".card"));
  return w;
}

const IMG = "data:image/png;base64,AA==";
const pics = [0, 1, 2, 3].map(() => ({ kind: "image", img: IMG }));
const words = [["手", "shǒu"], ["脚", "jiǎo"], ["头", "tóu"], ["眼", "yǎn"]].map(([zh, py]) => ({ kind: "word", zh, py }));

const w = board();
check("announces itself to Streamlit", w.__messages.some((m) => m.type === "streamlit:componentReady"));

// word -> picture: the word on top, four picture cards to tap
w.render({ sid: "g1", round: 0, prompt: { kind: "word", zh: "脚", py: "jiǎo" }, options: pics,
           answer: 1, answered: null, show_pinyin: true });
check("prompt word shown with pinyin", w.document.getElementById("prompt").textContent.includes("脚jiǎo"));
check("four tappable picture cards", w.cards().length === 4 && w.cards().every((b) => !b.disabled && b.querySelector("img")));
w.cards()[2].click();
let v = w.values().pop();
check("a tap answers: round and card reported", v.sid === "g1" && v.round === 0 && v.chosen === 2);
check("wrong tap shows red, the right card green", w.cards()[2].classList.contains("wrong") && w.cards()[1].classList.contains("right"));
check("one answer per round", w.cards().every((b) => b.disabled));
w.cards()[1].click();
check("a second tap sends nothing", w.values().length === 1);
// Python redraws the same round after scoring it: the board stays as it was
w.render({ sid: "g1", round: 0, prompt: { kind: "word", zh: "脚", py: "jiǎo" }, options: pics,
           answer: 1, answered: 2, show_pinyin: true });
check("redraw of the answered round keeps the colours", w.cards()[2].classList.contains("wrong"));

// next round: picture -> word, pinyin hidden
w.render({ sid: "g1", round: 1, prompt: { kind: "image", img: IMG }, options: words,
           answer: 0, answered: null, show_pinyin: false });
check("a new round is a fresh board", w.cards().every((b) => !b.disabled && !b.classList.contains("right")));
check("word cards without pinyin when asked", w.cards()[0].textContent === "手");
w.cards()[0].click();
check("right tap shows green", w.cards()[0].classList.contains("right") && w.values().pop().chosen === 0);

// a restored game comes back showing its answer
const w2 = board();
w2.render({ sid: "g2", round: 4, prompt: null, options: pics, answer: 3, answered: 3, show_pinyin: true },
          { base: "dark" });
check("listening round has no prompt card", w2.document.getElementById("prompt").innerHTML === "");
check("restored answered round, dark theme",
      w2.cards()[3].classList.contains("right") && w2.cards()[0].disabled && w2.document.body.classList.contains("dark"));

console.log(failed ? `${failed} failed` : "all passed");
process.exit(failed ? 1 : 0);
