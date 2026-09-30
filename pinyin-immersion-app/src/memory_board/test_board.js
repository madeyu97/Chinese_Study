// Tests for the memory board. Run: node test_board.js  (needs jsdom)
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

const CARDS = [
  { pair: "手", face: "image", img: "data:image/png;base64,AA==", zh: "手", py: "shǒu", en: "hand" },
  { pair: "脚", face: "word", img: "", zh: "脚", py: "jiǎo", en: "foot" },
  { pair: "手", face: "word", img: "", zh: "手", py: "shǒu", en: "hand" },
  { pair: "脚", face: "image", img: "data:image/png;base64,AA==", zh: "脚", py: "jiǎo", en: "foot" },
];

(async () => {
  const w = board();
  check("announces itself to Streamlit", w.__messages.some((m) => m.type === "streamlit:componentReady"));
  w.render({ sid: "s1", cards: CARDS, show_pinyin: true, state: { matched: [], moves: 0 } });
  const c = w.cards();
  check("one tappable button per card, all face down", c.length === 4 && c.every((b) => !b.classList.contains("up")));
  c[0].click();
  check("a tap turns the card over", c[0].classList.contains("up"));
  c[1].click();
  let v = w.values().pop();
  check("a turn is reported: one move, nothing matched", v.sid === "s1" && v.moves === 1 && v.matched.length === 0);
  c[2].click();
  check("taps wait while a wrong pair is showing", !c[2].classList.contains("up"));
  await new Promise((r) => setTimeout(r, 1000));
  check("a wrong pair turns back by itself", !c[0].classList.contains("up") && !c[1].classList.contains("up"));
  c[0].click(); c[2].click();
  v = w.values().pop();
  check("picture + its word is a pair", JSON.stringify(v.matched) === "[0,2]" && v.moves === 2);
  check("a found pair stays up and can't be tapped", c[0].classList.contains("matched") && c[0].disabled);
  check("the word and its meaning are shown", w.document.getElementById("status").textContent.includes("hand"));
  // Python re-renders after each turn: the board keeps its own state
  w.render({ sid: "s1", cards: CARDS, show_pinyin: true, state: { matched: [], moves: 0 } });
  check("a rerun of the same game changes nothing", w.cards()[0].classList.contains("matched"));
  c[1].click(); c[3].click();
  v = w.values().pop();
  check("last pair: everything matched in three turns", v.matched.length === 4 && v.moves === 3);

  // a saved game comes back as it was left
  const w2 = board();
  w2.render({ sid: "s2", cards: CARDS, show_pinyin: false, state: { matched: [0, 2], moves: 5 } });
  check("a resumed game starts from its saved state",
        w2.cards()[0].classList.contains("matched") && w2.document.getElementById("count").textContent.includes("Turns: 5"));
  check("pinyin hidden when asked", !w2.document.body.innerHTML.includes("jiǎo</div>"));
  w2.render({ sid: "s3", cards: CARDS, show_pinyin: true, state: { matched: [], moves: 0 } }, { base: "dark" });
  check("a new game replaces the old board; dark theme followed",
        !w2.cards()[0].classList.contains("matched") && w2.document.body.classList.contains("dark"));

  console.log(failed ? `${failed} failed` : "all passed");
  process.exit(failed ? 1 : 0);
})();
