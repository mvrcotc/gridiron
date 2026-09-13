#!/usr/bin/env node
// Headless structural check of the built page. Renders the board, one player drawer and the Model
// page, counts what should be there, and can dump every rendered character so two builds diff exactly.
//   node tools/check_app.js                  summary
//   node tools/check_app.js --dump out.txt   summary + full rendered text
const fs=require('fs'), path=require('path');
let jsdom; try{ jsdom=require('jsdom'); }catch(e){ jsdom=require('/tmp/node_modules/jsdom'); }
const {JSDOM,VirtualConsole}=jsdom;
const APP=path.join(__dirname,'..','app');
const argv=process.argv.slice(2), di=argv.indexOf('--dump'), dump=di>=0?argv[di+1]:null;
const rd=f=>fs.readFileSync(path.join(APP,f),'utf8');
const SHIM='<script>window.matchMedia=window.matchMedia||function(q){return{matches:false,media:q,'+
  'addListener(){},removeListener(){},addEventListener(){},removeEventListener(){},onchange:null,'+
  'dispatchEvent(){return false}};};Element.prototype.scrollIntoView=Element.prototype.scrollIntoView||function(){};<\/script>';
// function replacers: a "$'" inside app.js must never be read as a replacement pattern
let html=rd('gridiron-v2.html')
  .replace('<script src="context.js"></script>',()=>SHIM+'<script>'+rd('context.js')+'</script>')
  .replace('<script src="app.js"></script>',()=>'<script>'+rd('app.js')+'</script>');
const errs=[], vc=new VirtualConsole(); vc.on('jsdomError',e=>errs.push(String(e&&e.message||e)));
const dom=new JSDOM(html,{runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc});
const W=dom.window, d=W.document, n=s=>d.querySelectorAll(s).length;
const click=el=>el&&el.dispatchEvent(new W.MouseEvent('click',{bubbles:true}));
const S={}; let text='';
setTimeout(()=>{
  text+=d.getElementById('games').textContent;
  Object.assign(S,{cards:n('.gcard'),expandedByDefault:n('.gcard.showall'),predictionBlocks:n('.gc-pred'),
    injuryPanels:n('.ijpanel'),weatherRows:n('.wf.info'),nestedSides_mustBe0:n('.gc-side .gc-side')});
  click([...d.querySelectorAll('#games .mrow2')].find(r=>/Higgins|Nabers|Gibbs/.test(r.textContent)));
  setTimeout(()=>{
    const dr=d.getElementById('drawer'); text+='\n@@DRAWER@@\n'+dr.textContent;
    Object.assign(S,{drawerMarketTables:dr.querySelectorAll('.mktab').length,drawerChainRows:dr.querySelectorAll('.chain > div').length});
    click(d.querySelector('.navitem[data-go="model"]'));
    setTimeout(()=>{
      text+='\n@@MODEL@@\n'+d.getElementById('modelgrid').textContent;
      Object.assign(S,{trackCard:n('.mcard.wide'),factorRows:n('.frow'),calibrationRows:n('.wprow'),verdicts:n('.verdict')});
      for(const [k,v] of Object.entries(S)) console.log('  %s %s',k.padEnd(22),v);
      console.log('  %s %d','js errors'.padEnd(22),errs.length); errs.slice(0,5).forEach(e=>console.log('    '+e));
      if(dump) fs.writeFileSync(dump,text);
      process.exitCode=errs.length?1:0; W.close();
    },150);
  },200);
},700);
