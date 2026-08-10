const fs=require("fs"),{JSDOM}=require("jsdom");
let html=fs.readFileSync("/home/claude/w/Chinese_Study-main/pinyin-immersion-app/src/hw_component/index.html","utf-8");
html=html.replace(/<script src="https:\/\/cdn[^"]*"><\/script>/,"");
const dom=new JSDOM(html,{url:"http://localhost/",runScripts:"dangerously",pretendToBeVisual:true,
 beforeParse(w){w.__msgs=[];w.parent.postMessage=m=>w.__msgs.push(m);
  w.navigator.vibrate=()=>{};w.speechSynthesis={getVoices:()=>[],cancel(){},speak(){}};
  w.SpeechSynthesisUtterance=function(){};w.__writers=[];
  w.HanziWriter={loadCharacterData:()=>Promise.resolve({strokes:new Array(5)}),
   create:(t,ch,cfg)=>{const o={ch,cfg,quizOpts:null,quiz(q){this.quizOpts=q;},
     animateCharacter(x){setTimeout(()=>x&&x.onComplete&&x.onComplete(),0);},
     highlightStroke(){},cancelQuiz(){}};w.__writers.push(o);return o;}};}});
const w=dom.window,sleep=ms=>new Promise(r=>setTimeout(r,ms));
const lw=()=>w.__writers[w.__writers.length-1];
function ok(c,m){if(!c){console.error("FAIL "+m);process.exit(1);}console.log("  ok "+m);}
(async()=>{
 await sleep(20);
 // a well-practised character carries a strict leniency
 const s={session_id:"p1",mode:"standard",chars:[{character:"的",is_new:false,stroke_count:8,
   char_pinyin:"de",word:"我的",word_pinyin:"wǒ de",word_english:"my",char_gloss:"possessive",
   freq_label:"#1 most common",leniency:0.79,precision_level:9}]};
 w.dispatchEvent(new w.MessageEvent("message",{data:{type:"streamlit:render",args:{session:s}}}));
 await sleep(60);
 ok(lw().cfg!==undefined,"writer created");
 ok(lw().quizOpts.leniency===0.79,"graded quiz uses the character's earned leniency ("+lw().quizOpts.leniency+")");
 ok(w.document.getElementById("app").textContent.includes("precision 9/10"),"precision level shown on card");
 // a new character gets the generous default
 const s2={session_id:"p2",mode:"standard",chars:[{character:"一",is_new:false,stroke_count:1,
   char_pinyin:"yī",word:"一",word_pinyin:"yī",word_english:"one",char_gloss:"one",
   leniency:1.25,precision_level:0}]};
 w.dispatchEvent(new w.MessageEvent("message",{data:{type:"streamlit:render",args:{session:s2}}}));
 await sleep(60);
 ok(lw().quizOpts.leniency===1.25,"new character gets the generous setting");
 ok(!w.document.getElementById("app").textContent.includes("precision 0/10"),"level 0 chip hidden (no clutter)");
 // missing leniency must not break older cached sessions
 const s3={session_id:"p3",mode:"standard",chars:[{character:"人",is_new:false,stroke_count:2,
   char_pinyin:"rén",word:"人",word_pinyin:"rén",word_english:"person",char_gloss:"person"}]};
 w.dispatchEvent(new w.MessageEvent("message",{data:{type:"streamlit:render",args:{session:s3}}}));
 await sleep(60);
 ok(lw().quizOpts.leniency===1.0,"falls back to 1.0 when leniency is absent");
 console.log("\nCOMPONENT PRECISION TESTS PASS");process.exit(0);
})().catch(e=>{console.error(e);process.exit(1);});
