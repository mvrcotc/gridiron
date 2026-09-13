/* ============================================================================
   Venue reference. Elevations are rounded to the nearest 10 ft and coordinates
   to 3 decimals -- precise enough for travel distance and body-clock maths,
   and honest about being approximate. tz drives the visiting team's body clock.
   ========================================================================== */

/* Documented characteristics of specific venues. These are reference facts, not
   computed from this season's data, and they sit beside the measured home-field
   swing rather than replacing it. */
var VENUE_NOTE={
 DEN:{t:'Altitude',d:'At 5,280 ft this is the highest venue in the league by roughly 3,200 ft. Thin air carries the ball farther on deep throws and kicks, and visiting players fatigue faster in the fourth quarter.'},
 KC:{t:'Crowd noise',d:'Arrowhead set the Guinness record for the loudest stadium at 142.2 dB in 2014. Sustained noise at that level drives visiting false starts and forces silent counts.'},
 SEA:{t:'Crowd noise',d:'Lumen Field held the noise record before Arrowhead at 137.6 dB, helped by a roof design that reflects sound down onto the field. Note that the measured home-field swing here has not matched the reputation over the last decade.'},
 NO:{t:'Enclosed noise',d:'The Superdome traps crowd noise with no outlet, one of the loudest indoor environments in the league.'},
 MIN:{t:'Enclosed noise',d:'U.S. Bank Stadium is fully enclosed and reflective, and rates among the loudest indoor venues.'},
 GB:{t:'Cold',d:'Lambeau is the coldest late-season venue in the league. Early in the season this is not a factor; from December it is a significant one.'},
 BUF:{t:'Wind and snow',d:'Lake-effect weather off Lake Erie produces the most disrupted conditions of any venue, including in-game snow that suppresses passing and kicking.'},
 CHI:{t:'Lake wind',d:'Wind off Lake Michigan swirls unpredictably at Soldier Field and has historically suppressed both passing efficiency and field-goal accuracy.'},
 CLE:{t:'Lake wind',d:'Open to Lake Erie, with wind patterns that make the north end zone notoriously difficult to kick toward.'},
 MIA:{t:'Heat and humidity',d:'September games in Miami are played in heat and humidity that visiting teams rarely train in, and the measured home swing here is the largest in the league.'},
 JAX:{t:'Heat',d:'Early-season heat in Jacksonville is among the most severe in the league.'},
 PIT:{t:'Field condition',d:'Natural grass at Acrisure degrades notably as the season progresses and is regularly cited by players as among the worst surfaces in the league.'},
 LV:{t:'Neutral crowd',d:'Allegiant draws unusually heavy visiting support, so the home-crowd component of home-field advantage is weaker here than anywhere else.'}
};

var STAD={
 BUF:{v:'Highmark Stadium',la:42.774,lo:-78.787,el:600,tz:'America/New_York',roof:'open'},
 MIA:{v:'Hard Rock Stadium',la:25.958,lo:-80.239,el:10,tz:'America/New_York',roof:'open'},
 NE:{v:'Gillette Stadium',la:42.091,lo:-71.264,el:285,tz:'America/New_York',roof:'open'},
 NYJ:{v:'MetLife Stadium',la:40.814,lo:-74.074,el:10,tz:'America/New_York',roof:'open'},
 NYG:{v:'MetLife Stadium',la:40.814,lo:-74.074,el:10,tz:'America/New_York',roof:'open'},
 BAL:{v:'M&T Bank Stadium',la:39.278,lo:-76.623,el:30,tz:'America/New_York',roof:'open'},
 CIN:{v:'Paycor Stadium',la:39.095,lo:-84.516,el:490,tz:'America/New_York',roof:'open'},
 CLE:{v:'Huntington Bank Field',la:41.506,lo:-81.699,el:580,tz:'America/New_York',roof:'open'},
 PIT:{v:'Acrisure Stadium',la:40.447,lo:-80.016,el:730,tz:'America/New_York',roof:'open'},
 HOU:{v:'NRG Stadium',la:29.685,lo:-95.411,el:50,tz:'America/Chicago',roof:'retractable'},
 IND:{v:'Lucas Oil Stadium',la:39.760,lo:-86.164,el:715,tz:'America/Indiana/Indianapolis',roof:'retractable'},
 JAX:{v:'EverBank Stadium',la:30.324,lo:-81.637,el:20,tz:'America/New_York',roof:'open'},
 TEN:{v:'Nissan Stadium',la:36.166,lo:-86.771,el:430,tz:'America/Chicago',roof:'open'},
 DEN:{v:'Empower Field at Mile High',la:39.744,lo:-105.020,el:5280,tz:'America/Denver',roof:'open'},
 KC:{v:'Arrowhead Stadium',la:39.049,lo:-94.484,el:890,tz:'America/Chicago',roof:'open'},
 LV:{v:'Allegiant Stadium',la:36.091,lo:-115.184,el:2030,tz:'America/Los_Angeles',roof:'dome'},
 LAC:{v:'SoFi Stadium',la:33.953,lo:-118.339,el:100,tz:'America/Los_Angeles',roof:'fixed'},
 LAR:{v:'SoFi Stadium',la:33.953,lo:-118.339,el:100,tz:'America/Los_Angeles',roof:'fixed'},
 LA:{v:'SoFi Stadium',la:33.953,lo:-118.339,el:100,tz:'America/Los_Angeles',roof:'fixed'},
 DAL:{v:'AT&T Stadium',la:32.748,lo:-97.093,el:550,tz:'America/Chicago',roof:'retractable'},
 PHI:{v:'Lincoln Financial Field',la:39.901,lo:-75.168,el:40,tz:'America/New_York',roof:'open'},
 WAS:{v:'Northwest Stadium',la:38.908,lo:-76.864,el:200,tz:'America/New_York',roof:'open'},
 WSH:{v:'Northwest Stadium',la:38.908,lo:-76.864,el:200,tz:'America/New_York',roof:'open'},
 CHI:{v:'Soldier Field',la:41.862,lo:-87.617,el:600,tz:'America/Chicago',roof:'open'},
 DET:{v:'Ford Field',la:42.340,lo:-83.046,el:600,tz:'America/New_York',roof:'dome'},
 GB:{v:'Lambeau Field',la:44.501,lo:-88.062,el:640,tz:'America/Chicago',roof:'open'},
 MIN:{v:'U.S. Bank Stadium',la:44.974,lo:-93.258,el:830,tz:'America/Chicago',roof:'dome'},
 ATL:{v:'Mercedes-Benz Stadium',la:33.755,lo:-84.401,el:1050,tz:'America/New_York',roof:'retractable'},
 CAR:{v:'Bank of America Stadium',la:35.226,lo:-80.853,el:750,tz:'America/New_York',roof:'open'},
 NO:{v:'Caesars Superdome',la:29.951,lo:-90.081,el:10,tz:'America/Chicago',roof:'dome'},
 TB:{v:'Raymond James Stadium',la:27.976,lo:-82.503,el:30,tz:'America/New_York',roof:'open'},
 ARI:{v:'State Farm Stadium',la:33.528,lo:-112.263,el:1070,tz:'America/Phoenix',roof:'retractable'},
 SF:{v:'Levi\u2019s Stadium',la:37.403,lo:-121.970,el:10,tz:'America/Los_Angeles',roof:'open'},
 SEA:{v:'Lumen Field',la:47.595,lo:-122.332,el:20,tz:'America/Los_Angeles',roof:'open'}
};
/* venues that are not a team's home park */
var NEUTRAL_VENUES={'Melbourne Cricket Ground':{la:-37.820,lo:144.983,el:100,tz:'Australia/Melbourne'}};

function haversine(a,b){
  var R=3958.8, t=Math.PI/180;
  var dLa=(b.la-a.la)*t, dLo=(b.lo-a.lo)*t;
  var h=Math.sin(dLa/2)*Math.sin(dLa/2)+
        Math.cos(a.la*t)*Math.cos(b.la*t)*Math.sin(dLo/2)*Math.sin(dLo/2);
  return Math.round(2*R*Math.asin(Math.sqrt(h)));
}
function venueOf(g){
  if(g.venue && NEUTRAL_VENUES[g.venue]) return NEUTRAL_VENUES[g.venue];
  return STAD[g.h]||null;
}
function localHour(iso,tz){
  try{
    var s=new Date(iso).toLocaleString('en-US',{timeZone:tz,hour:'numeric',hour12:false});
    return parseInt(s,10);
  }catch(_){ return null; }
}
function fmtLocal(iso,tz){
  try{
    return new Date(iso).toLocaleString('en-US',{timeZone:tz,hour:'numeric',minute:'2-digit'});
  }catch(_){ return ''; }
}

/* Each factor: {ic, k, v, note, favors:'home'|'away'|'', sev:0..2} */
var GLG=null;
function setLeague(x){GLG=x;}
function contextFactors(g){
  var out=[], ven=venueOf(g), away=STAD[g.a], home=STAD[g.h];

  if(g.neutral){
    out.push({grp:'set',ic:'globe',k:'Neutral site',v:g.venue||'',sev:2,favors:'',
      note:'Neither side has a home crowd, a home routine or a short trip. Treat published home-field edges as void.'});
  }

  /* elevation */
  if(ven&&ven.el!=null){
    var el=ven.el, sev=el>=4000?2:el>=1800?1:0;
    var note;
    if(el>=4000) note='Thin air. The ball carries noticeably farther on deep throws and kicks, and visiting players fatigue sooner \u2014 the single largest environmental factor in the league.';
    else if(el>=1800) note='Mild altitude. A small carry benefit on kicks; conditioning effects are marginal.';
    else note='Near sea level \u2014 no altitude effect.';
    out.push({grp:'cond',ic:'mtn',k:'Elevation',v:el.toLocaleString()+' ft',sev:sev,ref:'sea level',
      favors:(sev&&!g.neutral)?'home':'', note:note});
  }

  /* travel + body clock for the visitors */
  if(ven&&away){
    var mi=haversine(away,ven);
    var homeMi=(home&&g.neutral)?haversine(home,ven):null;
    var sev2=mi>=2500?2:mi>=1200?1:0;
    out.push({grp:'set',ic:'plane',k:'Visitor travel',v:mi.toLocaleString()+' mi',sev:sev2,
      favors:(sev2&&!g.neutral)?'home':'',
      note:g.neutral?('Both teams travelled to a neutral venue \u2014 '+g.a+' '+mi.toLocaleString()+
          ' mi'+(homeMi!=null?', '+g.h+' '+homeMi.toLocaleString()+' mi':'')+'. Neither side gets a routine week.')
        :mi>=2500?'A long-haul trip, often with a time-zone shift on top. Documented to cost visiting teams on the road.'
        :mi>=1200?'A moderate trip \u2014 a real but modest factor.'
        :'A short trip; travel is not a meaningful factor here.'});
    var h=localHour(g.date,away.tz);
    if(h!=null){
      var early=h<=10, late=h>=20;
      out.push({grp:'set',ic:'clock',k:'Visitor body clock',v:fmtLocal(g.date,away.tz),sev:early?1:0,
        favors:(early&&!g.neutral)?'home':'',
        note:early?'Kickoff lands in the visitors\u2019 morning. Teams crossing east for an early window have historically underperformed.'
          :late?'A late body-clock kickoff for the visitors \u2014 generally neutral to slightly favourable.'
          :'Kickoff sits comfortably inside the visitors\u2019 normal window.'});
    }
  }

  /* roof, and the weather immediately beside it -- together they answer one
     question: is anything about the environment going to change this game? */
  /* the icon and human label for a condition code are a rendering concern;
     the factor just carries the code and the renderer resolves it */
  var wxIcon='wx', wxLabel='';
  if(g.indoor){
    out.push({grp:'cond',ic:'dome',k:'Roof',v:'Indoor',sev:0,favors:'',
      note:'Climate controlled. Weather is removed as a variable, and indoor games historically run slightly higher scoring.'});
    out.push({grp:'cond',ic:'sun',k:'Conditions',v:'Not a factor',sev:0,favors:'',
      note:'Nothing outside reaches the field. Wind, rain and temperature can be ignored entirely for this game.'});
  } else {
    out.push({grp:'cond',ic:'open',k:'Roof',v:'Open air',sev:0,favors:'',note:'Conditions are in play.'});

    var done=g.state==='post';
    var t  = done ? (g.rtemp!=null?Number(g.rtemp):null) : (g.temp==null?null:Number(g.temp));
    var gu = done ? (g.rgust!=null?Number(g.rgust):null) : (g.gust==null?null:Number(g.gust));
    var pr = done ? (g.rprecip!=null?(Number(g.rprecip)>0?Math.round(Number(g.rprecip)*100)/100:0):null)
                  : (g.precip==null?null:Number(g.precip));
    if(t==null&&gu==null&&pr==null){
      out.push({grp:'cond',ic:'cloud',k:'Conditions',v:done?'Not archived':'No forecast yet',sev:0,favors:'',
        note:done?'Conditions were not archived for this game. ESPN drops the weather block once a game goes final, and the season-long record has not been backfilled yet.'
                 :'A forecast is usually published about a week out from kickoff.'});
    } else {
      var sev3=0, note3='Nothing in the forecast that changes how this game gets played.';
      if(gu!=null&&gu>=20){sev3=2;note3='Gusts at this level degrade deep passing and field-goal accuracy materially. Fade distance kickers and deep threats.';}
      else if(gu!=null&&gu>=15){sev3=1;note3='Enough wind to take the top off the deep passing game.';}
      else if(!done&&pr!=null&&pr>=50){sev3=1;note3='Rain likely \u2014 expect a run-leaning script and more drops.';}
      else if(done&&pr!=null&&pr>=2){sev3=1;note3='Rain fell during this game \u2014 worth noting against any passing line that missed.';}
      else if(t!=null&&t<=32){sev3=1;note3='Freezing conditions degrade ball handling and kicking.';}
      else if(t!=null&&t>=90){sev3=1;note3='Heat drives rotation and late-game cramping.';}
      var bits=[];
      if(t!=null) bits.push(t+'\u00B0F');
      if(gu!=null) bits.push(gu+(done?' mph wind':' mph gusts'));
      if(pr!=null) bits.push(done ? (pr>0?pr+' mm rain':'no rain') : pr+'% precip');
      out.push({grp:'cond',ic:done?(g.rfam||'cloud'):wxIcon, cond:g.cond, rlabel:done?g.rlabel:null,
        k:done?'Conditions (recorded)':'Conditions',
        v:bits.join(' \u00B7 '),sev:sev3,favors:'',
        note:(done?'Measured at kickoff from the weather record for this venue. ':'')+note3});
    }
    if(away&&(away.roof==='dome'||away.roof==='fixed')){
      out.push({grp:'cond',ic:'warn',k:'Dome team outdoors',v:g.a,sev:1,favors:'home',
        note:g.a+' play their home games under a roof and are outdoors here \u2014 worth discounting their passing and kicking game if conditions turn.'});
    }
  }
  if(g.surf||g.grass!=null){
    var sname=g.surf?String(g.surf).replace('fieldturf','FieldTurf').replace('matrixturf','MatrixTurf')
      .replace('sportturf','SportTurf').replace('astroturf','AstroTurf').replace('grass','Grass').replace('a_turf','AstroTurf')
      :(g.grass?'Grass':'Artificial turf');
    var natural=/grass/i.test(sname);
    out.push({grp:'cond',ic:'turf',k:'Surface',v:sname,sev:0,favors:'',
      note:natural?'Natural grass \u2014 slightly slower, and associated with fewer non-contact lower-body injuries.'
        :'Artificial turf \u2014 marginally faster footing, and a documented uptick in non-contact soft-tissue injuries.'});
  }

  /* what this specific venue does to visitors, measured and documented */
  if(!g.neutral){
    var vn=VENUE_NOTE[g.h];
    var hf=g.hfa;
    if(hf){
      var d=Number(hf.d), tough=d>=1.5, easy=d<=-1.5;
      out.push({grp:'set',ic:'stadium',k:'Venue edge',
        v:(hf.e>0?'+':'')+Number(hf.e).toFixed(1)+' pts',
        ref:Number(hf.lg).toFixed(1)+' league avg',
        d:(d>0?'+':'')+d.toFixed(1), dsign:d,
        sev:tough?1:0, favors:tough?'home':'',
        note:'Over '+hf.n+' home games since 2015, '+g.h+' have been '+Math.abs(Number(hf.e)).toFixed(1)+
          ' points '+(Number(hf.e)>=0?'better':'worse')+' at home than on the road. Measuring the swing against '+
          'their own road form removes roster quality, so what is left is the venue. League average swing is '+
          Number(hf.lg).toFixed(1)+' points. '+
          (tough?'This is a genuinely hard place to visit.'
           :easy?'Weaker than a typical home field despite any reputation.'
           :'About typical.')});
    }
    if(vn){
      out.push({grp:'set',ic:'stadium',k:vn.t,v:g.venue||g.h,sev:0,favors:'home',note:vn.d});
    }
  }

  /* market-implied home edge */
  if(g.spread!=null&&!g.neutral){
    var sp=Number(g.spread);
    out.push({grp:'set',ic:'home',k:'Home field',v:g.h,sev:0,favors:'home',
      note:'Roughly 1.5\u20132 points of the posted line is home field before anything team-specific. '+
        'The market currently has '+(sp<0?g.h+' favoured by '+Math.abs(sp):g.a+' favoured by '+Math.abs(sp))+'.'});
  }

  /* divisional familiarity */
  if(g.div){
    out.push({grp:'set',ic:'shield',k:'Divisional',v:'Yes',sev:0,favors:'',
      note:'Division opponents meet twice a year and know each other\u2019s personnel. These games run tighter than the spread suggests and historically a little lower scoring.'});
  }

  /* officiating crew: a real and under-watched mover of totals */
  if(g.ref&&g.ref.n){
    var rv=g.ref.avg, lgt=g.ref.lg, diff=(rv!=null&&lgt!=null)?rv-lgt:null;
    out.push({grp:'tend',ic:'whistle',k:'Referee',v:g.ref.n,
      ref:(lgt!=null?lgt.toFixed(1)+' league avg':null),
      d:(diff!=null?(diff>0?'+':'')+diff.toFixed(1)+' pts':null), dsign:(diff||0),
      sev:(diff!=null&&Math.abs(diff)>=4)?1:0,favors:'',
      note:(diff==null?'No 2025 sample for this crew.'
        :'Games under this crew averaged '+rv.toFixed(1)+' points last season against a league average of '+
         lgt.toFixed(1)+' \u2014 '+(diff>0?'+':'')+diff.toFixed(1)+' points, across '+g.ref.gp+' games. '+
         (Math.abs(diff)>=4?'Crews that call more differ measurably on totals; worth a look before betting the over or under.'
                          :'Close enough to average to ignore.'))});
  }

  /* pace and pass tendency set the volume every player projection sits on */
  var LG=(typeof GLG!=='undefined'&&GLG)?GLG:null;
  if(LG&&g.h_pace!=null&&g.a_pace!=null){
    var comb=(Number(g.h_pace)+Number(g.a_pace))/2, dp=comb-LG.plays;
    out.push({grp:'tend',ic:'gauge',k:'Pace',v:comb.toFixed(1)+' plays',
      ref:LG.plays.toFixed(1)+' league avg', d:(dp>0?'+':'')+dp.toFixed(1), dsign:dp,
      sev:Math.abs(dp)>=2.5?1:0,favors:'',
      note:'These two offences averaged '+comb.toFixed(1)+' plays a game last season against a league average of '+
        LG.plays.toFixed(1)+'. Plays are the denominator under every volume projection \u2014 '+
        (dp>=2.5?'a fast pairing lifts everyone\u2019s floor.'
         :dp<=-2.5?'a slow pairing caps everyone\u2019s ceiling.'
         :'roughly league-typical.')});
  }
  if(LG&&g.h_pr!=null&&g.a_pr!=null){
    var cpr=(Number(g.h_pr)+Number(g.a_pr))/2, dpr=cpr-LG.pr;
    out.push({grp:'tend',ic:'gauge',k:'Pass tendency',v:cpr.toFixed(0)+'% pass',
      ref:LG.pr.toFixed(1)+'% league avg', d:(dpr>0?'+':'')+dpr.toFixed(1)+'pt', dsign:dpr,
      sev:Math.abs(dpr)>=3?1:0,favors:'',
      note:'Combined pass rate of '+cpr.toFixed(1)+'% against a '+LG.pr.toFixed(1)+'% league average. '+
        (dpr>=3?'Both lean pass-first, which favours receivers over backs.'
         :dpr<=-3?'Both lean run-first, which suppresses target volume.'
         :'Neither team skews far from league-typical.')});
  }

  /* a new hand under centre resets everything a projection assumes */
  ['a','h'].forEach(function(sd){
    if(g[sd+'_qbnew']){
      out.push({grp:'tend',ic:'warn',k:'New quarterback',v:g[sd],sev:1,favors:sd==='a'?'home':'away',
        note:g[sd]+' open with a different primary passer than the one who threw most of their 2025 attempts. '+
          'Every target share and efficiency figure here was earned with someone else throwing \u2014 discount them accordingly.'});
    }
  });

  /* primetime */
  var etH=localHour(g.date,'America/New_York');
  if(etH!=null&&etH>=19){
    out.push({grp:'set',ic:'star',k:'Primetime',v:g.net||'National',sev:0,favors:'',
      note:'A standalone national window \u2014 full week of preparation and no competing games.'});
  }
  return out;
}
