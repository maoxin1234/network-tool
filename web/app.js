/* ═══════════════ 网络检测修复工具 — 前端逻辑 ═══════════════ */

const $  = (s, r=document) => r.querySelector(s);
const $$ = (s, r=document) => [...r.querySelectorAll(s)];
const api = () => window.pywebview.api;

/* ─── 配置 ─── */
const CHECK_ITEMS = [
  {id:"internet", ttl:"互联网连接", desc:"测试能否访问外网服务器", ico:"⬡", bg:"#EBF3FB", fg:"#005FB8"},
  {id:"dns",      ttl:"DNS 解析",  desc:"测试域名解析是否正常",   ico:"◎", bg:"#EDF7ED", fg:"#0E7A0E"},
  {id:"ping",     ttl:"网络延迟",  desc:"Ping 测试延迟与丢包率",  ico:"↯", bg:"#FFF4CE", fg:"#C77700"},
  {id:"vpn",      ttl:"VPN / 代理", desc:"检测代理状态、类型与风险", ico:"⛨", bg:"#F3EDFA", fg:"#7B4FB5"},
];

const REPAIR_ITEMS = [
  {id:"flush_dns",    ttl:"刷新 DNS 缓存", desc:"清除本地 DNS 缓存，解决域名解析异常", warn:"⚠ 安全操作，不影响正常使用", ico:"🗂", admin:false},
  {id:"reset_proxy",  ttl:"清除代理设置",  desc:"关闭系统代理，修复代理导致的连接问题", warn:"⚠ 会关闭当前代理",        ico:"🔗", admin:false},
  {id:"reset_winsock",ttl:"重置 Winsock", desc:"重置 Windows 网络协议栈",            warn:"⚠ 需要重启计算机生效",    ico:"⚙", admin:true},
  {id:"reset_ip",     ttl:"释放并更新 IP",desc:"重新获取 IP 地址，解决 IP 冲突",      warn:"⚠ 操作期间短暂断网",      ico:"🔄", admin:true},
  {id:"reset_adapter",ttl:"重置网络适配器",desc:"重置所有网络适配器到默认配置",        warn:"⚠ 需要重启计算机生效",    ico:"🔌", admin:true},
];

const REPAIR_LABEL = {
  flush_dns:"🗂 刷新 DNS", reset_proxy:"🔗 清除代理",
  reset_winsock:"⚙ 重置 Winsock", reset_ip:"↺ 更新 IP", reset_adapter:"⚙ 重置适配器",
};
const SUGGEST = {
  internet:["reset_ip","reset_adapter","reset_winsock"],
  dns:["flush_dns","reset_proxy"],
  ping:["reset_winsock","flush_dns"],
};
const RISK_BADGE = {none:"good", low:"good", medium:"warning", high:"bad"};
const RISK_CLASS = {none:"ok", low:"ok", medium:"wf", high:"fail"};

let isAdmin = false;
let lastResults = {};
let checking = false, speeding = false;

/* ─── 工具 ─── */
function toast(msg){
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(t._t); t._t = setTimeout(()=>t.classList.remove("show"), 1800);
}
function copyText(text){
  const ta = document.createElement("textarea");
  ta.value = text; document.body.appendChild(ta); ta.select();
  try{ document.execCommand("copy"); toast("已复制"); }catch(e){}
  ta.remove();
}

/* ═══════════════ 导航 ═══════════════ */
$$(".nav-item").forEach(b=>{
  b.onclick = ()=>{
    $$(".nav-item").forEach(x=>x.classList.remove("active"));
    b.classList.add("active");
    const pid = b.dataset.page;
    $$(".page").forEach(p=>p.classList.remove("active"));
    $("#page-"+pid).classList.add("active");
    if(pid==="info")    refreshInfo();
    if(pid==="history") renderHistory();
  };
});
const curPage = ()=> $(".nav-item.active").dataset.page;

document.addEventListener("keydown", e=>{
  if(e.key==="F5"){
    e.preventDefault();
    const p = curPage();
    if(p==="check" && !checking) runCheck();
    else if(p==="speed" && !speeding) startSpeed();
    else if(p==="info") refreshInfo();
  }
});

/* ═══════════════ 一键检测 ═══════════════ */
function buildCheckCards(){
  $("#checkCards").innerHTML = CHECK_ITEMS.map(it=>`
    <div class="card" id="cc-${it.id}">
      <div class="check-item">
        <div class="check-ico" style="background:${it.bg};color:${it.fg}">${it.ico}</div>
        <div class="check-body">
          <div class="ttl">${it.ttl}</div>
          <div class="desc">${it.desc}</div>
          <div class="res">—</div>
        </div>
        <div class="badge"></div>
      </div>
      <div class="sub" hidden></div>
    </div>`).join("");
}
function setBadge(id, state){ $(`#cc-${id} .badge`).className = "badge "+state; }
function setRes(id, text, cls){
  const el = $(`#cc-${id} .res`); el.textContent = text;
  el.style.color = cls==="ok" ? "var(--success)" : cls==="fail" ? "var(--danger)"
                 : cls==="wf" ? "var(--warn-fg)" : "var(--td)";
}

async function runCheck(){
  if(checking) return; checking = true;
  lastResults = {};
  $("#btnCheck").disabled = true;
  $("#checkSummary").innerHTML = "";
  CHECK_ITEMS.forEach(it=>{
    setBadge(it.id,"running"); setRes(it.id,"检测中…","");
    const sub = $(`#cc-${it.id} .sub`); sub.hidden = true; sub.innerHTML = "";
  });

  const steps = [
    ["internet", ()=>api().check_internet()],
    ["dns",      ()=>api().check_dns()],
    ["ping",     ()=>api().check_ping()],
    ["vpn",      ()=>api().check_vpn()],
  ];
  for(let i=0;i<steps.length;i++){
    const [id, fn] = steps[i];
    setProg("#checkProg", i/steps.length*100);
    $("#checkProgTxt").textContent = `检测 ${i+1} / ${steps.length}…`;
    const r = await fn();
    lastResults[id] = r;
    if(id==="vpn") renderVpn(r);
    else{
      const ok = r.status==="ok";
      setBadge(id, ok?"good":"bad");
      setRes(id, (ok?"✓ ":"✗ ")+r.summary, ok?"ok":"fail");
      if(!ok) renderSuggest(id);
    }
  }
  setProg("#checkProg",100);
  $("#checkProgTxt").textContent = "检测完成";
  $("#btnCheck").disabled = false;
  checking = false;
  renderSummary();
  api().save_history(lastResults);
}

function renderSuggest(id){
  const ids = SUGGEST[id]||[]; if(!ids.length) return;
  const sub = $(`#cc-${id} .sub`); sub.hidden = false;
  sub.innerHTML = `<div class="sub-row"><span class="sub-label">建议修复：</span>
    ${ids.map(rid=>`<button class="chip-btn" data-r="${rid}">${REPAIR_LABEL[rid]}</button>`).join("")}
    <span class="sub-line" style="margin:0 0 0 auto" id="fb-${id}"></span></div>`;
  $$(`#cc-${id} .chip-btn`).forEach(b=>{
    b.onclick = async ()=>{
      b.disabled = true; const fb = $(`#fb-${id}`); fb.textContent = "修复中…"; fb.className="sub-line wf";
      const res = await api().run_repair(b.dataset.r);
      fb.textContent = res.msg; fb.className = "sub-line "+(res.ok?"ok":"fail");
      b.disabled = false;
    };
  });
}

function renderVpn(r){
  const level = r.risk_level || "none";
  setBadge("vpn", RISK_BADGE[level]||"good");
  if(r.active){
    setRes("vpn", "⚠ "+r.summary+" · 风险"+r.risk_label, RISK_CLASS[level]);
    const sub = $("#cc-vpn .sub"); sub.hidden = false;
    sub.innerHTML = `
      <div class="risk-tag ${RISK_CLASS[level]}">⛨ 风险等级：${r.risk_label}</div>
      ${r.names&&r.names.length?`<div class="sub-line">检测到：${r.names.join("；")}</div>`:""}
      ${(r.reasons||[]).map(x=>`<div class="sub-line">· ${x}</div>`).join("")}`;
  }else{
    setRes("vpn","✓ 未使用 VPN / 代理","ok");
  }
}

function renderSummary(){
  const conn = Object.entries(lastResults).filter(([k,v])=>!v.informational && k!=="vpn");
  const okN = conn.filter(([,v])=>v.status==="ok").length;
  const total = conn.length, allOk = okN===total;
  $("#checkSummary").innerHTML = `
    <div class="card" style="display:flex;align-items:center;gap:14px">
      <div style="font-size:26px">${allOk?"✅":"⚠️"}</div>
      <div style="flex:1">
        <div style="font-size:15px;font-weight:700;color:${allOk?'var(--success)':'var(--warn-fg)'}">
          ${allOk?"网络状态良好":`发现 ${total-okN} 项异常`}</div>
        <div class="muted">${allOk?`全部 ${total} 项通过`:`${okN} / ${total} 项通过`}</div>
      </div>
      ${allOk?"":`<button class="btn btn-warn btn-sm" onclick="document.querySelector('[data-page=repair]').click()">前往修复</button>`}
    </div>`;
}

/* ═══════════════ 网速测试 ═══════════════ */
const GAUGE_LEN = 251.3;
function setGauge(speed){
  const ratio = Math.min(speed/100, 1);
  const fill = $("#gaugeFill");
  fill.style.strokeDashoffset = GAUGE_LEN*(1-ratio);
  fill.style.stroke = ratio>=0.65 ? "var(--success)" : ratio>=0.25 ? "var(--accent)" : "var(--warn-fg)";
  $("#speedNum").textContent = speed>0 ? speed.toFixed(1) : "—";
  $("#speedNum").style.color = fill.style.stroke;
}
function setProg(sel, pct){ $(sel).style.width = Math.max(0,Math.min(100,pct))+"%"; }

let speedSrcMap = {};
async function buildSpeedSources(){
  const names = await api().speed_sources();
  speedSrcMap = {};
  $("#speedSources").innerHTML = names.map((n,i)=>`
    <div class="src-row">
      <div class="src-name">${n}</div>
      <div class="src-bar"><i id="sb-${i}"></i></div>
      <div class="src-val" id="sv-${i}">等待…</div>
    </div>`).join("");
  names.forEach((n,i)=> speedSrcMap[n] = i);
}

function startSpeed(){
  if(speeding) return; speeding = true;
  $("#btnSpeed").disabled = true; $("#btnSpeedStop").disabled = false;
  setGauge(0); setProg("#speedProg",0);
  $("#speedStatus").textContent = "连接测速源中…";
  $$("#speedDetail b").forEach(b=>b.textContent="测速中…");
  Object.values(speedSrcMap).forEach(i=>{ $(`#sb-${i}`).style.width="0"; $(`#sv-${i}`).textContent="等待…"; $(`#sv-${i}`).style.color="var(--td)"; });
  api().start_speed_test();
}
$("#btnSpeedStop").onclick = ()=>{ api().stop_speed_test(); $("#speedStatus").textContent="正在停止…"; };

/* 后端推送回调 */
window.onSpeedStatus = (text, pct)=>{ $("#speedStatus").textContent = text; setProg("#speedProg", pct); };
window.onSpeedLive = (spd, name)=>{
  setGauge(spd);
  const i = speedSrcMap[name];
  if(i!==undefined){ $(`#sb-${i}`).style.width = Math.min(spd/100*100,100)+"%";
    $(`#sv-${i}`).textContent = spd.toFixed(1)+" Mbps ↗"; $(`#sv-${i}`).style.color="var(--accent)"; }
};
window.onSpeedSource = (name, spd, ok, err)=>{
  const i = speedSrcMap[name]; if(i===undefined) return;
  if(ok){ $(`#sb-${i}`).style.width = Math.min(spd/100*100,100)+"%";
    $(`#sv-${i}`).textContent = spd.toFixed(1)+" Mbps"; $(`#sv-${i}`).style.color="var(--success)"; }
  else  { $(`#sb-${i}`).style.width="0"; $(`#sv-${i}`).textContent="失败"; $(`#sv-${i}`).style.color="var(--danger)"; }
};
window.onSpeedDone = (res, cancelled)=>{
  speeding = false; $("#btnSpeed").disabled=false; $("#btnSpeedStop").disabled=true;
  if(cancelled){ $("#speedStatus").textContent="已取消"; return; }
  if(!res){ setGauge(0); $("#speedStatus").textContent="所有测速源均不可达";
    $$("#speedDetail b").forEach(b=>{b.textContent="—";}); return; }
  setGauge(res.best); setProg("#speedProg",100); $("#speedStatus").textContent="测速完成";
  const m = {avg:res.avg+" Mbps", peak:res.peak+" Mbps", dl_mb:res.dl_mb+" MB",
            el:res.el+" 秒", src:res.src, grade:res.grade};
  $$("#speedDetail b").forEach(b=> b.textContent = m[b.dataset.k] ?? "—");
};

/* ═══════════════ 智能修复 ═══════════════ */
function buildRepairCards(){
  $("#repairWarn").hidden = isAdmin;
  $("#repairCards").innerHTML = REPAIR_ITEMS.map(it=>`
    <div class="card">
      <div class="repair-item">
        <div class="repair-ico">${it.ico}</div>
        <div class="repair-body">
          <div class="ttl">${it.ttl}${it.admin&&!isAdmin?'<small>需要管理员</small>':''}</div>
          <div class="desc">${it.desc}</div>
          <div class="warn">${it.warn}</div>
          <div class="st" id="rst-${it.id}"></div>
        </div>
        <button class="btn btn-outline btn-sm" data-r="${it.id}">执行</button>
      </div>
    </div>`).join("");
  $$("#repairCards button[data-r]").forEach(b=>{
    b.onclick = async ()=>{
      b.disabled = true; const st = $(`#rst-${b.dataset.r}`);
      st.textContent="修复中…"; st.className="st wf";
      const res = await api().run_repair(b.dataset.r);
      st.textContent = res.msg; st.className = "st "+(res.ok?"ok":"fail");
      b.disabled = false;
      toast(res.ok?"修复完成":"修复失败");
    };
  });
}

/* ═══════════════ 网络信息 ═══════════════ */
async function refreshInfo(){
  $("#btnInfoRefresh").disabled = true;
  $("#infoCards").innerHTML = `<div class="muted" style="padding:8px">读取中…</div>`;
  const info = await api().get_network_info();
  const rows = [
    ["💻","主机名", info.hostname||"未知"],
    ["🌐","IPv4 地址",(info.ipv4||["无法获取"]).join("\n")],
    ["🚪","默认网关", info.gateway||"无法获取"],
    ["🔗","MAC 地址", info.mac||"未知"],
    ["📡","DNS 服务器",(info.dns_servers||["自动获取"]).join("\n")],
  ];
  $("#infoCards").innerHTML = rows.map(([e,l,v])=>`
    <div class="card">
      <div class="info-item">
        <div class="info-emoji">${e}</div>
        <div class="info-body"><div class="lbl">${l}</div><div class="val">${v}</div></div>
        <button class="btn btn-outline btn-sm" data-c="${v.replace(/\n/g,'  ').replace(/"/g,'&quot;')}">复制</button>
      </div>
    </div>`).join("");
  $$("#infoCards button[data-c]").forEach(b=> b.onclick=()=>copyText(b.dataset.c));
  $("#btnInfoRefresh").disabled = false;
}
$("#btnInfoRefresh").onclick = refreshInfo;

/* ═══════════════ 检测历史 ═══════════════ */
const HNAME = {internet:"互联网", dns:"DNS", ping:"延迟", vpn:"VPN"};
async function renderHistory(){
  const recs = await api().get_history();
  if(!recs || !recs.length){
    $("#historyList").innerHTML = `<div class="card empty">
      <div class="big">📋</div><div class="t">暂无历史记录</div>
      <div class="muted">在"一键检测"完成检测后，结果将自动保存到此处</div></div>`;
    return;
  }
  $("#historyList").innerHTML = recs.map(rec=>{
    const rs = rec.results||{};
    const conn = Object.entries(rs).filter(([k])=>k!=="vpn");
    const allOk = conn.every(([,v])=>v.status==="ok");
    return `<div class="card hist-card">
      <div class="ts">${allOk?"✅":"⚠️"} ${rec.ts||""}</div>
      <div class="hist-grid">
        ${Object.entries(rs).map(([sid,v])=>{
          const ok = v.status==="ok";
          return `<div class="hist-col">
            <div class="h-name ${ok?'ok':'fail'}">${ok?'✓':'✗'} ${HNAME[sid]||sid}</div>
            <div class="h-sum">${(v.summary||"").replace(/^[✓✗⚠]\s*/,'')}</div></div>`;
        }).join("")}
      </div></div>`;
  }).join("");
}

/* ═══════════════ 启动 ═══════════════ */
async function init(){
  buildCheckCards();
  buildSpeedSources();
  try{ const a = await api().get_admin(); isAdmin = a.admin; }catch(e){}
  const chip = $("#adminChip");
  chip.classList.add(isAdmin?"ok":"no");
  $("#adminText").textContent = isAdmin ? "管理员模式" : "普通用户（部分修复受限）";
  buildRepairCards();
}
window.addEventListener("pywebviewready", init);
