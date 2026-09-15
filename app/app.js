(function(){
"use strict";
/* ============================================================================
   Data is keyed by gsis_id throughout. Player names are a display attribute,
   never a key -- every join (usage, production, coverage, injuries) was made
   by id at build time. Values reaching markup pass esc() / col() / num(),
   and markup is inserted via DOMParser (inert; scripts never run).
   ========================================================================== */
var AMP=/&/g,LT=/</g,GT=/>/g,QU=/"/g;
function esc(s){return String(s==null?'':s).replace(AMP,'&amp;').replace(LT,'&lt;').replace(GT,'&gt;').replace(QU,'&quot;');}
var HEX=/^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i;
function col(c,fb){return HEX.test(String(c))?String(c):(fb||'#52525B');}
function num(v,fb){var n=Number(v);return isFinite(n)?n:(fb===undefined?0:fb);}
function render(el,markup){
  /* Table rows are dropped if parsed outside a table, so wrap when the
     destination is a section of one. DOMParser output stays inert either way. */
  var tag=(el.tagName||'').toLowerCase();
  var inTable=(tag==='tbody'||tag==='thead'||tag==='tfoot');
  var doc=new DOMParser().parseFromString(
    '<body>'+(inTable?'<table>'+markup+'</table>':markup)+'</body>','text/html');
  var src=doc.body;
  if(inTable) src=doc.body.querySelector('tbody')||doc.body.querySelector('table')||doc.body;
  var kids=[],n=src.firstChild;
  while(n){kids.push(document.importNode(n,true));n=n.nextSibling;}
  el.replaceChildren.apply(el,kids);
}
var D=window.GRIDIRON_DATA||JSON.parse(document.getElementById('gi-data').textContent);
var RM=matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ---- accessors: everything by id ---- */
function PL(id){return D.players[id]||{n:'\u2014',j:'',p:'',t:''};}
function U(id){return D.usage[id]||null;}
function PR(id){return D.prod[id]||null;}
function CV(id){return D.cov[id]||null;}
function RS(id){return (D.res||{})[id]||null;}
function IJ(id){return (D.injd||{})[id]||null;}
/* the actual line a player put up, in the order people read it */
function statLine(e){
  if(!e) return '';
  var b=[];
  if(e.tgt) b.push((e.rec||0)+'/'+e.tgt+' for '+(e.ry||0)+' yds');
  if(e.car) b.push(e.car+' car, '+(e.ru||0)+' yds');
  if(e.att) b.push((e.cmp||0)+'/'+e.att+', '+(e.py||0)+' yds');
  var td=(e.rtd||0)+(e.rutd||0)+(e.ptd||0);
  if(td) b.push(td+' TD');
  if(e.int) b.push(e.int+' INT');
  return b.join(' \u00b7 ');
}
function verdictChip(e){
  if(!e||!e.v) return '';
  var t=e.v==='beat'?'ABOVE AVG':e.v==='miss'?'BELOW AVG':'NEAR AVG';
  return '<span class="vd '+esc(e.v)+'" title="'+num(e.pts).toFixed(1)+
    ' PPR points against a '+num(e.exp).toFixed(1)+' per-game average across 2025">'+t+'</span>';
}
function outFor(ret){
  if(!ret) return null;
  var t=new Date(ret+'T12:00:00Z'); if(isNaN(t)) return null;
  var days=Math.round((t-Date.now())/86400000);
  if(days<=0) return 'cleared to return';
  if(days<=7) return days+' day'+(days===1?'':'s')+' away';
  var wk=Math.round(days/7);
  return 'about '+wk+' week'+(wk===1?'':'s')+' away';
}
function injChip(id){
  var i=IJ(id); if(!i) return '';
  var t=[i.sl||i.s];
  if(i.bp) t.push(i.bp+(i.side?' ('+i.side+')':''));
  if(i.ret){ var o=outFor(i.ret); t.push('expected back '+i.ret+(o?' \u2014 '+o:'')); }
  return ' <span class="tag '+esc(i.s)+'" style="font-size:8px" title="'+esc(t.join(' \u00b7 '))+'">'+esc(i.s)+'</span>';
}

/* ---- headshots ----------------------------------------------------------
   External images are blocked by the page's content policy, so every face
   ships in one sprite sheet and is positioned by cell. Players without a
   headshot keep their jersey number. */
var SP=D.sprite||null;
function faceOf(id){ return (SP && SP.idx && SP.idx[id]!=null) ? SP.idx[id] : null; }
function faceBg(id,size){
  var n=faceOf(id); if(n==null) return null;
  var c=n%SP.cols, r=Math.floor(n/SP.cols);
  return 'background-size:'+(SP.cols*size)+'px '+(SP.rows*size)+'px;'+
         'background-position:'+(-c*size)+'px '+(-r*size)+'px;';
}
function faceSvg(id,cx,cy,r,uid){
  var n=faceOf(id); if(n==null) return '';
  var col2=n%SP.cols, row=Math.floor(n/SP.cols), d=r*2;
  return '<clipPath id="fc'+uid+'"><circle cx="'+cx+'" cy="'+cy+'" r="'+(r-1.2)+'"/></clipPath>'+
    '<image clip-path="url(#fc'+uid+')" href="heads.webp" preserveAspectRatio="none" '+
    'x="'+(cx-r-col2*d)+'" y="'+(cy-r-row*d)+'" width="'+(SP.cols*d)+'" height="'+(SP.rows*d)+'"/>';
}

function shade(hex,f){
  var n=parseInt(col(hex).slice(1).padEnd(6,'0').slice(0,6),16),r=n>>16&255,g=n>>8&255,b=n&255;
  function c(v){return Math.max(0,Math.min(255,Math.round(f<1?v*f:v+(255-v)*(f-1))));}
  return '#'+((1<<24)+(c(r)<<16)+(c(g)<<8)+c(b)).toString(16).slice(1);
}
function lum(hex){var n=parseInt(col(hex).slice(1).padEnd(6,'0').slice(0,6),16);
  return (0.2126*(n>>16&255)+0.7152*(n>>8&255)+0.0722*(n&255))/255;}
function readable(h){return lum(h)>0.62?'#0B1013':'#FFFFFF';}
function distinct(a,b,alt){
  a=col(a);b=col(b);
  var ha=parseInt(a.slice(1).padEnd(6,'0').slice(0,6),16),hb=parseInt(b.slice(1).padEnd(6,'0').slice(0,6),16);
  var d=Math.abs((ha>>16&255)-(hb>>16&255))+Math.abs((ha>>8&255)-(hb>>8&255))+Math.abs((ha&255)-(hb&255));
  if(d<150&&Math.abs(lum(a)-lum(b))<0.22) return col(alt,'#A1A1AA');
  return a;
}
function teamColors(g){return {a:distinct(g.ac,g.hc,g.aa),h:col(g.hc)};}
function kick(iso){var d=new Date(iso);return isNaN(d)?'':
  d.toLocaleString('en-US',{weekday:'short',hour:'numeric',minute:'2-digit',timeZone:'America/New_York'}).replace(',','')+' ET';}
function implied(g){
  if(g.ou==null||g.spread==null) return null;
  var ou=num(g.ou),sp=num(g.spread);
  return {h:ou/2-sp/2, a:ou/2+sp/2};
}

/* ============================ edge model ============================ */
function recScore(id){
  var p=PR(id); if(!p||!p.S||!p.S.tgt) return null;
  var s=p.S, ypt=num(s.ry)/num(s.tgt,1);
  return Math.max(-32,Math.min(32,num(s.ts)*2.2+(ypt-7.5)*4.5-38));
}
function defScore(id){
  var c=CV(id); if(!c||num(c.tgt)<12) return null;
  return Math.max(-32,Math.min(32,(num(c.rat)-92)*0.62));
}
function edgeOf(oid,did){
  var r=recScore(oid),d=defScore(did);
  if(r==null&&d==null) return null;
  return Math.max(-26,Math.min(26,(r==null?0:r)*0.55+(d==null?0:d)*0.75));
}
function edgeColor(v){return v==null?'rgba(255,255,255,.28)':v>4?'#4ADE80':v<-4?'#F87171':'rgba(255,255,255,.45)';}

/* ============================ matchup index ============================ */
var PODS_O=[{k:'WR',t:'Wide receivers',n:3},{k:'TE',t:'Tight ends',n:1},
            {k:'RB',t:'Running backs',n:1},{k:'QB',t:'Quarterbacks',n:1},{k:'OL',t:'Offensive line',n:5}];
function podsD(s){return [{k:'CB',t:'Cornerbacks',n:3},{k:'S',t:'Safeties',n:2},
  {k:'LB',t:'Linebackers',n:s==='3-4'?3:2},{k:'DL',t:'Defensive line',n:s==='3-4'?3:4}];}

function coverPairs(od,dd){
  var wr=od.o.WR||[],cb=dd.d.CB||[];
  var outs=cb.filter(function(c){return c.p!=='NB';}),nb=cb.filter(function(c){return c.p==='NB';})[0];
  var out=[];
  if(wr[0]&&outs[0]) out.push([wr[0],outs[0],'WR']);
  if(wr[1]&&outs[1]) out.push([wr[1],outs[1],'WR']);
  if(wr[2]&&nb)      out.push([wr[2],nb,'WR']);
  if((od.o.TE||[])[0]&&(dd.d.S||[])[0]) out.push([od.o.TE[0],dd.d.S[0],'TE']);
  var lb=dd.d.LB||[];
  var ins=lb.filter(function(l){return /^(MLB|LILB|RILB)$/.test(l.p);})[0]||lb[0];
  if((od.o.RB||[])[0]&&ins) out.push([od.o.RB[0],ins,'RB']);
  return out;
}
/* every matchup on the slate, built once */
function buildMatchups(){
  var out=[];
  D.games.forEach(function(g,gi){
    [['h','a'],['a','h']].forEach(function(pair){
      var offT=pair[0]==='h'?g.h:g.a, defT=pair[0]==='h'?g.a:g.h;
      var od=D.depth[offT],dd=D.depth[defT];
      if(!od||!dd) return;
      var tc=teamColors(g), im=implied(g);
      var offC=offT===g.h?tc.h:tc.a, defC=defT===g.h?tc.h:tc.a;
      coverPairs(od,dd).forEach(function(p,idx){
        var oid=p[0].g,did=p[1].g;
        var lbl=p[2]+( p[2]==='WR' ? (idx+1) : 1 );
        out.push({gi:gi, poss:pair[0], oid:oid, did:did, fam:p[2], label:lbl, dslot:p[1].p,
          offT:offT, defT:defT, offC:offC, defC:defC,
          edge:edgeOf(oid,did),
          implied: im ? (offT===g.h?im.h:im.a) : null});
      });
    });
  });
  return out;
}
var MATCHUPS=buildMatchups();

/* ============================ small charts ============================ */
function sparkline(vals,color,w,h){
  if(!vals||vals.length<2) return '<svg class="spark" viewBox="0 0 '+w+' '+h+'" aria-hidden="true"></svg>';
  var mx=Math.max.apply(null,vals.concat([1])), n=vals.length;
  var pts=vals.map(function(v,i){
    return [ (n===1?w/2:i*(w-2)/(n-1))+1, h-1-(num(v)/mx)*(h-3) ];
  });
  var d=pts.map(function(p,i){return (i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1);}).join(' ');
  var area=d+' L'+pts[pts.length-1][0].toFixed(1)+' '+h+' L'+pts[0][0].toFixed(1)+' '+h+' Z';
  var last=pts[pts.length-1];
  return '<svg class="spark" viewBox="0 0 '+w+' '+h+'" aria-hidden="true">'+
    '<path d="'+area+'" fill="'+color+'" opacity=".16"/>'+
    '<path d="'+d+'" fill="none" stroke="'+color+'" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>'+
    '<circle cx="'+last[0].toFixed(1)+'" cy="'+last[1].toFixed(1)+'" r="2" fill="'+color+'"/></svg>';
}
function deltaTag(u){
  if(!u||u.s3==null||u.s==null) return '<span class="dlt fl">\u2014</span>';
  var d=num(u.s3)-num(u.s);
  var cls=d>=3?'up':d<=-3?'dn':'fl';
  var sign=d>0?'+':'';
  return '<span class="dlt '+cls+'">'+sign+d.toFixed(0)+'</span>';
}

/* ============================ BOARD ============================ */
var posFilter='all', query='', pinned=[], lastPlayer=null;
function volOf(m){
  var p=PR(m.oid); if(!p||!p.S) return null;
  var s=p.S,g=num(s.g,1)||1;
  if(m.fam==='RB') return (num(s.car)+num(s.tgt))/g;
  return num(s.tgt)/g;
}
function volLabel(m){
  var v=volOf(m);
  if(v==null) return '<span style="color:var(--fg-4)">\u2014</span>';
  return '<b>'+v.toFixed(1)+'</b> '+(m.fam==='RB'?'touch/g':'tgt/g');
}
var CICON=(function(){
  var o='stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" fill="none"';
  function w(i){return '<svg viewBox="0 0 24 24" aria-hidden="true" '+o+'>'+i+'</svg>';}
  return {
    mtn:w('<path d="M2 20h20L14.5 6.5 11 13l-2.2-3.4z"/>'),
    plane:w('<path d="M21 15.5 3 10V7l2 .6 1.5 2.2 4.5 1.3V4.6a1.6 1.6 0 0 1 3.2 0v7.4l7.3 2.1z"/><path d="M7 19.5h10"/>'),
    clock:w('<circle cx="12" cy="12" r="8.6"/><path d="M12 7.2V12l3.2 2"/>'),
    dome:w('<path d="M3.6 12.6a8.4 8.4 0 0 1 16.8 0"/><path d="M2.6 12.6h18.8v6.8H2.6z"/>'),
    open:w('<path d="M12 2.6v2M12 19.4v2M3.4 12h-2M22.6 12h-2M6 6l-1.4-1.4M19.4 19.4 18 18M18 6l1.4-1.4M4.6 19.4 6 18"/><circle cx="12" cy="12" r="4.2"/>'),
    turf:w('<path d="M3 20h18"/><path d="M6 20c0-4 1.4-6.6 3-8M12 20c0-5 .6-8 1.4-10M18 20c0-3.6-1-6-2.4-7.6"/>'),
    wind:w('<path d="M2.6 8.6h11a2.8 2.8 0 1 0-2.8-2.8M2.6 13h15.2a2.8 2.8 0 1 1-2.8 2.8M2.6 17.4h8"/>'),
    home:w('<path d="M3.4 10.6 12 3.6l8.6 7"/><path d="M5.6 9.6v10.8h12.8V9.6"/>'),
    star:w('<path d="m12 3.4 2.7 5.5 6 .9-4.3 4.2 1 6-5.4-2.8-5.4 2.8 1-6-4.3-4.2 6-.9z"/>'),
    globe:w('<circle cx="12" cy="12" r="8.8"/><path d="M3.2 12h17.6M12 3.2c2.2 2.4 3.4 5.5 3.4 8.8s-1.2 6.4-3.4 8.8c-2.2-2.4-3.4-5.5-3.4-8.8S9.8 5.6 12 3.2z"/>'),
    warn:w('<path d="M12 3.6 1.8 20.4h20.4z"/><path d="M12 9.6V14M12 17.4h.01"/>'),
    sun:w('<circle cx="12" cy="12" r="4.2"/><path d="M12 2.2v2.4M12 19.4v2.4M2.2 12h2.4M19.4 12h2.4M5.2 5.2l1.7 1.7M17.1 17.1l1.7 1.7M18.8 5.2l-1.7 1.7M6.9 17.1l-1.7 1.7"/>'),
    cloud:w('<path d="M7.4 18.4h9.4a3.7 3.7 0 0 0 .5-7.4 5.4 5.4 0 0 0-10.3-1.2 3.7 3.7 0 0 0 .4 8.6z"/>'),
    rain:w('<path d="M7.4 14.6h9.4a3.7 3.7 0 0 0 .5-7.4 5.4 5.4 0 0 0-10.3-1.2 3.7 3.7 0 0 0 .4 8.6z"/><path d="M8.6 18.1 7.4 21M13 18.1 11.8 21M17.4 18.1 16.2 21"/>'),
    storm:w('<path d="M7.4 14.2h9.4a3.7 3.7 0 0 0 .5-7.4 5.4 5.4 0 0 0-10.3-1.2 3.7 3.7 0 0 0 .4 8.6z"/><path d="M13.4 16.4 10 19.6h3.2L10.6 22.6"/>'),
    stadium:w('<path d="M3.4 7.6c0-1.9 3.9-3.4 8.6-3.4s8.6 1.5 8.6 3.4-3.9 3.4-8.6 3.4-8.6-1.5-8.6-3.4z"/><path d="M3.4 7.6v8.8c0 1.9 3.9 3.4 8.6 3.4s8.6-1.5 8.6-3.4V7.6"/><path d="M8.6 11.4v7.6M15.4 11.4v7.6"/>'),
    shield:w('<path d="M12 2.8 4.6 5.8v5.6c0 4.4 3.1 8.4 7.4 9.8 4.3-1.4 7.4-5.4 7.4-9.8V5.8z"/>'),
    whistle:w('<path d="M14.6 9.4H21M8.4 6.2a5.4 5.4 0 1 0 0 10.8 5.4 5.4 0 0 0 5.2-4h5.1a2.2 2.2 0 0 0 0-4.4h-5.1"/>'),
    gauge:w('<path d="M4.2 18a9 9 0 1 1 15.6 0"/><path d="m12 14 4-4"/><circle cx="12" cy="14" r="1.6"/>'),
    snow:w('<path d="M7.4 14.6h9.4a3.7 3.7 0 0 0 .5-7.4 5.4 5.4 0 0 0-10.3-1.2 3.7 3.7 0 0 0 .4 8.6z"/><path d="M8.4 18.6v2.8M7.2 19.3l2.4 1.4M9.6 19.3l-2.4 1.4M15.6 18.6v2.8M14.4 19.3l2.4 1.4M16.8 19.3l-2.4 1.4"/>')
  };
})();

/* games, each with its conditions and the matchups inside it */
function cellHTML(x){
  var cls=x.sev>=2?'s2':x.sev===1?'s1':'';
  var ic=x.ic, note=x.note;
  if(x.rlabel) note=x.rlabel+'. '+note;
  if(ic==='wx'){
    var wc=WXC[num(x.cond,-1)];
    ic = wc ? (/storm/.test(wc[0])?'storm' : /rain/.test(wc[0])?'rain'
             : /snow/.test(wc[0])?'snow' : /sun|moon/.test(wc[0])?'sun' : 'cloud') : 'cloud';
    if(wc) note = wc[1]+'. '+note;
  }
  var meta='';
  if(x.d) meta+='<span class="cd '+(num(x.dsign)>0?'up':num(x.dsign)<0?'dn':'')+'">'+esc(x.d)+'</span>';
  if(x.ref) meta+='<span>vs '+esc(x.ref)+'</span>';
  if(x.favors) meta+='<span class="cfav">'+esc(x.favors==='home'?'\u2192 HOME':'\u2192 AWAY')+'</span>';
  return '<div class="cell '+cls+'" title="'+esc(note)+'">'+
    '<span class="ci">'+(CICON[ic]||'')+'</span>'+
    '<span class="cb"><span class="cl">'+esc(x.k)+'</span>'+
    '<span class="cvv">'+esc(x.v)+'</span>'+
    (meta?'<span class="cr">'+meta+'</span>':'')+
    '</span></div>';
}
/* three groups, in the order a reader actually asks the questions:
   what is it like out there, where is this being played, how do these teams behave */
var CGROUPS=[['cond','Conditions'],['set','Setting'],['tend','Tendencies']];
function conditionsGrid(f){
  var h='';
  CGROUPS.forEach(function(gp){
    var items=f.filter(function(x){return (x.grp||'set')===gp[0];});
    if(!items.length) return;
    h+='<div class="cgroup"><div class="cglabel">'+esc(gp[1])+'</div>'+
       '<div class="cgitems">'+items.map(cellHTML).join('')+'</div></div>';
  });
  return h;
}

/* share of the offence, on the row where the player already is */
function shareInline(id){
  var pr=PR(id); if(!pr||!pr.S||!pr.S.ts) return '';
  var ts=num(pr.S.ts); if(ts<=0) return '';
  var w=Math.min(100, ts/32*100);          /* 32% is about the league ceiling */
  return '<span class="tshare" title="'+esc(PL(id).n)+' took '+ts.toFixed(1)+
    '% of his offence\u2019s targets in 2025">'+
    '<span class="tsb"><i style="width:'+w.toFixed(0)+'%"></i></span>'+
    '<span class="tsv">'+ts.toFixed(0)+'%</span></span>';
}

function PRD(id){ return (D.pred||{})[id]||null; }
function fx(n,d){ var v=num(n); var s=v.toFixed(d===undefined?1:d); return s.replace(/\.0$/,''); }
function spLab(g,v){
  if(v==null||v==='') return '\u2014';
  var n=num(v);
  if(Math.abs(n)<0.05) return 'PK';
  return (n<0 ? esc(g.h)+' \u2212'+fx(-n) : esc(g.a)+' \u2212'+fx(n));
}
function leanSp(g,p){
  if(p.dsp==null) return '';
  var d=num(p.dsp);
  if(Math.abs(d)<0.25) return 'agrees with the market';
  return fx(Math.abs(d))+' pts toward '+esc(d>0?g.a:g.h);
}
function leanTot(p){
  if(p.dtot==null) return '';
  var d=num(p.dtot);
  if(Math.abs(d)<0.25) return 'agrees with the market';
  return fx(Math.abs(d))+' pts toward the '+(d>0?'over':'under');
}
function predRows(g,p,k){
  var a=k==='sp', gi=a?p.sp:p.tot, bl=a?p.bsp:p.btot, ve=a?g.spread:g.ou;
  function cell(v){ return a?spLab(g,v):(v==null?'\u2014':fx(v)); }
  return '<div class="pr-r gi"><span>GridIron</span><b>'+cell(gi)+'</b></div>'+
         '<div class="pr-r"><span>Blended</span><b>'+cell(bl)+'</b></div>'+
         '<div class="pr-r"><span>Vegas</span><b>'+cell(ve)+'</b></div>';
}
function volLine(g,side,tc){
  var d=side==='h'?PRD(g.id).h:PRD(g.id).a, men=d.men||[];
  if(!men.length) return '';
  var top=men.slice(0,4).map(function(m){
    return '<span class="vn">'+esc(m.n)+' <b>'+fx(m.y,0)+'</b></span>'; }).join('');
  return '<div class="pr-vol"><span class="vk">projected starters account for '+
    (d.pyd==null?'\u2014':fx(d.pyd,0))+' yds</span>'+top+'</div>';
}
function grade(g,p){
  var sc=g.sc; if(!sc||g.state!=='post') return '';
  var am=num(sc.h)-num(sc.a), gm=num(p.ph)-num(p.pa);
  var me=Math.abs(am-gm), ve=(g.spread==null?null:Math.abs(am-(-num(g.spread))));
  var out='final '+g.a+' '+num(sc.a)+'\u2013'+g.h+' '+num(sc.h)+
    ' \u00b7 GridIron missed the margin by '+fx(me);
  if(ve!=null) out+=', Vegas by '+fx(ve);
  return esc(out);
}
function RD(team){ return (D.redist||{})[team]||null; }
function injPanel(g){
  var out='';
  [g.a,g.h].forEach(function(t){
    var r=RD(t); if(!r||!r.out.length) return;
    var gone=r.out.filter(function(o){return num(o.med,0)>0.4||num(o.car,0)>2||num(o.tgt,0)>1.5;});
    if(!gone.length) return;
    var to=(r.to||[]).filter(function(m){return num(m.a)-num(m.b)>=0.2;}).slice(0,4);
    out+='<div class="ijrow"><span class="ijt">'+esc(t)+'</span>'+
      '<span class="ijout">'+gone.map(function(o){
        return '<b>'+esc(o.n)+'</b> <em>'+esc(o.s)+'</em>'+
          (num(o.med,0)>0.4?' <i>'+num(o.med).toFixed(1)+' pts</i>':'')+
          '<u>'+(num(o.car,0)>=1?num(o.car).toFixed(0)+' car':'')+
          (num(o.car,0)>=1&&num(o.tgt,0)>=1?' \u00b7 ':'')+
          (num(o.tgt,0)>=1?num(o.tgt).toFixed(0)+' tgt':'')+'</u>';
      }).join('<span class="ijsep">\u00b7</span>')+'</span>'+
      '<span class="ijto">'+(to.length
        ? to.map(function(m){
            return '<span class="ijg">'+esc(m.n)+' <b>'+num(m.b).toFixed(1)+'\u2192'+
              num(m.a).toFixed(1)+'</b></span>'; }).join('')
        : '<span class="ijnone">no projected teammate absorbs enough to matter</span>')+'</span></div>';
  });
  if(!out) return '';
  return '<div class="ijpanel"><div class="ijhd">Ruled out, and where the volume goes'+
    '<small>75% of lost targets and 54% of lost carries are recovered \u2014 measured on 2025</small></div>'+
    out+'</div>';
}
function injRow(pj){
  var j=pj.inj; if(!j) return '';
  var pc=(num(j.m)-1)*100;
  if(Math.abs(pc)<0.5) return '';
  var bits=[];
  if(num(j.c)>=0.4) bits.push('+'+num(j.c).toFixed(1)+' carries');
  if(num(j.t)>=0.3) bits.push('+'+num(j.t).toFixed(1)+' targets');
  return '<div><span class="lab">Someone else is out<small>'+esc((j.who||[]).join(', '))+
    ' \u2014 '+esc(bits.join(', ')||'a small share')+'</small></span>'+
    '<span class="val" style="color:#4ADE80">+'+pc.toFixed(1)+'%<em>'+
    num(j.b).toFixed(1)+' \u2192 '+num(j.a!=null?j.a:pj.med).toFixed(1)+'</em></span></div>';
}

function shiftText(g,v){
  var h=num(v)/2, s=function(x){return (x>=0?'+':'\u2212')+Math.abs(x).toFixed(1);};
  return esc(g.h)+' '+s(h)+' \u00b7 '+esc(g.a)+' '+s(-h);
}
function predBlock(g){
  var p=PRD(g.id); if(!p) return '';
  var tc=teamColors(g), wpH=num(p.wp), wpA=100-wpH, T=D.track||{}, HO=T.held||T.all||{};
  var rows='';
  rows+='<div class="wf"><span class="wk">'+esc(g.an)+' offense vs '+esc(g.hn)+' defense</span>'+
    '<span class="wd">'+fx(p.a.yd,0)+' yds \u00b7 '+fx(p.a.td,1)+' TD \u00b7 '+fx(p.a.to,1)+' TO</span>'+
    '<span class="wv">'+num(p.a.p0).toFixed(1)+'</span></div>'+volLine(g,'a',tc);
  rows+='<div class="wf"><span class="wk">'+esc(g.hn)+' offense vs '+esc(g.an)+' defense</span>'+
    '<span class="wd">'+fx(p.h.yd,0)+' yds \u00b7 '+fx(p.h.td,1)+' TD \u00b7 '+fx(p.h.to,1)+' TO</span>'+
    '<span class="wv">'+num(p.h.p0).toFixed(1)+'</span></div>'+volLine(g,'h',tc);
  (p.steps||[]).forEach(function(s){
    var zero=Math.abs(num(s.v))<0.05;
    if(zero&&!g.neutral) return;
    rows+='<div class="wf shift"><span class="wk">'+esc(s.k)+'</span><span class="wd">'+esc(s.w)+
      ' \u00b7 moves points between the teams, not onto the total</span><span class="wv">'+(zero?'0.0':shiftText(g,s.v))+'</span></div>';
  });
  var wxg=(D.wx||{})[g.id];
  if(wxg){
    var pc=(num(wxg.m.att)*num(wxg.m.ypa)-1)*100;
    if(Math.abs(pc)>=1.5)
      rows+='<div class="wf info"><span class="wk">Conditions, on passing yardage</span><span class="wd">'+
        esc(wxg.dome?'indoors \u2014 no wind or cold':num(wxg.wind).toFixed(0)+' mph sustained wind'+(num(wxg.temp)<=40?', '+num(wxg.temp).toFixed(0)+'\u00b0F':''))+
        ' \u00b7 in every player projection below; not added to the game total</span>'+
        '<span class="wv '+(pc>0?'up':'dn')+'">'+(pc>0?'+':'\u2212')+Math.abs(pc).toFixed(1)+'%</span></div>';
  }
  (p.tsteps||[]).forEach(function(s){
    rows+='<div class="wf shift"><span class="wk">'+esc(s.k)+'</span><span class="wd">'+esc(s.w)+
      ' \u00b7 adds to the total, split evenly between the teams</span><span class="wv">'+(num(s.v)>=0?'+':'\u2212')+Math.abs(num(s.v)).toFixed(1)+' total</span></div>';
  });
  if(!(p.tsteps||[]).some(function(s){ return s.k==='Referee crew'; }))
    rows+='<div class="wf zero"><span class="wk">Referee crew</span>'+
      '<span class="wd">no measurable effect on scoring so far \u2014 zero weight, re-tested every week</span><span class="wv">0.0</span></div>';
  return '<div class="gc-pred">'+
    '<div class="pr-hd"><span class="pr-t">GridIron\u2019s <em class="s">own call</em></span></div>'+
    liveStrip(g)+
    '<div class="pr-grid">'+
      '<div class="pr-col"><span class="pr-lab">Spread</span><div class="pr-rows">'+predRows(g,p,'sp')+'</div>'+
        '<div class="pr-d">'+esc(leanSp(g,p))+'</div></div>'+
      '<div class="pr-col"><span class="pr-lab">Total</span><div class="pr-rows">'+predRows(g,p,'to')+'</div>'+
        '<div class="pr-d">'+esc(leanTot(p))+'</div></div>'+
      '<div class="pr-col wpc"><span class="pr-lab">Win probability</span>'+
        '<div class="wpbar"><i style="width:'+wpA.toFixed(0)+'%;background:'+tc.a+'"></i><i style="width:'+wpH.toFixed(0)+'%;background:'+tc.h+'"></i></div>'+
        '<div class="wpl"><span><b>'+esc(g.a)+'</b> '+wpA.toFixed(0)+'%</span><span><b>'+esc(g.h)+'</b> '+wpH.toFixed(0)+'%</span></div>'+
        '<div class="pr-d">\u00b1'+fx(p.sd)+' pts typical error</div></div>'+
    '</div>'+
    '<div class="pr-how"><span class="pr-lab">How it got there</span>'+rows+
      '<div class="wf tot"><span class="wk">Projected score</span><span class="wd">'+grade(g,p)+'</span>'+
      '<span class="wv">'+esc(g.a)+' '+num(p.pa).toFixed(1)+' \u00b7 '+esc(g.h)+' '+num(p.ph).toFixed(1)+'</span></div></div>'+
    ledgerNote(g)+
    '<div class="pr-foot">'+esc((p.notes||[]).join(' \u00b7 '))+((p.notes||[]).length?'. ':'')+
      'On '+num(HO.atsn).toLocaleString()+' games from 2023\u201325 that the model never trained on, GridIron picked <b>'+
      num(HO.ats).toFixed(1)+'%</b> against the spread \u2014 short of the 52.4% needed to profit. '+
      'Read a disagreement as a reason to look closer, not as an edge.</div>'+
  '</div>';
}
function matchRow(m){
  var op=PL(m.oid),dp=PL(m.did),u=U(m.oid),e=m.edge,ec=edgeColor(e);
  var gm=D.games[m.gi], done=gm.state==='post', inp=gm.state==='in', lv=liveLine(gm,m.oid);
  var r=done?(RS(m.oid)||lv):(inp?lv:null), pj=done?null:((inp&&lv)?null:PJ(m.oid));
  var c=col(m.offC);
  return '<div class="mline"><button class="mrow2" data-oid="'+esc(m.oid)+'" data-gi="'+m.gi+'">'+
    (function(){var bg=faceBg(m.oid,28);
      return bg ? '<span class="jn face" style="'+bg+'">'+(op.j?'<span class="num">'+esc(op.j)+'</span>':'')+'</span>'
        : '<span class="jn" style="background:linear-gradient(180deg,'+shade(c,1.4)+','+shade(c,.6)+');color:'+
          readable(c)+'">'+esc(op.j||'-')+'</span>';})()+
    '<span class="side2"><span class="n1">'+esc(op.n)+injChip(m.oid)+
      ' <span class="lbl3">'+esc(m.label)+'</span></span>'+
      '<span class="n2">'+(r&&statLine(r)
        ? esc(statLine(r))
        : 'vs '+esc(dp.n)+' <em>'+esc(m.dslot||dp.p||'')+'</em>')+'</span>'+
      shareInline(m.oid)+'</span>'+
    '<span class="sn">'+(u&&u.s!=null?Math.round(u.s)+'%':'\u2014')+'</span>'+
    (r
      ? '<span class="act">'+(r.pts!=null?r.pts.toFixed(1):'\u2014')+'</span>'+(r.live?'<span class="vd live">'+(inp?'LIVE':'UNOFFICIAL')+'</span>':verdictChip(r))
      : (pj
          ? '<span class="pj"><span class="med">'+pj.med.toFixed(1)+'</span>'+rangeBar(pj,72,16)+'</span>'
          : '<span class="ev" style="color:'+ec+'">'+(e==null?'\u2014':(e>0?'+':'')+e.toFixed(0))+'</span>'))+
    '</button>'+
    '<button class="pinbtn2" data-pin="'+esc(m.oid)+'" aria-pressed="'+(pinned.indexOf(m.oid)>=0)+'" '+
      'aria-label="Compare '+esc(op.n)+'"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" '+
      'stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><path d="M12 5v14M5 12h14"/>'+
      '</svg></button></div>';
}
function jersey(id,color,size){
  var p=PL(id),c=col(color),bg=faceBg(id,size);
  if(bg) return '<span class="jer face" style="width:'+size+'px;height:'+size+'px;'+bg+'"></span>';
  return '<span class="jer" style="width:'+size+'px;height:'+size+'px;font-size:'+(size*0.46).toFixed(0)+'px;'+
    'background:linear-gradient(180deg,'+shade(c,1.4)+','+shade(c,.6)+');color:'+readable(c)+'">'+
    esc(p.j||'\u2013')+'</span>';
}

/* ============================================================================
   Projection rendering. Distributions arrive as quantile grids from the
   build-time simulation; everything here reads or interpolates them.
   ========================================================================== */
function PJ(id){return (D.proj||{})[id]||null;}
var QS=(D.cal&&D.cal.qs)||[2,5,10,20,25,30,40,50,60,70,75,80,85,90,95,98];

/* P(X > line), by interpolating the simulated CDF */
function pOver(q, line){
  if(!q||!q.length) return null;
  var ps=QS||[];
  if(line<=q[0]) return 1-ps[0]/100;
  if(line>=q[q.length-1]) return 1-ps[ps.length-1]/100;
  for(var i=1;i<q.length;i++){
    if(line<=q[i]){
      var t=(q[i]-q[i-1])>0?(line-q[i-1])/(q[i]-q[i-1]):0;
      return 1-(ps[i-1]+t*(ps[i]-ps[i-1]))/100;
    }
  }
  return 0;
}
/* compact floor-median-ceiling bar for a table row */
function rangeBar(r,w,h){
  if(!r) return '';
  var lo=0, hi=Math.max(r.ceil,1)*1.12;
  var x=function(v){return Math.max(0,Math.min(w,(v-lo)/(hi-lo)*w));};
  return '<svg class="rng" viewBox="0 0 '+w+' '+h+'" aria-hidden="true">'+
    '<rect x="0" y="'+(h/2-2)+'" width="'+w+'" height="4" rx="2" fill="rgba(255,255,255,.09)"/>'+
    '<rect x="'+x(r.flr)+'" y="'+(h/2-2.5)+'" width="'+Math.max(2,x(r.ceil)-x(r.flr))+'" height="5" rx="2.5" '+
      'fill="url(#rgGrad)" opacity=".9"/>'+
    '<circle cx="'+x(r.med)+'" cy="'+(h/2)+'" r="3.4" fill="#FAFAFA"/>'+
    '<defs><linearGradient id="rgGrad" x1="0" y1="0" x2="1" y2="0">'+
    '<stop offset="0" stop-color="#60A5FA" stop-opacity=".55"/>'+
    '<stop offset="100%" stop-color="#4ADE80" stop-opacity=".85"/></linearGradient></defs></svg>';
}
/* full density, differentiated from the quantile grid */
function distChart(q,w,h,med,flr,ceil){
  if(!q||q.length<4) return '';
  var ps=QS, pts=[], i;
  for(i=1;i<q.length;i++){
    var dx=q[i]-q[i-1], dp=(ps[i]-ps[i-1])/100;
    pts.push({x:(q[i]+q[i-1])/2, d: dx>0 ? dp/dx : 0});
  }
  var lo=q[0], hi=q[q.length-1], span=Math.max(1e-6,hi-lo);
  var maxd=Math.max.apply(null,pts.map(function(p){return p.d;}))||1;
  var X=function(v){return (v-lo)/span*w;};
  var Y=function(d){return h-6-(d/maxd)*(h-22);};
  /* light smoothing so the curve reads as a shape, not a histogram */
  var sm=pts.map(function(p,i2){
    var a=pts[Math.max(0,i2-1)].d, b=p.d, c=pts[Math.min(pts.length-1,i2+1)].d;
    return {x:p.x, d:(a+2*b+c)/4};
  });
  var path=sm.map(function(p,i2){return (i2?'L':'M')+X(p.x).toFixed(1)+' '+Y(p.d).toFixed(1);}).join(' ');
  var area=path+' L'+X(sm[sm.length-1].x).toFixed(1)+' '+(h-6)+' L'+X(sm[0].x).toFixed(1)+' '+(h-6)+' Z';
  var s='<svg class="dist" viewBox="0 0 '+w+' '+h+'" role="img" aria-label="Simulated outcome distribution">'+
    '<defs><linearGradient id="dg" x1="0" y1="0" x2="0" y2="1">'+
    '<stop offset="0" stop-color="#60A5FA" stop-opacity=".5"/>'+
    '<stop offset="100%" stop-color="#60A5FA" stop-opacity=".03"/></linearGradient></defs>';
  /* the middle-half band */
  s+='<rect x="'+X(flr).toFixed(1)+'" y="6" width="'+Math.max(1,X(ceil)-X(flr)).toFixed(1)+'" height="'+(h-12)+
     '" fill="#4ADE80" opacity=".07"/>';
  s+='<path d="'+area+'" fill="url(#dg)"/>';
  s+='<path d="'+path+'" fill="none" stroke="#93C5FD" stroke-width="1.8" stroke-linejoin="round"/>';
  s+='<line x1="'+X(med).toFixed(1)+'" y1="4" x2="'+X(med).toFixed(1)+'" y2="'+(h-6)+
     '" stroke="#FBBF24" stroke-width="1.8"/>';
  s+='<line x1="0" y1="'+(h-6)+'" x2="'+w+'" y2="'+(h-6)+'" stroke="rgba(255,255,255,.14)"/>';
  s+='</svg>';
  return s;
}

/* ============================ charts ============================
   Forms chosen by the data's job, not by preference: part-to-whole gets a
   stacked strip, magnitude-with-uncertainty gets a range plot. The categorical
   slots below are the validated dark-mode steps; every segment is direct
   labelled so identity never rests on colour alone. */
var SLOT=['var(--s1)','var(--s2)','var(--s3)','var(--s4)','var(--s5)','var(--s6)'];

function VER(gid,f){ var v=(D.verify||{})[gid]; return v?v[f]:null; }
function vbadge(gid,f){
  var r=VER(gid,f); if(!r) return '';
  var tick='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="m5 13 4 4L19 7"/></svg>';
  var bang='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M12 7v7M12 17.5h.01"/></svg>';
  var dot ='<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="5"/></svg>';
  if(r.s==='ok')     return '<span class="vbadge ok" title="Agreed by '+esc(r.srcs.join(' and '))+'">'+tick+'2 sources</span>';
  if(r.s==='x')      return '<span class="vbadge x" title="'+esc(r.srcs[0])+' says '+esc(r.v)+', '+esc(r.srcs[1])+' says '+esc(r.o)+'. Shown value is '+esc(r.srcs[0])+'\u2019s.">'+bang+'differ</span>';
  return '<span class="vbadge single" title="Only '+esc(r.srcs[0])+' publishes this">'+dot+'1 source</span>';
}

/* part-to-whole: how one offence divides its targets */
function shareChart(team, label){
  var dep=D.depth[team]; if(!dep) return '';
  var picks=[];
  (dep.o.WR||[]).slice(0,3).forEach(function(e){picks.push(e.g);});
  if((dep.o.TE||[])[0]) picks.push(dep.o.TE[0].g);
  if((dep.o.RB||[])[0]) picks.push(dep.o.RB[0].g);
  var rows=picks.map(function(id){
    var pr=PR(id); return {id:id, n:PL(id).n, ts:(pr&&pr.S&&pr.S.ts)?num(pr.S.ts):0};
  }).filter(function(r){return r.ts>0;});
  if(rows.length<2) return '';
  var used=rows.reduce(function(a,r){return a+r.ts;},0);
  var other=Math.max(0,100-used);
  var all=rows.concat(other>1?[{id:null,n:'Everyone else',ts:other}]:[]);
  var segs='', key='';
  all.forEach(function(r,i){
    var c = r.id? SLOT[i%6] : 'var(--line)';
    var wide = r.ts>=9;
    segs+='<div class="shareseg" style="flex:'+r.ts.toFixed(2)+';background:'+c+'" '+
      'title="'+esc(r.n)+' \u2014 '+r.ts.toFixed(1)+'% of targets in 2025">'+
      (wide?'<span>'+r.ts.toFixed(0)+'%</span>':'')+'</div>';
    key+='<div><i style="background:'+c+'"></i>'+esc(r.n.split(' ').slice(-1)[0])+
      ' <b>'+r.ts.toFixed(1)+'%</b></div>';
  });
  return '<div class="viz"><h4>'+esc(label)+'</h4>'+
    '<p class="vsub">Share of the offence\u2019s targets last season. A concentrated bar means '+
    'one receiver carries the passing game; an even one means volume is hard to predict.</p>'+
    '<div class="sharebar">'+segs+'</div><div class="sharekey">'+key+'</div></div>';
}

/* magnitude with uncertainty: every projected player in this game, one scale */
function rangeChart(gidx){
  var ms=MATCHUPS.filter(function(m){return m.gi===gidx;});
  var rows=[];
  ms.forEach(function(m){
    var pj=PJ(m.oid); if(!pj) return;
    rows.push({n:PL(m.oid).n, id:m.oid, flr:pj.flr, med:pj.med, ceil:pj.ceil, team:m.offT});
  });
  if(rows.length<3) return '';
  rows.sort(function(a,b){return b.med-a.med;});
  var hi=Math.max.apply(null,rows.map(function(r){return r.ceil;}))*1.04;
  var body=rows.map(function(r){
    var L=function(v){return (v/hi*100);};
    return '<div class="rangerow"><span class="rn">'+esc(r.n)+'</span>'+
      '<span class="rangetrack" title="'+esc(r.n)+' \u2014 floor '+r.flr.toFixed(1)+
        ', median '+r.med.toFixed(1)+', ceiling '+r.ceil.toFixed(1)+' PPR points">'+
        '<span class="ax"></span>'+
        '<span class="bandr" style="left:'+L(r.flr).toFixed(1)+'%;width:'+Math.max(0.8,L(r.ceil)-L(r.flr)).toFixed(1)+'%"></span>'+
        '<span class="medr" style="left:'+L(r.med).toFixed(1)+'%"></span></span>'+
      '<span class="rv">'+r.med.toFixed(1)+'</span></div>';
  }).join('');
  return '<div class="viz"><h4>Projected range</h4>'+
    '<p class="vsub">Each bar spans the middle of 20,000 simulations \u2014 25th to 85th percentile \u2014 '+
    'with the median marked. Long bars are volatile; short ones are safe.</p>'+
    body+'<div class="rangescale"><span>0</span><span>'+ (hi/2).toFixed(0) +'</span><span>'+hi.toFixed(0)+' pts</span></div></div>';
}

/* trend over time: one series, so no legend -- the title names it */
function trendChart(vals,label,unit){
  if(!vals||vals.length<3) return '';
  var W=316,H=76,P=6;
  var mx=Math.max.apply(null,vals.concat([1]))*1.12, n=vals.length;
  var X=function(i){return P+i*(W-2*P)/(n-1);};
  var Y=function(v){return H-14-(num(v)/mx)*(H-24);};
  var pts=vals.map(function(v,i){return [X(i),Y(v)];});
  var line=pts.map(function(p,i){return (i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1);}).join(' ');
  var area=line+' L'+pts[n-1][0].toFixed(1)+' '+(H-14)+' L'+pts[0][0].toFixed(1)+' '+(H-14)+' Z';
  var s='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'+esc(label)+' by week">'+
    '<defs><linearGradient id="tg1" x1="0" y1="0" x2="0" y2="1">'+
    '<stop offset="0" stop-color="#3987e5" stop-opacity=".38"/>'+
    '<stop offset="100%" stop-color="#3987e5" stop-opacity="0"/></linearGradient></defs>'+
    '<line x1="'+P+'" y1="'+(H-14)+'" x2="'+(W-P)+'" y2="'+(H-14)+'" stroke="#26262A"/>'+
    '<path d="'+area+'" fill="url(#tg1)"/>'+
    '<path d="'+line+'" fill="none" stroke="#3987e5" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>';
  pts.forEach(function(p,i){
    s+='<circle cx="'+p[0].toFixed(1)+'" cy="'+p[1].toFixed(1)+'" r="'+(i===n-1?3.6:2.4)+'" '+
       'fill="'+(i===n-1?'#3987e5':'#0E0E11')+'" stroke="#3987e5" stroke-width="1.6">'+
       '<title>'+num(vals[i])+(unit||'')+'</title></circle>';
  });
  s+='<text x="'+P+'" y="'+(H-3)+'" font-size="9" fill="#52525B">'+n+' weeks ago</text>'+
     '<text x="'+(W-P)+'" y="'+(H-3)+'" font-size="9" fill="#52525B" text-anchor="end">latest '+
     num(vals[n-1])+(unit||'')+'</text></svg>';
  return s;
}

function drawViz(gidx){
  var g=D.games[gidx];
  var h=rangeChart(gidx);
  render(document.getElementById('vizrow'), h||'<div class="nodata">Not enough 2025 history to chart this game.</div>');
}

/* ============================ compare tray ============================ */
function statOf(id,k){
  var p=PR(id),u=U(id);
  if(k==='snap') return u?u.s:null;
  if(k==='snap3') return u?u.s3:null;
  if(!p||!p.S) return null;
  var s=p.S,g=num(s.g,1)||1;
  if(k==='tgt') return num(s.tgt)/g;
  if(k==='yds') return (num(s.ry)+num(s.ru))/g;
  if(k==='td') return num(s.rtd)+num(s.rutd);
  if(k==='ts') return s.ts||null;
  return null;
}
var CMPROWS=[['snap','Snap %','%'],['snap3','Last 3 wks','%'],['ts','Target share','%'],
             ['tgt','Targets / game',''],['yds','Yards / game',''],['td','Touchdowns','']];
function drawTray(){
  var tray=document.getElementById('tray');
  document.getElementById('traycount').textContent = pinned.length
    ? pinned.length+' pinned' : '';
  if(!pinned.length){ tray.classList.remove('on'); return; }
  var best={};
  CMPROWS.forEach(function(r){
    var vals=pinned.map(function(id){return statOf(id,r[0]);}).filter(function(v){return v!=null;});
    best[r[0]]=vals.length?Math.max.apply(null,vals):null;
  });
  var h='';
  pinned.forEach(function(id){
    var p=PL(id);
    var m=MATCHUPS.filter(function(x){return x.oid===id;})[0];
    var lead=CMPROWS.every(function(r){
      var v=statOf(id,r[0]); return v==null||best[r[0]]==null||v>=best[r[0]];
    });
    h+='<div class="cmpcol'+(lead?' lead':'')+'">'+
      '<div class="cmp-hd">'+jersey(id,m?m.offC:'#666',26)+
      '<div style="min-width:0"><div class="nm">'+esc(p.n)+'</div>'+
      '<div class="sub2 mono" style="font-size:9px;color:var(--fg-4)">'+esc(p.p)+' \u00b7 '+esc(p.t)+
      (m?' vs '+esc(m.defT):'')+'</div></div>'+
      '<button class="pinbtn" data-pin="'+esc(id)+'" aria-pressed="true" style="margin-left:auto" '+
      'aria-label="Remove"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" '+
      'stroke-width="2.6" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg></button></div>';
    CMPROWS.forEach(function(r){
      var v=statOf(id,r[0]);
      var isBest=v!=null&&best[r[0]]!=null&&Math.abs(v-best[r[0]])<1e-9&&pinned.length>1;
      h+='<div class="cmprow"><span class="k">'+esc(r[1])+'</span>'+
        '<span class="v'+(isBest?' best':'')+'">'+
        (v==null?'<span style="color:var(--fg-4);font-size:12px">\u2014</span>':v.toFixed(r[2]==='%'?0:1)+r[2])+
        '</span></div>';
    });
    if(m) h+='<div class="cmprow"><span class="k">Matchup edge</span><span class="v" style="color:'+
      edgeColor(m.edge)+'">'+(m.edge==null?'\u2014':(m.edge>0?'+':'')+m.edge.toFixed(0))+'</span></div>';
    h+='</div>';
  });
  var el=document.getElementById('cmp');
  el.style.gridTemplateColumns='repeat('+pinned.length+',minmax(0,1fr))';
  render(el,h);
  tray.classList.add('on');
}
function togglePin(id){
  var i=pinned.indexOf(id);
  if(i>=0) pinned.splice(i,1);
  else { if(pinned.length>=4) pinned.shift(); pinned.push(id); }
  if(typeof route==='number') drawMatchups(); drawTray();
}

/* ============================ FIELD VIEW ============================ */
var VW=1400,VH=830;
var FX=14,FY=14,FW=VW-28,FH=VH-28;
var GL=FX+FW*(10/120),GR=FX+FW*(110/120),CY=FY+FH/2;
var LOS=FX+FW*(58/120);
var gi=D.games.findIndex(function(g){return g.state==='in';});
if(gi<0) gi=D.games.findIndex(function(g){return g.state==='pre';}); if(gi<0) gi=0;
var poss='h',selected=null,mode='form',route='teams';
var DCOLS=4,DPITCH=147;
var DROW_O={WR:105,TE:268,RB:431,QB:594,OL:757},DROW_D={CB:150,S:330,LB:510,DL:690};
var DX0_O=150,DX0_D=800;

function spread(n,y0,y1,x){var o=[],i;for(i=0;i<n;i++)o.push([x,n===1?(y0+y1)/2:y0+(y1-y0)*i/(n-1)]);return o;}
function placeOff(fam,list){
  if(fam==='WR') return [[168,108],[168,726],[318,612]].slice(0,list.length);
  if(fam==='TE') return [[486,740]];
  if(fam==='RB') return [[326,486]];
  if(fam==='QB') return [[474,374]];
  if(fam==='OL') return spread(list.length,138,626,624);
  return [];
}
function placeDef(fam,list){
  if(fam==='CB'){var wide=[[1268,108],[1268,726]],slot=[1126,598],o=[],w=0;
    list.forEach(function(p){o.push(p.p==='NB'?slot:(wide[w++]||slot));});return o;}
  if(fam==='S') return list.map(function(p,i){return p.p==='SS'?[962,734]:(i===0?[1188,378]:[962,734]);});
  if(fam==='LB') return spread(list.length,252,566,890);
  if(fam==='DL') return spread(list.length,196,604,748);
  return [];
}
function placeDepth(fam,list,side){
  var y=(side==='off'?DROW_O:DROW_D)[fam]; if(y==null) return [];
  var x0=(side==='off'?DX0_O:DX0_D),n=list.length,pitch=DPITCH,o=[],i;
  if(n>DCOLS){pitch=130;x0-=34;}
  for(i=0;i<n;i++)o.push([x0+i*pitch,y]);
  return o;
}
function turf(){
  var s='',i,x;
  for(i=0;i<24;i++)
    s+='<rect x="'+(FX+i*FW/24)+'" y="'+FY+'" width="'+(FW/24)+'" height="'+FH+'" fill="'+(i%2?'#1A8A33':'#147528')+'"/>';
  s+='<rect x="'+FX+'" y="'+FY+'" width="'+(FW*10/120)+'" height="'+FH+'" fill="#0E5D22" opacity=".82"/>';
  s+='<rect x="'+GR+'" y="'+FY+'" width="'+(FW*10/120)+'" height="'+FH+'" fill="#0E5D22" opacity=".82"/>';
  s+='<rect x="'+FX+'" y="'+FY+'" width="'+FW+'" height="'+FH+'" filter="url(#grain)" opacity=".4"/>';
  s+='<g stroke="#FFFFFF" stroke-opacity=".6" stroke-width="2">';
  for(i=0;i<=20;i++){x=GL+i*(GR-GL)/20;s+='<line x1="'+x+'" y1="'+FY+'" x2="'+x+'" y2="'+(FY+FH)+'"/>';}
  s+='</g>';
  s+='<rect x="'+FX+'" y="'+FY+'" width="'+FW+'" height="'+FH+'" fill="none" stroke="#FFFFFF" stroke-opacity=".9" stroke-width="4"/>';
  s+='<g stroke="#FFFFFF" stroke-opacity=".9" stroke-width="3.5"><line x1="'+GL+'" y1="'+FY+'" x2="'+GL+'" y2="'+(FY+FH)+'"/>'+
     '<line x1="'+GR+'" y1="'+FY+'" x2="'+GR+'" y2="'+(FY+FH)+'"/></g>';
  var HT=FY+FH*(23.583/53.33),HB=FY+FH-FH*(23.583/53.33),yd=(GR-GL)/100;
  s+='<g stroke="#FFFFFF" stroke-opacity=".38" stroke-width="1.6">';
  for(i=1;i<100;i++){ if(i%5===0) continue; x=GL+i*yd;
    s+='<line x1="'+x+'" y1="'+(HT-5)+'" x2="'+x+'" y2="'+(HT+5)+'"/>'+
       '<line x1="'+x+'" y1="'+(HB-5)+'" x2="'+x+'" y2="'+(HB+5)+'"/>'+
       '<line x1="'+x+'" y1="'+(FY+3)+'" x2="'+x+'" y2="'+(FY+13)+'"/>'+
       '<line x1="'+x+'" y1="'+(FY+FH-13)+'" x2="'+x+'" y2="'+(FY+FH-3)+'"/>';}
  s+='</g>';
  var nums=[10,20,30,40,50,40,30,20,10];
  s+='<g fill="#FFFFFF" fill-opacity=".48" font-family="Archivo,sans-serif" font-weight="700" font-size="34" letter-spacing="6">';
  nums.forEach(function(n,k){var nx=GL+(k+1)*10*yd,ty=FY+96,by=FY+FH-70;
    s+='<text x="'+nx+'" y="'+ty+'" transform="rotate(180 '+nx+' '+(ty-11)+')" text-anchor="middle">'+n+'</text>'+
       '<text x="'+nx+'" y="'+by+'" text-anchor="middle">'+n+'</text>';});
  s+='</g>';
  return s;
}
function depthChrome(){
  var s='<g class="dchrome">';
  [DX0_O,DX0_D].forEach(function(x0){
    s+='<rect x="'+(x0-96)+'" y="58" width="'+(DPITCH*DCOLS+100)+'" height="764" rx="10" fill="#03080A" opacity=".6"/>';
    ['FIRST','SECOND','THIRD','FOURTH'].forEach(function(hd,i){
      s+='<text x="'+(x0+i*DPITCH)+'" y="78" text-anchor="middle" font-family="IBM Plex Mono,monospace" '+
         'font-size="9.5" font-weight="600" letter-spacing="1.6" fill="#FFFFFF" fill-opacity=".42">'+hd+'</text>';});
  });
  [[DROW_O,DX0_O],[DROW_D,DX0_D]].forEach(function(pr){
    Object.keys(pr[0]).forEach(function(k){var y=pr[0][k];
      s+='<text x="'+(pr[1]-68)+'" y="'+(y+6)+'" text-anchor="middle" font-family="Barlow Condensed,sans-serif" '+
         'font-weight="700" font-size="22" fill="#FFFFFF" fill-opacity=".5" letter-spacing="1">'+k+'</text>'+
         '<line x1="'+(pr[1]-88)+'" y1="'+(y+62)+'" x2="'+(pr[1]+DPITCH*3+70)+'" y2="'+(y+62)+'" '+
         'stroke="#FFFFFF" stroke-opacity=".1"/>';});
  });
  return s+'</g>';
}
function token(o){
  var r=26,c=col(o.color),ink=readable(c),lw=String(o.label).length*7.6+16;
  var g='<g class="tok'+(o.sel?' sel':'')+(o.ghost?' ghost':'')+'" data-id="'+esc(o.id)+'" '+
    'data-side="'+esc(o.side)+'" data-fam="'+esc(o.fam)+'" data-dx="'+o.dx.toFixed(1)+'" '+
    'data-dy="'+o.dy.toFixed(1)+'" data-ghost="'+(o.ghost?1:0)+'" tabindex="0" role="button" '+
    'aria-label="'+esc(o.label)+' '+esc(o.name)+', number '+esc(o.jersey||'unknown')+'">'+
    '<g class="tokin" style="animation-delay:'+num(o.delay)+'ms">';
  g+='<circle class="glow" cx="'+o.x+'" cy="'+o.y+'" r="'+(r+11)+'" fill="'+(o.sel?'#FBBF24':c)+'" filter="url(#soft)"/>';
  g+='<ellipse cx="'+o.x+'" cy="'+(o.y+r*0.9)+'" rx="'+(r*0.96)+'" ry="'+(r*0.3)+'" fill="#000" opacity=".45" filter="url(#soft)"/>';
  g+='<circle class="disc" cx="'+o.x+'" cy="'+o.y+'" r="'+r+'" fill="url(#tk'+esc(o.gid)+')" stroke="'+
     (o.sel?'#FFFFFF':'rgba(255,255,255,.9)')+'" stroke-width="'+(o.sel?3:2)+'"/>';
  g+='<path d="M '+(o.x-r*0.74)+' '+(o.y-r*0.3)+' A '+(r*0.88)+' '+(r*0.88)+' 0 0 1 '+(o.x+r*0.16)+' '+(o.y-r*0.84)+
     '" fill="none" stroke="#FFFFFF" stroke-opacity=".42" stroke-width="2" stroke-linecap="round"/>';
  if(o.inj) g+='<circle cx="'+o.x+'" cy="'+o.y+'" r="'+(r+5)+'" fill="none" stroke="'+
     (o.inj==='O'?'#F87171':'#FBBF24')+'" stroke-width="2.6" stroke-dasharray="'+(o.inj==='O'?'999':'6 5')+'"/>';
  var fsv=faceSvg(o.id,o.x,o.y,r,o.uid);
  if(fsv) g+=fsv;
  else g+='<text x="'+o.x+'" y="'+(o.y+9)+'" text-anchor="middle" font-weight="600" font-size="23" '+
     'fill="'+ink+'" pointer-events="none">'+esc(o.jersey||'-')+'</text>';
  g+='<g pointer-events="none"><rect x="'+(o.x-lw/2)+'" y="'+(o.y-r-24)+'" width="'+lw+'" height="18" rx="4" '+
     'fill="'+c+'" stroke="rgba(255,255,255,.4)"/><text x="'+o.x+'" y="'+(o.y-r-10.5)+'" text-anchor="middle" '+
     'font-family="Barlow Condensed,sans-serif" font-weight="700" font-size="13.5" letter-spacing=".7" fill="'+ink+'">'+
     esc(o.label)+'</text></g>';
  g+='<text x="'+o.x+'" y="'+(o.y+r+19)+'" text-anchor="middle" font-family="Archivo,sans-serif" font-weight="700" '+
     'font-size="13.5" fill="#FFFFFF" pointer-events="none" style="paint-order:stroke;stroke:#040A07;stroke-width:4px;'+
     'stroke-linejoin:round">'+esc(o.name)+'</text>';
  g+='<text x="'+o.x+'" y="'+(o.y+r+33)+'" text-anchor="middle" font-family="IBM Plex Mono,monospace" font-size="10.5" '+
     'fill="#D4D4D8" pointer-events="none" style="paint-order:stroke;stroke:#040A07;stroke-width:3.5px;stroke-linejoin:round">'+
     (o.snap!=null?Math.round(o.snap)+'% snaps':'no 2025 snaps')+'</text>';
  g+='<circle class="hit" cx="'+o.x+'" cy="'+o.y+'" r="'+(r+14)+'"/></g></g>';
  return g;
}
function buildField(){
  var g=D.games[gi],H=header();
  var offT=poss==='h'?g.h:g.a,defT=poss==='h'?g.a:g.h;
  var offC=H.offc,defC=H.defc;
  var od=D.depth[offT],dd=D.depth[defT];
  var box=document.getElementById('fbox');
  if(!od||!dd){render(box,'<div class="empty">No depth chart published for this matchup yet.</div>');return;}
  var PD=podsD(dd.s);
  var s='<svg class="pitch" viewBox="0 0 '+VW+' '+VH+'" role="img" aria-label="'+esc(offT)+' offense against '+esc(defT)+' defense">'+
   '<defs><filter id="soft" x="-70%" y="-70%" width="240%" height="240%"><feGaussianBlur stdDeviation="6"/></filter>'+
   '<filter id="grain"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="3" seed="11"/>'+
   '<feColorMatrix type="saturate" values="0"/><feComponentTransfer><feFuncA type="linear" slope=".13"/></feComponentTransfer></filter>'+
   '<radialGradient id="vig" cx="50%" cy="46%" r="76%"><stop offset="50%" stop-color="#000" stop-opacity="0"/>'+
   '<stop offset="100%" stop-color="#000" stop-opacity=".62"/></radialGradient>'+
   '<linearGradient id="lights" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFF" stop-opacity=".12"/>'+
   '<stop offset="46%" stop-color="#FFF" stop-opacity="0"/><stop offset="100%" stop-color="#000" stop-opacity=".22"/></linearGradient>'+
   '<linearGradient id="tkO" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="'+shade(offC,1.5)+'"/>'+
   '<stop offset="50%" stop-color="'+col(offC)+'"/><stop offset="100%" stop-color="'+shade(offC,.56)+'"/></linearGradient>'+
   '<linearGradient id="tkD" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="'+shade(defC,1.5)+'"/>'+
   '<stop offset="50%" stop-color="'+col(defC)+'"/><stop offset="100%" stop-color="'+shade(defC,.56)+'"/></linearGradient></defs>'+
   '<rect width="'+VW+'" height="'+VH+'" fill="#061009"/>'+turf();
  s+='<text x="'+(FX+FW*5/120)+'" y="'+CY+'" transform="rotate(-90 '+(FX+FW*5/120)+' '+CY+')" text-anchor="middle" '+
     'font-family="Archivo,sans-serif" font-weight="800" font-size="40" letter-spacing="10" fill="#FFF" fill-opacity=".32">'+esc(defT)+'</text>'+
     '<text x="'+(GR+FW*5/120)+'" y="'+CY+'" transform="rotate(90 '+(GR+FW*5/120)+' '+CY+')" text-anchor="middle" '+
     'font-family="Archivo,sans-serif" font-weight="800" font-size="40" letter-spacing="10" fill="#FFF" fill-opacity=".32">'+esc(offT)+'</text>';
  var yd=(GR-GL)/100;
  s+='<line x1="'+LOS+'" y1="'+FY+'" x2="'+LOS+'" y2="'+(FY+FH)+'" stroke="#60A5FA" stroke-width="4" opacity=".95"/>'+
     '<line x1="'+(LOS+10*yd)+'" y1="'+FY+'" x2="'+(LOS+10*yd)+'" y2="'+(FY+FH)+'" stroke="#FBBF24" stroke-width="4" opacity=".95"/>';
  var n=0,toks='';
  function lay(cfgs,side,color,gid,placer){
    var src=side==='off'?od.o:dd.d;
    cfgs.forEach(function(cfg){
      var all=src[cfg.k]||[];
      var shown=all.slice(0,Math.max(cfg.n,Math.min(DCOLS,all.length)));
      if(!shown.length) return;
      var f=placer(cfg.k,shown.slice(0,cfg.n)),dsp=placeDepth(cfg.k,shown,side);
      var anchor=f[f.length-1]||[LOS,CY];
      shown.forEach(function(p,i){
        var fs=f[i]||anchor,ds=dsp[i]||fs,pl=PL(p.g),u=U(p.g);
        toks+=token({id:p.g,uid:(n+1),name:pl.n,jersey:pl.j,label:cfg.k+(i+1),fam:cfg.k,
          x:fs[0],y:fs[1],dx:ds[0]-fs[0],dy:ds[1]-fs[1],ghost:i>=cfg.n,
          color:color,gid:gid,side:side,inj:(IJ(p.g)||{}).s,snap:u?u.s:null,
          sel:!!(selected&&selected===p.g),delay:RM?0:(n++)*26});
      });
    });
  }
  lay(PODS_O,'off',offC,'O',placeOff);
  lay(PD,'def',defC,'D',placeDef);
  s+=toks+depthChrome();
  s+='<rect x="'+FX+'" y="'+FY+'" width="'+FW+'" height="'+FH+'" fill="url(#lights)" pointer-events="none"/>'+
     '<rect width="'+VW+'" height="'+VH+'" fill="url(#vig)" pointer-events="none"/>'+
     '<g font-family="IBM Plex Mono,monospace" font-size="12" font-weight="600" letter-spacing="1.6">'+
     '<text x="30" y="'+(VH-16)+'" fill="#FFF" fill-opacity=".6">'+esc(offT)+' OFFENSE</text>'+
     '<text x="'+(VW-30)+'" y="'+(VH-16)+'" text-anchor="end" fill="#FFF" fill-opacity=".6">'+esc(defT)+' DEFENSE \u00b7 '+esc(dd.s)+'</text></g></svg>';
  render(box,s);
  var svg=box.querySelector('svg');
  applyLayout(svg,true);
  if(!RM){svg.classList.add('anim');setTimeout(function(){svg.classList.remove('anim');},1600);}
  wireField(box,offC,defC,offT,defT);
}
function applyLayout(svg,instant){
  if(!svg) return;
  var depth=mode==='depth';
  svg.classList.toggle('depthmode',depth);
  svg.querySelectorAll('.tok').forEach(function(el){
    if(instant) el.classList.add('instant');
    el.style.transform=depth?'translate('+num(el.dataset.dx)+'px,'+num(el.dataset.dy)+'px)':'translate(0px,0px)';
    var ghost=el.dataset.ghost==='1';
    el.classList.toggle('ghost',ghost&&!depth);
    el.setAttribute('tabindex',(ghost&&!depth)?'-1':'0');
  });
  if(instant) requestAnimationFrame(function(){
    svg.querySelectorAll('.tok.instant').forEach(function(e){e.classList.remove('instant');});});
}
function setMode(m){
  if(m===mode) return;
  mode=m;
  document.querySelectorAll('#layout button').forEach(function(b){
    b.setAttribute('aria-pressed',String(b.dataset.l===mode));});
  applyLayout(document.querySelector('#fbox svg'),false);
}

/* ---- weather ---- */
var ICO=(function(){
  var o='stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" fill="none"';
  var CL='M7.4 18.4h9.4a3.7 3.7 0 0 0 .5-7.4 5.4 5.4 0 0 0-10.3-1.2 3.7 3.7 0 0 0 .4 8.6z';
  var RY='M12 1.9v2M12 16.1v2M2.9 10h2M19.1 10h2M5.6 3.6 7 5M17 15l1.4 1.4M18.4 3.6 17 5M7 15l-1.4 1.4';
  function w(i){return '<svg viewBox="0 0 24 24" aria-hidden="true" '+o+'>'+i+'</svg>';}
  return {sun:w('<circle cx="12" cy="10" r="4"/><path d="'+RY+'"/>'),
    sunCloud:w('<circle cx="9" cy="7.4" r="2.8"/><path d="M9 1.9v1.6M3.7 7.4H2.1M14.3 6.2l1.1-1.1"/><path d="'+CL+'"/>'),
    cloud:w('<path d="'+CL+'"/>'),
    fog:w('<path d="M7.4 14.4h9.4a3.7 3.7 0 0 0 .5-7.4 5.4 5.4 0 0 0-10.3-1.2 3.7 3.7 0 0 0 .4 8.6z"/><path d="M4 18h9M7 21.2h10"/>'),
    rain:w('<path d="M7.4 14.6h9.4a3.7 3.7 0 0 0 .5-7.4 5.4 5.4 0 0 0-10.3-1.2 3.7 3.7 0 0 0 .4 8.6z"/><path d="M8.6 18.1 7.4 21M13 18.1 11.8 21M17.4 18.1 16.2 21"/>'),
    storm:w('<path d="M7.4 14.2h9.4a3.7 3.7 0 0 0 .5-7.4 5.4 5.4 0 0 0-10.3-1.2 3.7 3.7 0 0 0 .4 8.6z"/><path d="M13.4 16.4 10 19.6h3.2L10.6 22.6"/>'),
    stadium:w('<path d="M3.4 7.6c0-1.9 3.9-3.4 8.6-3.4s8.6 1.5 8.6 3.4-3.9 3.4-8.6 3.4-8.6-1.5-8.6-3.4z"/><path d="M3.4 7.6v8.8c0 1.9 3.9 3.4 8.6 3.4s8.6-1.5 8.6-3.4V7.6"/><path d="M8.6 11.4v7.6M15.4 11.4v7.6"/>'),
    shield:w('<path d="M12 2.8 4.6 5.8v5.6c0 4.4 3.1 8.4 7.4 9.8 4.3-1.4 7.4-5.4 7.4-9.8V5.8z"/>'),
    whistle:w('<path d="M14.6 9.4H21M8.4 6.2a5.4 5.4 0 1 0 0 10.8 5.4 5.4 0 0 0 5.2-4h5.1a2.2 2.2 0 0 0 0-4.4h-5.1"/>'),
    gauge:w('<path d="M4.2 18a9 9 0 1 1 15.6 0"/><path d="m12 14 4-4"/><circle cx="12" cy="14" r="1.6"/>'),
    snow:w('<path d="M7.4 14.6h9.4a3.7 3.7 0 0 0 .5-7.4 5.4 5.4 0 0 0-10.3-1.2 3.7 3.7 0 0 0 .4 8.6z"/><path d="M8.4 18.6v2.8M7.2 19.3l2.4 1.4M9.6 19.3l-2.4 1.4M15.6 18.6v2.8M14.4 19.3l2.4 1.4M16.8 19.3l-2.4 1.4"/>'),
    wind:w('<path d="M2.6 8.6h11a2.8 2.8 0 1 0-2.8-2.8M2.6 13h15.2a2.8 2.8 0 1 1-2.8 2.8M2.6 17.4h8"/>'),
    moon:w('<path d="M20.4 14.6A8.6 8.6 0 0 1 9.4 3.6a8.6 8.6 0 1 0 11 11z"/>'),
    moonCloud:w('<path d="M15.4 6.6A5.2 5.2 0 0 1 9 2.4a5.2 5.2 0 1 0 6.4 6.6"/><path d="'+CL+'"/>'),
    dome:w('<path d="M3.4 12.4a8.6 8.6 0 0 1 17.2 0"/><path d="M2.4 12.4h19.2v7.2H2.4z"/><path d="M7.6 19.6v-3.4h3v3.4M13.4 19.6v-3.4h3v3.4"/>')};
})();
var WXC={1:['sun','Sunny'],2:['sun','Mostly sunny'],3:['sunCloud','Partly sunny'],4:['sunCloud','Intermittent clouds'],
 5:['fog','Hazy sunshine'],6:['sunCloud','Mostly cloudy'],7:['cloud','Cloudy'],8:['cloud','Overcast'],11:['fog','Fog'],
 12:['rain','Showers'],13:['rain','Cloudy with showers'],14:['rain','Partly sunny with showers'],15:['storm','Thunderstorms'],
 16:['storm','Cloudy with storms'],17:['storm','Partly sunny with storms'],18:['rain','Rain'],19:['snow','Flurries'],
 22:['snow','Snow'],24:['snow','Ice'],25:['snow','Sleet'],26:['rain','Freezing rain'],30:['sun','Hot'],31:['snow','Cold'],
 32:['wind','Windy'],33:['moon','Clear'],34:['moon','Mostly clear'],35:['moonCloud','Partly cloudy'],
 36:['moonCloud','Intermittent clouds'],38:['moonCloud','Mostly cloudy'],39:['rain','Showers'],40:['rain','Cloudy with showers'],
 41:['storm','Storms'],42:['storm','Cloudy with storms'],43:['snow','Flurries'],44:['snow','Snow']};
var WXP={sun:['#27272A','#111114','#FCD34D'],sunCloud:['#242428','#101013','#D4D4D8'],cloud:['#212125','#0E0E11','#A1A1AA'],
 fog:['#202024','#0E0E11','#A1A1AA'],rain:['#1E2530','#0D0F13','#93C5FD'],storm:['#26243A','#101019','#C4B5FD'],
 snow:['#24262B','#0F1012','#E4E4E7'],wind:['#212428','#0E0F11','#A1A1AA'],moon:['#1B2033','#0C0E14','#A5B4FC'],
 moonCloud:['#1B2033','#0C0E14','#A5B4FC'],dome:['#232326','#0F0F11','#A1A1AA']};
function wxRead(g){
  var t=g.temp==null?null:num(g.temp),gu=g.gust==null?null:num(g.gust),pr=g.precip==null?null:num(g.precip);
  if(g.indoor) return {sev:'',lvl:'None',txt:'Roof-covered venue \u2014 conditions are not a factor.'};
  if(gu!=null&&gu>=20) return {sev:'crit',lvl:'High',txt:'Gusts to '+gu+' mph. Deep passing and field goals materially degraded.'};
  if(gu!=null&&gu>=15) return {sev:'warn',lvl:'Elevated',txt:'Gusts to '+gu+' mph \u2014 enough to take the top off the passing game.'};
  if(pr!=null&&pr>=50) return {sev:'warn',lvl:'Elevated',txt:pr+'% chance of rain. Expect a run-leaning script.'};
  if(t!=null&&t<=32) return {sev:'warn',lvl:'Elevated',txt:'Freezing at kickoff \u2014 ball handling and kicking fall off.'};
  if(t!=null&&t>=90) return {sev:'warn',lvl:'Elevated',txt:t+'\u00b0F. Heat drives rotation and late cramping.'};
  return {sev:'',lvl:'Low',txt:'Nothing in the forecast that changes how this game gets played.'};
}
function weather(g){
  var el=document.getElementById('gmetrics'); if(!el) return;
  var im=implied(g), done=g.state==='post';
  var h='';
  function tile(l,v){h+='<dl class="mtile"><dt>'+l+'</dt><dd>'+v+'</dd></dl>';}
  if(g.det) tile('Line',esc(g.det)+vbadge(g.id,'spread'));
  if(g.ou!=null) tile('Total',num(g.ou)+vbadge(g.id,'total'));
  if(im){tile('Implied '+esc(g.a),im.a.toFixed(1)); tile('Implied '+esc(g.h),im.h.toFixed(1));}
  if(g.att) tile('Attendance',num(g.att).toLocaleString());
  if(!h) tile('Market','<span style="font-size:14px;color:var(--fg-4)">no line</span>');

  render(el,h);

  /* score, beside the title rather than above the metrics */
  var sc=document.getElementById('gscore');
  if((done||g.state==='in')&&g.sc){
    render(sc,'<span class="fin">'+esc(scoreTag(g))+'</span>'+
      '<span class="sv '+(g.sc.a>g.sc.h?'w':'l')+'">'+esc(g.a)+' '+num(g.sc.a)+'</span>'+
      '<span class="dash">\u2013</span>'+
      '<span class="sv '+(g.sc.h>g.sc.a?'w':'l')+'">'+esc(g.h)+' '+num(g.sc.h)+'</span>');
  } else render(sc,'');
}

function header(){
  var g=D.games[gi],tc=teamColors(g),ac=tc.a,hc=tc.h;
  render(document.getElementById('gmatch'),
    '<span class="dot" style="width:11px;height:11px;background:'+ac+'"></span><span class="t">'+esc(g.a)+'</span>'+
    '<span class="at-">'+esc(g.an)+'</span><span class="at-" style="opacity:.5">at</span>'+
    '<span class="dot" style="width:11px;height:11px;background:'+hc+'"></span><span class="t">'+esc(g.h)+'</span>'+
    '<span class="at-">'+esc(g.hn)+'</span>');
  var loc=[g.venue,[g.city,g.st].filter(Boolean).join(', ')].filter(Boolean).join(' \u00b7 ');
  render(document.getElementById('gsub'),
    [esc(loc),esc(g.net),esc(g.state==='in'?liveClock(g):kick(g.date))].filter(Boolean).join('<span class="sep">\u00b7</span>'));
  render(document.getElementById('toggle'),['h','a'].map(function(k){
    var t=k==='h'?g.h:g.a,c=k==='h'?hc:ac;
    return '<button data-p="'+k+'" aria-pressed="'+(poss===k)+'">'+
      '<span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:'+c+';margin-right:7px"></span>'+
      esc(t)+' offense</button>';}).join(''));
  weather(g);
  return {offc:poss==='h'?hc:ac,defc:poss==='h'?ac:hc};
}
var NICON={
  teams:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h16"/><path d="M9 3v18"/></svg>',
  model:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 20V5"/><path d="M3 20h17"/><path d="m6.5 15 4-5 3.5 3 5-7"/></svg>'
};
function buildSidebar(){
  var h='<div class="navgrp">Overview</div>'+
    '<button class="navitem" data-go="teams" aria-current="'+(route==='teams')+'">'+
      '<span class="ic">'+NICON.teams+'</span><span class="lb">Teams</span></button>'+
    '<button class="navitem" data-go="model" aria-current="'+(route==='model')+'">'+
      '<span class="ic">'+NICON.model+'</span><span class="lb">Model</span></button>';
  var last='';
  /* feed order is not chronological; sidebar reads by kickoff, indices preserved */
  var order=D.games.map(function(g,i){return {g:g,i:i};})
    .sort(function(a,b){return new Date(a.g.date)-new Date(b.g.date);});
  var q=query.toLowerCase(), shown=0;
  order.forEach(function(o){
    var g=o.g, i=o.i, d=new Date(g.date);
    if(q&&!gameMatches(g,i,q)) return;
    shown++;
    var day=isNaN(d)?'':d.toLocaleDateString('en-US',{weekday:'long',month:'short',day:'numeric',timeZone:'America/New_York'});
    if(day!==last){ h+='<div class="navgrp">'+esc(day)+'</div>'; last=day; }
    var tc=teamColors(g), done=g.state==='post';
    var when=done?scoreTag(g):g.state==='in'?liveClock(g)+(g.sc?' \u00b7 '+num(g.sc.a)+'-'+num(g.sc.h):''):(kick(g.date).split(' ').slice(1).join(' ').replace(' ET',''));
    h+='<button class="navitem" data-go="'+i+'" aria-current="'+(route===i)+'">'+
      '<span class="gdots"><i style="background:'+tc.a+'"></i><i style="background:'+tc.h+'"></i></span>'+
      '<span class="lb">'+esc(g.a)+' <span style="opacity:.45">at</span> '+esc(g.h)+'</span>'+
      '<span class="mt">'+esc(when)+'</span></button>';
  });
  if(q&&!shown) h+='<div class="navgrp">No games match \u201c'+esc(query)+'\u201d</div>';
  render(document.getElementById('sidenav'),h);
}

/* ------------------------- one game, in full ------------------------- */
/* ------------------------- search: games in the sidebar, teams on the Teams page ------------------------- */
function gameMatches(g,i,q){
  if([g.a,g.h,g.an,g.hn].some(function(x){return String(x||'').toLowerCase().indexOf(q)>=0;})) return true;
  return MATCHUPS.some(function(m){
    return m.gi===i&&(PL(m.oid).n.toLowerCase().indexOf(q)>=0||PL(m.did).n.toLowerCase().indexOf(q)>=0);});
}

/* ------------------------- one game, everything about it ------------------------- */
function drawGame(){ drawGameInfo(); buildField(); }
function drawGameInfo(){
  var g=D.games[gi];
  header();
  render(document.getElementById('gcall'), predBlock(g)+injPanel(g));
  drawRecords(g);
  var f=contextFactors(g);
  render(document.getElementById('gctx'), conditionsGrid(f));
  render(document.getElementById('gnotes'),'<div>'+f.map(function(x){
    return '<p><b>'+esc(x.k)+(x.v?' \u2014 '+esc(x.v):'')+':</b> '+esc(x.note)+'</p>';}).join('')+'</div>');
  drawViz(gi);
  drawMatchups();
}
function drawMatchups(){
  var g=D.games[gi], tc=teamColors(g);
  var ms=MATCHUPS.filter(function(m){ return m.gi===gi&&(posFilter==='all'||m.fam===posFilter); });
  function side(label,color,list){
    return '<div class="gc-side"><h4><span class="sq" style="background:'+color+'"></span>'+esc(label)+'</h4>'+
      (list.length?list.map(matchRow).join(''):'<div class="nodata">Nothing matches that filter.</div>')+'</div>';
  }
  render(document.getElementById('gmatchups'),
    '<div class="mpane">'+
      side(g.a+' offense vs '+g.h+' defense',tc.a,ms.filter(function(m){return m.offT===g.a;}))+
      side(g.h+' offense vs '+g.a+' defense',tc.h,ms.filter(function(m){return m.offT===g.h;}))+'</div>');
  document.getElementById('sectitle').textContent = g.state==='post'?'Results':g.state==='in'?'Live':'Matchups';
}
function fieldInView(){
  var b=document.getElementById('fbox'); if(!b||typeof route!=='number') return false;
  var r=b.getBoundingClientRect(); return r.top<innerHeight*0.7&&r.bottom>innerHeight*0.3;
}

/* ------------------------- teams: standings and season statistics ------------------------- */
var tseason=null, tview='div', tsort={k:'pct',d:-1};
function TD(){ return D.teams||null; }
function teamOf(ab){ var T=TD(); if(T) for(var k in T.meta){ if(T.meta[k].ab===ab) return k; } return ab; }
function wlt(a){ return (a[0]||0)+'-'+(a[1]||0)+(a[2]?'-'+a[2]:''); }
function winp(a){ var n=(a[0]||0)+(a[1]||0)+(a[2]||0); return n?((a[0]||0)+0.5*(a[2]||0))/n:-1; }
function signed(v){ return v==null?'\u2014':v>0?'+'+v:v<0?'\u2212'+Math.abs(v):'0'; }
function lastFive(s){
  if(!s) return '\u2014';
  return '<span class="l5">'+String(s).split('').map(function(c){return '<i class="'+c+'">'+c+'</i>';}).join('')+'</span>';
}
function streakVal(r){ var m=String(r.streak||'').match(/^([WLT])(\d+)$/); return m?(m[1]==='W'?+m[2]:m[1]==='L'?-m[2]:0):0; }
function slateGameOf(code){
  var T=TD(), ab=(T&&T.meta[code]&&T.meta[code].ab)||code;
  for(var i=0;i<D.games.length;i++){ if(D.games[i].a===ab||D.games[i].h===ab) return i; }
  return -1;
}
function weekCell(code){
  var i=slateGameOf(code); if(i<0) return '<span class="tbye">Bye</span>';
  var g=D.games[i], ab=TD().meta[code].ab, home=g.h===ab, opp=home?g.a:g.h, txt;
  if((g.state==='post'||g.state==='in')&&g.sc){
    var me=home?g.sc.h:g.sc.a, them=home?g.sc.a:g.sc.h;
    txt=(g.state==='in'?'LIVE ':me>them?'W ':me<them?'L ':'T ')+me+'\u2013'+them+(home?' vs ':' @ ')+opp;
  } else txt=(home?'vs ':'@ ')+opp+' \u00b7 '+kick(g.date).replace(' ET','');
  return '<button class="twk" data-game="'+i+'">'+esc(txt)+'</button>';
}
var TCOL=[
  {k:'team',l:'Team',all:1},
  {k:'rec',l:'W-L-T',all:1,v:function(r){return wlt([r.w,r.l,r.t]);},s:function(r){return r.pct==null?-1:r.pct;},t:'Won, lost, tied'},
  {k:'pct',l:'Pct',all:1,v:function(r){return r.pct==null?'\u2014':r.pct.toFixed(3).replace(/^0/,'');},s:function(r){return r.pct==null?-1:r.pct;},t:'Win percentage; a tie counts half'},
  {k:'div',l:'Div',all:1,v:function(r){return wlt(r.div);},s:function(r){return winp(r.div);},t:'Record against division opponents'},
  {k:'conf',l:'Conf',all:1,v:function(r){return wlt(r.conf);},s:function(r){return winp(r.conf);},t:'Record against conference opponents'},
  {k:'home',l:'Home',v:function(r){return wlt(r.home);},s:function(r){return winp(r.home);},t:'Record at home'},
  {k:'away',l:'Away',v:function(r){return wlt(r.away);},s:function(r){return winp(r.away);},t:'Record on the road'},
  {k:'pf',l:'PF',all:1,v:function(r){return r.pf;},s:function(r){return r.pf;},t:'Points scored'},
  {k:'pa',l:'PA',all:1,v:function(r){return r.pa;},s:function(r){return r.pa;},t:'Points allowed'},
  {k:'diff',l:'Diff',all:1,v:function(r){return r.gp?signed(r.diff):'\u2014';},s:function(r){return r.diff;},t:'Points scored minus points allowed'},
  {k:'pfg',l:'PF/G',v:function(r){return r.gp?fx(r.pfg):'\u2014';},s:function(r){return r.gp?r.pfg:-1;},t:'Points scored per game'},
  {k:'pag',l:'PA/G',v:function(r){return r.gp?fx(r.pag):'\u2014';},s:function(r){return r.gp?r.pag:99;},t:'Points allowed per game'},
  {k:'streak',l:'Strk',all:1,v:function(r){return r.streak||'\u2014';},s:streakVal,t:'Current streak'},
  {k:'last5',l:'Last 5',all:1,html:1,v:function(r){return lastFive(r.last5);},s:function(r){return (String(r.last5).match(/W/g)||[]).length;},t:'Most recent five results, oldest first'},
  {k:'ats',l:'ATS',v:function(r){return wlt(r.ats);},s:function(r){return winp(r.ats);},t:'Against the closing spread: covered, failed, pushed'},
  {k:'ou',l:'O/U',v:function(r){return wlt(r.ou);},s:function(r){return winp(r.ou);},t:'Games over, under or on the closing total'},
  {k:'ypg',l:'Yds/G',v:function(r){return r.ypg==null?'\u2014':fx(r.ypg);},s:function(r){return r.ypg==null?-1:r.ypg;},t:'Passing plus rushing yards per game'},
  {k:'ypga',l:'Opp Yds/G',v:function(r){return r.ypga==null?'\u2014':fx(r.ypga);},s:function(r){return r.ypga==null?9999:r.ypga;},t:'Yards allowed per game'},
  {k:'to',l:'TO +/-',v:function(r){return signed(r.to);},s:function(r){return r.to==null?-99:r.to;},t:'Takeaways minus giveaways'},
  {k:'wk',l:'This week',all:1}
];
function teamRow(code,r,cols,rank){
  var m=TD().meta[code];
  var h='<tr data-team="'+esc(code)+'"><td><span class="tteam">'+(rank?'<em>'+rank+'</em>':'')+
    '<i style="background:'+col(m.color)+'"></i><b>'+esc(m.ab)+'</b><span>'+esc(m.name)+'</span></span></td>';
  cols.slice(1).forEach(function(c){
    var v=c.k==='wk'?weekCell(code):c.v(r), cls='';
    if((c.k==='diff'||c.k==='to')&&r.gp&&c.s(r)!=null) cls=c.s(r)>0?' class="pos"':c.s(r)<0?' class="neg"':'';
    h+='<td data-k="'+c.k+'"'+cls+'>'+(c.html||c.k==='wk'?v:esc(v))+'</td>';
  });
  return h+'</tr>';
}
function teamTable(codes,S,cols,sortable,ranked){
  var th='<tr>'+cols.map(function(c){
    var tt=c.t?' title="'+esc(c.t)+'"':'';
    if(!sortable||c.k==='team'||c.k==='wk') return '<th scope="col"'+tt+'>'+esc(c.l)+'</th>';
    var on=tsort.k===c.k;
    return '<th scope="col"'+tt+(on?' aria-sort="'+(tsort.d<0?'descending':'ascending')+'"':'')+'>'+
      '<button data-sort="'+c.k+'">'+esc(c.l)+(on?(tsort.d<0?' \u2193':' \u2191'):'')+'</button></th>';
  }).join('')+'</tr>';
  return '<div class="twrap"><table class="tt"><thead>'+th+'</thead><tbody>'+
    codes.map(function(code){ return teamRow(code,S.rows[code],cols,ranked?S.rows[code].rank:null); }).join('')+'</tbody></table></div>';
}
function drawTeams(){
  var T=TD(), box=document.getElementById('ttables');
  if(!T||!T.by){ render(box,'<div class="empty">Team statistics are not in this build yet.</div>'); render(document.getElementById('tleaders'),''); return; }
  if(tseason==null){ var cur=T.by[String(T.current)]; tseason=String(cur&&cur.final_games?T.current:T.seasons[1]); }
  var S=T.by[tseason], q=query.toLowerCase();
  render(document.getElementById('tseason'),T.seasons.map(function(s){
    var b=T.by[String(s)];
    return '<button data-season="'+s+'" aria-pressed="'+(String(s)===tseason)+'">'+s+
      (b&&b.final_games<b.scheduled?' \u00b7 week '+b.through:'')+'</button>';}).join(''));
  document.querySelectorAll('#tview button').forEach(function(x){ x.setAttribute('aria-pressed',String(x.dataset.view===tview)); });
  function match(code){ var m=T.meta[code]; return !q||[m.ab,m.name,m.full].some(function(x){return String(x||'').toLowerCase().indexOf(q)>=0;}); }
  var played=Object.keys(S.rows).filter(function(c){return S.rows[c].gp>0;});
  function best(fn,low){
    return played.slice().sort(function(a,b){
      var d=low?fn(S.rows[a])-fn(S.rows[b]):fn(S.rows[b])-fn(S.rows[a]);
      return d||(S.rows[b].diff-S.rows[a].diff)||(a<b?-1:1);})[0];
  }
  function tile(label,code,val){
    var m=T.meta[code];
    return '<dl class="mtile"><dt>'+esc(label)+'</dt><dd><i class="tdot" style="background:'+col(m.color)+'"></i>'+
      esc(m.ab)+' <small>'+esc(val)+'</small></dd></dl>';
  }
  var tiles='';
  if(played.length){
    var c1=best(function(r){return r.pct;}), c2=best(function(r){return r.pfg;}), c3=best(function(r){return r.pag;},true),
        c4=best(function(r){return r.diff;}), c5=best(function(r){return winp(r.ats);});
    tiles=tile('Best record',c1,wlt([S.rows[c1].w,S.rows[c1].l,S.rows[c1].t]))+tile('Top scoring',c2,fx(S.rows[c2].pfg)+' pts/g')+
      tile('Best defense',c3,fx(S.rows[c3].pag)+' allowed/g')+tile('Best differential',c4,signed(S.rows[c4].diff))+
      tile('Best ATS',c5,wlt(S.rows[c5].ats));
  }
  render(document.getElementById('tleaders'),tiles);
  var h='', shown=0;
  if(tview==='div'){
    var cols=TCOL.filter(function(c){return c.all;});
    ['AFC','NFC'].forEach(function(conf){
      h+='<div class="tconf"><h3 class="tconfh">'+conf+'</h3><div class="tgrid">';
      T.divisions.filter(function(dv){return dv.conf===conf;}).forEach(function(dv){
        var codes=dv.teams.filter(match).sort(function(a,b){return S.rows[a].rank-S.rows[b].rank;});
        if(!codes.length) return;
        shown+=codes.length;
        h+='<div class="tblk"><h4>'+esc(dv.name)+'</h4>'+teamTable(codes,S,cols,false,true)+'</div>';
      });
      h+='</div></div>';
    });
  } else {
    var c=TCOL.filter(function(x){return x.k===tsort.k;})[0]||TCOL[1];
    var codes=Object.keys(S.rows).filter(match).sort(function(a,b){
      var ra=S.rows[a], rb=S.rows[b], d=(c.s(ra)-c.s(rb))*(tsort.d<0?-1:1);
      return d||(num(rb.pct,-1)-num(ra.pct,-1))||(rb.diff-ra.diff)||(a<b?-1:1);});
    shown=codes.length;
    h='<div class="tblk">'+teamTable(codes,S,TCOL,true,false)+'</div>';
  }
  render(box,shown?h:'<div class="empty">No team matches \u201c'+esc(query)+'\u201d.</div>');
  render(document.getElementById('tnote'),
    esc((S.final_games?S.final_games+' of '+S.scheduled+' games final'+(S.final_games<S.scheduled?', through week '+S.through:''):'No games played yet')+
    '. '+T.note+' Against the spread and over/under use the closing line.'));
}

/* the two teams' seasons, side by side, on the game page */
function drawRecords(g){
  var T=TD(), el=document.getElementById('grecords'), hint=document.getElementById('grechint');
  if(!T||!T.by){ render(el,'<div class="nodata">Team statistics are not in this build yet.</div>'); if(hint) hint.textContent=''; return; }
  var A=teamOf(g.a), H=teamOf(g.h), cur=T.by[String(T.current)], prev=T.by[String(T.current-1)];
  var useCur=!!(cur&&cur.rows[A]&&cur.rows[H]&&(cur.rows[A].gp||cur.rows[H].gp)), S=useCur?cur:prev, season=useCur?T.current:T.current-1;
  if(!S||!S.rows[A]||!S.rows[H]){ render(el,'<div class="nodata">No season statistics for these teams.</div>'); return; }
  var ra=S.rows[A], rh=S.rows[H], tc=teamColors(g), ORD=['','1st','2nd','3rd','4th'];
  function pg(f){ return function(r){ return r.gp&&r[f]!=null?fx(r[f]):'\u2014'; }; }
  var ROWS=[
    ['Record',function(r){return wlt([r.w,r.l,r.t]);},function(r){return r.gp?r.pct:null;},1],
    ['Division',function(r,code){return wlt(r.div)+' \u00b7 '+ORD[r.rank]+' in '+T.meta[code].div;},null,0],
    ['Points scored / game',pg('pfg'),function(r){return r.gp?r.pfg:null;},1],
    ['Points allowed / game',pg('pag'),function(r){return r.gp?r.pag:null;},-1],
    ['Point differential',function(r){return r.gp?signed(r.diff):'\u2014';},function(r){return r.gp?r.diff:null;},1],
    ['Streak',function(r){return r.streak||'\u2014';},null,0],
    ['Last 5',function(r){return lastFive(r.last5);},null,0,1],
    ['Against the spread',function(r){return wlt(r.ats);},function(r){return r.gp?winp(r.ats):null;},1],
    ['Over / under',function(r){return wlt(r.ou);},null,0],
    ['Yards / game',pg('ypg'),function(r){return r.ypg;},1],
    ['Yards allowed / game',pg('ypga'),function(r){return r.ypga;},-1],
    ['Turnover margin',function(r){return signed(r.to);},function(r){return r.to;},1]
  ];
  var h='<div class="twrap"><table class="tt rcmp"><thead><tr><th scope="col">'+season+'</th>'+
    '<th scope="col"><span class="tteam"><i style="background:'+tc.a+'"></i><b>'+esc(g.a)+'</b></span></th>'+
    '<th scope="col"><span class="tteam"><i style="background:'+tc.h+'"></i><b>'+esc(g.h)+'</b></span></th></tr></thead><tbody>';
  ROWS.forEach(function(row){
    var va=row[1](ra,A), vh=row[1](rh,H), ca='', ch='';
    if(row[2]){
      var xa=row[2](ra), xh=row[2](rh);
      if(xa!=null&&xh!=null&&xa!==xh){ var aBetter=(xa-xh)*row[3]>0; ca=aBetter?' class="better"':''; ch=aBetter?'':' class="better"'; }
    }
    h+='<tr data-row="'+esc(row[0])+'"><td>'+esc(row[0])+'</td><td'+ca+'>'+(row[4]?va:esc(va))+'</td><td'+ch+'>'+(row[4]?vh:esc(vh))+'</td></tr>';
  });
  h+='</tbody></table></div>';
  var last='';
  if(useCur&&prev&&prev.rows[A]&&prev.rows[H]){
    var pa=prev.rows[A], ph=prev.rows[H];
    last='<p class="tnote">Last season: '+esc(g.a)+' '+wlt([pa.w,pa.l,pa.t])+' \u00b7 '+esc(g.h)+' '+wlt([ph.w,ph.l,ph.t])+'. ';
  } else last='<p class="tnote">';
  render(el,h+last+'<button class="linkbtn" data-teams="1">Full standings on the Teams page</button></p>');
  if(hint) hint.textContent=(useCur?season+(S.final_games<S.scheduled?' through week '+S.through:''):season+' season \u2014 '+T.current+' has no games for these teams yet')+
    '. Bold marks the better side.';
}

function crumbFor(){
  var el=document.getElementById('crumb');
  if(route==='teams') return render(el,'<span>Week 1</span><span class="cs">/</span><b>Teams</b>');
  if(route==='model') return render(el,'<span>Week 1</span><span class="cs">/</span><b>Model</b>');
  var g=D.games[gi];
  render(el,'<span>Week 1</span><span class="cs">/</span><span>'+esc(g.a)+' at '+esc(g.h)+'</span>'+
    '<span class="cs">/</span><b>'+esc(g.state==='post'?'Final':g.state==='in'?'Live':'Preview')+'</b>');
}
function go(target){
  route=target;
  if(typeof target==='number'){ gi=target; selected=null; }
  document.querySelectorAll('.navitem').forEach(function(b){
    b.setAttribute('aria-current', String(String(b.dataset.go)===String(target)));
  });
  ['p-teams','p-game','p-model'].forEach(function(id){document.getElementById(id).classList.remove('on');});
  if(target==='teams'){ document.getElementById('p-teams').classList.add('on'); drawTeams(); }
  else if(target==='model'){ document.getElementById('p-model').classList.add('on'); drawModel(); }
  else { document.getElementById('p-game').classList.add('on'); drawGame(); }
  crumbFor();
  try{ history.replaceState(null,'',location.pathname+location.search+'#'+(typeof target==='number'?'game-'+D.games[target].id:target)); }catch(e){}
  var ml=document.getElementById('menulbl'); if(ml) ml.textContent=target==='teams'?'Teams':target==='model'?'Model':(D.games[gi].a+' at '+D.games[gi].h);
  var sd=document.getElementById('side'), mb=document.getElementById('menubtn'); if(sd) sd.classList.remove('open'); if(mb) mb.setAttribute('aria-expanded','false');
  var sc=document.getElementById('scroller'); if(sc) sc.scrollTop=0;
}

/* ============================ drawer ============================ */
function kv(k,v,sub,delta){return '<div class="kv"><span class="k">'+k+'</span><span class="v">'+v+
  (sub?'<small>'+sub+'</small>':'')+(delta||'')+'</span></div>';}
function dtag(cur,prev,suffix){
  if(cur==null||prev==null) return '';
  var d=cur-prev;
  if(Math.abs(d)<0.05) return '';
  return '<span class="d '+(d>0?'up':'dn')+'">'+(d>0?'\u25b2':'\u25bc')+Math.abs(d).toFixed(1)+(suffix||'')+'</span>';
}
function wxRow(pj){
  var w=pj.wx; if(!w) return '';
  var pc=(num(w.m)-1)*100, up=pc>0;
  if(Math.abs(pc)<0.5) return '';
  return '<div><span class="lab">Conditions<small>'+esc(wxWhy())+'</small></span>'+
    '<span class="val" style="color:'+(up?'#4ADE80':'#F87171')+'">'+(up?'+':'\u2212')+
    Math.abs(pc).toFixed(1)+'%<em>'+num(w.b).toFixed(1)+' \u2192 '+num(w.a!=null?w.a:pj.med).toFixed(1)+'</em></span></div>';
}
function wxWhy(){
  var g=D.games[gi], w=(D.wx||{})[g&&g.id];
  if(!w) return 'measured effect of this venue and forecast';
  if(w.dome) return 'indoors \u2014 no wind or cold';
  var b=[];
  if(num(w.wind)>=9) b.push(num(w.wind).toFixed(0)+' mph sustained wind');
  if(num(w.temp)<=40) b.push(num(w.temp).toFixed(0)+'\u00B0F');
  return b.length ? b.join(', ') : 'mild conditions, small positive';
}
function PROPS(id){ var P=D.props; return (P&&P.by&&P.by[id])||null; }
function asOf(){
  var f=D.props&&D.props.fetched; if(!f) return '';
  var d=new Date(f); if(isNaN(d)) return '';
  return ' \u00b7 lines as of '+d.toLocaleString('en-US',{weekday:'short',hour:'numeric',minute:'2-digit',timeZone:'America/New_York'})+' ET';
}
function marketTable(id,opts){
  var m=PROPS(id); if(!m) return '';
  var rows='';
  opts.forEach(function(o){
    var v=m[o[0]]; if(!v) return;
    var mv=(v.open==null||v.open===v.line)?'':(v.line>v.open?'+':'\u2212')+Math.abs(v.line-v.open).toFixed(1);
    var rel=num(v.rel), side=rel>0.5?'over':'under', pc=Math.round(100*Math.max(rel,1-rel));
    rows+='<div class="mkrow"><span class="mkk">'+esc(v.lab)+'</span>'+
      '<span class="mkl">'+num(v.line).toFixed(1)+(mv?'<i>'+esc(mv)+'</i>':'')+'</span>'+
      '<span class="mkp '+(pc>=60?'lean':'')+'">'+esc(side)+' '+pc+'%</span></div>';
  });
  if(!rows) return '';
  return '<div class="mktab"><div class="mkhd">DraftKings line<small>movement since open \u00b7 '+
    'GridIron\u2019s read, net of its own average lean'+esc(asOf())+'</small></div>'+rows+
    '<div class="mkfoot">No prices are published with these lines, so break-even is taken as \u2212110 '+
    '(52.4%). A line that has moved a long way often carries news this model has not seen.</div></div>';
}
function openPlayer(id,color,team){
  lastPlayer=[id,color,team];
  selected=id;
  var p=PL(id),u=U(id),pr=PR(id),cv=CV(id);
  var g=D.games[gi],ijx=IJ(id),inj=ijx?ijx.s:null,c=col(color||'#3F3F46');
  var m=MATCHUPS.filter(function(x){return x.oid===id;})[0];
  var h='<div class="dhd"><button class="close" aria-label="Close"><svg width="15" height="15" viewBox="0 0 24 24" '+
    'fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg></button>'+
    '<div class="dtop">'+(function(){var bg=faceBg(id,46);
      return bg ? '<div class="dtok face" style="'+bg+'"></div>'
        : '<div class="dtok" style="background:linear-gradient(180deg,'+shade(c,1.38)+','+shade(c,.62)+
          ');color:'+readable(c)+'">'+esc(p.j||'-')+'</div>';})()+
    '<div><div class="dname">'+esc(p.n)+'</div><div class="dmeta">'+
    '<span>'+esc(p.p)+'</span><span style="opacity:.4">\u00b7</span><span>'+esc(team||p.t)+'</span>'+
    (inj?'<span class="tag '+esc(inj)+'">'+esc(inj==='O'?'Out':inj==='IR'?'Injured reserve':
        inj==='Q'?'Questionable':'Doubtful')+'</span>':'')+
    '</div></div></div></div><div class="dbody">';

  var pj=PJ(id);
  if(pj){
    var x=pj.x;
    h+='<div class="grp"><h4>Projection</h4><div class="pjbox">'+
      '<div class="pjtop"><span class="big">'+pj.med.toFixed(1)+'</span>'+
      '<span class="unit">median PPR<br>points</span>'+
      '<span class="fc">floor <b>'+pj.flr.toFixed(1)+'</b> &nbsp; ceiling <b>'+pj.ceil.toFixed(1)+'</b><br>'+
      '25th / 85th percentile of 20,000 simulations</span></div>'+
      distChart(pj.q,330,96,pj.med,pj.flr,pj.ceil)+
      '<div class="distlab"><span>'+pj.q[0].toFixed(0)+'</span><span>likely range</span>'+
      '<span>'+pj.q[pj.q.length-1].toFixed(0)+'</span></div></div></div>';

    h+='<div class="grp"><h4>How that number was built</h4><div class="chain">'+
      '<div><span class="lab">Team pass attempts<small>league pace, adjusted for this spread</small></span>'+
        '<span class="val">'+(num(D.cal.script.plays)*0.54).toFixed(0)+'<em>est</em></span></div>'+
      '<div><span class="lab">His target share<small>regressed, k='+num(D.cal.k.ts)+'</small></span>'+
        '<span class="val">'+x.tgt.toFixed(1)+'<em>targets</em></span></div>'+
      '<div><span class="lab">Catch rate<small>regressed, k='+num(D.cal.k.cr)+'</small></span>'+
        '<span class="val">'+(x.cr*100).toFixed(0)+'%</span></div>'+
      '<div><span class="lab">Yards per target<small>regressed k='+num(D.cal.k.ypt)+
        (x.adj?', opponent '+(x.adj>0?'+':'')+x.adj.toFixed(2):', opponent neutral')+'</small></span>'+
        '<span class="val">'+x.ypt.toFixed(2)+'</span></div>'+
      (x.car>=2?'<div><span class="lab">Carries \u00D7 yards per carry</span>'+
        '<span class="val">'+x.car.toFixed(1)+' \u00D7 '+x.ypc.toFixed(1)+'</span></div>':'')+
      '<div><span class="lab">Touchdown rate<small>from depth of target, not his own TD history</small></span>'+
        '<span class="val">'+(x.tdpt*100).toFixed(1)+'%<em>per target</em></span></div>'+
      wxRow(pj)+injRow(pj)+
      '<div class="eq"><span class="lab">Simulated 20,000 times</span>'+
        '<span class="val">'+pj.med.toFixed(1)+'<em>median</em></span></div>'+
      '</div><div class="nodata">Built from '+num(x.n).toFixed(0)+' prior opportunities. '+
      'The smaller that number, the harder every rate is pulled toward the positional average.</div></div>';

    var opts=[['q','Fantasy points (PPR)',pj.q,'pts']];
    if(pj.qry) opts.push(['qry','Receiving yards',pj.qry,'yds']);
    if(pj.qrec) opts.push(['qrec','Receptions',pj.qrec,'']);
    if(pj.qru) opts.push(['qru','Rushing yards',pj.qru,'yds']);
    if(pj.qpy) opts.push(['qpy','Passing yards',pj.qpy,'yds']);
    var mk=PROPS(id), first=null;
    opts.forEach(function(o){ if(!first&&mk&&mk[o[0]]) first=o[0]; });
    if(first) opts.sort(function(a,b){return (b[0]===first?1:0)-(a[0]===first?1:0);});
    var start = (first&&mk[first]) ? mk[first].line : opts[0][2][QS.indexOf(50)];
    h+='<div class="grp"><h4>Prop calculator</h4>'+marketTable(id,opts)+
      '<div class="prop" data-pid="'+esc(id)+'">'+
      '<div class="hd2">Probability of going over a line</div><div class="row2">'+
      '<select class="pmkt">'+opts.map(function(o,i){
        return '<option value="'+o[0]+'"'+(i?'':' selected')+'>'+esc(o[1])+
          (mk&&mk[o[0]]?' \u2014 DK '+num(mk[o[0]].line).toFixed(1):'')+'</option>';}).join('')+'</select>'+
      '<input class="pline" type="number" step="0.5" value="'+num(start).toFixed(1)+
        '" aria-label="Line"></div>'+
      '<div class="out"><span class="ov">\u2014</span><span class="ovl">raw model chance to go over</span>'+
      '<span class="bar2"><i style="width:50%"></i></span></div></div></div>';
  }
  var rs=RS(id), ij=IJ(id);
  var gdone=D.games[gi] && D.games[gi].state==='post';
  if(rs){
    var vv=rs.v?('<span class="vd '+esc(rs.v)+'" style="font-size:10px">'+
      (rs.v==='beat'?'BEAT PROJECTION':rs.v==='miss'?'UNDER PROJECTION':'MET PROJECTION')+'</span>'):'';
    h+='<div class="grp"><h4>Week 1 result</h4><div class="resbox">'+
      '<div class="big"><span class="pts">'+num(rs.pts).toFixed(1)+'</span>'+
      '<span class="exp">PPR pts \u00B7 expected '+(rs.exp!=null?num(rs.exp).toFixed(1):'\u2014')+'</span>'+vv+'</div>'+
      '<div class="sl">'+esc(statLine(rs)||'Did not record a statistic')+'</div></div>'+
      '<div class="nodata">Expected is his own 2025 per-game average, not a projection service. '+
      'Single-game output is right-skewed, so the median week lands below a season mean \u2014 '+
      'read UNDER as \u201cbelow his own average\u201d, not \u201cbad\u201d.</div></div>';
  }
  if(ij){
    h+='<div class="grp"><h4>Injury</h4>'+
      kv('Status','<span style="font-size:13px;font-family:Archivo">'+esc(ij.sl||ij.s)+'</span>')+
      (ij.bp?kv('Body part',esc(ij.bp)+(ij.side&&ij.side!=='Not Specified'?' <small>'+esc(ij.side)+'</small>':'')):'')+
      (ij.loc?kv('Region',esc(ij.loc)):'')+
      (ij.ret?kv('Expected back','<span style="font-size:13px;font-family:Archivo">'+esc(ij.ret)+'</span>'):'')+
      (outFor(ij.ret)?kv('Timeline','<span style="font-size:13px;font-family:Archivo">'+esc(outFor(ij.ret))+'</span>'):'')+
      '<div class="nodata">'+(ij.s==='IR'?'On injured reserve \u2014 out for an extended stretch, not just this week. '+
        'Drop him from weekly plans and treat the next man up as the starter.'
        :ij.s==='O'?'Ruled out \u2014 the man behind him on the depth chart moves up.'
        :ij.s==='D'?'Doubtful. Treat as unlikely to play and plan for the backup.'
        :'Questionable is a genuine coin flip. Check the inactive list 90 minutes before kickoff.')+
      '</div></div>';
  }
  if(u){
    h+='<div class="grp"><h4>Usage</h4>'+
      kv('Snap share, season',u.s.toFixed(0),'%')+
      kv('Snap share, last 3',u.s3.toFixed(0),'%',dtag(u.s3,u.s,'pt'))+
      kv('Games played',u.g)+
      '<div class="trendbox"><div class="lbl2">Snap share by week</div>'+
      sparkline(u.sp,'#60A5FA',300,44)+'</div></div>';
  }
  if(pr&&pr.S){
    var S=pr.S,L=pr.L3||{},gs=num(S.g,1)||1,gl=num(L.g,1)||1;
    if(S.tgt){
      h+='<div class="grp"><h4>Receiving</h4>'+
        kv('Targets / game',(num(S.tgt)/gs).toFixed(1),'',dtag(num(L.tgt)/gl,num(S.tgt)/gs))+
        kv('Target share',(S.ts||0).toFixed(1),'%')+
        kv('Catch rate',(num(S.rec)/num(S.tgt,1)*100).toFixed(1),'%')+
        kv('Yards / game',(num(S.ry)/gs).toFixed(1),'',dtag(num(L.ry)/gl,num(S.ry)/gs))+
        kv('Yards / target',(num(S.ry)/num(S.tgt,1)).toFixed(2))+
        kv('Touchdowns',num(S.rtd))+'</div>';
      if(pr.tsp) h+='<div class="trendbox"><div class="lbl2">Targets by week</div>'+
        (trendChart(pr.tsp,'Targets','')||sparkline(pr.tsp,'#FBBF24',300,44))+'</div>';
    }
    if(S.car) h+='<div class="grp"><h4>Rushing</h4>'+kv('Carries / game',(num(S.car)/gs).toFixed(1),'',dtag(num(L.car)/gl,num(S.car)/gs))+
      kv('Yards / game',(num(S.ru)/gs).toFixed(1))+kv('Yards / carry',(num(S.ru)/num(S.car,1)).toFixed(2))+
      kv('Touchdowns',num(S.rutd))+'</div>';
    if(S.att) h+='<div class="grp"><h4>Passing</h4>'+kv('Attempts / game',(num(S.att)/gs).toFixed(1))+
      kv('Completion %',(num(S.cmp)/num(S.att,1)*100).toFixed(1),'%')+
      kv('Yards / game',(num(S.py)/gs).toFixed(1))+kv('Touchdowns',num(S.ptd))+'</div>';
  }
  if(cv&&cv.tgt){
    var rat=num(cv.rat);
    h+='<div class="grp"><h4>In coverage</h4>'+kv('Targeted',num(cv.tgt))+
      kv('Completion % allowed',num(cv.cpct),'%')+kv('Yards allowed',num(cv.yds))+
      kv('Passer rating allowed',rat.toFixed(1))+kv('TD / INT',num(cv.td)+' / '+num(cv.int))+
      '<div class="nodata">'+(rat>100?'Quarterbacks posted a '+rat.toFixed(1)+' rating throwing at him, well above the ~92 league average. A matchup to attack.'
      :rat<85?'Held quarterbacks to '+rat.toFixed(1)+', comfortably better than the ~92 average. Difficult coverage.'
      :'A '+rat.toFixed(1)+' rating allowed sits near the ~92 league average.')+'</div></div>';
  }
  if(m){
    var dp=PL(m.did);
    h+='<div class="grp"><h4>This week</h4>'+
      kv('Covered by','<span style="font-size:13px;font-family:Archivo">'+esc(dp.n)+
        ' <span style="color:var(--fg-4);font-size:11px">'+esc(m.dslot||dp.p||'')+'</span></span>')+
      kv('Edge',(m.edge==null?'\u2014':(m.edge>0?'+':'')+m.edge.toFixed(0)))+
      kv('Implied team total',m.implied==null?'\u2014':m.implied.toFixed(1))+'</div>';
  }
  if(!u&&!pr&&!cv) h+='<div class="grp"><h4>2025</h4><div class="nodata">No box-score or snap sample. '+
    'Expected for linemen and for rookies who did not play last season.</div></div>';
  h+='<div class="src">Keyed by gsis_id; usage, production, coverage and injuries all joined by id, never by name. '+
    'Season and last-3 figures from the 2025 weekly files. Depth chart '+esc(String(D.dt).slice(0,10))+'.</div></div>';
  var d=document.getElementById('drawer');
  render(d,h); d.classList.add('on');
  document.getElementById('scrim').classList.add('on');
  var b=d.querySelector('.close');
  b.addEventListener('click',closeDrawer); b.focus();
  var box=d.querySelector('.prop');
  if(box){
    var mk=box.querySelector('.pmkt'), ln=box.querySelector('.pline');
    var ov=box.querySelector('.ov'), bar=box.querySelector('.bar2 i'), lbl=box.querySelector('.ovl');
    function recalc(){
      var q=PJ(box.dataset.pid)[mk.value];
      var p=pOver(q, parseFloat(ln.value));
      if(p==null){ov.textContent='\u2014';return;}
      var pc=Math.round(p*100);
      ov.textContent=pc+'%';
      ov.style.color = pc>=60?'#4ADE80' : pc<=40?'#F87171' : '#FAFAFA';
      bar.style.width=pc+'%';
      lbl.textContent='raw model chance to go over \u00b7 fair odds '+
        (p>=.5 ? '-'+Math.round(p/(1-p)*100) : '+'+Math.round((1-p)/p*100));
    }
    mk.addEventListener('change',function(){
      var q=PJ(box.dataset.pid)[mk.value], m=PROPS(box.dataset.pid);
      ln.value = (m&&m[mk.value]) ? Number(m[mk.value].line).toFixed(1)
                                  : q[QS.indexOf(50)].toFixed(mk.value==='qrec'?0:1);
      recalc();
    });
    ln.addEventListener('input',recalc);
    recalc();
  }
}
function closeDrawer(){
  lastPlayer=null;
  document.getElementById('drawer').classList.remove('on');
  document.getElementById('scrim').classList.remove('on');
  if(selected){selected=null; if(typeof route==='number') buildField();}
  if(typeof LIVE!=='undefined'&&LIVE.codeStale) reloadForNewApp();
}

/* ============================ model view ============================ */
function dumbbell(by){
  var yrs=Object.keys(by).sort(), W=560, rowH=26, PAD=46, H=yrs.length*rowH+40;
  var lo=8.4, hi=11.6, x=function(v){return PAD+(num(v)-lo)/(hi-lo)*(W-PAD-58);};
  var s='<svg viewBox="0 0 '+W+' '+H+'" class="dbl" role="img" '+
    'aria-label="Average margin error by season, GridIron against the closing line">';
  for(var g=9;g<=11;g++)
    s+='<line x1="'+x(g).toFixed(1)+'" y1="14" x2="'+x(g).toFixed(1)+'" y2="'+(H-22)+
       '" stroke="var(--line-3)" stroke-width="1"/>'+
       '<text x="'+x(g).toFixed(1)+'" y="'+(H-8)+'" text-anchor="middle" class="dax">'+g+'</text>';
  yrs.forEach(function(y,i){
    var r=by[y], cy=26+i*rowH, xv=x(r.vm), xg=x(r.gm);
    s+='<text x="0" y="'+(cy+4)+'" class="dyr">'+esc(y)+'</text>'+
       '<line x1="'+xv.toFixed(1)+'" y1="'+cy+'" x2="'+xg.toFixed(1)+'" y2="'+cy+
       '" stroke="var(--line)" stroke-width="2" stroke-linecap="round"/>'+
       '<circle cx="'+xv.toFixed(1)+'" cy="'+cy+'" r="4.5" fill="var(--fg-4)"/>'+
       '<circle cx="'+xg.toFixed(1)+'" cy="'+cy+'" r="4.5" fill="var(--fg)"/>'+
       '<text x="'+(x(hi)+8)+'" y="'+(cy+4)+'" class="dv">+'+num(r.gm-r.vm).toFixed(2)+'</text>';
  });
  return s+'</svg>';
}
function trackExtras(){
  var T=D.track||{}, out='', C=T.wpcal;
  if(C&&C.bands&&C.bands.length){
    out+='<h4 class="fh">Are the win probabilities honest?</h4>'+
      '<p class="sub3">When GridIron gives a team a 65% chance, that team should win about 65% of the time. '+
      'Before recalibration the average miss was 4.45 points of probability; walk-forward across '+
      num(T.all&&T.all.n).toLocaleString()+' games it is now '+num(C.err).toFixed(2)+'.</p>'+
      '<div class="wpcal">';
    C.bands.forEach(function(b){
      var gap=num(b.a)-num(b.p);
      out+='<div class="wprow"><span class="wpb">'+num(b.b)+'\u2013'+(num(b.b)+10)+'%</span>'+
        '<span class="wptr"><i class="wpp" style="left:'+num(b.p).toFixed(1)+'%"></i>'+
        '<i class="wpa" style="left:'+num(b.a).toFixed(1)+'%"></i></span>'+
        '<span class="wpv">'+num(b.a).toFixed(0)+'%<em>'+(gap>=0?'+':'\u2212')+Math.abs(gap).toFixed(1)+'</em></span>'+
        '<span class="wpn">n '+num(b.n)+'</span></div>';
    });
    out+='<div class="wpleg"><span><i class="wpp"></i>GridIron said</span>'+
      '<span><i class="wpa"></i>actually won</span><span class="wpx">0% to 100% across each row</span></div></div>';
  }
  if(T.qb) out+='<div class="verdict"><b>Quarterbacks.</b> '+esc(T.qb.s)+'</div>';
  if(D.injrule) out+='<div class="verdict"><b>Injuries.</b> '+esc(D.injrule.note)+'</div>';
  if(D.props) out+='<div class="verdict"><b>Prop lines.</b> '+num(D.props.n)+' DraftKings lines matched to a '+
    'GridIron distribution this week. '+esc(D.props.note)+'</div>';
  return out;
}
var LSTAT={'holds':['At its best value','hold'],'watching':['Watching','watch'],'rejected':['Kept','hold'],
  'pending':['Passed once \u2014 confirming','pend'],'confirmed':['Confirmed','pend'],'applied':['Changed','chg'],
  'proposed':['Awaiting approval','prop'],'declined earlier':['Declined','rej'],'not reviewed yet':['Not reviewed yet','hold']};
var LWHY={'holds':'no better value found','watching':'a change looks better but is not proven','rejected':'the change tested did worse',
  'pending':'a change passed once; it must pass again next week','confirmed':'a change passed twice','applied':'changed by the learning loop',
  'proposed':'a big change is waiting for the owner','declined earlier':'the owner declined a change'};
function decisionBox(d,cls){
  var st=LSTAT[d.status]||[d.status||'Open',cls];
  var ck=(d.checks||[]).map(function(c){ return '<li class="'+(c.ok?'ok':'no')+'">'+(c.ok?'\u2713 ':'\u2717 ')+esc(c.text)+'</li>'; }).join('');
  var pr=(d.pros||[]).map(function(x){ return '<li>'+esc(x.text)+' <i>+'+num(x.pts).toFixed(2)+'</i></li>'; }).join('');
  var co=(d.cons||[]).map(function(x){ return '<li>'+esc(x.text)+' <i>\u2212'+num(x.pts).toFixed(2)+'</i></li>'; }).join('');
  return '<div class="ldec l-'+cls+'"><div class="ldh"><span class="fv lv-'+cls+'">'+esc(cls==='prop'?'Awaiting approval':st[0])+'</span>'+
    '<b>'+esc(d.title||d.name||'')+'</b>'+(d.model&&d.model!=='pregame'?'<span class="lmod">'+(d.model==='live'?'live model':'player projections')+'</span>':'')+'</div>'+(ck?'<ul class="lchk">'+ck+'</ul>':'')+
    '<div class="lpc"><div><span class="lpl">Pros</span><ul>'+(pr||'<li>none</li>')+'</ul></div>'+
    '<div><span class="lpl">Cons</span><ul>'+(co||'<li>none</li>')+'</ul></div></div>'+
    '<div class="lnet">pros minus cons '+(num(d.net)>=0?'+':'\u2212')+Math.abs(num(d.net)).toFixed(2)+
    (cls==='prop'?' \u00b7 the owner approves or declines it in GitHub Actions (proposal '+esc(d.id)+')':'')+'</div></div>';
}
function learnCard(){
  var L=D.learn; if(!L||!L.weights) return '';
  var R=L.rules||{}, LR=L.last_review;
  var h='<div class="mcard wide" id="learn"><h3>How GridIron <em>learns</em></h3>'+
    '<p class="sub3">After each week of games, every weight below is re-tested on games its new value never saw, against the weights that were actually in force. '+
    'A weight changes only when the gain clears '+Math.round(100*(1-num(R.alpha,0.05)))+'% confidence after correcting for how many ideas were tested at once, '+
    'holds up in at least '+num(R.better_blocks,3)+' seasons, does no damage elsewhere, scores more pros than cons, and passes again the following week. '+
    'Small moves apply on their own and are undone if they then do worse; big moves, or switching a factor on or off, wait for the owner\u2019s approval.</p>';
  if(LR) h+='<div class="lrev"><span><b>Last review</b> '+esc(LR.date)+'</span><span>games through '+num(LR.cutoff[0])+' week '+num(LR.cutoff[1])+'</span>'+
    '<span>'+num(LR.tested)+' ideas tested</span><span>'+(LR.applied.length?LR.applied.length+' change applied':'no change')+'</span>'+
    (LR.proposed.length?'<span>'+LR.proposed.length+' awaiting approval</span>':'')+'<span>pregame weights version '+num(L.version)+'</span><span>live weights version '+num(L.live_version)+'</span><span>player weights version '+num(L.players_version)+'</span></div>';
  h+='<div class="ftab ltab">';
  var lastModel=null, MN={'pregame':'Pregame odds model','live':'Live in-game model','players':'Player projections'};
  L.weights.forEach(function(w){
    if(w.model&&w.model!==lastModel){
      lastModel=w.model;
      h+='<div class="lgrp">'+esc((L.models||MN)[w.model]||MN[w.model]||w.model)+'<small>weights version '+num(w.model==='live'?L.live_version:(w.model==='players'?L.players_version:L.version))+'</small></div>';
    }
    var st=LSTAT[w.status]||[w.status,'hold'];
    h+='<div class="frow lrow"><span class="fk">'+esc(w.name)+'<small>'+esc(w.what)+'</small></span>'+
      '<span class="fv lv-'+st[1]+'">'+esc(st[0])+'</span>'+
      '<span class="fs"><b class="lval">'+esc(w.value)+'</b>'+(w.last_change?' \u00b7 changed '+esc(w.last_change.date)+' ('+esc(w.last_change.how)+')':'')+
      (LWHY[w.status]?'<small class="lwhy">'+esc(LWHY[w.status])+'</small>':'')+'</span></div>';
  });
  h+='</div>';
  (L.proposals||[]).forEach(function(p){ h+=decisionBox(p,'prop'); });
  var ds=(L.decisions||[]).filter(function(d){ return LR&&d.review===LR.id&&d.status!=='rejected'&&d.status!=='proposed'; });
  ds.sort(function(a,b){ return num(a.p_adj,1)-num(b.p_adj,1); });
  if(ds.length){
    h+='<h4 class="fh">Closest to changing</h4><p class="sub3">The ideas with the strongest evidence in the latest review, and exactly why each has not changed the model.</p>';
    ds.slice(0,3).forEach(function(d){ h+=decisionBox(d,(LSTAT[d.status]||['','watch'])[1]); });
  } else if(!(L.proposals||[]).length) h+='<div class="verdict">Nothing came close in the latest review.</div>';
  return h+'</div>';
}
/* ------------------------- kickoff ledger: real calls, frozen at kickoff ------------------------- */
function signedPts(v){ return (v>0?'+':v<0?'\u2212':'')+Math.abs(num(v)).toFixed(1)+' pts'; }
function ledgerNote(g){
  var e=((D.ledger||{}).entries||{})[g.id]; if(!e) return '';
  if(!e.frozen){
    if(e.missed&&g.state!=='pre') return '<div class="pr-ledger">Not in the since-launch record: this game kicked off before GridIron recorded a call.</div>';
    return g.state==='pre'&&e.call?'<div class="pr-ledger">This call goes into the since-launch record when it freezes at kickoff.</div>':'';
  }
  var c=e.call||{}, f=e.first, cl=e.close, fin=e.final;
  var bits=['<b>Frozen at kickoff:</b> GridIron '+spLab(g,c.sp)+', total '+esc(fx(c.tot))];
  if(f&&f.spread!=null) bits.push('first line GridIron saw '+spLab(g,f.spread));
  if(cl&&cl.spread!=null) bits.push('closed '+spLab(g,cl.spread)+(cl.ou!=null?', total '+esc(fx(cl.ou)):''));
  if(fin&&cl&&cl.spread!=null&&c.ph!=null){
    var am=fin.h-fin.a, cm=-cl.spread, pick=Math.sign((c.ph-c.pa)-cm), res=Math.sign(am-cm);
    bits.push('final '+esc(g.a)+' '+fin.a+'\u2013'+esc(g.h)+' '+fin.h+
      (!pick?'':res===0?' (push against the close)':pick===res?' (GridIron\u2019s side covered the close)':' (GridIron\u2019s side did not cover the close)'));
  }
  return '<div class="pr-ledger">'+bits.join(' \u00b7 ')+'</div>';
}
function ledgerCard(){
  var LG=D.ledger; if(!LG||!LG.record) return '';
  var R=LG.record, n=R.settled||0;
  function tile(k,v,s){ return '<div class="ttile"><span class="tk">'+esc(k)+'</span><span class="tv">'+esc(v)+'</span><span class="ts2">'+esc(s)+'</span></div>'; }
  function rec(a){ return a[0]+'-'+a[1]+(a[2]?'-'+a[2]:''); }
  function pct(a){ var d=a[0]+a[1]; return d?(100*a[0]/d).toFixed(1)+'%':'\u2014'; }
  var h='<div class="mcard wide" id="since"><h3>Since launch, <em>real calls only</em></h3>'+
    '<p class="sub3">Every GridIron prediction is frozen at kickoff and scored against the closing line and the final score, so nothing here was known after the fact '+
    '\u2014 unlike the backtest above. '+esc(R.frozen+' calls frozen, '+n+' settled'+(R.pending?', '+R.pending+' awaiting a final score':'')+
    (R.missed?', '+R.missed+' games kicked off before GridIron recorded a call':'')+'.')+'</p>';
  if(!n) return h+'<div class="verdict">No settled games yet.</div></div>';
  var clv=R.clv||{}, clt=R.clv_total||{};
  h+='<div class="ttiles">'+
    tile('Margin error',num(R.gm).toFixed(2)+' pts','closing line '+num(R.vm).toFixed(2))+
    tile('Total error',R.gt==null?'\u2014':num(R.gt).toFixed(2)+' pts',R.vt==null?'no closing totals':'closing line '+num(R.vt).toFixed(2))+
    tile('Against the close',pct(R.ats),rec(R.ats)+' \u00b7 break-even is 52.4%')+
    tile('Line moved toward GridIron',clv.n?clv.toward+' of '+clv.n:'\u2014',clv.n?'average '+signedPts(clv.pts)+' from the first line it saw':'no line moves yet')+
  '</div>'+
  '<div class="verdict"><b>Read this with care.</b> '+n+' games cannot separate skill from luck; against-the-spread results need hundreds. '+
    'Whether the line moves toward GridIron\u2019s number before kickoff is the quicker signal bettors watch, and that too is only '+(clv.n||0)+' games so far. '+
    'Straight up '+rec(R.su)+(R.brier!=null?' \u00b7 win-probability Brier score '+num(R.brier).toFixed(3)+' over '+R.brier_n+' games':'')+
    ' \u00b7 totals '+rec(R.ou)+' against the close'+(clt.n?', '+clt.toward+' of '+clt.n+' totals moved toward GridIron':'')+'.</div>';
  return h+'</div>';
}
function trackCard(){
  var T=D.track; if(!T) return '';
  var A=T.held||T.all, W=T.wk1, F=T.ptsfit;
  function tile(k,v,s){ return '<div class="ttile"><span class="tk">'+esc(k)+'</span>'+
    '<span class="tv">'+esc(v)+'</span><span class="ts2">'+esc(s)+'</span></div>'; }
  var h='<div class="mcard wide"><h3>GridIron against the market</h3>'+
    '<p class="sub3">The four headline figures cover 2023\u201325, seasons never used to fit the model or its calibration. Every game from 2019 on is predicted walk-forward \u2014 the model only ever '+
    'sees weeks that came before the one it is calling. The closing line is the benchmark, and it is '+
    'a very hard one.</p>'+
    '<div class="ttiles">'+
      tile('Margin error',num(A.gm).toFixed(2)+' pts','market '+num(A.vm).toFixed(2)+' \u00b7 GridIron is '+
           num(A.gm-A.vm).toFixed(2)+' worse')+
      tile('Total error',num(A.gt).toFixed(2)+' pts','market '+num(A.vt).toFixed(2)+' \u00b7 near parity')+
      tile('Against the spread',num(A.ats).toFixed(1)+'%',num(A.atsw)+' of '+num(A.atsn).toLocaleString()+
           ' \u00b7 break-even is 52.4%')+
      tile('Picks the winner',num(A.su)+'%','straight up, no spread')+
    '</div>'+
    '<div class="dwrap"><div class="dleg"><span><i class="d1"></i>GridIron</span>'+
      '<span><i class="d2"></i>Closing line</span><span class="dsp">average margin error, points</span></div>'+
      dumbbell(T.by)+'</div>'+
    '<div class="verdict"><b>What this actually means.</b> GridIron is close to the market but behind it, '+
    'and betting its disagreements would have lost money \u2014 '+num(A.ats).toFixed(1)+'% against the spread '+
    'over '+num(A.atsn).toLocaleString()+' games is a coin flip once you pay the vig. That is the expected '+
    'result: the closing line absorbs injury news, lineup changes and sharp money that a box-score model '+
    'never sees. Use GridIron\u2019s number to understand <em class="s">why</em> a game is priced where it is, '+
    'and treat a gap as a prompt to go look at the factors below it \u2014 not as an edge.</div>'+
    (num(W.gm)-num(W.vm)<=0.1?
    '<div class="verdict ok"><b>The one bright spot.</b> In week 1, when nobody has current-season data and '+
    'the market\u2019s information advantage is smallest, GridIron runs '+num(W.gm).toFixed(2)+' against the '+
    'line\u2019s '+num(W.vm).toFixed(2)+' \u2014 effectively parity.</div>':
    '<div class="verdict"><b>Week 1.</b> Even in week 1, when nobody has current-season data, GridIron runs '+num(W.gm).toFixed(2)+
    ' against the line\u2019s '+num(W.vm).toFixed(2)+'. The market is ahead from the first week.</div>');
  var VLAB={large:'Large',real:'Real',priced:'Priced in',none:'No effect',confounded:'Confounded'};
  h+='<h4 class="fh">Which intangibles actually move a game</h4>'+
     '<p class="sub3">'+esc(T.note_scope||'')+'</p>'+
     '<div class="ftab">';
  (T.factors||[]).forEach(function(f){
    h+='<div class="frow v-'+esc(f.v)+'"><span class="fk">'+esc(f.k)+
       (f.scope?'<small>on '+esc(f.scope)+'</small>':'')+'</span>'+
       '<span class="fv">'+esc(VLAB[f.v]||f.v)+'</span>'+
       '<span class="fs">'+esc(f.s)+(f.t!=null?' (t\u00a0=\u00a0'+num(f.t).toFixed(1)+', n\u00a0=\u00a0'+
         num(f.n).toLocaleString()+')':'')+'</span></div>';
  });
  h+='</div>'+trackExtras()+
    '<div class="verdict"><b>How points come out of a box score.</b> Fitted on all 544 team-games of 2025: '+
    'each offensive touchdown is worth '+num(F.td).toFixed(1)+' points, every 100 yards adds '+
    num(F.yds*100).toFixed(1)+', and a turnover costs '+num(Math.abs(F.to)).toFixed(1)+'. That conversion '+
    'explains '+Math.round(num(F.r2)*100)+'% of team scoring, so even a perfect box-score forecast would '+
    'still miss by about '+num(F.rmse).toFixed(1)+' points a side. GridIron gets '+
    num(T.blend.w)+'% of the blended line; the learning loop re-tests that share every week.</div></div>';
  return h;
}

function drawModel(){
  var C=D.cal; if(!C) return;
  var h=trackCard()+ledgerCard()+learnCard();
  /* calibration */
  var worst=Math.max.apply(null,C.pit.map(function(v){return Math.abs(v-0.1);}));
  h+='<div class="mcard"><h3>Calibration</h3>'+
    '<p class="sub3">Where actual results landed inside the predicted distribution, across '+num(C.n).toLocaleString()+
    ' player-weeks the model never saw during fitting. A perfect model puts 10% in every band \u2014 '+
    'the yellow line. Largest miss here is '+(worst*100).toFixed(1)+' points.</p>';
  C.pit.forEach(function(v,i){
    var w=Math.min(100,v/0.16*100);
    h+='<div class="pitrow"><span>'+(i*10)+'\u2013'+(i*10+10)+'%</span>'+
      '<span class="tr2"><i style="width:'+w.toFixed(0)+'%"></i>'+
      '<span class="ideal" style="left:'+(0.1/0.16*100).toFixed(0)+'%"></span></span>'+
      '<span style="text-align:right">'+(v*100).toFixed(1)+'%</span></div>';
  });
  h+='<p class="sub3" style="margin:10px 0 0">Total deviation from uniform: <b style="color:var(--fg)">'+
    C.dev+'</b>. Lower is better; 0 would be perfect.</p></div>';

  /* shrinkage */
  h+='<div class="mcard"><h3>Regression to <em>the mean</em></h3>'+
    '<p class="sub3">How much league-average evidence gets added before a player\u2019s own rate is trusted. '+
    'These were found by grid search against held-out weeks, not chosen by hand \u2014 and the ordering is the '+
    'point: volume stabilises fast, efficiency slowly.</p><div class="ktab">'+
    '<div><span class="kk">Target share<small>trusted quickly</small></span><span class="kv2">k = '+num(C.k.ts)+'</span></div>'+
    '<div><span class="kk">Catch rate<small>moderate regression</small></span><span class="kv2">k = '+num(C.k.cr)+'</span></div>'+
    '<div><span class="kk">Yards per target<small>heavily regressed</small></span><span class="kv2">k = '+num(C.k.ypt)+'</span></div>'+
    '</div><p class="sub3" style="margin-top:10px">Touchdown rate is not on this list on purpose. It is taken '+
    'from depth of target and league conversion, never from a player\u2019s own touchdown history \u2014 it is far '+
    'too noisy to carry forward.</p></div>';

  /* game script */
  h+='<div class="mcard"><h3>Game <em>script</em></h3>'+
    '<p class="sub3">Fitted on all 272 games of 2025: how a team\u2019s pass rate moves with the spread. '+
    'The effect is real but modest \u2014 worth including, not worth leaning on.</p><div class="ktab">'+
    '<div><span class="kk">Pass rate at a pick-em</span><span class="kv2">'+(num(C.script.icept)*100).toFixed(1)+'%</span></div>'+
    '<div><span class="kk">Per point of underdog</span><span class="kv2">+'+(num(C.script.slope)*100).toFixed(2)+' pts</span></div>'+
    '<div><span class="kk">A 7-point underdog</span><span class="kv2">+'+(num(C.script.slope)*700).toFixed(1)+' pts</span></div>'+
    '<div><span class="kk">League plays per game</span><span class="kv2">'+num(C.script.plays).toFixed(1)+'</span></div>'+
    '</div></div>';

  /* opponent adjustment */
  var ds=Object.keys(C.def).map(function(t){return [t,C.def[t]];}).sort(function(a,b){return a[1]-b[1];});
  var mx=Math.max.apply(null,ds.map(function(d){return Math.abs(d[1]);}))||1;
  h+='<div class="mcard"><h3>Coverage, <em>net of schedule</em></h3>'+
    '<p class="sub3">Each defence\u2019s effect on yards allowed per target, with the quality of the offences it '+
    'faced regressed out. Negative is tougher coverage. Raw allowed-yardage overstates the spread between '+
    'defences by roughly a tenth; much of what looks like defensive quality is schedule.</p><div class="defbars">';
  ds.forEach(function(d){
    var v=d[1], w=Math.abs(v)/mx*50;
    h+='<div class="defrow"><span class="tm2">'+esc(d[0])+'</span>'+
      '<span class="zz"><span class="mid2"></span>'+
      '<i style="background:'+(v<0?'#4ADE80':'#F87171')+';'+
      (v<0?'right:50%;width:'+w.toFixed(1)+'%':'left:50%;width:'+w.toFixed(1)+'%')+'"></i></span>'+
      '<span class="nv" style="color:'+(v<0?'#4ADE80':v>0?'#F87171':'var(--fg-4)')+'">'+
      (v>0?'+':'')+v.toFixed(2)+'</span></div>';
  });
  h+='</div></div>';

  /* baselines */
  h+='<div class="mcard"><h3>Positional <em>baselines</em></h3>'+
    '<p class="sub3">The 2025 league averages every player is regressed toward, and the depth-of-target curve '+
    'that sets touchdown rate.</p><div class="ktab">';
  ['WR','TE','RB'].forEach(function(k){
    var b=C.base[k]; if(!b) return;
    h+='<div><span class="kk">'+k+'<small>catch rate \u00b7 yds/target \u00b7 aDOT</small></span>'+
      '<span class="kv2">'+(b.cr*100).toFixed(0)+'% \u00b7 '+b.ypt.toFixed(2)+' \u00b7 '+b.adot.toFixed(1)+'</span></div>';
  });
  h+='</div></div>';

  /* cross-source agreement */
  var FIELDS=[['spread','Betting line','ESPN / DraftKings vs nflverse'],
    ['total','Game total','ESPN / DraftKings vs nflverse'],
    ['score_a','Final score, away','ESPN vs nflverse'],
    ['score_h','Final score, home','ESPN vs nflverse'],
    ['roof','Roof state','ESPN venue vs nflverse schedule'],
    ['surface','Playing surface','ESPN venue vs nflverse schedule'],
    ['temp','Temperature','AccuWeather vs Open-Meteo'],
    ['gust','Wind gusts','AccuWeather vs Open-Meteo']];
  var tally={}, disputes=[];
  Object.keys(D.verify||{}).forEach(function(gid){
    var V=D.verify[gid], gm=null;
    D.games.forEach(function(x){if(x.id===gid) gm=x;});
    Object.keys(V).forEach(function(f){
      tally[f]=tally[f]||{ok:0,x:0,single:0};
      tally[f][V[f].s]++;
      if(V[f].s==='x'&&gm) disputes.push({g:gm.a+' at '+gm.h,f:f,a:V[f].v,b:V[f].o,s:V[f].srcs});
    });
  });
  h+='<div class="mcard"><h3>Cross-checked <em>against a second source</em></h3>'+
    '<p class="sub3">Where two independent feeds publish the same fact, both are read and compared. '+
    'A value only carries a <b>2 sources</b> badge when they agree; where they differ the app shows '+
    'ESPN\u2019s and flags it rather than silently picking one.</p>'+
    '<div class="srchd"><span>Fact</span><span>Agree</span><span>Differ</span><span>One</span></div>';
  FIELDS.forEach(function(f){
    var t=tally[f[0]]; if(!t) return;
    h+='<div class="srcrow"><span class="sk">'+esc(f[1])+'<small style="display:block;color:var(--fg-4);font-size:10px;margin-top:1px">'+
      esc(f[2])+'</small></span>'+
      '<span class="sn ok">'+(t.ok||'\u2013')+'</span>'+
      '<span class="sn '+(t.x?'x':'')+'">'+(t.x||'\u2013')+'</span>'+
      '<span class="sn one">'+(t.single||'\u2013')+'</span></div>';
  });
  if(disputes.length){
    h+='<p class="sub3" style="margin:14px 0 6px"><b>Open disagreements</b></p>';
    disputes.forEach(function(x){
      h+='<div class="srcrow" style="grid-template-columns:1fr auto"><span class="sk">'+esc(x.g)+
        ' \u00B7 '+esc(x.f)+'</span><span class="sn x">'+esc(x.a)+' vs '+esc(x.b)+'</span></div>';
    });
  }
  h+='</div>';

  /* limits, stated plainly */
  h+='<div class="mcard"><h3>What this model <em>does not know</em></h3>'+
    '<p class="sub3">Stated so you can discount it appropriately.</p><div class="ktab">'+
    '<div><span class="kk">Routes run<small>the best volume denominator is not free data</small></span><span class="kv2">\u2014</span></div>'+
    '<div><span class="kk">Red-zone opportunity<small>TD rate uses depth of target as a proxy</small></span><span class="kv2">\u2014</span></div>'+
    '<div><span class="kk">Shadow coverage<small>never published; matchups are alignment-inferred</small></span><span class="kv2">\u2014</span></div>'+
    '<div><span class="kk">This season\u2019s form<small>2026 has barely started; priors are 2025</small></span><span class="kv2">\u2014</span></div>'+
    '<div><span class="kk">Injury severity<small>status is known, snap impact is not modelled</small></span><span class="kv2">\u2014</span></div>'+
    '</div></div>';
  var grid=document.getElementById('modelgrid');
  render(grid,h);
  grid.querySelectorAll('.mcard').forEach(function(c,i){c.style.animationDelay=(i*55)+'ms';});
}

/* ============================ wiring ============================ */
var tip=document.getElementById('tip');
function hideTip(){tip.classList.remove('on');}
function moveTip(e){
  var r=tip.getBoundingClientRect(),x=e.clientX+15,y=e.clientY+15;
  if(x+r.width>innerWidth-10) x=e.clientX-r.width-15;
  if(y+r.height>innerHeight-10) y=e.clientY-r.height-15;
  tip.style.left=Math.max(8,x)+'px'; tip.style.top=Math.max(8,y)+'px';
}
function wireField(box,offC,defC,offT,defT){
  box.querySelectorAll('.tok').forEach(function(el){
    var id=el.dataset.id,side=el.dataset.side;
    function open(){openPlayer(id,side==='off'?offC:defC,side==='off'?offT:defT);buildField();}
    el.addEventListener('click',open);
    el.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();open();}});
    el.addEventListener('mouseenter',function(e){
      var p=PL(id),u=U(id),pr=PR(id),cv=CV(id),line='';
      if(pr&&pr.S&&pr.S.tgt) line=num(pr.S.tgt)+' tgt \u00b7 '+num(pr.S.ry)+' yds';
      else if(pr&&pr.S&&pr.S.att) line=num(pr.S.py)+' pass yds';
      else if(pr&&pr.S&&pr.S.car) line=num(pr.S.car)+' car \u00b7 '+num(pr.S.ru)+' yds';
      else if(cv&&cv.tgt) line=num(cv.tgt)+' tgt \u00b7 '+num(cv.rat).toFixed(1)+' rtg allowed';
      render(tip,'<div class="tn">'+esc(p.n)+'</div><div class="tp">'+esc(p.p)+(u?' \u00b7 '+u.s.toFixed(0)+'% snaps':'')+'</div>'+
        (line?'<div class="ts">'+esc(line)+'</div>':''));
      tip.classList.add('on');moveTip(e);
    });
    el.addEventListener('mousemove',moveTip);
    el.addEventListener('mouseleave',hideTip);
    el.addEventListener('blur',hideTip);
  });
}
document.getElementById('sidenav').addEventListener('click',function(e){
  var b=e.target.closest('[data-go]'); if(!b) return;
  var v=b.dataset.go;
  go(v==='teams'||v==='model' ? v : +v);
});
document.getElementById('menubtn').addEventListener('click',function(){
  var sd=document.getElementById('side'), on=sd.classList.toggle('open'); this.setAttribute('aria-expanded',String(on));
});
document.getElementById('p-teams').addEventListener('click',function(e){
  var b=e.target.closest('[data-season]'); if(b){ tseason=b.dataset.season; drawTeams(); return; }
  b=e.target.closest('[data-view]'); if(b){ tview=b.dataset.view; drawTeams(); return; }
  b=e.target.closest('[data-sort]');
  if(b){ var k=b.dataset.sort; tsort=tsort.k===k?{k:k,d:-tsort.d}:{k:k,d:(k==='pa'||k==='pag'||k==='ypga')?1:-1}; drawTeams(); return; }
  b=e.target.closest('[data-game]'); if(b) go(+b.dataset.game);
});
document.getElementById('gjump').addEventListener('click',function(e){
  var b=e.target.closest('button[data-jump]'); if(!b) return;
  var t=document.getElementById(b.dataset.jump); if(t) t.scrollIntoView({behavior:'smooth',block:'start'});
});
document.getElementById('grecords').addEventListener('click',function(e){ if(e.target.closest('[data-teams]')) go('teams'); });
document.getElementById('whybtn').addEventListener('click',function(){
  var sec=this.closest('.sec'), on=sec.classList.toggle('shownotes');
  this.setAttribute('aria-expanded',String(on));
  this.querySelector('span').textContent = on ? 'Hide detail' : 'Why it matters';
});
document.getElementById('posf').addEventListener('click',function(e){
  var b=e.target.closest('button[data-p]'); if(!b) return;
  posFilter=b.dataset.p;
  document.querySelectorAll('#posf button').forEach(function(x){
    x.setAttribute('aria-pressed',String(x.dataset.p===posFilter));});
  if(typeof route==='number') drawMatchups();
});
document.getElementById('q').addEventListener('input',function(e){
  query=e.target.value.trim();
  buildSidebar(); if(route==='teams') drawTeams();
});
document.getElementById('gmatchups').addEventListener('click',function(e){
  var pin=e.target.closest('[data-pin]');
  if(pin){ togglePin(pin.dataset.pin); return; }
  var row=e.target.closest('.mrow2[data-oid]'); if(!row) return;
  var m=MATCHUPS.filter(function(x){return x.oid===row.dataset.oid;})[0];
  openPlayer(row.dataset.oid, m?m.offC:'#3F3F46', m?m.offT:'');});
document.getElementById('cmp').addEventListener('click',function(e){
  var pin=e.target.closest('[data-pin]'); if(pin) togglePin(pin.dataset.pin);});
document.getElementById('trayclear').addEventListener('click',function(){
  pinned=[]; if(typeof route==='number') drawMatchups(); drawTray();});
document.getElementById('toggle').addEventListener('click',function(e){
  var b=e.target.closest('button[data-p]');
  if(b&&b.dataset.p!==poss){poss=b.dataset.p;selected=null;buildField();}});
document.getElementById('layout').addEventListener('click',function(e){
  var b=e.target.closest('button[data-l]'); if(b) setMode(b.dataset.l);});
document.getElementById('scrim').addEventListener('click',closeDrawer);
addEventListener('keydown',function(e){
  if(e.key==='Escape'){closeDrawer();return;}
  if(e.target&&/^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
  if(typeof route!=='number') return;
  if(e.key==='ArrowDown'){e.preventDefault(); if(gi+1<D.games.length) go(gi+1);}
  else if(e.key==='ArrowUp'){e.preventDefault(); if(gi>0) go(gi-1);}
  else if(fieldInView()&&(e.key==='g'||e.key==='G')){e.preventDefault();setMode(mode==='form'?'depth':'form');}
  else if(fieldInView()&&e.key===' '){e.preventDefault();poss=poss==='h'?'a':'h';selected=null;buildField();}
});

/* ---------------------------------------------------------------- live games
   Scores, clock and box scores come straight from ESPN in the browser. Only game-state fields are
   touched here; lines, projections and predictions change only when a new audited data.json arrives. */
var ESPN='https://site.api.espn.com/apis/site/v2/sports/football/nfl/';
function getJSON(u){
  if(window.GRIDIRON_FIXTURE) return Promise.resolve(window.GRIDIRON_FIXTURE(u));
  return fetch(u,{cache:'no-store'}).then(function(r){return r.ok?r.json():null;});
}
function scoreTag(g){ return g.state==='in' ? 'LIVE' : (/OT/.test(g.detail||'') ? 'FINAL/OT' : 'FINAL'); }
function liveClock(g){ return g.state!=='in' ? '' : (g.detail || ((g.period?'Q'+g.period+' ':'')+(g.clock||''))); }
function erf(x){
  var sg=x<0?-1:1; x=Math.abs(x); var t=1/(1+0.3275911*x);
  return sg*(1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-0.284496736)*t+0.254829592)*t*Math.exp(-x*x));
}
function bandOf(v,edges){ for(var i=0;i<edges.length-1;i++){ if(v>=edges[i]&&v<edges[i+1]) return i; } return edges.length-2; }
function clockSecs(c){ var m=/^(\d+):(\d{2})/.exec(String(c||'')); return m?(+m[1])*60+(+m[2]):0; }
/* the live model, fitted on 2019-22 play-by-play and tested on 2023-25: the pregame margin fades with the clock while
   the score and the value of the current possession take over. The pregame margin and total are GridIron's own, or
   blends with the last betting line before kickoff once the learning loop has switched that on (w_market) */
function liveProjection(g){
  var L=D.live, p=PRD(g.id);
  if(!L||!L.margin||!p||g.state!=='in'||!g.sc) return null;
  var per=num(g.period,1), S=per>=5?0:Math.max(0,Math.min(3600,(4-per)*900+clockSecs(g.clock))), frac=S/3600;
  var Dm=num(g.sc.h)-num(g.sc.a), M0=num(p.ph)-num(p.pa), T0=num(p.ph)+num(p.pa), ep=0;
  var le=((D.ledger||{}).entries||{})[g.id], ln=(le&&le.last)||{};
  var msp=ln.spread!=null?ln.spread:g.spread, mou=ln.ou!=null?ln.ou:g.ou, wm=num(L.margin.w_market,0), wt=num((L.total||{}).w_market,0);
  if(wm&&msp!=null) M0=(1-wm)*M0+wm*(-num(msp));
  if(wt&&mou!=null) T0=(1-wt)*T0+wt*num(mou);
  if(g.dn>=1&&g.dn<=4&&g.possHome&&g.yte!=null){
    var yl=num(g.yte), dd=num(g.dist,0)||10;
    ep=g.possHome*num(L.ep.table[bandOf(yl,L.ep.yard_bands)][g.dn-1][bandOf(dd,L.ep.dist_bands)]);
  }
  var M=L.margin, mean=Dm+M.a_ep*ep+M.b_prior*M0*frac+M.c_frac*frac, sd=Math.sqrt(M.sigma*M.sigma*frac+M.eps*M.eps);
  var wp=0.5*(1+erf(mean/(sd*Math.SQRT2)));
  if(L.platt){ var c=Math.min(1-1e-6,Math.max(1e-6,wp)), z=Math.log(c/(1-c)); wp=1/(1+Math.exp(-(L.platt.alpha+L.platt.beta*z))); }
  var T=L.total, tot=num(g.sc.h)+num(g.sc.a)+T.t_prior*T0*frac+T.t_frac*frac+T.t_ep*Math.abs(ep);
  return {wp:wp, mean:mean, total:tot, ph:(tot+mean)/2, pa:(tot-mean)/2, ep:ep, frac:frac};
}
function liveStrip(g){
  var lp=liveProjection(g); if(!lp) return '';
  var pre=num((PRD(g.id)||{}).wp,50);
  return '<div class="pr-live"><span class="lvtag">LIVE</span> <span class="lvk">'+esc(liveClock(g))+'</span> '+
    '<span class="lvi"><em>Win probability</em> <b>'+esc(g.a)+' '+Math.round(100*(1-lp.wp))+'%</b> \u00b7 <b>'+esc(g.h)+' '+Math.round(100*lp.wp)+'%</b> '+
      '<small>pregame '+esc(g.h)+' '+Math.round(pre)+'%</small></span> '+
    '<span class="lvi"><em>Projected final</em> <b>'+esc(g.a)+' '+lp.pa.toFixed(1)+' \u2013 '+esc(g.h)+' '+lp.ph.toFixed(1)+'</b></span> '+
    '<span class="lvi"><em>Live spread / total</em> <b>'+spLab(g,Math.round(-lp.mean*2)/2)+'</b> \u00b7 <b>'+fx(Math.round(lp.total*2)/2)+'</b></span>'+
  '</div>';
}
function liveLine(g,oid){ var b=LIVE.box[g.id]; return (b&&b.stats[oid])||null; }
function applyScoreboard(sb){
  if(!sb||!sb.events) return false;
  var byId={}, changed=false;
  D.games.forEach(function(g){ byId[g.id]=g; });
  sb.events.forEach(function(e){
    var g=byId[e.id], c=(e.competitions||[])[0]; if(!g||!c||!c.status) return;
    var st=c.status, ty=st.type||{}, T={}, abbr={};
    (c.competitors||[]).forEach(function(x){ T[x.homeAway]=x; abbr[(x.team||{}).id]=(x.team||{}).abbreviation; });
    var nu={state:ty.state||g.state, sdesc:ty.description||g.sdesc, detail:ty.shortDetail||null, clock:st.displayClock||null, period:st.period||0};
    if(nu.state==='in'||nu.state==='post'){
      var a=parseInt((T.away||{}).score,10), h=parseInt((T.home||{}).score,10);
      if(!isNaN(a)&&!isNaN(h)) nu.sc={a:a,h:h};
    }
    var si=c.situation||null;
    nu.poss=(si&&si.possession)?(abbr[si.possession]||null):null;
    nu.down=si?(si.shortDownDistanceText||si.downDistanceText||null):null;
    nu.redzone=!!(si&&si.isRedZone);
    var hid=String(((T.home||{}).team||{}).id||'');
    nu.dn=(si&&si.down>=1&&si.down<=4)?si.down:0;
    nu.dist=(si&&si.distance!=null)?si.distance:null;
    nu.possHome=(si&&si.possession)?(String(si.possession)===hid?1:-1):0;
    /* yards to the end zone: ESPN's own count if sent, else the "KC 35" text read against the team with the ball,
       else yardLine, which ESPN measures from the home goal line (a home offense has 100-yardLine to go) */
    nu.yte=null;
    if(si&&si.yardsToEndzone!=null&&isFinite(Number(si.yardsToEndzone))) nu.yte=Number(si.yardsToEndzone);
    else if(si&&nu.possHome){
      var pt=/^([A-Za-z]{2,4})?\s*(\d{1,2})$/.exec(String(si.possessionText||'').trim());
      if(pt&&+pt[2]===50) nu.yte=50;
      else if(pt&&pt[1]&&nu.poss) nu.yte=(pt[1].toUpperCase()===String(nu.poss).toUpperCase())?100-(+pt[2]):+pt[2];
      else if(si.yardLine!=null&&isFinite(Number(si.yardLine))) nu.yte=nu.possHome>0?100-Number(si.yardLine):Number(si.yardLine);
    }
    Object.keys(nu).forEach(function(k){ if(JSON.stringify(g[k])!==JSON.stringify(nu[k])){ g[k]=nu[k]; changed=true; } });
  });
  return changed;
}
function parseBox(s){
  var out={}, n=function(x){ var k=parseFloat(x); return isNaN(k)?0:k; };
  ((s&&s.boxscore&&s.boxscore.players)||[]).forEach(function(tm){
    (tm.statistics||[]).forEach(function(grp){
      var L=grp.labels||[];
      (grp.athletes||[]).forEach(function(a){
        var gs=(D.espn||{})[String((a.athlete||{}).id)]; if(!gs) return;
        var v={}; L.forEach(function(l,i){ v[l]=(a.stats||[])[i]; });
        var e=out[gs]||(out[gs]={live:true});
        if(grp.name==='receiving'){ e.rec=n(v.REC); e.ry=n(v.YDS); e.rtd=n(v.TD); if(v.TGTS!=null) e.tgt=n(v.TGTS); }
        if(grp.name==='rushing'){ e.car=n(v.CAR); e.ru=n(v.YDS); e.rutd=n(v.TD); }
        if(grp.name==='passing'){ var ca=String(v['C/ATT']||'0/0').split('/'); e.cmp=n(ca[0]); e.att=n(ca[1]); e.py=n(v.YDS); e.ptd=n(v.TD); e['int']=n(v.INT); }
        if(grp.name==='fumbles'){ e.fum=n(v.LOST); }
      });
    });
  });
  Object.keys(out).forEach(function(gs){
    var e=out[gs];
    e.pts=Math.round(((e.rec||0)+0.1*(e.ry||0)+6*(e.rtd||0)+0.1*(e.ru||0)+6*(e.rutd||0)+0.04*(e.py||0)+4*(e.ptd||0)-2*(e['int']||0)-2*(e.fum||0))*10)/10;
  });
  return out;
}
function pollBoxes(){
  var due=D.games.filter(function(g){
    var b=LIVE.box[g.id];
    if(g.state==='in') return !b || Date.now()-b.at>110000;
    if(g.state==='post') return !(b&&b.final) && Date.now()-Date.parse(g.date)<8*3600000;
    return false;
  });
  if(!due.length) return Promise.resolve(false);
  return Promise.all(due.map(function(g){
    return getJSON(ESPN+'summary?event='+encodeURIComponent(g.id)).then(function(s){
      if(!s) return false;
      LIVE.box[g.id]={at:Date.now(), stats:parseBox(s), final:g.state==='post'}; return true;
    }).catch(function(){ return false; });
  })).then(function(r){ return r.some(Boolean); });
}
function liveWindow(){
  var now=Date.now();
  return D.games.some(function(g){
    var k=Date.parse(g.date);
    return g.state==='in' || (g.state==='pre' && k && k-now<30*60000 && now-k<6*3600000);
  });
}
function redraw(){
  var sc=document.getElementById('scroller'), top=sc?sc.scrollTop:0;
  buildSidebar();
  if(route==='teams') drawTeams();
  else if(typeof route==='number') drawGameInfo();
  if(sc) sc.scrollTop=top;
  stampFresh();
}
function pollScores(){
  if(!LIVE.on) return;
  getJSON(ESPN+'scoreboard').then(function(sb){
    if(!sb) return;
    LIVE.sb=sb; LIVE.scoresAt=Date.now();
    var changed=applyScoreboard(sb);
    return pollBoxes().then(function(bx){ if(changed||bx) redraw(); });
  }).catch(function(){}).then(function(){
    stampFresh(); clearTimeout(LIVE.timer);
    LIVE.timer=setTimeout(pollScores, liveWindow()?60000:600000);
  });
}
function ago(iso){
  var t=Date.parse(iso); if(isNaN(t)) return '';
  var s=Math.max(0,Math.round((Date.now()-t)/1000));
  if(s<90) return s+'s ago';
  var m=Math.round(s/60); if(m<90) return m+' min ago';
  var h=Math.round(m/60); return h<48 ? h+' h ago' : Math.round(h/24)+' days ago';
}
var LIVE={on:!!(window.GRIDIRON_LIVE||window.GRIDIRON_FIXTURE), box:{}, sb:null, timer:null, version:(D.meta&&D.meta.version)||null,
  code:window.GRIDIRON_CODE||null, codeStale:false, scoresAt:null};
function stampFresh(){
  var el=document.getElementById('stamp'); if(!el) return;
  var meta=D.meta||{}, bits=[];
  if(LIVE.codeStale){ el.textContent='app updated \u00b7 click to reload'; el.classList.add('stale'); return; }
  bits.push(meta.built ? 'model data '+ago(meta.built) : 'depth chart '+String(D.dt).slice(0,10)+' \u00b7 '+MATCHUPS.length+' matchups');
  if(LIVE.scoresAt) bits.push('scores '+ago(new Date(LIVE.scoresAt).toISOString()));
  el.textContent=bits.join(' \u00b7 ');
  /* stale: older than 35 minutes while a game is on or within three hours of kickoff, otherwise older than 8 hours */
  var now=Date.now(), age=meta.built?now-Date.parse(meta.built):0;
  var hot=D.games.some(function(g){ var k=Date.parse(g.date); return g.state==='in'||(g.state==='pre'&&k-now<3*3600000); });
  var stale=!!(meta.built&&age>(hot?35*60000:8*3600000));
  el.classList.toggle('stale',stale);
  var sb=document.getElementById('stalebar');
  if(sb){
    sb.hidden=!stale;
    render(sb,stale?'<b>GridIron\u2019s data was last updated '+esc(ago(meta.built))+'.</b> A refresh may be failing'+(hot?' during a game window':'')+
      ', so lines, injuries and projections here may be out of date. Scores and box scores still update live from ESPN.':'');
  }
}
function applyData(nd){
  if(!nd||!nd.games||!nd.games.length) return;
  var sc=document.getElementById('scroller'), top=sc?sc.scrollTop:0;
  var gid=(D.games[gi]||{}).id, open=lastPlayer;
  D=nd; SP=D.sprite||null; if(LIVE.sb) applyScoreboard(LIVE.sb); MATCHUPS=buildMatchups();
  var ni=D.games.findIndex(function(g){return g.id===gid;}); gi=ni<0?0:ni;
  if(typeof setLeague==='function') setLeague(D.lg||null);
  buildSidebar();
  go(typeof route==='number'?gi:route);
  if(sc) sc.scrollTop=top;
  if(open&&D.players[open[0]]) openPlayer(open[0],open[1],open[2]);
  stampFresh();
}
/* a new version of the page itself was published: reload in place -- the address keeps the current view --
   unless a player drawer is open, in which case it reloads as soon as the drawer closes */
function reloadForNewApp(){
  var dr=document.getElementById('drawer');
  if(dr&&dr.classList.contains('on')) return;
  location.reload();
}
function routeFromHash(){
  var h=String(location.hash||'').replace(/^#/,'');
  if(h==='model') return 'model';
  var m=h.match(/^game-(\d+)$/);
  if(m){ for(var i=0;i<D.games.length;i++){ if(String(D.games[i].id)===m[1]) return i; } }
  return 'teams';
}
function pollVersion(){
  if(!LIVE.on) return;
  getJSON('version.json?t='+Date.now()).then(function(v){
    if(!v) return;
    if(v.code&&LIVE.code&&v.code!==LIVE.code){ LIVE.codeStale=true; reloadForNewApp(); return; }
    if(!v.version||v.version===LIVE.version) return;
    return getJSON(v.data||('data.json?v='+encodeURIComponent(v.version))).then(function(nd){
      if(nd&&nd.meta&&nd.meta.version===v.version){ LIVE.version=v.version; applyData(nd); }
    });
  }).catch(function(){}).then(stampFresh);
}
if(typeof setLeague==='function') setLeague(D.lg||null);
buildSidebar(); go(routeFromHash());
stampFresh();
if(LIVE.on){
  pollScores();
  setInterval(pollVersion,120000); setInterval(stampFresh,30000);
  document.addEventListener('visibilitychange',function(){ if(!document.hidden) pollVersion(); });
  document.getElementById('stamp').addEventListener('click',function(){ if(LIVE.codeStale) location.reload(); });
}
})();
