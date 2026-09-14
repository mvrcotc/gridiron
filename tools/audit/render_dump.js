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
  for(const card of all(d,'#games .gcard')){
    const g=D.games[+card.dataset.gi];
    out.cards.push({id:g.id,meta:T(card.querySelector('.gc-meta')),score:T(card.querySelector('.gc-score')),live:T(card.querySelector('.pr-live')),conf:T(card.querySelector('.pr-conf')),
      pred:all(card,'.pr-col').map(c=>({lab:T(c.querySelector('.pr-lab')),rows:all(c,'.pr-r').map(r=>[T(r.querySelector('span')),T(r.querySelector('b'))]),
        lean:T(c.querySelector('.pr-d')),wpl:all(c,'.wpl span').map(T)})),
      wf:all(card,'.wf').map(r=>({cls:r.className,k:T(r.querySelector('.wk')),d:T(r.querySelector('.wd')),v:T(r.querySelector('.wv'))})),
      inj:all(card,'.ijrow').map(r=>({t:T(r.querySelector('.ijt')),out:T(r.querySelector('.ijout')),to:all(r,'.ijg').map(T)})),
      cells:all(card,'.fullgrid .cell').map(x=>({k:T(x.querySelector('.cl')),v:T(x.querySelector('.cvv')),meta:T(x.querySelector('.cr'))})),
      rows:all(card,'.mrow2').map(r=>({oid:r.dataset.oid,med:T(r.querySelector('.pj .med')),act:T(r.querySelector('.act')),n2:T(r.querySelector('.n2'))})),
      foot:T(card.querySelector('.pr-foot')),text:T(card)});
  }
  const rows=all(d,'#games .mrow2'),pick=[];
  for(const r of rows){const o=r.dataset.oid,p=(D.proj||{})[o]; if(!p||pick.some(x=>x.o===o)) continue;
    if(D.props&&D.props.by&&D.props.by[o]&&pick.filter(x=>x.why==='prop').length<3) pick.push({o,why:'prop',r});
    else if(p.inj&&!pick.some(x=>x.why==='inj')) pick.push({o,why:'inj',r});
    else if(p.wx&&Math.abs(p.wx.m-1)>=0.02&&!pick.some(x=>x.why==='wx')) pick.push({o,why:'wx',r});}
  for(const pk of pick){ pk.r.click(); await sleep(120); const dr=d.getElementById('drawer');
    out.drawers.push({oid:pk.o,why:pk.why,big:T(dr.querySelector('.pjtop .big')),line:(dr.querySelector('.pline')||{}).value,ov:T(dr.querySelector('.ov')),
      chain:all(dr,'.chain > div').map(x=>[T(x.querySelector('.lab')),T(x.querySelector('.val'))]),
      market:all(dr,'.mkrow').map(x=>[T(x.querySelector('.mkk')),T(x.querySelector('.mkl')),T(x.querySelector('.mkp'))])});
    const sc=d.getElementById('scrim'); if(sc) sc.click(); await sleep(40); }
  d.querySelector('.navitem[data-go="model"]').click(); await sleep(150);
  out.model={tiles:all(d,'.ttile').map(x=>[T(x.querySelector('.tk')),T(x.querySelector('.tv')),T(x.querySelector('.ts2'))]),
    frows:all(d,'.frow').map(T),wprows:all(d,'.wprow').map(T),text:T(d.getElementById('modelgrid'))};
  out.errors=errs; fs.writeFileSync(process.argv[2]||'/dev/stdout',JSON.stringify(out)); W.close();
},700);
