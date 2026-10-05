"""Small dependency-free operations dashboard served by the FastAPI app."""

# The embedded HTML/CSS/JavaScript is intentionally kept as a single response
# document; its browser-oriented lines do not use Python's usual line length.
# ruff: noqa: E501

import json

from fastapi.responses import HTMLResponse


def dashboard_page(api_v1_prefix: str) -> HTMLResponse:
    """Return the dashboard shell; data is loaded from the protected API."""
    page = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Payment Operations Dashboard</title>
  <style>
    :root { color-scheme: dark; --bg:#101828; --panel:#182230; --muted:#9aa8b8; --text:#f4f7fb; --green:#25c281; --red:#fa5c5c; --amber:#ffc857; --line:#314054; }
    * { box-sizing:border-box; } body { margin:0; font:15px/1.4 Inter,ui-sans-serif,system-ui,sans-serif; background:var(--bg); color:var(--text); }
    main { max-width:1240px; margin:auto; padding:32px 20px 56px; } h1 { margin:0; font-size:28px; } h2 { font-size:17px; margin:0 0 14px; } p { color:var(--muted); }
    .top { display:flex; align-items:end; justify-content:space-between; gap:16px; flex-wrap:wrap; margin-bottom:24px; } .controls { display:flex; gap:8px; flex-wrap:wrap; }
    input,select,button { border:1px solid var(--line); background:var(--panel); color:var(--text); border-radius:7px; padding:9px 10px; } input { width:340px; max-width:70vw; } button { cursor:pointer; background:#2864dc; border-color:#2864dc; font-weight:650; }
    .notice { min-height:22px; color:var(--muted); margin:0 0 14px; } .grid { display:grid; gap:14px; grid-template-columns:repeat(4,minmax(0,1fr)); } .panel { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:17px; }
    .value { font-size:28px; font-weight:700; margin-top:6px; } .label { color:var(--muted); font-size:13px; } .processor-grid { display:grid; gap:14px; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); margin:14px 0 24px; }
    .processor-card h3 { margin:0; font-size:16px; } .status { float:right; font-size:11px; font-weight:700; border-radius:99px; padding:4px 8px; } .healthy { background:#123f32; color:#71e0ad; } .unhealthy { background:#532c30; color:#ff9b9b; } .inactive { background:#51462b; color:#ffe19a; }
    .stats { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:15px; } .stats strong { font-size:18px; display:block; }.chart-panel { margin-top:16px; } canvas { width:100%; height:330px; display:block; } .legend { display:flex; gap:14px; flex-wrap:wrap; font-size:12px; color:var(--muted); margin:10px 0 0; } .dot { display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:5px; }
    @media (max-width:760px) { .grid { grid-template-columns:repeat(2,1fr); } input { width:100%; max-width:none; } }
  </style>
</head>
<body><main>
  <div class="top"><div><h1>Payment Operations</h1><p>Processor health, routing outcomes, and traffic.</p></div><div class="controls"><input id="token" type="password" placeholder="Paste JWT access token"><select id="days"><option value="14">Last 14 days</option><option value="30">Last 30 days</option><option value="7">Last 7 days</option></select><button id="refresh">Refresh</button></div></div>
  <p class="notice" id="notice">Enter a JWT access token to load analytics.</p>
  <section class="grid" id="summary"></section><section class="processor-grid" id="processors"></section>
  <section class="panel chart-panel"><h2>Payment Traffic</h2><canvas id="traffic" width="1160" height="330"></canvas><div class="legend" id="legend"></div></section>
</main>
<script>
const apiPrefix=__API_PREFIX__;
const colors=['#76a7ff','#25c281','#ffc857','#ee83e5','#ff8c69'];
const token=document.querySelector('#token'), days=document.querySelector('#days'), notice=document.querySelector('#notice');
token.value=sessionStorage.getItem('dashboard_token')||'';
const escapeHtml=value=>String(value).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
function pct(value){return `${Number(value).toFixed(2)}%`}
function statusClass(status){return status==='HEALTHY'?'healthy':status==='INACTIVE'?'inactive':'unhealthy'}
function render(data){
  document.querySelector('#summary').innerHTML=[['Total routed',data.total_routed],['Successful',`${data.total_successful_payments} · ${pct(data.success_percentage)}`],['Failed',`${data.total_failed_payments} · ${pct(data.failure_percentage)}`],['Updated',new Date(data.generated_at+'Z').toLocaleTimeString()]].map(([label,value])=>`<article class="panel"><span class="label">${label}</span><div class="value">${value}</div></article>`).join('');
  document.querySelector('#processors').innerHTML=data.processors.map(p=>`<article class="panel processor-card"><span class="status ${statusClass(p.health_status)}">${p.health_status}</span><h3>${escapeHtml(p.processor_name)}</h3><p>${escapeHtml(p.processor_code)}</p><div class="stats"><div><span class="label">Routed</span><strong>${p.total_routed}</strong></div><div><span class="label">Avg latency</span><strong>${p.average_latency_ms??'—'}${p.average_latency_ms!==null?' ms':''}</strong></div><div><span class="label">Success</span><strong>${pct(p.success_percentage)}</strong></div><div><span class="label">Failure</span><strong>${pct(p.failure_percentage)}</strong></div></div></article>`).join('');
  drawTraffic(data.traffic, data.processors.map(p=>p.processor_code));
}
function drawTraffic(points,codes){
  const canvas=document.querySelector('#traffic'), ctx=canvas.getContext('2d'), width=canvas.width, height=canvas.height, pad={l:46,r:18,t:18,b:38}; ctx.clearRect(0,0,width,height);
  const series=[{name:'Total',color:'#ffffff',values:points.map(p=>p.total_payments)},...codes.map((code,i)=>({name:code,color:colors[i%colors.length],values:points.map(p=>p.processors[code]||0)}))];
  const max=Math.max(1,...series.flatMap(s=>s.values)); const x=i=>pad.l+(width-pad.l-pad.r)*(points.length<=1?.5:i/(points.length-1)); const y=v=>height-pad.b-(height-pad.t-pad.b)*v/max;
  ctx.strokeStyle='#314054';ctx.lineWidth=1;ctx.font='11px system-ui';ctx.fillStyle='#9aa8b8'; for(let i=0;i<=4;i++){const value=Math.round(max*i/4), yy=y(value);ctx.beginPath();ctx.moveTo(pad.l,yy);ctx.lineTo(width-pad.r,yy);ctx.stroke();ctx.fillText(value,7,yy+4)}
  series.forEach(s=>{ctx.strokeStyle=s.color;ctx.lineWidth=2;ctx.beginPath();s.values.forEach((v,i)=>i?ctx.lineTo(x(i),y(v)):ctx.moveTo(x(i),y(v)));ctx.stroke()});
  points.forEach((p,i)=>{if(i===0||i===points.length-1||points.length<=7){ctx.fillStyle='#9aa8b8';ctx.fillText(p.date.slice(5),x(i)-13,height-14)}});
  document.querySelector('#legend').innerHTML=series.map(s=>`<span><i class="dot" style="background:${s.color}"></i>${s.name}</span>`).join('');
}
async function load(){const accessToken=token.value.trim();if(!accessToken){notice.textContent='Enter a JWT access token to load analytics.';return}sessionStorage.setItem('dashboard_token',accessToken);notice.textContent='Loading…';try{const response=await fetch(`${apiPrefix}/analytics/overview?days=${days.value}`,{headers:{Authorization:`Bearer ${accessToken}`}});if(!response.ok)throw new Error(response.status===401?'Token is invalid or expired.':`Request failed (${response.status}).`);render(await response.json());notice.textContent='Live processor health is refreshed each time you load the dashboard.'}catch(error){notice.textContent=error.message}}
document.querySelector('#refresh').addEventListener('click',load);days.addEventListener('change',load);if(token.value)load();
</script></body></html>"""
    return HTMLResponse(page.replace("__API_PREFIX__", json.dumps(api_v1_prefix.rstrip("/"))))
