(() => {
  "use strict";

  const STORAGE_KEY = "zhenxun.s2.starry.lab.v1";
  const SAVE_VERSION = 1;
  const CASTS_PER_DAY = 140;
  const EFFORT_TARGET = 1200;
  const MIRACLE_TARGET = 7777777;
  const MIRACLE_MOD = 10000000;
  const MAX_FISH_RENDER = 80;

  const LOCATIONS = ["牛奶河","月影湾","寂静海","碎星滩","银砂湖","永夜港","天穹瀑","彗尾溪","零光沼","星门彼岸"];
  const WEATHER = {
    lost_wind:{name:"迷途风",symbol:"〰",desc:"迷途风穿过水面，星光若隐若现。"},
    solar_wind:{name:"太阳风",symbol:"☼",desc:"太阳粒子照亮鱼线，星空鱼出现率提升 50%。"},
    meteor_shower:{name:"流星雨",symbol:"☄",desc:"每条星空鱼生成两次，留下评分更高的一条。"},
    hengjiyuan:{name:"恒纪元",symbol:"◌",desc:"宇宙进入稳定纪元，星空鱼的数字质量显著提高。"}
  };
  const POOL_NAMES = {none:"无奖励",low:"低级奖池",middle:"中级奖池",high:"高级奖池",ultimate:"究极奖池"};
  const ITEM_INFO = {
    corn:["玉米","普通补给品","◒"],black_market_extra_ticket:["黑商额外兑换券","可突破黑商兑换次数","券"],
    lottery_fragment_low:["中级抽奖碎片","5 个自动兑换中级奖励","碎"],wish_score:["0.5 积分","愿望积分奖励","✦"],
    duoduo_potion:["真多多药水","复制最终生成的星空鱼，持续 12 竿","∞"],lucky_potion:["幸运药水","额外生成一组并择优，持续 24 竿","☘"],
    reset_potion:["回档药水","恢复今天全部垂钓次数","↶"],cat_frame:["猫框","用于升级星空木框","猫"],
    lottery_fragment_mid:["高级抽奖碎片","5 个自动兑换高级奖励","碎"],flash_potion:["闪光药水","三种星空天气合一，持续 8 竿","ϟ"],
    time_potion:["时光药水","立即完整模拟并进入次日","时"],utr_select_ticket:["UTR 自选券","解锁后可自选同地图 UTR 鱼","UTR"],
    lottery_fragment_high:["究极抽奖碎片","5 个自动兑换究极奖励","碎"]
  };
  const REWARD_POOLS = {
    low:[{key:"corn",count:1},{key:"black_market_extra_ticket",count:1},{key:"lottery_fragment_low",count:1},{key:"wish_score",count:1,score:.5}],
    middle:[{key:"duoduo_potion",count:1},{key:"lucky_potion",count:1},{key:"reset_potion",count:1},{key:"cat_frame",count:3},{key:"lottery_fragment_mid",count:1}],
    high:[{key:"flash_potion",count:1},{key:"time_potion",count:1},{key:"utr_select_ticket",count:1},{key:"lottery_fragment_high",count:1}],
    ultimate:[{key:"time_potion",count:10},{key:"utr_select_ticket",count:10}]
  };

  const FEATURE_SCORE = {
    "3_same_run":1.432856,"4_same_run":2.552842,"5_same_run":3.721246,"6_same_run":5,
    "3_step_high":1.227224,"4_step_high":2.402305,"5_step_high":3.638272,"6_step_high":5,
    "3_slide":.757901,"4_slide":1.517984,"5_slide":2.368759,"6_slide":3.337242,
    "3_pure_snake":1.180417,"4_pure_snake":1.874649,"5_pure_snake":2.698536,"6_pure_snake":3.653647,
    "3_snake":1.180417,"4_snake":1.567993,"5_snake":2.133004,"6_snake":2.838033,
    "3_palindrome":.505804,"4_palindrome":1.570086,"5_palindrome":1.705313,"6_palindrome":3.004365,
    "6_all_small_0_4":1.806180,"6_all_big_5_9":1.806180,"6_all_odd":1.806180,"6_all_even":1.806180,
    ABAB:1.598599,ABCABC:3.142668,star_airplane:1.899285,two_pair:1.359121,three_pair:3.091515,
    full_house:2.454693,chunk_sequence:2.658763,pihu:.802444
  };
  const DIRECT_LABEL = {"6_all_small_0_4":"6位全小(0-4)","6_all_big_5_9":"6位全大(5-9)","6_all_odd":"6位全奇","6_all_even":"6位全偶",ABAB:"ABAB",ABCABC:"ABCABC",star_airplane:"星空飞机",two_pair:"两对",three_pair:"三对",full_house:"葫芦",chunk_sequence:"连号",pihu:"屁胡"};
  const SUFFIX = {same_run:"同号连段",step_high:"步步高",slide:"滑梯",pure_snake:"纯正贪吃蛇",snake:"贪吃蛇",palindrome:"回文"};

  const $ = id => document.getElementById(id);
  const qsa = selector => [...document.querySelectorAll(selector)];
  const clamp = (n,min,max) => Math.max(min,Math.min(max,n));
  const randomChoice = arr => arr[Math.floor(Math.random()*arr.length)];
  const formatId = value => String(Number(value)).padStart(6,"0");
  const esc = value => String(value).replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
  const nowTime = () => new Date().toLocaleTimeString("zh-CN",{hour:"2-digit",minute:"2-digit",hour12:false});

  function defaultState(){
    return {version:SAVE_VERSION,day:1,castsLeft:CASTS_PER_DAY,weather:rollWeather(),effort:0,totalScore:0,tickets:0,coins:0,
      allFish:[],items:{},starFrames:0,celestialFrameLevel:0,starryFrameLevel:0,totalCasts:0,totalStarry:0,totalMiracles:0,
      buffs:{lucky:0,flash:0,duoduo:0},debug:{weather:"auto",forceDrop:false,infiniteCasts:false,lucky:false,flash:false,duoduo:false},
      logs:[],lastCatch:null,uid:1,createdAt:Date.now(),updatedAt:Date.now()};
  }
  function normalizeState(raw){
    const base=defaultState(); const s=Object.assign(base,raw||{});
    s.items=Object.assign({},base.items,raw?.items||{}); s.buffs=Object.assign({},base.buffs,raw?.buffs||{}); s.debug=Object.assign({},base.debug,raw?.debug||{});
    s.allFish=Array.isArray(raw?.allFish)?raw.allFish:[]; s.logs=Array.isArray(raw?.logs)?raw.logs.slice(0,80):[];
    s.castsLeft=clamp(Number(s.castsLeft)||0,0,CASTS_PER_DAY); s.day=Math.max(1,Number(s.day)||1); s.uid=Math.max(Number(s.uid)||1,s.allFish.length+1);
    return s;
  }
  function load(){try{const raw=localStorage.getItem(STORAGE_KEY);return raw?normalizeState(JSON.parse(raw)):defaultState()}catch(e){console.warn(e);return defaultState()}}
  let state=load(), toastTimer=null, saveTimer=null, quiet=false, queued={tickets:0,miracles:0};
  function save(immediate=false){
    clearTimeout(saveTimer); const run=()=>{state.updatedAt=Date.now();localStorage.setItem(STORAGE_KEY,JSON.stringify(state));updateStorageSize();$("saveBtn").querySelector("span").textContent="已保存"};
    $("saveBtn").querySelector("span").textContent="保存中"; if(immediate)run();else saveTimer=setTimeout(run,180);
  }
  function toast(msg){clearTimeout(toastTimer);const el=$("toast");el.textContent=msg;el.classList.add("show");toastTimer=setTimeout(()=>el.classList.remove("show"),2100)}
  function log(text,type="normal"){state.logs.unshift({text,type,day:state.day,time:nowTime()});state.logs=state.logs.slice(0,60)}
  function rollWeather(){const r=Math.random();return r<.5?"lost_wind":r<2/3?"solar_wind":r<5/6?"meteor_shower":"hengjiyuan"}
  function effectiveWeather(){return state.debug.weather!=="auto"?state.debug.weather:state.weather}
  function activeBuff(name){return !!state.debug[name] || Number(state.buffs[name]||0)>0}

  function digitsOf(value){return formatId(value).split("").map(Number)}
  function sign(n){return n>0?1:n<0?-1:0}
  function windowSame(d,s,l){for(let i=1;i<l;i++)if(d[s+i]!==d[s])return false;return true}
  function windowStep(d,s,l){const diff=d[s+1]-d[s];if(diff!==1&&diff!==-1)return false;for(let i=2;i<l;i++)if(d[s+i]-d[s+i-1]!==diff)return false;return true}
  function windowSlide(d,s,l){const dif=[];for(let i=1;i<l;i++)dif.push(d[s+i]-d[s+i-1]);return dif.every(x=>x===0||x===1)||dif.every(x=>x===0||x===-1)}
  function windowSnake(d,s,l,pure){let prev=0,moved=false,turned=false;for(let i=1;i<l;i++){const diff=d[s+i]-d[s+i-1];if(pure){if(diff!==1&&diff!==-1)return false}else if(diff<-1||diff>1)return false;const dir=sign(diff);if(dir){moved=true;if(prev&&dir!==prev)turned=true;prev=dir}}return moved&&turned}
  function windowPalindrome(d,s,l){for(let i=0;i<Math.floor(l/2);i++)if(d[s+i]!==d[s+l-1-i])return false;return true}
  function motifAbab(d,s){return d[s]===d[s+2]&&d[s+1]===d[s+3]&&d[s]!==d[s+1]}
  function motifAbcabc(d){const [a,b,c]=d;return a===d[3]&&b===d[4]&&c===d[5]&&new Set([a,b,c]).size===3}
  function chunkSequence(d){const a=[d[0]*10+d[1],d[2]*10+d[3],d[4]*10+d[5]];if(a[1]-a[0]===a[2]-a[1]&&Math.abs(a[1]-a[0])===1)return"2+2+2";const x=d[0]*100+d[1]*10+d[2],y=d[3]*100+d[4]*10+d[5];return Math.abs(y-x)===1?"3+3":null}
  function starAirplane(d){for(let i=1;i<5;i++)if(d[i]!==d[i-1]&&d[i]!==d[i+1])return false;return true}
  function exactPairRuns(d){const out=[];for(let i=0;i<d.length;){let e=i+1;while(e<d.length&&d[e]===d[i])e++;if(e-i===2)out.push([i,e]);i=e}return out}
  function fullHouse(d,s){const w=d.slice(s,s+5);if(w.length<5)return false;const runs=[];for(let i=0;i<5;){let e=i+1;while(e<5&&w[e]===w[i])e++;runs.push(e-i);i=e}return runs.join(",")==="3,2"||runs.join(",")==="2,3"}
  function contained(ok,start,length){for(let big=length+1;big<=6;big++)for(let bs=0;bs<=6-big;bs++)if(bs<=start&&start+length<=bs+big&&ok.get(`${bs}:${big}`))return true;return false}
  function labelCn(label){if(DIRECT_LABEL[label])return DIRECT_LABEL[label];const idx=label.indexOf("_");return `${label.slice(0,idx)}位${SUFFIX[label.slice(idx+1)]||label.slice(idx+1)}`}
  function rewardPool(score){return score<=0?"none":score<=2?"low":score<=5?"middle":score<=10?"high":"ultimate"}
  function band(score){return score===0?"普通":score<=2?"小吉":score<=4?"良品":score<=6?"稀有":score<=8?"珍品":score<=10?"极品":score<=12?"传说":"神话"}
  function makeFeature(label,family,span,note=""){return{label,family,span,note,score:FEATURE_SCORE[label],name:labelCn(label)}}
  function scoreFish(value){
    const d=digitsOf(value),ok={};for(const family of ["same_run","step_high","slide","pure_snake","snake","palindrome"])ok[family]=new Map();
    for(let len=3;len<=6;len++)for(let start=0;start<=6-len;start++){
      ok.same_run.set(`${start}:${len}`,windowSame(d,start,len));ok.step_high.set(`${start}:${len}`,windowStep(d,start,len));ok.slide.set(`${start}:${len}`,windowSlide(d,start,len));
      ok.pure_snake.set(`${start}:${len}`,windowSnake(d,start,len,true));ok.snake.set(`${start}:${len}`,windowSnake(d,start,len,false));ok.palindrome.set(`${start}:${len}`,windowPalindrome(d,start,len));
    }
    const f=[];
    if(d.every(x=>x<=4))f.push(makeFeature("6_all_small_0_4","range","1-6"));if(d.every(x=>x>=5))f.push(makeFeature("6_all_big_5_9","range","1-6"));
    if(d.every(x=>x%2===1))f.push(makeFeature("6_all_odd","parity","1-6"));if(d.every(x=>x%2===0))f.push(makeFeature("6_all_even","parity","1-6"));if(starAirplane(d))f.push(makeFeature("star_airplane","star_airplane","1-6"));
    for(let len=3;len<=6;len++)for(let start=0;start<=6-len;start++){const key=`${start}:${len}`,span=`${start+1}-${start+len}`;
      if(ok.same_run.get(key)&&!contained(ok.same_run,start,len))f.push(makeFeature(`${len}_same_run`,`same_run`,span));
      if(ok.slide.get(key)&&!contained(ok.slide,start,len))f.push(makeFeature(`${len}_${ok.step_high.get(key)?"step_high":"slide"}`,ok.step_high.get(key)?"step_high":"slide",span));
      if(ok.snake.get(key)&&!contained(ok.snake,start,len))f.push(makeFeature(`${len}_${ok.pure_snake.get(key)?"pure_snake":"snake"}`,ok.pure_snake.get(key)?"pure_snake":"snake",span));
      if(ok.palindrome.get(key)&&!contained(ok.palindrome,start,len))f.push(makeFeature(`${len}_palindrome`,`palindrome`,span));
    }
    for(let s=0;s<=2;s++)if(motifAbab(d,s))f.push(makeFeature("ABAB","rhythm",`${s+1}-${s+4}`));if(motifAbcabc(d))f.push(makeFeature("ABCABC","rhythm","1-6"));
    const pairs=exactPairRuns(d);if(pairs.length>=2){const lab=pairs.length>=3?"three_pair":"two_pair";f.push(makeFeature(lab,"pairs",`${pairs[0][0]+1}-${pairs[pairs.length-1][1]}`))}
    const spans=[];for(let s=0;s<=1;s++)if(fullHouse(d,s))spans.push([s,s+5]);if(spans.length)f.push(makeFeature("full_house","full_house",`${spans[0][0]+1}-${spans[spans.length-1][1]}`));
    const seq=chunkSequence(d);if(seq)f.push(makeFeature("chunk_sequence","chunk_sequence","1-6",seq));
    const counts={};d.forEach(x=>counts[x]=(counts[x]||0)+1);if(!f.length&&Math.max(...Object.values(counts))>=3){const hot=Object.keys(counts).filter(k=>counts[k]>=3).map(Number);const pos=digits.map((d,i)=>hot.includes(d)?i:-1).filter(i=>i>=0);const parts=[];let s=pos[0],p=pos[0];for(let i=1;i<pos.length;i++){const x=pos[i];if(x===p+1){p=x;continue;}parts.push(s===p?String(s+1):(s+1)+"-"+(p+1));s=p=x;}parts.push(s===p?String(s+1):(s+1)+"-"+(p+1));f.push(makeFeature("pihu","pihu",parts.join(",")));}
    f.sort((a,b)=>b.score-a.score||a.span.localeCompare(b.span)||a.label.localeCompare(b.label));const raw=f.reduce((a,x)=>a+x.score,0),display=Math.floor(raw+.5);
    return{id:Number(value),idText:formatId(value),rawScore:raw,displayScore:display,features:f,pool:rewardPool(display),band:band(display)};
  }

  function generateId(heng){if(heng){let out="";for(let i=0;i<6;i++)out+=randomChoice("2345678");return Number(out)}return Math.floor(Math.random()*1000000)}
  function better(a,b){return a.rawScore!==b.rawScore?(a.rawScore>b.rawScore?a:b):(a.id>b.id?a:b)}
  function rollStarry(){
    const weather=effectiveWeather(),flash=activeBuff("flash"),solar=weather==="solar_wind"||flash,meteor=weather==="meteor_shower"||flash,heng=weather==="hengjiyuan"||flash,lucky=activeBuff("lucky");
    let rate=.05*(solar?1.5:1)*(flash?1.5:1);if(state.debug.forceDrop)rate=1;if(Math.random()>=rate)return null;
    const group=()=>{let best=scoreFish(generateId(heng));if(meteor)best=better(best,scoreFish(generateId(heng)));return best};
    let best=group();if(lucky)best=better(best,group());return best;
  }

  function addItem(key,count=1){state.items[key]=(state.items[key]||0)+count}
  function drawReward(pool,depth=0){
    if(!REWARD_POOLS[pool])return null;const item={...randomChoice(REWARD_POOLS[pool])};addItem(item.key,item.count);if(item.score){state.totalScore+=item.score;state.effort+=item.score}
    if(depth<8){const chain={lottery_fragment_low:"middle",lottery_fragment_mid:"high",lottery_fragment_high:"ultimate"};const next=chain[item.key];if(next)while((state.items[item.key]||0)>=5){state.items[item.key]-=5;const upgraded=drawReward(next,depth+1);log(`5 枚碎片自动升级：${upgraded.name} ×${upgraded.count}`,"reward")}}
    return{...item,name:ITEM_INFO[item.key]?.[0]||item.key,pool};
  }
  function galleryFish(){return [...state.allFish].filter(f=>f.displayScore>=4).sort((a,b)=>b.displayScore-a.displayScore||b.rawScore-a.rawScore||a.id-b.id).slice(0,10)}
  function bagFish(){const ids=new Set(galleryFish().map(f=>f.uid));return state.allFish.filter(f=>!ids.has(f.uid))}
  function addFish(scored,{reward=true,check=true}={}){
    const entry={uid:state.uid++,id:scored.id,idText:scored.idText,rawScore:scored.rawScore,displayScore:scored.displayScore,band:scored.band,pool:scored.pool,features:scored.features.map(x=>({label:x.label,name:x.name,score:x.score})),day:state.day,location:11+((state.day-1)%10)};
    state.allFish.push(entry);state.totalStarry++;state.totalScore+=entry.displayScore;state.effort+=entry.displayScore;
    const prize=reward?drawReward(entry.pool):null;checkTickets();if(check)checkMiracle();return{entry,prize};
  }
  function checkTickets(){while(state.effort>=EFFORT_TARGET){state.effort-=EFFORT_TARGET;state.tickets++;queued.tickets++;log(`努力值达标，获得第 ${state.tickets} 张 S2 入场券！`,"reward");if(!quiet)showModal("ticketModal")}}

  function subsetIndices(values){
    if(values.length<8)return null;const candidates=values.map((v,i)=>({v:Number(v.id)%MIRACLE_MOD,i})).sort((a,b)=>b.v-a.v||b.i-a.i).slice(0,26).sort((a,b)=>a.i-b.i);
    const n=candidates.length,mid=Math.floor(n/2),left=candidates.slice(0,mid),right=candidates.slice(mid),map=new Map(),ls=1<<left.length,rs=1<<right.length;
    const sumsL=new Array(ls).fill(0);for(let i=0;i<left.length;i++){const bit=1<<i;for(let mask=0;mask<bit;mask++)sumsL[mask|bit]=sumsL[mask]+left[i].v}
    for(let mask=0;mask<ls;mask++){const k=sumsL[mask]%MIRACLE_MOD;if(!map.has(k))map.set(k,mask)}
    const sumsR=new Array(rs).fill(0);for(let i=0;i<right.length;i++){const bit=1<<i;for(let mask=0;mask<bit;mask++)sumsR[mask|bit]=sumsR[mask]+right[i].v}
    for(let rm=0;rm<rs;rm++){const need=(MIRACLE_TARGET-(sumsR[rm]%MIRACLE_MOD)+MIRACLE_MOD)%MIRACLE_MOD,lm=map.get(need);if(lm===undefined||(lm===0&&rm===0))continue;const out=[];for(let i=0;i<left.length;i++)if(lm&(1<<i))out.push(left[i].i);for(let i=0;i<right.length;i++)if(rm&(1<<i))out.push(right[i].i);if(out.length)return out}
    return null;
  }
  function checkMiracle(){
    const bag=bagFish();if(bag.length<8)return;const indices=subsetIndices(bag);if(!indices)return;const used=indices.map(i=>bag[i]),uids=new Set(used.map(f=>f.uid));state.allFish=state.allFish.filter(f=>!uids.has(f.uid));state.starFrames++;state.totalMiracles++;queued.miracles++;
    log(`奇迹命中 7777777：消耗 ${used.length} 条星空鱼，获得星辰木框 ×1`,"reward");$("miracleText").textContent=`${used.length} 条背包星空鱼的编号之和命中七个 7，已转化为第 ${state.starFrames} 个星辰木框。`;if(!quiet)showModal("miracleModal");
  }

  const NORMAL_FISH=["银鳞鱼","月光鳐","奶油鲤","星砂鳗","玻璃水母","彗尾鲫"];
  function consumeBuffs(){for(const k of ["lucky","flash","duoduo"])if(state.buffs[k]>0)state.buffs[k]--}
  function cast({silent=false}={}){
    if(state.castsLeft<=0&&!state.debug.infiniteCasts)return null;if(!state.debug.infiniteCasts)state.castsLeft--;state.totalCasts++;state.coins+=5+Math.floor(Math.random()*13);
    const normal=randomChoice(NORMAL_FISH),starry=rollStarry();let last=null;
    if(starry){const copies=activeBuff("duoduo")?2:1;const rewards=[];for(let i=0;i<copies;i++){const added=addFish(starry);last=added.entry;if(added.prize)rewards.push(added.prize)}
      const prizeText=rewards.length?rewards.map(r=>`${r.name}×${r.count}`).join("、"):"无额外奖励";log(`⭐ ${starry.idText} · ${starry.displayScore}分 ${starry.features.slice(0,2).map(x=>x.name).join(" + ")||"无显著番型"}；${prizeText}`,"starry");state.lastCatch={...last,rewardText:prizeText,copies};
    }else log(`钓到 ${normal}，获得 ${5+Math.floor(Math.random()*8)} 枚鱼币。`);
    consumeBuffs();if(!silent)render();return state.lastCatch;
  }

  function advanceDay({simulateRemaining=true,silent=false}={}){
    if(simulateRemaining)while(state.castsLeft>0)cast({silent:true});state.day++;state.castsLeft=CASTS_PER_DAY;state.weather=rollWeather();
    log(`进入第 ${state.day} 天，${WEATHER[effectiveWeather()].name}笼罩 ${LOCATIONS[(state.day-1)%10]}。`,"reward");if(!silent){render();toast(`已进入第 ${state.day} 天 · ${WEATHER[effectiveWeather()].name}`)}
  }
  function simulateDays(days){
    const count=Math.max(1,Number(days)||1),before={fish:state.totalStarry,tickets:state.tickets,miracles:state.totalMiracles,score:state.totalScore};quiet=true;queued={tickets:0,miracles:0};
    for(let i=0;i<count;i++)advanceDay({simulateRemaining:true,silent:true});quiet=false;render();save();
    toast(`模拟 ${count} 天：+${state.totalStarry-before.fish} 鱼 · +${Math.round((state.totalScore-before.score)*10)/10} 分${state.tickets>before.tickets?` · +${state.tickets-before.tickets} 券`:""}`);
  }
  function simulateToTicket(){const target=state.tickets+1,before=state.day;quiet=true;queued={tickets:0,miracles:0};let guard=365;while(state.tickets<target&&guard-->0)advanceDay({simulateRemaining:true,silent:true});quiet=false;render();save();toast(state.tickets>=target?`用 ${state.day-before} 天获得下一张 S2 入场券`:`365 天内未达标，请检查调试数值`)}

  function useItem(key){
    if((state.items[key]||0)<=0)return toast("该道具数量不足");
    if(key==="lucky_potion"){state.items[key]--;state.buffs.lucky+=24;toast("幸运药水生效 24 竿")}
    else if(key==="flash_potion"){state.items[key]--;state.buffs.flash+=8;toast("伽马射线暴生效 8 竿")}
    else if(key==="duoduo_potion"){state.items[key]--;state.buffs.duoduo+=12;toast("真多多药水生效 12 竿")}
    else if(key==="reset_potion"){state.items[key]--;state.castsLeft=CASTS_PER_DAY;toast("今日垂钓次数已恢复")}
    else if(key==="time_potion"){state.items[key]--;advanceDay({simulateRemaining:true,silent:true});toast("时光流转，已进入次日")}
    else return toast("该道具在实验室中为展示用途");log(`使用道具：${ITEM_INFO[key][0]}`,"reward");render();save();
  }
  function upgradeFrame(type){const isStarry=type==="starry",level=isStarry?state.starryFrameLevel:state.celestialFrameLevel,cost=level+1;if(level>=10)return toast("该木框已经满级");const owned=isStarry?(state.items.cat_frame||0):state.starFrames;if(owned<cost)return toast(`需要 ${cost} 个${isStarry?"猫框":"星辰木框"}`);if(isStarry){state.items.cat_frame-=cost;state.starryFrameLevel++}else{state.starFrames-=cost;state.celestialFrameLevel++}log(`${isStarry?"星空木框":"星辰展示栏"}强化至 ${level+1} 级`,"reward");render();save();toast("强化成功")}

  function showModal(id){const el=$(id);el.classList.add("open");el.setAttribute("aria-hidden","false")}
  function hideModal(id){const el=$(id);el.classList.remove("open");el.setAttribute("aria-hidden","true")}
  function render(){renderHeader();renderBuffs();renderCatch();renderLog();renderBag();renderGallery();renderDebug();save()}
  function renderHeader(){
    const w=effectiveWeather(),info=WEATHER[w];$("heroCard").className=`hero-card weather-${w}`;$("dayLabel").textContent=`第 ${state.day} 天`;$("locationLabel").textContent=`${LOCATIONS[(state.day-1)%10]} · ${11+(state.day-1)%10}图`;$("weatherDesc").textContent=info.desc;$("weatherSymbol").textContent=info.symbol;$("weatherName").textContent=info.name;
    $("castsLeft").textContent=state.debug.infiniteCasts?"∞":state.castsLeft;$("castsMax").textContent=CASTS_PER_DAY;$("effortValue").textContent=Math.round(state.effort*10)/10;$("effortTarget").textContent=EFFORT_TARGET;$("effortBar").style.width=`${clamp(state.effort/EFFORT_TARGET*100,0,100)}%`;$("starryCount").textContent=state.totalStarry;$("scoreValue").textContent=Math.round(state.totalScore*10)/10;$("ticketValue").textContent=state.tickets;$("castBtn").disabled=state.castsLeft<=0&&!state.debug.infiniteCasts;
  }
  function renderBuffs(){const w=effectiveWeather(),flash=activeBuff("flash");const data=[
    ["掉率",state.debug.forceDrop?"100%":`${(.05*((w==="solar_wind"||flash)?1.5:1)*(flash?1.5:1)*100).toFixed(2).replace(/\.00$/,"")}%`,true],
    ["☘",`幸运${activeBuff("lucky")?"开启":"关闭"}`,activeBuff("lucky")],["ϟ",`闪光${flash?"开启":"关闭"}`,flash],["∞",`多多${activeBuff("duoduo")?"开启":"关闭"}`,activeBuff("duoduo")]
  ];$("buffStrip").innerHTML=data.map(x=>`<div class="buff-chip ${x[2]?"on":""}"><b>${x[0]}</b>${x[1]}</div>`).join("")}
  function renderCatch(){const c=state.lastCatch;if(!c){$("catchEmpty").classList.remove("hidden");$("catchResult").classList.add("hidden");return}$("catchEmpty").classList.add("hidden");$("catchResult").classList.remove("hidden");$("resultFishId").textContent=c.idText;$("resultScore").textContent=c.displayScore;$("resultBand").textContent=c.band;$("resultFeatures").innerHTML=(c.features.length?c.features:[{name:"无显著番型"}]).slice(0,6).map(f=>`<span>${esc(f.name)}</span>`).join("");$("resultReward").textContent=`${POOL_NAMES[c.pool]} · ${c.rewardText||"无奖励"}${c.copies>1?" · 多多复制×2":""}`;$("resultTime").textContent=`第${c.day}天`;$("catchCard").classList.remove("pulse");requestAnimationFrame(()=>$("catchCard").classList.add("pulse"))}
  function renderLog(){const el=$("timeline");el.innerHTML=state.logs.length?state.logs.slice(0,24).map(x=>`<div class="log-row ${x.type}"><i></i><p>${esc(x.text)}</p><b>D${x.day} ${x.time}</b></div>`).join(""):`<div class="timeline-empty">还没有记录，先抛出第一竿吧。</div>`}
  function renderBag(){
    const bag=bagFish().sort((a,b)=>b.day-a.day||b.displayScore-a.displayScore);$("bagCapacity").textContent=`${bag.length} 条`;
    $("fishInventory").innerHTML=bag.length?`<div class="fish-grid">${bag.slice(0,MAX_FISH_RENDER).map(f=>`<article class="fish-tile pool-${f.pool}"><i class="pool-dot"></i><div class="id">${f.idText}</div><div class="meta"><span>D${f.day} · ${f.location}图</span><b>${f.displayScore} 分</b></div><div class="traits">${esc(f.features.slice(0,2).map(x=>x.name).join(" + ")||"无显著番型")}</div></article>`).join("")}</div>${bag.length>MAX_FISH_RENDER?`<div class="timeline-empty">仅展示最新 ${MAX_FISH_RENDER} 条，共 ${bag.length} 条</div>`:""}`:`<div class="empty-panel"><b>背包空空如也</b>高分鱼会进入展馆，其余星空鱼留在这里参与奇迹。</div>`;
    const keys=Object.keys(ITEM_INFO);$("itemInventory").innerHTML=`<div class="item-list">${keys.map(k=>{const n=state.items[k]||0,usable=["lucky_potion","flash_potion","duoduo_potion","reset_potion","time_potion"].includes(k);return`<article class="item-row"><div class="item-icon">${ITEM_INFO[k][2]}</div><div class="item-info"><b>${ITEM_INFO[k][0]}</b><small>${ITEM_INFO[k][1]}</small></div><strong>×${n}</strong>${usable?`<button class="frame-upgrade" style="width:46px" data-use-item="${k}" ${n?"":"disabled"}>使用</button>`:""}</article>`}).join("")}</div>`;
    const cat=state.items.cat_frame||0,starCost=state.starryFrameLevel+1,celCost=state.celestialFrameLevel+1;$("frameInventory").innerHTML=`<div class="item-list"><article class="item-row"><div class="item-icon">✧</div><div class="item-info"><b>星空木框 · Lv.${state.starryFrameLevel}/10</b><small>展示最贵的鱼，签到奖励 ×4 · 持有猫框 ${cat}</small><button class="frame-upgrade" data-upgrade="starry" ${state.starryFrameLevel>=10||cat<starCost?"disabled":""}>消耗 ${starCost} 猫框强化</button></div></article><article class="item-row"><div class="item-icon">✦</div><div class="item-info"><b>星辰展示栏 · Lv.${state.celestialFrameLevel}/10</b><small>奇迹产物 · 持有星辰木框 ${state.starFrames}</small><button class="frame-upgrade" data-upgrade="celestial" ${state.celestialFrameLevel>=10||state.starFrames<celCost?"disabled":""}>消耗 ${celCost} 星辰木框强化</button></div></article></div>`;
  }
  function renderGallery(){const list=galleryFish();$("galleryList").innerHTML=list.length?list.map((f,i)=>`<article class="gallery-entry"><div class="rank">${String(i+1).padStart(2,"0")}</div><div><div class="gid">${f.idText}</div><small>${esc(f.features.slice(0,3).map(x=>x.name).join(" + ")||"无显著番型")} · D${f.day}</small></div><strong>${f.displayScore}</strong></article>`).join(""):`<div class="empty-panel"><b>展馆尚未点亮</b>获得至少 4 分的星空鱼后，它会自动陈列于此。</div>`}
  function renderDebug(){
    $("forceDrop").checked=state.debug.forceDrop;$("infiniteCasts").checked=state.debug.infiniteCasts;$("dbgLucky").checked=state.debug.lucky;$("dbgFlash").checked=state.debug.flash;$("dbgDuoduo").checked=state.debug.duoduo;qsa("#weatherDebug button").forEach(b=>b.classList.toggle("active",b.dataset.weather===state.debug.weather));updateStorageSize();
  }
  function updateStorageSize(){const raw=localStorage.getItem(STORAGE_KEY)||JSON.stringify(state);$("storageSize").textContent=`${(new Blob([raw]).size/1024).toFixed(1)} KB`}

  function bind(){
    qsa(".bottom-nav button").forEach(btn=>btn.addEventListener("click",()=>{qsa(".bottom-nav button").forEach(x=>x.classList.toggle("active",x===btn));qsa(".page").forEach(p=>p.classList.toggle("active",p.dataset.page===btn.dataset.target));scrollTo({top:0,behavior:"smooth"})}));
    qsa(".inventory-tabs button").forEach(btn=>btn.addEventListener("click",()=>{qsa(".inventory-tabs button").forEach(x=>x.classList.toggle("active",x===btn));qsa(".inventory-panel").forEach(p=>p.classList.toggle("active",p.id.toLowerCase().startsWith(btn.dataset.inventory)))}));
    $("castBtn").addEventListener("click",()=>{const before=state.totalStarry;cast();toast(state.totalStarry>before?"星光咬钩！获得星空鱼":"水面泛起普通涟漪")});
    $("autoDayBtn").addEventListener("click",()=>advanceDay({simulateRemaining:true}));$("clearLogBtn").addEventListener("click",()=>{state.logs=[];render();toast("记录已清空")});$("saveBtn").addEventListener("click",()=>{save(true);toast("进度已保存到本机")});
    qsa("[data-sim-days]").forEach(b=>b.addEventListener("click",()=>simulateDays(b.dataset.simDays)));$("simTicketBtn").addEventListener("click",simulateToTicket);
    qsa("#weatherDebug button").forEach(b=>b.addEventListener("click",()=>{state.debug.weather=b.dataset.weather;render();toast(b.dataset.weather==="auto"?"恢复自动天气":`已锁定 ${WEATHER[b.dataset.weather].name}`)}));$("rollWeatherBtn").addEventListener("click",()=>{state.weather=rollWeather();render();toast("今日天气已重抽")});
    for(const [id,key] of [["forceDrop","forceDrop"],["infiniteCasts","infiniteCasts"],["dbgLucky","lucky"],["dbgFlash","flash"],["dbgDuoduo","duoduo"]])$(id).addEventListener("change",e=>{state.debug[key]=e.target.checked;render()});
    qsa("[data-grant]").forEach(b=>b.addEventListener("click",()=>{const k=b.dataset.grant;if(k==="score"){state.effort+=100;state.totalScore+=100;checkTickets()}else if(k==="fish"){quiet=true;for(let i=0;i<10;i++)addFish(scoreFish(generateId(false)));quiet=false}else if(k==="cat")addItem("cat_frame",10);else if(k==="star")state.starFrames+=10;log(`调试注入：${b.textContent.trim()}`,"reward");render();toast("数值已注入")}));
    document.addEventListener("click",e=>{const use=e.target.closest("[data-use-item]");if(use)useItem(use.dataset.useItem);const up=e.target.closest("[data-upgrade]");if(up)upgradeFrame(up.dataset.upgrade)});
    $("miracleOk").addEventListener("click",()=>hideModal("miracleModal"));$("ticketOk").addEventListener("click",()=>hideModal("ticketModal"));
    $("exportBtn").addEventListener("click",()=>{save(true);const blob=new Blob([JSON.stringify(state,null,2)],{type:"application/json"}),a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download=`S2星空垂钓_D${state.day}.json`;a.click();URL.revokeObjectURL(a.href);toast("存档已导出")});
    $("importBtn").addEventListener("click",()=>$("importFile").click());$("importFile").addEventListener("change",async e=>{const file=e.target.files[0];if(!file)return;try{state=normalizeState(JSON.parse(await file.text()));save(true);render();toast("存档导入成功")}catch{toast("存档文件无法识别")}e.target.value=""});
    $("resetBtn").addEventListener("click",()=>{if(!confirm("确定重置 S2 实验室全部本地进度吗？此操作不可撤销。"))return;localStorage.removeItem(STORAGE_KEY);state=defaultState();render();toast("进度已重置")});
    window.addEventListener("beforeunload",()=>save(true));document.addEventListener("visibilitychange",()=>{if(document.hidden)save(true)});
  }

  bind();render();
  window.S2Lab={scoreFish,cast,simulateDays,getState:()=>structuredClone(state)};
})();

