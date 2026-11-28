// Sentence writing: characters to come are hidden, ones you can't write yet
// are filled in, the current one is a blank; a struggled character is not
// requeued (the sentence keeps its order).
const fs=require("fs"),{JSDOM}=require("jsdom");
let html=fs.readFileSync(require("path").join(__dirname, "index.html"),"utf-8");
html=html.replace(/<script src="https:\/\/cdn[^"]*"><\/script>/,"");
const dom=new JSDOM(html,{url:"http://localhost/",runScripts:"dangerously",pretendToBeVisual:true,
 beforeParse(w){w.__msgs=[];w.parent.postMessage=m=>w.__msgs.push(m);
  w.navigator.vibrate=()=>{};w.speechSynthesis={getVoices:()=>[],cancel(){},speak(){}};
  w.SpeechSynthesisUtterance=function(){};w.__writers=[];
  w.HanziWriter={loadCharacterData:()=>Promise.resolve({strokes:new Array(6)}),
   create:(t,ch,cfg)=>{const o={ch,cfg,quizOpts:null,quiz(q){this.quizOpts=q;},
     animateCharacter(x){setTimeout(()=>x&&x.onComplete&&x.onComplete(),0);},
     highlightStroke(){},cancelQuiz(){}};w.__writers.push(o);return o;}};}});
const w=dom.window,sleep=ms=>new Promise(r=>setTimeout(r,ms));
const lw=()=>w.__writers[w.__writers.length-1];
const mw=()=>w.document.getElementById("masked-word");
function ok(c,m){if(!c){console.error("FAIL "+m);process.exit(1);}console.log("  ok "+m);}
// 我会说中文。 - you write 我 说 文; 会 and 中 are given
const card=(ch,i,step)=>({character:ch,is_new:false,stroke_count:6,char_pinyin:"x",
  word:"我会说中文。",word_pinyin:"Wǒ huì shuō Zhōngwén.",word_english:"I can speak Chinese.",
  group_word:"我会说中文。",group_index:i,group_total:3,group_step:step,group_given:[1,3],
  group_hide_pending:true,leniency:1.0,precision_level:0});
(async()=>{
 await sleep(20);
 w.dispatchEvent(new w.MessageEvent("message",{data:{type:"streamlit:render",
   args:{session:{session_id:"s1",mode:"sentence",chars:[card("我",0,0),card("说",2,1),card("文",4,2)]}}}}));
 await sleep(60);
 ok(!mw().textContent.includes("我")&&!mw().textContent.includes("说")&&!mw().textContent.includes("文"),
    "writing 我: nothing of yours shown");
 ok(mw().textContent.includes("会")&&mw().textContent.includes("中"),"characters you can't write are given");
 ok(mw().querySelectorAll(".blank").length===1&&mw().querySelectorAll(".hidden-ch").length===2,
    "one blank, the two still to come hidden");
 ok(w.document.getElementById("app").textContent.includes("character 1 of 3"),"position among yours");
 ok(w.document.getElementById("word-english").textContent==="I can speak Chinese.","the English is the cue");
 // struggle badly with 我: no requeue in a sentence
 for(let k=0;k<5;k++) lw().quizOpts.onMistake({});
 lw().quizOpts.onComplete({});
 await sleep(60);
 w.document.getElementById("tap-next").onclick();
 await sleep(60);
 ok(mw().textContent.includes("我")&&!mw().textContent.includes("说"),"next: 我 written, 说 the blank");
 ok(w.document.getElementById("app").textContent.includes("character 2 of 3"),"…the sentence keeps its order");
 console.log("sentence writing: all ok");
 process.exit(0);
})();
