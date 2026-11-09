/* Relay's animation is an illustration, not a connection to agents or infrastructure.
   IntersectionObserver changes story chapters; CSS animates only meaningful events. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
  const mobile = window.matchMedia('(max-width: 760px)');
  const stages = [
    {delivered:13,app:'Investigating delivery failures',cloud:'Waiting for the app’s finding',maya:'Review',leo:'Review',finding:'The incident is open. Private diagnostics have not been shared.',check:'Not yet run',caption:'A customer sees one failure. The answer spans two companies.'},
    {delivered:13,app:'Checks failed message-service starts',cloud:'Checks its own connection capacity',maya:'Review',leo:'Review',finding:'Each agent investigates its own systems. Detailed reports stay on their own side.',check:'Investigating',caption:'Private records stay in place. Findings can be prepared for review.'},
    {delivered:13,app:'Prepares a finding for Maya’s review',cloud:'Waiting for an approved finding',maya:'Reviewing',leo:'Review',finding:'Waiting for Maya. The proposed finding has not reached HarborCloud yet.',check:'Not yet repaired',caption:'Maya reviews the proposed finding. Her approval controls what crosses.'},
    {delivered:15,app:'Customer test still fails. Checks the app.',cloud:'Capacity restored after Leo’s approval',maya:'Shared',leo:'Approved',finding:'Maya’s approved finding reached HarborCloud. Its reviewed result returns: cloud checks pass, customer delivery still fails.',check:'6 / 6 passed',caption:'Cloud healthy. Only 15 of 24 messages arrived. The investigation continues.'},
    {delivered:24,app:'App recovered after Maya’s approval',cloud:'Cloud repair remains verified',maya:'Approved',leo:'Approved',finding:'Both repairs are verified. The incident records findings, approvals, and the customer’s delivery result.',check:'6 / 6 passed',caption:'The earlier failed message is recovered with its original ID. Repeating it creates no second copy.'}
  ];
  let current=0;
  const chapters=[...document.querySelectorAll('.chapter')];
  const dots=[...document.querySelectorAll('[data-scene]')];
  const grid=$('delivery-grid');
  for(let i=0;i<24;i++){const cell=document.createElement('span');cell.className='delivery-cell';cell.style.transitionDelay=`${(i%12)*25}ms`;grid.append(cell);}
  function render(index,announce=false){
    current=Math.max(0,Math.min(stages.length-1,index));
    const s=stages[current];
    $('story-diagram').dataset.step=String(current);
    $('finding-packet').setAttribute('aria-hidden',String(current<2));
    document.querySelector('.approved-stamp').setAttribute('aria-hidden',String(current<3));
    $('story-delivery').innerHTML=`${s.delivered}<small>/24</small>`;
    $('stage-position').textContent=`${current+1} of 5`;
    $('app-task').textContent=s.app;
    $('cloud-task').textContent=s.cloud;
    $('maya-decision').textContent=s.maya;
    $('leo-decision').textContent=s.leo;
    $('shared-finding').textContent=s.finding;
    $('cloud-outcome').textContent=s.check;
    $('diagram-caption').textContent=s.caption;
    $('finding-label').textContent=current>=3?'Approved finding + evidence':'Finding + evidence for review';
    [...grid.children].forEach((cell,i)=>cell.classList.toggle('arrived',i<s.delivered));
    chapters.forEach((chapter,i)=>chapter.classList.toggle('is-active',i===current));
    dots.forEach((dot,i)=>{dot.classList.toggle('is-active',i===current);if(i===current)dot.setAttribute('aria-current','step');else dot.removeAttribute('aria-current');});
    $('previous').disabled=current===0;
    $('next-scene').disabled=current===4;
    if(announce)$('announcement').textContent=`Scene ${current+1}. ${chapters[current].querySelector('h3').textContent} ${s.caption}`;
  }
  let manualUntil=0;
  function navigate(index){
    manualUntil=Date.now()+1200;
    render(index,true);
    const target=mobile.matches?$('story-diagram'):chapters[current];
    target.scrollIntoView({behavior:motionPreference.matches?'instant':'smooth',block:mobile.matches?'start':'center'});
  }
  dots.forEach(dot=>dot.addEventListener('click',()=>navigate(Number(dot.dataset.scene))));
  document.querySelectorAll('[data-next]').forEach(button=>button.addEventListener('click',()=>navigate(Number(button.dataset.next))));
  $('previous').addEventListener('click',()=>navigate(current-1));
  $('next-scene').addEventListener('click',()=>navigate(current+1));
  let observer;
  function observeChapters(){
    if(observer)observer.disconnect();
    if(mobile.matches)return;
    observer=new IntersectionObserver(entries=>{
      if(Date.now()<manualUntil)return;
      const eligible=entries.filter(entry=>entry.isIntersecting).sort((a,b)=>b.intersectionRatio-a.intersectionRatio);
      if(eligible.length)render(Number(eligible[0].target.dataset.step));
    },{rootMargin:'-25% 0px -25% 0px',threshold:[0,.15,.3,.5,.7]});
    chapters.forEach(chapter=>observer.observe(chapter));
  }
  mobile.addEventListener('change',observeChapters);
  observeChapters();
  render(0);

  const heroCaptions=[
    'Your message never arrives. Which company needs to fix it?',
    'Each agent investigates its own side. Private diagnostics stay there.',
    'Maya approves a finding. Switch carries it to HarborCloud’s agent.',
    'The cloud passes. Messages still fail. The result goes back to TeamChat.',
    'Both owners approve their repairs. Now the message arrives.'
  ];
  let heroPhase=0,heroTimer=null,paused=motionPreference.matches,heroVisible=true;
  function paintHero(){
    $('hero-stage').dataset.phase=String(heroPhase);
    $('hero-caption').textContent=heroCaptions[heroPhase];
    $('hero-message-status').textContent=heroPhase===4?'Recovered':'Not delivered';
  }
  function clearHeroTimer(){if(heroTimer!==null){clearTimeout(heroTimer);heroTimer=null;}}
  function scheduleHero(){
    clearHeroTimer();
    if(paused||!heroVisible||heroPhase>=4||document.hidden)return;
    heroTimer=setTimeout(()=>{heroPhase+=1;paintHero();scheduleHero();},heroPhase===0?3800:4000);
  }
  function updateMotion(){
    document.documentElement.classList.toggle('motion-paused',paused);
    $('motion-control').textContent=paused?'Play motion':'Pause motion';
    $('motion-control').setAttribute('aria-pressed',String(paused));
    scheduleHero();
  }
  $('motion-control').addEventListener('click',()=>{paused=!paused;updateMotion();});
  $('replay-overview').addEventListener('click',()=>{heroPhase=0;paintHero();if(!motionPreference.matches)paused=false;updateMotion();});
  motionPreference.addEventListener('change',()=>{paused=motionPreference.matches;updateMotion();});
  document.addEventListener('visibilitychange',scheduleHero);
  const heroObserver=new IntersectionObserver(entries=>{heroVisible=entries[0].isIntersecting;scheduleHero();},{threshold:.1});
  heroObserver.observe($('hero-stage'));
  paintHero();updateMotion();

  const themeButton=$('theme-control');
  const themeMedia=window.matchMedia('(prefers-color-scheme: dark)');
  const systemTheme=()=>themeMedia.matches?'dark':'light';
  try{const saved=localStorage.getItem('relay-theme');if(saved==='dark'||saved==='light')document.documentElement.dataset.theme=saved;}catch{/* Theme works when browser storage is disabled. */}
  function themeLabel(){const active=document.documentElement.dataset.theme||systemTheme();themeButton.textContent=active==='dark'?'Light':'Dark';themeButton.setAttribute('aria-label',`Use ${active==='dark'?'light':'dark'} color theme`);}
  themeButton.addEventListener('click',()=>{const next=(document.documentElement.dataset.theme||systemTheme())==='dark'?'light':'dark';document.documentElement.dataset.theme=next;try{localStorage.setItem('relay-theme',next);}catch{}themeLabel();});
  themeMedia.addEventListener('change',themeLabel);themeLabel();
})();
