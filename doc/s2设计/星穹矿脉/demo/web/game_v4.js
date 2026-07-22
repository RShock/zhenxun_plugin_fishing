(function () {
  "use strict";
  var CFG={core:1e8,pulses:4,daySeconds:12,secondExponent:308,depthScale:2e5,mineralNoise:.02,exactCycleLimit:64};
  var SECOND_NEED=10n**BigInt(CFG.secondExponent);
  var disturbance=function(ore,pulse){return 1+CFG.mineralNoise*[-1,.5,1,-.5][(ore+pulse)%4]};
  var projectStable=function(prefix,sample,count){return{resets:prefix.resets+count,days:prefix.days+BigInt(sample.days)*count,reward:prefix.reward+BigInt(sample.reward)*count}};
  window.XQKM_EXTRAPOLATION={SECOND_NEED:SECOND_NEED,disturbance:disturbance,projectStable:projectStable,formula:"总量=精确前缀+稳定态单循环×剩余轮数"};
  var ORES=[
    {key:"stone",name:"猫砂石",rarity:"N",layer:"风化壳",unlock:0,base:9,cost:8,cg:1.74,pg:2.04,weight:1,color:"#64748b"},
    {key:"copper",name:"铜须矿",rarity:"R",layer:"浅岩层",unlock:.12,base:3.2,cost:24,cg:1.76,pg:2.08,weight:2.2,color:"#2563eb"},
    {key:"amethyst",name:"紫晶猫眼",rarity:"SR",layer:"晶簇层",unlock:.32,base:1,cost:90,cg:1.78,pg:2.12,weight:5,color:"#7c3aed"},
    {key:"gold",name:"金猫锭",rarity:"SSR",layer:"熔金层",unlock:.58,base:.28,cost:360,cg:1.8,pg:2.16,weight:12,color:"#b45309"},
    {key:"rainbow",name:"虹核晶",rarity:"UR",layer:"星核层",unlock:.82,base:.06,cost:1800,cg:1.82,pg:2.2,weight:30,color:"#dc2626"}
  ];
  var TECHS=[
    {key:"start",name:"整备协议",cost:3,need:3,text:"自动开局并预升猫砂石"},
    {key:"upgrade",name:"升级协议",cost:3,need:6,text:"自动购买矿物等级"},
    {key:"layer",name:"地层协议",cost:3,need:9,text:"自动确认新地层"},
    {key:"reset",name:"无限协议",cost:3,need:12,text:"自动执行一阶无限"}
  ];
  function id(x){return document.getElementById(x)}
  function fmt(x){return x<1e6?Math.floor(x).toLocaleString("zh-CN"):x.toExponential(2)}
  function fresh(){return{day:1,dayProgress:0,mining:false,depth:0,resets:0,shards:0,spent:0,tech:{},lv:[0,0,0,0,0],stock:[0,0,0,0,0],open:[true,false,false,false,false],manual:0,cycleDay:1,pulseIndex:0,logs:[],won:false,extrapolation:null}}
  var st=fresh(),speed=1,acc=0,last=performance.now(),toastTimer=0;
  function has(k){return !!st.tech[k]}
  function mult(){return Math.pow(1.18,Object.keys(st.tech).length)}
  function log(s,c){st.logs.unshift({s:s,c:c||""});st.logs=st.logs.slice(0,80)}
  function toast(s){id("toast").textContent=s;id("toast").classList.add("show");clearTimeout(toastTimer);toastTimer=setTimeout(function(){id("toast").classList.remove("show")},1400)}
  function beginCycle(){st.depth=0;st.lv=[0,0,0,0,0];st.stock=[0,0,0,0,0];st.open=[true,false,false,false,false];st.cycleDay=1;st.pulseIndex=0;st.manual=0;if(has("start")){st.lv[0]=2;st.stock[0]=16}else{st.manual++;log("手动整备新矿区","up")}}
  function cost(i){return ORES[i].cost*Math.pow(ORES[i].cg,st.lv[i])}
  function buy(i,auto){if(!st.open[i]||st.stock[i]<cost(i))return false;st.stock[i]-=cost(i);st.lv[i]++;if(!auto)st.manual++;return true}
  function discover(){var r=st.depth/CFG.core;ORES.forEach(function(o,i){if(!st.open[i]&&r>=o.unlock){st.open[i]=true;if(!has("layer")){st.manual++;log("手动确认 "+o.layer+" · "+o.name,"inf")}else log("地层协议发现 "+o.name,"inf")}})}
  function autoUpgrades(){if(!has("upgrade"))return;ORES.forEach(function(_,i){for(var n=0;n<2;n++)if(!buy(i,true))break})}
  function pulse(){if(!st.mining||st.won)return;var gain=0;ORES.forEach(function(o,i){if(st.open[i]){var expected=o.base*Math.pow(o.pg,st.lv[i])*mult()/CFG.pulses,q=expected*disturbance(i,st.pulseIndex);st.stock[i]+=q;gain+=q*o.weight*CFG.depthScale}});st.pulseIndex++;st.depth+=gain;discover();autoUpgrades();if(st.depth>=CFG.core)firstOrder()}
  function firstOrder(){if(!has("reset")){st.manual++;st.mining=false;log("已挖穿：请手动执行一阶无限","win");toast("等待一阶无限");return}doReset()}
  function doReset(){if(st.depth<CFG.core)return false;var sampleDays=st.cycleDay;st.resets++;st.shards++;log("一阶无限 #"+st.resets+"：库存、等级、自动化与进度全部清除；获得 1 星核","inf");if(Object.keys(st.tech).length===4){var prefix={resets:BigInt(st.resets),days:BigInt(st.day),reward:BigInt(st.shards)},remaining=SECOND_NEED-prefix.resets,projected=projectStable(prefix,{days:sampleDays,reward:1},remaining);st.extrapolation={sampleDays:sampleDays,cycles:remaining,totalDays:projected.days,totalReward:projected.reward};st.won=true;st.mining=false;id("winText").textContent="已精确模拟 "+st.resets+" 轮；稳定态完整单循环耗时 "+sampleDays+" 日。其余 "+remaining.toString()+" 轮已按单循环批量外推，未逐轮遍历。";id("winModal").classList.add("show");return true}beginCycle();return true}
  function buyTech(k){var t=TECHS.filter(function(x){return x.key===k})[0];if(!t||has(k)||st.resets<t.need||st.shards<t.cost)return;st.shards-=t.cost;st.spent+=t.cost;st.tech[k]=true;log("购买永久科技："+t.name,"win");toast(t.name+" 已永久生效")}
  function advance(days){var p=days*CFG.pulses+acc,n=Math.floor(p);acc=p-n;for(var i=0;i<n;i++)pulse();st.dayProgress+=days;while(st.dayProgress>=1&&!st.won){st.dayProgress--;st.day++;st.cycleDay++}}
  function currentLayer(){var r=st.depth/CFG.core,x=ORES[0];ORES.forEach(function(o){if(r>=o.unlock)x=o});return x.layer}
  function renderShop(){id("shop").innerHTML=TECHS.map(function(t){var owned=has(t.key),locked=st.resets<t.need,ok=!owned&&!locked&&st.shards>=t.cost;return'<div class="upgrade '+(locked?'locked':'')+'"><div class="upgrade-body"><div class="name"><span class="label">'+t.name+'</span><span class="pill">'+(owned?'已永久解锁':t.cost+' 星核')+'</span></div><div class="meta">'+t.text+' · 一阶 #'+t.need+' 后可购</div></div><button data-tech="'+t.key+'" '+(ok?'':'disabled')+'>'+(owned?'已购买':'购买')+'</button></div>'}).join("")}
  function render(){var r=Math.min(1,st.depth/CFG.core),p=st.won?1:0;id("coinsVal").textContent=st.shards+" 星核";id("depthVal").textContent=fmt(st.depth)+" / 1e8";id("depthBar").style.width=(r*100)+"%";id("depthBarLabel").textContent=(r*100).toFixed(2)+"% · "+currentLayer();id("dayBar").style.width=(st.dayProgress*100)+"%";id("dayBarLabel").textContent="D"+st.day+" · 本轮 D"+st.cycleDay;id("progressVal").textContent=(st.dayProgress*100).toFixed(1)+"%";id("intervalVal").textContent=has("upgrade")?"升级已自动":"每日低频访问";id("qtyVal").textContent=st.open.filter(Boolean).length+" / 5";id("dptVal").textContent="×"+mult().toFixed(2);id("inf1Val").textContent=(p*100).toFixed(1)+"%";id("ticksVal").textContent=st.won?"10^308 / 10^308":st.resets+" / 10^308";id("sessionLabel").textContent=st.won?"已通关":st.mining?"挖矿中":st.depth>=CFG.core?"等待一阶无限":"已停工";id("runPill").textContent=st.mining?"挖矿中":"空闲";id("dayPill").textContent="D"+st.day;id("infPill").textContent="二阶 "+(p*100).toFixed(1)+"%";id("upPill").textContent="本轮手动 "+st.manual;id("autoPill").textContent="永久科技 "+Object.keys(st.tech).length+"/4";id("settleMode").textContent="一阶无限 #"+st.resets;id("speedLabel").textContent="1日≈"+(CFG.daySeconds/speed).toFixed(1)+"s · ×"+speed;id("btnStart").disabled=st.mining||st.won||st.depth>=CFG.core;id("btnStop").disabled=!st.mining;id("btnDay").textContent=st.depth>=CFG.core&&!has("reset")?"一阶无限":"次日";renderShop();id("oreGrid").innerHTML=ORES.map(function(o,i){return'<div class="ore"><div class="name" style="color:'+o.color+'">'+o.rarity+' '+o.name+'</div><div class="qty">'+(st.open[i]?fmt(st.stock[i])+" · Lv."+st.lv[i]:"未发现")+'</div></div>'}).join("");id("rarityBars").innerHTML=ORES.map(function(o,i){return'<div class="rb"><div class="rb-name" style="color:'+o.color+'">'+o.rarity+'</div><div class="track"><i style="width:'+Math.min(100,st.lv[i]*5)+'%;background:'+o.color+'"></i></div><div class="rb-pct">Lv.'+st.lv[i]+'</div></div>'}).join("");id("log").innerHTML=st.logs.length?st.logs.map(function(x){return'<div class="e '+x.c+'">'+x.s+'</div>'}).join(""):'<div class="e">前三次需完整手动重玩；一阶无限会清除本轮全部内容。</div>'}
  function init(){beginCycle();id("btnStart").onclick=function(){st.mining=true;log("开始挖矿","up");render()};id("btnStatus").onclick=render;id("btnStop").onclick=function(){st.mining=false;log("结束挖矿并结算","up");render()};id("btnDay").onclick=function(){if(st.depth>=CFG.core&&!has("reset"))doReset();else advance(1-st.dayProgress+.0001);render()};id("shop").onclick=function(e){var b=e.target.closest("button[data-tech]");if(b)buyTech(b.dataset.tech);render()};id("oreGrid").onclick=function(){if(has("upgrade"))return;for(var n=0;n<3;n++){var best=-1;ORES.forEach(function(_,i){if(st.open[i]&&st.stock[i]>=cost(i)&&(best<0||st.lv[i]<st.lv[best]))best=i});if(best<0)break;buy(best,false)}render()};document.querySelectorAll("button[data-speed]").forEach(function(b){b.onclick=function(){speed=Number(b.dataset.speed);render()}});id("btnReset").onclick=function(){st=fresh();speed=1;acc=0;id("winModal").classList.remove("show");beginCycle();render()};log("S2 v4.2 · 稳定态单循环批量外推","day");render();requestAnimationFrame(frame)}
  function frame(t){var dt=Math.min(.25,(t-last)/1000);last=t;if(st.mining&&!st.won)advance(speed/CFG.daySeconds*dt);render();requestAnimationFrame(frame)}
  window.S2MiningDemo={config:CFG,ores:ORES,techs:TECHS,snapshot:function(){return JSON.parse(JSON.stringify(st,function(_,v){return typeof v==="bigint"?v.toString():v}))},start:function(){st.mining=true},advanceDays:function(d){advance(d);render()},firstOrder:doReset,reset:function(){st=fresh();beginCycle();render()}};
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();
})();
