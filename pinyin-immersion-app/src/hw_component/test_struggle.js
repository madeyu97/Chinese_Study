const fs=require("fs"), {JSDOM}=require("jsdom");
let html=fs.readFileSync("/home/claude/extract/Chinese_Study-main/pinyin-immersion-app/src/hw_component/index.html","utf-8");
html=html.replace(/<script src="https:\/\/cdn[^"]*"><\/script>/,"");
const dom=new JSDOM(html,{url:"http://localhost/",runScripts:"dangerously",pretendToBeVisual:true,
 beforeParse(w){
  w.__msgs=[]; w.parent.postMessage=(m)=>w.__msgs.push(m);
  w.navigator.vibrate=()=>{}; w.speechSynthesis={getVoices:()=>[],cancel(){},speak(){}};
  w.SpeechSynthesisUtterance=function(){};
  w.__writers=[];
  w.HanziWriter={loadCharacterData:()=>Promise.resolve({strokes:new Array(3)}),
   create:(t,ch,cfg)=>{const wr={ch,cfg,quizOpts:null,
     animateCharacter(o){setTimeout(()=>o&&o.onComplete&&o.onComplete(),0);},
     quiz(o){this.quizOpts=o;},highlightStroke(){},cancelQuiz(){},
     done(m){for(let k=0;k<m;k++)this.quizOpts.onMistake&&this.quizOpts.onMistake({});
             this.quizOpts.onComplete&&this.quizOpts.onComplete({});}};
     w.__writers.push(wr);return wr;}};
 }});
const w=dom.window, sleep=ms=>new Promise(r=>setTimeout(r,ms));
const lw=()=>w.__writers[w.__writers.length-1];
const vals=()=>w.__msgs.filter(m=>m.type==="streamlit:setComponentValue");
function ok(c,m){if(!c){console.error("FAIL "+m);process.exit(1);}console.log("  ok "+m);}
(async()=>{
 await sleep(20);
 // STRUGGLE MODE: one char, must graduate on 2 consecutive cleans
 const session={session_id:"s1",mode:"struggle",chars:[
   {character:"惯",is_new:false,stroke_count:3,char_pinyin:"guàn",word:"习惯",word_pinyin:"xí guàn",word_english:"habit"}]};
 w.dispatchEvent(new w.MessageEvent("message",{data:{type:"streamlit:render",args:{session}}}));
 await sleep(30);
 // attempt 1: 2 mistakes (not clean) -> should requeue (queue grows)
 lw().done(2); await sleep(50);
 w.document.getElementById("tap-next").onclick(); await sleep(20);
 // attempt 2: clean -> streak 1, still requeue
 lw().done(0); await sleep(50);
 w.document.getElementById("tap-next").onclick(); await sleep(20);
 // attempt 3: clean -> streak 2 -> graduate, session ends
 lw().done(0); await sleep(50);
 w.document.getElementById("tap-next").onclick(); await sleep(30);
 const v=vals()[vals().length-1].value;
 ok(v.results.length===3,"struggle: char drilled 3× until clean-twice ("+v.results.length+")");
 ok(v.done===true,"struggle: session ends after graduating");
 const g=v.results.map(r=>r.mistakes);
 ok(g[0]===2&&g[1]===0&&g[2]===0,"struggle: mistake counts recorded per attempt");
 ok(w.document.getElementById("summary").style.display!=="none","summary shown");

 // STANDARD MODE: >3 mistakes requeues later in same session
 const s2={session_id:"s2",mode:"standard",chars:[
   {character:"A",is_new:false,stroke_count:3,char_pinyin:"a",word:"A",word_pinyin:"a",word_english:"x"},
   {character:"B",is_new:false,stroke_count:3,char_pinyin:"b",word:"B",word_pinyin:"b",word_english:"y"}]};
 w.dispatchEvent(new w.MessageEvent("message",{data:{type:"streamlit:render",args:{session:s2}}}));
 await sleep(30);
 lw().done(5); await sleep(50);           // A: 5 mistakes -> requeue
 w.document.getElementById("tap-next").onclick(); await sleep(20);
 lw().done(0); await sleep(50);           // B clean
 w.document.getElementById("tap-next").onclick(); await sleep(20);
 lw().done(0); await sleep(50);           // A again (requeued)
 w.document.getElementById("tap-next").onclick(); await sleep(30);
 const v2=vals()[vals().length-1].value;
 const chars=v2.results.map(r=>r.character).join("");
 ok(v2.results.length===3,"standard: badly-missed char requeued (3 attempts for 2 chars)");
 ok(chars.indexOf("A")!==chars.lastIndexOf("A"),"standard: 'A' appears twice");
 console.log("\nALL COMPONENT STRUGGLE/REQUEUE TESTS PASS");process.exit(0);
})().catch(e=>{console.error(e);process.exit(1);});
