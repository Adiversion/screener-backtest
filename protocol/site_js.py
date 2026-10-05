"""JavaScript for the research site, kept out of the renderer.

A large blob of text, not logic. It lives apart from site_html.py so the
render and write functions stay reviewable, and apart from the CSS so neither
file approaches the 300-line limit.

The page must run from a GitHub Pages URL with no server behind it, so this is
vanilla JS against two JSON files -- no framework, no build step, no CDN.
"""
from __future__ import annotations

JS = r"""
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
let DATA=null, TAPE=null;

async function boot(){
  DATA=await (await fetch('stocks.json?v='+Date.now())).json();
  $('#asof').textContent='session '+DATA.asof+' · '+DATA.universe.symbols+' symbols · '
    +DATA.universe.from+' → '+DATA.universe.to;
  const cl=$('#cleared'); if(cl) cl.textContent=DATA.stats.cleared;
  renderList(DATA.clearing);
  renderComponents();
  renderEvidence();
  renderCaveats();
  wire();
}

function fmt(v,d=2){ if(v===null||v===undefined||Number.isNaN(v))return '—';
  return typeof v==='number'? v.toFixed(d) : v; }
function pct(v){ return v===null||v===undefined? '—' : (v*100).toFixed(0)+'%'; }
function cr(v){ return v===null||v===undefined? '—' : (v*100).toFixed(1)+'%'; }

function wire(){
  $('#q').addEventListener('input',e=>{
    const t=e.target.value.trim().toUpperCase();
    if(!t){ show('list'); return; }
    const hits=Object.keys(DATA.stocks).filter(s=>s.includes(t)).slice(0,40);
    show('result');
    if(!hits.length){ $('#result').innerHTML=
      '<div class="card"><div class="sym">No symbol matching "'+t+
      '"</div><p class="sub">'+DATA.universe.symbols+
      ' NSE cash equities are scored this session. Check the spelling, or try part of the ticker.</p></div>';
      return; }
    $('#result').innerHTML=hits.map(s=>{
      const v=DATA.stocks[s];
      return '<a class="list" style="padding:9px 11px;border:1px solid var(--line);'+
        'border-radius:8px;margin:6px 0;text-decoration:none;color:var(--text);'+
        'background:var(--panel2);display:flex;justify-content:space-between" href="#'+
        encodeURIComponent(s)+'"><b>'+s+'</b><span>'+
        (v.clears?'<span class="verdict pass">CLEARS</span>':'<span class="verdict fail">REJECTED</span>')+
        '</span><span class="muted">score '+fmt(v.score,3)+' · '+pct(v.percentile)+'</span></a>';
    }).join('');
  });
  $$('.tab').forEach(t=>t.onclick=()=>{
    $$('.tab').forEach(x=>x.classList.remove('on'));
    t.classList.add('on'); show(t.dataset.p);
  });
  window.onhashchange=()=>route();
}

function route(){
  const s=decodeURIComponent(location.hash.slice(1));
  if(s && DATA && DATA.stocks[s]){ show('stock'); draw(s); }
  else if(!s && location.hash==='#research') show('research');
  else show('list');
}
function show(p){
  ['list','result','stock','research'].forEach(x=>
    $('#'+x).classList.toggle('hide', x!==p));
}

function renderList(syms){
  $('#list').innerHTML=
    '<h2>'+syms.length+' of '+DATA.universe.symbols+' symbols clear every hard gate</h2>'
    +'<p class="sub">The gates are strict on purpose. On most days very few names pass, '
    +'and on some days none do — that is the engine protecting capital, not a bug.</p>'
    +'<div class="list">'+syms.map(s=>
      '<a href="#'+encodeURIComponent(s)+'"><div class="row"><b>'+s+'</b>'
      +'<span class="pill">score '+fmt(DATA.stocks[s].score,3)+'</span></div>'
      +'<div class="sub">₹'+fmt(DATA.stocks[s].close)+' · '
      +cr(DATA.stocks[s].ret120)+' in 120d · '+(DATA.stocks[s].industry||'—')+'</div></a>'
    ).join('')+'</div>';
}

function draw(sym){
  const light=DATA.stocks[sym];
  $('#stock').innerHTML=
    '<div class="row"><div><span class="sym" style="font-size:22px">'+sym+'</span>'
    +'<span class="pill">score '+fmt(light.score,3)+'</span></div>'
    +'<span class="verdict '+(light.clears?'pass':'fail')+'">'
    +(light.clears?'CLEARS EVERY GATE':'REJECTED')+'</span></div>'
    +'<p class="sub">loading the full evidence…</p>';
  loadStock(sym);
}

async function loadStock(sym){
  let v;
  try{ v=await (await fetch('stock/'+sym+'.json?v='+Date.now())).json(); }
  catch(e){ $('#stock').innerHTML='<div class="card">detail unavailable for '+sym+'</div>'; return; }
  const failed=v.gates.filter(g=>!g.passed);
  const comps=Object.entries(v.components).map(([k,p])=>{
    const meta=DATA.components.find(c=>c.field===k)||{};
    return '<tr><td>'+(meta.label||k)+'</td><td class="muted" style="font-size:11px">'
      +pct(v[k])+'</td><td style="width:130px"><div class="bar"><i style="width:'
      +((p||0)*100)+'%"></i></div></td><td class="muted">'+(meta.weight!=null?('w '+meta.weight):'')
      +'</td><td class="muted" style="font-size:11px">'+(meta.why||'')+'</td></tr>';
  }).join('');

  $('#stock').innerHTML=
  '<div class="row"><div><span class="sym" style="font-size:22px">'+sym+'</span> '
    +(v.industry?'<span class="pill">'+v.industry+'</span>':'')+'</div>'
    +'<span class="verdict '+(v.clears?'pass':'fail')+'">'
    +(v.clears?'CLEARS EVERY GATE':'REJECTED')+'</span></div>'
    +'<p class="sub">'+(v.clears
      ? 'This name clears every hard gate. It is a RESEARCH_CANDIDATE — a research screen, not a recommendation.'
      : 'This name fails '+failed.length+' of '+v.gates.length+' hard gates. The full evidence is below, so the rejection is explainable rather than opaque.')+'</p>'
  +'<p class="sub">'+(v.clears
      ? 'This name clears every hard gate. It is a RESEARCH_CANDIDATE — a research screen, not a recommendation.'
      : 'This name fails '+failed.length+' of '+v.gates.length+' hard gates. The full evidence is below, so the rejection is explainable rather than opaque.')+'</p>'

  +'<div class="grid">'
    +kpi('Score', fmt(v.score,3))+kpi('Percentile', pct(v.percentile))
    +kpi('Close','₹'+fmt(v.close))+kpi('52w high', fmt(v.prox52,3))
    +kpi('ATR%', cr(v.atrpct))+kpi('RVOL20', fmt(v.rvol20,2))
    +kpi('120d', cr(v.ret120))+kpi('20d', cr(v.ret20))
    +kpi('Turnover 20d','₹'+fmt((v.turnover20||0)/1e7,0)+' Cr')
    +kpi('Sessions', v.sessions)+kpi('Coverage', pct(v.coverage)+' '+v.data_status)
    +(v.screen_tag?kpi('Session tag', v.screen_tag):'')
  +'</div>'

  +'<h3>Hard gates</h3><table><tr><th>Gate</th><th>Value</th><th>Threshold</th>'
    +'<th></th><th>Why</th></tr>'
    +v.gates.map(g=>'<tr><td>'+g.criterion+'</td><td>'+
        (typeof g.value==='number'?fmt(g.value,4):String(g.value==null?'unknown':g.value))+
        '</td><td class="muted">'+g.threshold+'</td><td class="'+(g.passed?'ok':'no')+'">'
        +(g.passed?'PASS':'FAIL')+'</td><td class="muted" style="font-size:11px">'
        +g.meaning+'</td></tr>').join('')+'</table>'

  +'<h3>What the score is made of</h3>'
    +'<p class="sub">Each component is a cross-sectional percentile against the whole '
    +'universe on '+DATA.asof+' — not an absolute level.</p>'
    +'<table><tr><th>Component</th><th>Raw</th><th>Percentile</th><th>Weight</th>'
    +'<th>Evidence</th></tr>'+comps+'</table>'
    +'<p class="note">The weights were fitted to 5-day forward returns. They were '
    +'never validated on a months-long holding period, and the strongest factor '
    +'(low volatility) loses as a short-horizon entry rule. Read the research tab.</p>'

  +'<h3>Recent sessions</h3><table><tr><th>Date</th><th>Close</th><th>RVOL20</th>'
    +'<th>ATR%</th><th>20d return</th></tr>'+(v.tape||[]).slice().reverse().map(r=>
    '<tr><td class="muted">'+r.date+'</td><td>₹'+fmt(r.close)+'</td><td>'
    +fmt(r.rvol20,2)+'</td><td>'+cr(r.atrpct)+'</td><td>'+cr(r.ret20)+'</td></tr>'
    ).join('')+'</table>';
}

function kpi(k,v){ return '<div class="kpi"><div class="k">'+k+'</div><div class="v">'+v+'</div></div>'; }

function renderComponents(){
  $('#comps').innerHTML='<table><tr><th>Component</th><th>Weight</th><th>Measures</th>'
    +'<th>Why it earns the weight</th></tr>'+DATA.components.map(c=>
    '<tr><td>'+c.label+'</td><td>'+(c.weight!=null?c.weight:'—')+'</td><td>'
    +c.measures+'</td><td class="muted">'+c.why+'</td></tr>').join('')+'</table>'
    +'<h3>Hard gates every stock must clear</h3><table><tr><th>Gate</th>'
    +'<th>Threshold</th><th>Why</th></tr>'+DATA.gates.map(g=>
    '<tr><td>'+g.criterion+'</td><td><code>'+g.threshold+'</code></td><td>'
    +g.meaning+'</td></tr>').join('')+'</table>';
}

function renderEvidence(){
  const e=DATA.evidence||{};
  let h='<p class="sub">What the engine measured about its own rules. These are the '
    +'findings that decide what this site is allowed to claim.</p>';
  if(e.verdict){
    h+='<h3>Does the ranking actually rank?</h3><p class="sub">'+e.verdict.note
      +'</p><table><tr><th>Decile</th><th>Observations</th><th>Mean score</th>'
      +'<th>+5d</th><th>+20d</th><th>vs universe</th></tr>'
      +e.verdict.rows.map(r=>{
        return '<tr><td><b>'+r.decile+'</b> '+(r.decile==='D1'?'<span class="muted">(lowest)</span>':'')
          +(r.decile==='D10'?' <span class="muted">(highest)</span>':'')+'</td><td>'
          +Number(r.events).toLocaleString()+'</td><td>'+fmt(r.score_mean,3)
          +'</td><td>'+cr(r.fwd5,2)+'</td><td>'+cr(r.fwd20,2)+'</td><td>'
          +(r.excess>0?'<span class="ok">':'<span class="no">')+cr(r.excess,2)
          +'</span></td></tr>';
      }).join('')+'</table>'
      +'<p class="note">D1 is the lowest-scoring tenth of the universe and D10 the '
      +'highest. A ladder that rises from D1 to D10 means the score orders '
      +'outcomes; a flat or falling one means it does not.</p>';
  }
  if(e.ic){
    h+='<h3>Information coefficients vs the 5-day forward return</h3>'
      +'<p class="sub">Measured on 108,742 breakout events. A positive IC means the '
      +'higher value went with the better next 5 days.</p><table><tr><th>Factor</th>'
      +'<th>IC</th><th>t</th><th>Reading</th></tr>'
      +e.ic.map(r=>'<tr><td>'+r.factor+'</td><td>'+fmt(r.ic,4)+'</td><td>'
        +fmt(r.t,2)+'</td><td class="muted">'+r.reading+'</td></tr>').join('')
      +'</table>';
  }
  if(e.factors_dropped){
    h+='<h3>Factors the protocol proposed, and what happened to them</h3>'
      +'<p class="sub">The research protocol\'s own instruction is: if a factor adds '
      +'no information beyond simpler ones, discard the complexity.</p><table>'
      +e.factors_dropped.map(r=>'<tr><td>'+r.factor+'</td><td>'+fmt(r.ic,5)+'</td>'
        +'<td>'+fmt(r.t,2)+'</td><td class="muted">'+r.verdict+'</td></tr>').join('')
      +'</table>';
  }
  if(e.rotation){
    h+='<h3>Single-position rotation — one stock, the whole account</h3>'
      +'<p class="sub">'+e.rotation.note+'</p><table><tr><th>Pick</th><th>Trades</th>'
      +'<th>CAGR</th><th>Max drawdown</th><th>Hit rate</th><th>Per trade</th></tr>'
      +e.rotation.runs.map(r=>'<tr><td>'+r.pick+'</td><td>'+r.trades+'</td><td>'
        +cr(r.CAGR)+'</td><td>'+cr(r.max_dd)+'</td><td>'+pct(r.WinRate)+'</td><td>'
        +cr(r.Expectancy,2)+'</td></tr>').join('')+'</table>'
      +'<p class="note">'+e.rotation.verdict+'</p>';
  }
  if(e.costs){
    h+='<h3>What one rotation costs</h3>'
      +'<p class="sub">The DP charge is flat <i>per sell</i>, so it scales as 1/capital. '
      +'This is arithmetic, not opinion.</p><table><tr><th>Capital</th>'
      +'<th>DP as % of account</th><th>Round trip</th><th>Idle cash</th>'
      +'<th>Gross move for a +15% net target</th></tr>'
      +e.costs.map(c=>'<tr><td>₹'+Number(c.capital).toLocaleString()+'</td><td>'
        +c.dp_pct_of_capital+'%</td><td>'+c.round_trip_bps_of_capital+' bps</td><td>'
        +c.idle_cash_pct+'%</td><td>'+cr(c.gross_for_target,2)+'</td></tr>').join('')
      +'</table>';
  }
  if(e.geometry){
    h+='<h3>Target / stop geometry</h3><p class="sub">'+e.geometry.note+'</p>'
      +'<table><tr><th>Target</th><th>Stop</th><th>Trades</th><th>CAGR</th>'
      +'<th>Max drawdown</th><th>Hit rate</th></tr>'
      +e.geometry.rows.map(r=>'<tr><td>'+pct(r.target,0)+'</td><td>'+pct(r.stop,0)
        +'</td><td>'+r.trades+'</td><td>'+cr(r.CAGR)+'</td><td>'+cr(r.max_dd)
        +'</td><td>'+pct(r.hit_rate)+'</td></tr>').join('')+'</table>';
  }
  if(e.audits){
    h+='<h3>Data integrity &amp; multiple-testing control</h3><table>'
      +e.audits.map(a=>'<tr><td>'+a.name+'</td><td class="muted">'+a.verdict
        +'</td></tr>').join('')+'</table>';
  }
  $('#evidence').innerHTML=h;
}

function renderCaveats(){
  $('#caveats').innerHTML='<h2>What this does and does not prove</h2><ul>'
    +DATA.caveats.map(c=>'<li>'+c+'</li>').join('')+'</ul>';
}
"""
