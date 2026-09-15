// Renders the page headlessly and extracts every number a reader sees, as JSON.
// Renders site/ (what GitHub Pages serves) when it has been built, else the artifact page in app/.
//   node tools/audit/render_dump.js out.json          (GRIDIRON_RENDER=site|artifact to force)
const fs=require('fs'),path=require('path');
let jsdom; try{jsdom=require('jsdom');}catch(e){jsdom=require('/tmp/node_modules/jsdom');}
const {JSDOM,VirtualConsole}=jsdom;
const ROOT=path.join(__dirname,'..','..'), SITE=path.join(ROOT,'site'), APP=path.join(ROOT,'app');
const MODE=process.env.GRIDIRON_RENDER||(fs.existsSync(path.join(SITE,'index.html'))?'site':'artifact');
const DIR=MODE==='site'?SITE:APP, rd=f=>fs.readFileSync(path.join(DIR,f),'utf8');
let SHIM='<script>window.matchMedia=window.matchMedia||function(q){return{matches:false,media:q,addListener(){},removeListener(){},'+
 'addEventListener(){},removeEventListener(){},onchange:null,dispatchEvent(){return false}};};'+
 'Element.prototype.scrollIntoView=Element.prototype.scrollIntoView||function(){};<\/script>';
// optional fixture: stand in for ESPN so live-game rendering can be audited offline (GRIDIRON_FIXTURE_FILE=path.json)
if(process.env.GRIDIRON_FIXTURE_FILE){
  const F=fs.readFileSync(process.env.GRIDIRON_FIXTURE_FILE,'utf8').replace(/<\//g,'<\\/');
  SHIM='<script>(function(){var F='+F+';window.GRIDIRON_FIXTURE=function(u){if(/scoreboard/.test(u))return F.scoreboard;'+
    'var m=/event=([^&]+)/.exec(u);return m?(F.summaries[decodeURIComponent(m[1])]||null):null;};})();<\/script>'+SHIM;
}
let html;
if(MODE==='site'){
  const loader=/<script>\s*\(function\(\)\{[\s\S]*?GRIDIRON_LIVE[\s\S]*?<\/script>/;
  const idx=rd('index.html'); if(!loader.test(idx)) throw new Error('site/index.html has no data loader');
  const V=JSON.parse(rd('version.json'));
  html=idx.replace(loader,()=>SHIM+'<script>window.GRIDIRON_CODE='+JSON.stringify(V.code)+';window.GRIDIRON_DATA='+rd(V.data)+';<\/script>'+
    '<script>'+rd(V.context)+'<\/script><script>'+rd(V.app)+'<\/script>');
} else {
  html=rd('gridiron-v2.html').replace('<script src="context.js"></script>',()=>SHIM+'<script>'+rd('context.js')+'</script>')
    .replace('<script src="app.js"></script>',()=>'<script>'+rd('app.js')+'</script>');
}
const errs=[],vc=new VirtualConsole(); vc.on('jsdomError',e=>errs.push(String(e&&e.message||e)));
const dom=new JSDOM(html,{runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc});
const W=dom.window,d=W.document,T=el=>el?el.textContent.replace(/\s+/g,' ').trim():null,all=(r,s)=>[...r.querySelectorAll(s)];
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
setTimeout(async()=>{
  const D=W.GRIDIRON_DATA||JSON.parse(d.getElementById('gi-data').textContent), out={mode:MODE,cards:[],drawers:[],model:{},sidebar:[]};
  out.sidebar=all(d,'.navitem[data-go]').filter(n=>/^\d+$/.test(n.dataset.go)).map(n=>({gi:+n.dataset.go,text:T(n)}));
  out.stamp=T(d.getElementById('stamp'));
  out.teams={};
  for(const season of all(d,'#tseason button[data-season]').map(b=>b.dataset.season)){
    d.querySelector('#tseason button[data-season="'+season+'"]').click(); await sleep(20);
    const grab=()=>({leaders:all(d,'#tleaders .mtile').map(x=>[T(x.querySelector('dt')),T(x.querySelector('dd'))]),
      rows:all(d,'#ttables tr[data-team]').map(tr=>({team:tr.dataset.team,rank:T(tr.querySelector('.tteam em')),
        cells:Object.fromEntries(all(tr,'td[data-k]').map(td=>[td.dataset.k,T(td)]))})),note:T(d.getElementById('tnote'))});
    const div=grab();
    d.querySelector('#tview button[data-view="league"]').click(); await sleep(20);
    const league=grab();
    d.querySelector('#tview button[data-view="div"]').click(); await sleep(20);
    out.teams[season]={div,league};
  }
  out.teamsText=T(d.getElementById('p-teams'));
  const cells=tr=>Object.fromEntries(all(tr,'td[data-k]').map(td=>[td.dataset.k,T(td)]));
  out.weeks={};
  for(const season of all(d,'#tseason button[data-season]').map(b=>b.dataset.season)){
    d.querySelector('#tseason button[data-season="'+season+'"]').click(); await sleep(10);
    d.querySelector('#tview button[data-view="weeks"]').click(); await sleep(10);
    out.weeks[season]={};
    for(const w of all(d,'#tweeks button[data-week]').map(b=>b.dataset.week)){
      d.querySelector('#tweeks button[data-week="'+w+'"]').click(); await sleep(5);
      out.weeks[season][w]={rows:all(d,'#ttables tr[data-wgame]').map(tr=>({espn:tr.dataset.wgame,cells:cells(tr)})),heads:all(d,'#ttables thead th').map(T),note:T(d.getElementById('tnote'))};
    }
    d.querySelector('#tview button[data-view="div"]').click(); await sleep(10);
  }
  out.teampages={};
  for(const code of [...new Set(all(d,'#ttables tr[data-team]').map(tr=>tr.dataset.team))]){
    const row=d.querySelector('#ttables tr[data-team="'+code+'"]'); if(!row) continue;
    row.querySelector('td[data-k="rec"]').click(); await sleep(10);
    const pages={};
    for(const season of all(d,'#tmseason button[data-season]').map(b=>b.dataset.season)){
      d.querySelector('#tmseason button[data-season="'+season+'"]').click(); await sleep(10);
      pages[season]={on:d.getElementById('p-team').classList.contains('on'),head:T(d.getElementById('tmhead')),crumb:T(d.getElementById('crumb')),
        tiles:all(d,'#tmmetrics .mtile').map(x=>[T(x.querySelector('dt')),T(x.querySelector('dd'))]),week:T(d.getElementById('tmweek')),
        sched:all(d,'#tmsched tr[data-wk]').map(tr=>({wk:tr.dataset.wk,cells:cells(tr)})),heads:all(d,'#tmsched thead th').map(T),
        bars:all(d,'#tmchart .tmbar').map(g=>+g.dataset.wk),inj:all(d,'#tminj .tminjrow').map(x=>x.dataset.pid),
        players:all(d,'#tmplayers tr[data-pid]').map(tr=>({id:tr.dataset.pid,cells:cells(tr)})),text:T(d.getElementById('p-team'))};
    }
    out.teampages[code]=pages;
    d.querySelector('.navitem[data-go="teams"]').click(); await sleep(10);
  }
  const picks=[];
  for(const nav of all(d,'.navitem[data-go]').filter(n=>/^\d+$/.test(n.dataset.go))){
    const gi=+nav.dataset.go, g=D.games[gi]; nav.click(); await sleep(15);
    const call=d.getElementById('gcall');
    out.cards.push({id:g.id,gi,meta:T(d.getElementById('gsub')),metrics:all(d,'#gmetrics .mtile').map(x=>[T(x.querySelector('dt')),T(x.querySelector('dd'))]),
      score:T(d.getElementById('gscore')),live:T(call.querySelector('.pr-live')),conf:T(call.querySelector('.pr-conf')),
      pred:all(call,'.pr-col').map(c=>({lab:T(c.querySelector('.pr-lab')),rows:all(c,'.pr-r').map(r=>[T(r.querySelector('span')),T(r.querySelector('b'))]),
        lean:T(c.querySelector('.pr-d')),wpl:all(c,'.wpl span').map(T)})),
      wf:all(call,'.wf').map(r=>({cls:r.className,k:T(r.querySelector('.wk')),d:T(r.querySelector('.wd')),v:T(r.querySelector('.wv'))})),
      inj:all(call,'.ijrow').map(r=>({t:T(r.querySelector('.ijt')),out:T(r.querySelector('.ijout')),to:all(r,'.ijg').map(T)})),
      cells:all(d,'#gctx .cell').map(x=>({k:T(x.querySelector('.cl')),v:T(x.querySelector('.cvv')),meta:T(x.querySelector('.cr'))})),
      rows:all(d,'#gmatchups .mrow2').map(r=>({oid:r.dataset.oid,med:T(r.querySelector('.pj .med')),act:T(r.querySelector('.act')),n2:T(r.querySelector('.n2'))})),
      records:all(d,'#grecords tr[data-row]').map(tr=>[tr.dataset.row].concat(all(tr,'td').slice(1).map(T))),
      jump:all(d,'#gjump button').map(T),field:!!d.querySelector('#fbox svg'),
      ledger:T(call.querySelector('.pr-ledger')),foot:T(call.querySelector('.pr-foot')),text:T(d.getElementById('p-game'))});
    for(const r of all(d,'#gmatchups .mrow2')){const o=r.dataset.oid,p=(D.proj||{})[o]; if(!p||picks.some(x=>x.o===o)) continue;
      if(D.props&&D.props.by&&D.props.by[o]&&picks.filter(x=>x.why==='prop').length<3) picks.push({o,why:'prop',gi});
      else if(p.inj&&!picks.some(x=>x.why==='inj')) picks.push({o,why:'inj',gi});
      else if(p.wx&&Math.abs(p.wx.m-1)>=0.02&&!picks.some(x=>x.why==='wx')) picks.push({o,why:'wx',gi});}
  }
  for(const pk of picks){ d.querySelector('.navitem[data-go="'+pk.gi+'"]').click(); await sleep(15);
    const r=d.querySelector('#gmatchups .mrow2[data-oid="'+pk.o+'"]'); if(!r) continue;
    r.click(); await sleep(120); const dr=d.getElementById('drawer');
    out.drawers.push({oid:pk.o,why:pk.why,big:T(dr.querySelector('.pjtop .big')),line:(dr.querySelector('.pline')||{}).value,ov:T(dr.querySelector('.ov')),
      chain:all(dr,'.chain > div').map(x=>[T(x.querySelector('.lab')),T(x.querySelector('.val'))]),
      market:all(dr,'.mkrow').map(x=>[T(x.querySelector('.mkk')),T(x.querySelector('.mkl')),T(x.querySelector('.mkp'))])});
    const sc=d.getElementById('scrim'); if(sc) sc.click(); await sleep(40); }
  d.querySelector('.navitem[data-go="model"]').click(); await sleep(150);
  out.model={learn:{rows:all(d,'.ltab .lrow').map(r=>({k:T(r.querySelector('.fk')),st:T(r.querySelector('.fv')),v:T(r.querySelector('.lval'))})),rev:T(d.querySelector('.lrev')),dec:all(d,'.ldec').length},since:all(d,'#since .ttile').map(x=>[T(x.querySelector('.tk')),T(x.querySelector('.tv')),T(x.querySelector('.ts2'))]),sinceText:T(d.getElementById('since')),tiles:all(d,'.mcard:not(#since) .ttile').map(x=>[T(x.querySelector('.tk')),T(x.querySelector('.tv')),T(x.querySelector('.ts2'))]),
    frows:all(d,'.ftab:not(.ltab) .frow').map(T),wprows:all(d,'.wprow').map(T),text:T(d.getElementById('modelgrid'))};
  out.errors=errs; fs.writeFileSync(process.argv[2]||'/dev/stdout',JSON.stringify(out)); W.close();
},700);
