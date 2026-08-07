const fs=require("fs"), {JSDOM}=require("jsdom");
let html=fs.readFileSync("/home/claude/w/Chinese_Study-main/pinyin-immersion-app/src/hw_component/index.html","utf-8");
html=html.replace(/<script src="https:\/\/cdn[^"]*"><\/script>/,"");
const dom=new JSDOM(html,{url:"http://localhost/",runScripts:"dangerously",pretendToBeVisual:true,
 beforeParse(w){
  w.__msgs=[]; w.parent.postMessage=m=>w.__msgs.push(m);
  w.navigator.vibrate=()=>{}; w.speechSynthesis={getVoices:()=>[],cancel(){},speak(){}};
  w.SpeechSynthesisUtterance=function(){};
  w.__writers=[];
  w.HanziWriter={loadCharacterData:()=>Promise.resolve({strokes:new Array(8)}),
   create:(t,ch,cfg)=>{const o={ch,cfg,quiz(q){this.q=q;},animateCharacter(x){setTimeout(()=>x&&x.onComplete&&x.onComplete(),0);},highlightStroke(){},cancelQuiz(){}};w.__writers.push(o);return o;}};
 }});
const w=dom.window, sleep=ms=>new Promise(r=>setTimeout(r,ms));
function ok(c,m){if(!c){console.error("FAIL "+m);process.exit(1);}console.log("  ok "+m);}
(async()=>{
 await sleep(20);
 const session={session_id:"s1",mode:"standard",chars:[{
   character:"的", is_new:false, stroke_count:8, char_pinyin:"de",
   word:"我的猫", word_pinyin:"wǒ de māo", word_english:"my cat",
   char_gloss:"of / ~'s (possessive particle)", freq_rank:1,
   freq_label:"#1 most common"}]};
 w.dispatchEvent(new w.MessageEvent("message",{data:{type:"streamlit:render",args:{session}}}));
 await sleep(60);
 const text=w.document.getElementById("app").textContent;
 ok(text.includes("#1 most common"), "frequency rating shown on the card");
 ok(text.includes("possessive particle"), "character's own definition shown");
 ok(text.includes("This character:"), "definition is labelled distinctly from the word");
 ok(!text.includes("的"), "the answer character is still NOT revealed anywhere");
 ok(w.document.querySelectorAll("#masked-word .blank").length===1, "target still masked in the word");
 ok(text.includes("my cat"), "word context still present");
 // a character with no gloss must not leave an empty box
 const s2={session_id:"s2",mode:"standard",chars:[{character:"龘",is_new:true,stroke_count:48,
   char_pinyin:"dá", word:"龘", word_pinyin:"dá", word_english:"", char_gloss:"", freq_label:"rare"}]};
 w.dispatchEvent(new w.MessageEvent("message",{data:{type:"streamlit:render",args:{session:s2}}}));
 await sleep(60);
 ok(w.document.getElementById("char-gloss").style.display==="none","empty definition box hidden");
 console.log("\nCUE RENDERING TESTS PASS");process.exit(0);
})().catch(e=>{console.error(e);process.exit(1);});
