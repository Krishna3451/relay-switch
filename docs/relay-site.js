/* A bounded educational simulation. This never calls agents or infrastructure. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const labels = ['Incident', 'Finding', 'Cloud repair', 'Delivery check', 'App repair', 'Recovered'];
  const approvedFinding = 'Messages fail during connection overload. Can HarborCloud check connection capacity?';
  const scenes = [
    {
      kicker: 'The incident', title: 'Messages are not arriving.', delivered: 13, cloud: 'Not checked',
      app: 'The agent finds connection failures and message servers that did not start.',
      sharedAuthor: 'Maya reports the incident', shared: 'People are sending messages, but some never arrive. We need both teams to investigate.',
      provider: 'The provider agent has no access to TeamChat’s private service observations.',
      rule: 'The shared incident is where the two companies coordinate.',
      explain: 'Each agent can investigate its own systems. A useful finding must cross the boundary before the other team can act.',
      action: 'Review the finding'
    },
    {
      kicker: 'Maya controls sharing', title: 'Review what leaves TeamChat.', delivered: 13, cloud: 'Not checked',
      app: 'The agent prepares a short finding. Maya reviews this exact text before the other company receives it.',
      sharedAuthor: 'Waiting for Maya’s review', shared: 'The proposed finding has not reached HarborCloud yet.',
      provider: 'Waiting for a finding that TeamChat’s owner has approved for sharing.',
      rule: 'Nothing crosses just because the agent wrote it.',
      explain: 'Only this reviewed finding will cross. Detailed diagnostic observations remain private to TeamChat.',
      action: 'Maya: share finding'
    },
    {
      kicker: 'Leo controls the cloud change', title: 'The approved finding arrives.', delivered: 13, cloud: 'Change proposed',
      app: 'Maya has approved the short finding. TeamChat’s detailed service observations remain on its own side.',
      sharedAuthor: 'Owner-approved TeamChat finding', shared: approvedFinding, finding: true,
      provider: 'The agent finds an overloaded connection and proposes more capacity. Leo reviews the change on his side.',
      rule: 'Switch carries the approved finding to the counterpart agent.',
      explain: 'Sharing evidence is separate from approving a system change. Only HarborCloud’s owner can approve its cloud repair.',
      action: 'Leo: approve cloud repair'
    },
    {
      kicker: 'Test the customer outcome', title: 'The cloud passes. Messages still fail.', delivered: 15, cloud: '6 / 6 passed',
      app: 'The reviewed cloud result sends TeamChat’s agent back to its own failed message-service starts.',
      sharedAuthor: 'HarborCloud’s reviewed result', shared: 'The cloud connection passes all six checks. A fresh TeamChat test still delivers only 15 of 24 messages.',
      provider: 'The approved capacity change is complete. A healthy cloud connection has not finished the incident.',
      rule: 'The customer’s delivery result continues the investigation.',
      explain: 'This is the important handoff. “My system is healthy” is not the same as “the customer’s problem is solved.”',
      action: 'Review TeamChat’s repair'
    },
    {
      kicker: 'Maya controls the app change', title: 'Finish the recovery on the app side.', delivered: 15, cloud: '6 / 6 passed',
      app: 'The agent proposes recovering the failed message-service starts, then repeating the delivery test. Maya reviews the proposed change.',
      sharedAuthor: 'The incident remains open', shared: 'Cloud capacity is restored. TeamChat is reviewing its remaining recovery; customer delivery still needs to pass.',
      provider: 'HarborCloud cannot approve or apply TeamChat’s private app change.',
      rule: 'Each company keeps authority over its own systems.',
      explain: 'Maya’s approval authorizes the app recovery. The agent then has to verify that messages actually arrive.',
      action: 'Maya: approve app repair'
    },
    {
      kicker: 'Verify before closing', title: '24 sent. 24 arrived.', delivered: 24, cloud: '6 / 6 passed',
      app: 'After the approved recovery, the agent repeats the same delivery test. All 24 messages arrive.',
      sharedAuthor: 'The reviewed recovery result', shared: 'Both repairs are verified. The shared incident records what was shared, who approved each change, and what the delivery checks found.',
      provider: 'The provider’s repair and the app’s repair have both been checked against the customer’s outcome.',
      rule: 'The stopping condition is verified delivery.',
      explain: 'One more check: recover an earlier failed message using its original identity, without creating a second copy.',
      action: null
    }
  ];
  let current = 0;
  let retries = 0;
  const stepList = $('steps');
  labels.forEach((label, index) => {
    const li = document.createElement('li');
    const number = document.createElement('span');
    number.className = 'step-number';
    number.setAttribute('aria-hidden', 'true');
    number.textContent = String(index + 1);
    li.append(number, document.createTextNode(label));
    stepList.append(li);
  });

  function render(announce = true) {
    const scene = scenes[current];
    $('scene-kicker').textContent = scene.kicker;
    $('scene-title').textContent = scene.title;
    $('delivery-count').replaceChildren(document.createTextNode(String(scene.delivered)));
    const denominator = document.createElement('span');
    denominator.textContent = '/24';
    $('delivery-count').append(denominator);
    $('cloud-count').textContent = scene.cloud;
    $('app-note').textContent = scene.app;
    $('finding-review').hidden = current !== 1;
    $('finding-review-text').textContent = approvedFinding;
    $('cloud-note').textContent = scene.provider;
    const author = document.createElement('strong');
    author.textContent = scene.sharedAuthor;
    const text = document.createElement('span');
    text.textContent = scene.shared;
    if (scene.finding) text.className = 'finding';
    $('shared-message').replaceChildren(author, text);
    $('shared-rule').textContent = scene.rule;
    $('scene-explanation').textContent = scene.explain;
    $('advance').hidden = !scene.action;
    if (scene.action) $('advance').textContent = scene.action;
    $('retry').hidden = current !== scenes.length - 1;
    $('retry').textContent = retries ? 'Repeat the same request' : 'Retry original message';
    $('previous').disabled = current === 0;
    $('retry-result').hidden = !retries || current !== scenes.length - 1;
    $('retry-result').textContent = retries > 1
      ? 'Repeated request recognized. Still exactly one delivered copy.'
      : 'Original message recovered. Same identity and text. One delivered copy.';
    [...stepList.children].forEach((step, index) => {
      step.classList.toggle('is-complete', index < current);
      if (index === current) step.setAttribute('aria-current', 'step');
      else step.removeAttribute('aria-current');
    });
    const grid = $('workspace-grid');
    grid.classList.remove('is-changing');
    void grid.offsetWidth;
    grid.classList.add('is-changing');
    if (announce) $('announcement').textContent = `${scene.kicker}. ${scene.title} ${scene.delivered} of 24 messages delivered. ${scene.explain}`;
  }

  function revealMobileScene() {
    if (!window.matchMedia('(max-width: 760px)').matches) return;
    document.querySelector('.scene-header').scrollIntoView({
      block: 'start',
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'
    });
  }

  $('advance').addEventListener('click', () => {
    if (current < scenes.length - 1) { current += 1; render(); }
    if (current === scenes.length - 1) $('retry').focus({preventScroll: true});
    revealMobileScene();
  });
  $('previous').addEventListener('click', () => {
    if (current > 0) { current -= 1; render(); }
    if (current === 0) $('advance').focus({preventScroll: true});
    revealMobileScene();
  });
  $('restart').addEventListener('click', () => { current = 0; retries = 0; render(); $('advance').focus({preventScroll: true}); revealMobileScene(); });
  $('retry').addEventListener('click', () => { retries += 1; render(false); $('announcement').textContent = $('retry-result').textContent; });
  $('incident').hidden = false;
  render(false);

  const themeButton = $('theme-control');
  const systemTheme = () => window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  let savedTheme = null;
  try { savedTheme = localStorage.getItem('relay-theme'); } catch { /* Browser storage can be disabled. */ }
  if (savedTheme === 'dark' || savedTheme === 'light') document.documentElement.dataset.theme = savedTheme;
  function updateThemeLabel() {
    const active = document.documentElement.dataset.theme || systemTheme();
    themeButton.textContent = active === 'dark' ? 'Light' : 'Dark';
    themeButton.setAttribute('aria-label', `Use ${active === 'dark' ? 'light' : 'dark'} color theme`);
  }
  themeButton.addEventListener('click', () => {
    const next = (document.documentElement.dataset.theme || systemTheme()) === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('relay-theme', next); } catch { /* Theme still works without storage. */ }
    updateThemeLabel();
  });
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', updateThemeLabel);
  updateThemeLabel();
})();
