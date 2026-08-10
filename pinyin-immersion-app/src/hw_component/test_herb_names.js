const fs=require("fs"),{JSDOM}=require("jsdom");
let html=fs.readFileSync("/home/claude/w/Chinese_Study-main/pinyin-immersion-app/src/hw_component/index.html","utf-8");
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
const txt=()=>w.document.getElementById("app").textContent;
function ok(c,m){if(!c){console.error("FAIL "+m);process.exit(1);}console.log("  ok "+m);}
const card=(ch,i,written)=>({character:ch,is_new:false,stroke_count:6,char_pinyin:"x",
  word:"麻黃",word_pinyin:"Má Huáng",word_english:"ephedra",char_gloss:"g",
  group_word:"麻黃",group_index:i,group_total:2,group_written:written,
  herb_tier:1,leniency:1.0,precision_level:0,radicals:[]});
(async()=>{
 await sleep(20);
 w.dispatchEvent(new w.MessageEvent("message",{data:{type:"streamlit:render",
   args:{session:{session_id:"g1",mode:"standard",chars:[card("麻",0,[]),card("黃",1,["麻"])]}}}}));
 await sleep(60);
 // FIRST character: neither char revealed as the answer; 黃 shown dimmed
 ok(!txt().includes("麻"),"writing 麻: the answer is not revealed");
 ok(txt().includes("黃"),"the rest of the name (黃) is visible as context");
 ok(w.document.querySelectorAll("#masked-word .blank").length===1,"one blank box");
 ok(w.document.querySelectorAll("#masked-word .pending").length===1,"upcoming char dimmed");
 ok(txt().includes("character 1 of 2"),"position within the name shown");
 ok(txt().includes("Má Huáng"),"herb pinyin shown");
 // finish it, move to the SECOND character
 lw().quizOpts.onComplete({});
 await sleep(60);
 w.document.getElementById("tap-next").onclick();
 await sleep(60);
 ok(txt().includes("麻"),"writing 黃: the already-written 麻 is now shown");
 ok(!txt().includes("黃"),"…and 黃 itself is hidden");
 ok(w.document.querySelectorAll("#masked-word .done").length===1,"earlier char marked done");
 ok(txt().includes("character 2 of 2"),"position updated");
 // non-herb cards must still work
 w.dispatchEvent(new w.MessageEvent("message",{data:{type:"streamlit:render",
  args:{session:{session_id:"g2",mode:"standard",chars:[{character:"好",is_new:false,
   stroke_count:6,char_pinyin:"hǎo",word:"你好",word_pinyin:"nǐ hǎo",
   word_english:"hello",char_gloss:"good",freq_label:"#82"}]}}}}));
 await sleep(60);
 ok(txt().includes("你")&&!txt().includes("好"),"ordinary vocab cards unchanged");
 console.log("\nHERB NAME DRILL TESTS PASS");process.exit(0);
})().catch(e=>{console.error(e);process.exit(1);});
