// This view renders the running services. It never scripts an agent conversation.
const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const roles = {teamchat:{owner:'Maya',label:'TeamChat'},harborcloud:{owner:'Leo',label:'HarborCloud'}};
const ui = {engine:null,coordination:null,engineError:'',coordinationError:'',role:'teamchat',busy:new Set(),localMessages:new Map(),review:null,lastRender:new Map(),polling:false,draftInitialized:false};
const terminal = new Set(['released','executed','rejected','expired','failed']);
let toastTimer;

function timestamp(value) {
  if (!value) return '';
  const date = new Date(typeof value === 'number' && value < 1e11 ? value * 1000 : value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});
}
function iso(value) {
  const date = new Date(typeof value === 'number' && value < 1e11 ? value * 1000 : value);
  return Number.isNaN(date.getTime()) ? '' : date.toISOString();
}
function expired(proposal) {
  return Boolean(proposal.expiresAt) && new Date(iso(proposal.expiresAt)).getTime() <= Date.now();
}
function ownLabel(role) { return roles[role]?.label || 'Company'; }
function pending(proposal) { return proposal.status === 'pending' && !expired(proposal); }
function proposals() { return ui.coordination?.proposals || []; }
function plainContent(content) {
  if (typeof content === 'string') return content;
  if (!content || typeof content !== 'object') return '';
  return ['summary','finding','message','reason'].map(key => content[key]).filter(value => typeof value === 'string').join('\n\n');
}
function contentOf(proposal) { return proposal.body?.content || proposal.content || {}; }
function operationOf(proposal) { return proposal.engineProposal || contentOf(proposal).operation || {}; }
function proposalTitle(proposal) {
  const operation = operationOf(proposal);
  if (operation.operation === 'increase_gateway_capacity') return 'Repair the cloud connection';
  if (operation.operation === 'reconcile_failed_allocations') return 'Restore TeamChat’s chat capacity';
  return proposal.title || (proposal.kind === 'disclosure' ? 'Share an incident finding' : 'Review a proposed change');
}
function consequence(proposal) {
  const operation = operationOf(proposal);
  if (operation.operation === 'increase_gateway_capacity') return `Increase this cloud connection to ${operation.target?.capacity ?? 'the proposed number of'} simultaneous requests. TeamChat’s chat service is unchanged by this action.`;
  if (operation.operation === 'reconcile_failed_allocations') return `Clear ${operation.target?.allocationIds?.length ?? 'the listed'} failed starts and restart chat capacity, one start at a time. Working chat capacity is preserved.`;
  return proposal.kind === 'disclosure' ? `Share exactly the finding below with ${proposal.role === 'teamchat' ? 'HarborCloud' : 'TeamChat'} through Switch.` : (operation.summary || proposal.title || 'Apply the specific change below.');
}
function replace(selector, markup, scroll = false) {
  const element = $(selector);
  if (!element || ui.lastRender.get(selector) === markup) return;
  const nearBottom = element.scrollHeight - element.scrollTop - element.clientHeight < 65;
  const oldScroll = element.scrollTop;
  element.innerHTML = markup;
  ui.lastRender.set(selector,markup);
  if (scroll) element.scrollTop = nearBottom ? element.scrollHeight : oldScroll;
}
async function request(path, body, timeout = 12000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(path, {method:body === undefined ? 'GET' : 'POST',headers:body === undefined ? {} : {'Content-Type':'application/json'},body:body === undefined ? undefined : JSON.stringify(body),signal:controller.signal,cache:'no-store'});
    const value = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(value.error || `The service returned HTTP ${response.status}.`);
      error.result = value;
      throw error;
    }
    return value;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('The service did not respond in time. Check the live state before trying again.');
    throw error;
  } finally { clearTimeout(timer); }
}
function toast(message, error = false) {
  const element = $('#toast');
  clearTimeout(toastTimer);
  element.textContent = message;
  element.classList.toggle('error',error);
  element.hidden = false;
  toastTimer = setTimeout(() => { element.hidden = true; }, 6500);
}
function notice(message) {
  $('#global-notice').textContent = message;
  $('#global-notice').hidden = !message;
}
async function poll() {
  if (ui.polling) return;
  ui.polling = true;
  try {
    const results = await Promise.allSettled([request('/api/state',undefined,6000),request('/api/coordination',undefined,6000)]);
    for (const [index,result] of results.entries()) {
      const name = index ? 'coordination' : 'engine';
      if (result.status === 'fulfilled') { ui[name] = result.value; ui[`${name}Error`] = ''; }
      else ui[`${name}Error`] = result.reason?.message || 'The service is unavailable.';
    }
    render();
  } finally { ui.polling = false; }
}
function renderConnection() {
  const engineOnline = Boolean(ui.engine) && !ui.engineError;
  const coordinationOnline = Boolean(ui.coordination) && !ui.coordinationError;
  const element = $('#connection');
  element.className = `connection ${engineOnline && coordinationOnline ? 'connected' : 'error'}`;
  replace('#connection',`<span class="status-dot"></span><span>${engineOnline && coordinationOnline ? 'App and Switch connected' : engineOnline ? 'App connected · Switch offline' : ui.engineError ? 'App unavailable' : 'Connecting to the demo'}</span>`);
  const label = $('#switch-label');
  label.className = `live-label ${coordinationOnline ? 'connected' : ''}`;
  replace('#switch-label',`<span class="status-dot"></span>${coordinationOnline ? 'Live' : 'Offline'}`);
  if (ui.engineError) notice(`The app is unavailable. ${ui.engine ? 'The last received state is shown. ' : ''}${ui.engineError}`);
  else if (ui.coordinationError) notice(`The chat app is connected. Agent coordination is unavailable: ${ui.coordinationError}`);
  else if (ui.coordination?.status === 'error') notice('An agent stopped with an error. No approval is automatic. Review the actual events in Show evidence.');
  else if (ui.coordination?.mode && ui.coordination.mode !== 'manual') notice('This run is in automated test mode. Human review is not being demonstrated.');
  else notice('');
}
function renderSummary() {
  const state = ui.engine;
  if (!state) return;
  const cloudApplied = (state.proposals || []).some(p => p.operation === 'increase_gateway_capacity' && p.status === 'applied');
  const healthy = state.health?.status === 'healthy' && state.health?.fresh === true;
  const degraded = state.health?.status === 'degraded';
  const incident = state.scenario?.phase === 'incident';
  const recovered = healthy && state.scenario?.phase === 'recovered';
  const heading = $('#case-status');
  const cloudVerified = state.cloud?.gatewayCanary?.status === 'healthy' && state.cloud.gatewayCanary.cloudRevision === state.cloud.revision;
  const text = recovered ? 'Chat delivery verified' : cloudApplied && !healthy ? `${cloudVerified ? 'Cloud repaired' : 'Cloud capacity changed'} · chat still needs recovery` : degraded || incident ? 'The busy-morning check failed' : state.burst?.running ? 'Testing a busy morning' : 'Ready for a busy morning';
  heading.className = `case-status ${recovered ? 'good' : degraded || incident || cloudApplied && !healthy ? 'warning' : ''}`;
  heading.innerHTML = `<span class="status-dot"></span>${esc(text)}`;
  const chat = $('#chat-health');
  chat.textContent = recovered ? 'Delivery verified' : state.app?.status === 'no_capacity' ? 'Needs recovery' : degraded || incident ? 'Disrupted' : 'Ready';
  chat.className = `small-badge ${recovered ? 'good' : degraded || incident || state.app?.status === 'no_capacity' ? 'warning' : ''}`;
  const failedStarts = state.app?.failedAllocations ?? 0;
  const cloudText = cloudApplied ? cloudVerified ? 'The provider’s connection check passed' : 'Owner-approved capacity increase applied' : state.cloud?.rejected > 0 ? 'Requests were refused during the busy morning' : 'The provider owns this connection';
  const cloudStatus = cloudApplied ? cloudVerified ? 'Repaired' : 'Capacity changed' : incident || degraded ? 'Investigate' : 'Ready';
  const appText = healthy ? `Latest check: ${state.health.delivered}/${state.health.attempted} messages arrived` : state.app?.status === 'no_capacity' ? `${failedStarts} failed starts are holding chat capacity` : state.app?.status === 'serving' ? 'The chat service has its planned capacity' : `The chat service has reduced capacity${failedStarts ? ` · ${failedStarts} failed starts` : ''}`;
  replace('#service-summary',`<div class="service-row"><span class="service-icon" aria-hidden="true">↔</span><div><strong>Cloud connection</strong><p>${esc(cloudText)}</p></div><span class="service-state ${cloudVerified ? 'good' : incident || degraded ? 'warning' : 'neutral'}">${esc(cloudStatus)}</span></div><div class="service-row"><span class="service-icon" aria-hidden="true">▦</span><div><strong>${cloudApplied && !healthy ? 'Chat still needs recovery' : 'Chat capacity'}</strong><p>${esc(appText)}</p></div><span class="service-state ${healthy ? 'good' : state.app?.status === 'no_capacity' || degraded ? 'warning' : 'neutral'}">${healthy ? 'Verified' : state.app?.status === 'no_capacity' ? 'Blocked' : 'Measured separately'}</span></div>`);
  const impact = state.impact || {};
  replace('#impact-summary',impact.attempted ? `<span><strong>${esc(impact.delivered)}</strong> delivered</span><span class="${impact.failed ? 'failed-text' : ''}"><strong>${esc(impact.failed)}</strong> failed attempts</span>${impact.pending ? `<span><strong>${esc(impact.pending)}</strong> pending</span>` : ''}` : '<span class="muted">Delivery results appear after a real attempt.</span>');
  $('#load-activity').hidden = !state.burst?.running;
  const note = $('#director-note');
  const humanMessages = (state.messages || []).filter(message => message.author !== 'Load test');
  const failedHuman = humanMessages.some(message => message.status === 'failed');
  const allHumanDelivered = humanMessages.length > 0 && humanMessages.every(message => message.status === 'delivered');
  const recoveredNote = failedHuman ? 'Now retry the original failed message. Your message must arrive, too.' : allHumanDelivered ? 'Your message already arrived. You can retry an actual failed test message below.' : humanMessages.length ? 'Check your message’s actual delivery status below.' : 'Delivery is verified. You can retry an actual failed test message below.';
  note.textContent = state.burst?.running ? 'Your message is part of a real busy-morning check. Delivery below comes from the chat database.' : recovered ? recoveredNote : cloudApplied && !healthy ? 'The cloud owner has acted. TeamChat’s owner still needs to restore the chat service.' : incident || degraded ? 'Last busy-morning check failed. Ask the agents; each company investigates its own side.' : 'Start a busy morning with your draft message and 23 other real requests.';
}
function renderMessages() {
  const returned = ui.engine?.messages || [];
  if (ui.engine && !ui.draftInitialized) {
    const input = $('#message-input');
    if (returned.some(message => message.author !== 'Load test') && input.value === 'Can anyone see this?' && document.activeElement !== input) input.value = '';
    ui.draftInitialized = true;
  }
  const merged = new Map(returned.map(message => [message.id,message]));
  for (const [id,message] of ui.localMessages) {
    if (merged.has(id)) ui.localMessages.delete(id);
    else merged.set(id,message);
  }
  const all = [...merged.values()].sort((a,b) => String(a.createdAt).localeCompare(String(b.createdAt)));
  const load = all.filter(message => message.author === 'Load test');
  const manual = all.filter(message => message.author !== 'Load test');
  if (!all.length) {
    replace('#chat-messages','<div class="empty-state"><span class="empty-icon" aria-hidden="true">↗</span><h3>A message should simply arrive.</h3><p>Send one below. Its delivery status comes from the running chat app.</p></div>',true);
    return;
  }
  function markup(message) {
    const status = ['pending','delivered','failed','unconfirmed'].includes(message.status) ? message.status : 'pending';
    const symbol = status === 'delivered' ? '✓' : status === 'failed' ? '!' : '◷';
    const label = status === 'delivered' ? 'Delivered' : status === 'failed' ? 'Not delivered' : status === 'unconfirmed' ? 'Delivery unconfirmed' : 'Sending…';
    const isLoad = message.author === 'Load test';
    return `<article class="message ${isLoad ? 'load-message' : ''}" data-message-id="${esc(message.id)}"><span class="message-avatar" aria-hidden="true">${isLoad ? '↗' : esc((message.author || 'Y')[0])}</span><div class="message-copy"><div class="message-meta"><strong>${esc(isLoad ? 'Demo traffic' : message.author || 'You')}</strong><time class="message-time" datetime="${esc(iso(message.createdAt))}">${esc(timestamp(message.createdAt))}</time></div><p class="message-text">${esc(message.text)}</p><div class="message-state ${status}"${message.error ? ` title="${esc(message.error)}"` : ''}><span aria-hidden="true">${symbol}</span>${label}${status === 'failed' || status === 'unconfirmed' ? `<button type="button" class="retry-message" data-retry="${esc(message.id)}"${ui.busy.has(`send:${message.id}`) ? ' disabled' : ''}>${isLoad ? 'Retry test message' : 'Retry message'}</button>` : ''}</div></div></article>`;
  }
  // Load traffic is an actual measurement, kept compact so the original message remains visible.
  const recentLoad = load.slice(-3);
  const failedLoad = load.findLast(message => message.status === 'failed');
  if (failedLoad && !recentLoad.some(message => message.id === failedLoad.id)) recentLoad.unshift(failedLoad);
  const loadMarkup = load.length ? `<div class="load-group">Recent demo traffic · ${load.length} messages</div>${recentLoad.map(markup).join('')}` : '';
  replace('#chat-messages',`${manual.map(markup).join('')}${loadMarkup}`,false);
}
function renderFeed() {
  const messages = ui.coordination?.messages || [];
  if (!messages.length) {
    const started = (ui.coordination?.investigations || []).length > 0;
    replace('#incident-feed',`<div class="feed-empty"><span class="empty-icon" aria-hidden="true">↔</span><h3>${started ? 'Waiting for an approved finding.' : 'Bring the right people together.'}</h3><p>${started ? 'The company agents investigate privately. Their owners review what can be shared here.' : 'Ask the agents to investigate. Only findings approved for sharing appear here.'}</p><div class="ownership-note"><span>Maya · TeamChat</span><span aria-hidden="true">↔</span><span>Leo · HarborCloud</span></div></div>`,true);
    return;
  }
  replace('#incident-feed',messages.map(message => {
    const text = plainContent(message.content) || 'An approved incident message was received. Open Show evidence for its exact content.';
    const kind = {question:'Question',evidence:'Finding',verification:'Verification',repair_proposal:'Approved change'}[message.kind] || 'Incident message';
    return `<article class="feed-message"><span class="feed-avatar ${message.role === 'harborcloud' ? 'cloud' : ''}" aria-hidden="true">${message.role === 'harborcloud' ? 'H' : 'T'}</span><div class="feed-copy"><div class="feed-meta"><strong>${esc(ownLabel(message.role))} agent</strong><time datetime="${esc(iso(message.at))}">${esc(timestamp(message.at))}</time></div><div class="feed-kind">${esc(kind)}</div><div class="feed-body">${esc(text)}</div>${message.kind === 'repair_proposal' ? '<div class="feed-operation-note">This message carries the approved plan. Execution and delivery are verified separately.</div>' : ''}${message.receipt ? '<div class="feed-receipt"><span aria-hidden="true">✓</span> Shared through Switch · owner reviewed</div>' : ''}</div></article>`;
  }).join(''),true);
}
function renderOwner() {
  const role = ui.role;
  const own = roles[role];
  document.querySelectorAll('[data-role]').forEach(button => {
    const selected = button.dataset.role === role;
    button.setAttribute('aria-selected',String(selected));
    button.tabIndex = selected ? 0 : -1;
    const count = proposals().filter(p => p.role === button.dataset.role && pending(p)).length;
    const badge = $(`#count-${button.dataset.role}`);
    badge.textContent = count;
    badge.hidden = !count;
    button.setAttribute('aria-label',`${roles[button.dataset.role].owner}, ${ownLabel(button.dataset.role)}${count ? `, ${count} decision${count === 1 ? '' : 's'} waiting` : ''}`);
  });
  $('#owner-desk').setAttribute('aria-labelledby',`tab-${role}`);
  $('.roleplay-note').textContent = `You are playing ${own.owner}, the fictional ${own.label} owner.`;
  const agent = ui.coordination?.agents?.find(item => item.role === role);
  const labels = {thinking:'Investigating your company’s side…',awaiting_approval:'Your decision is needed.',idle:'No investigation started yet.',waiting:'Waiting for the next finding.',complete:'Investigation complete.',budget_complete:'Agent decision limit reached.',error:'The agent stopped with an error.'};
  const agentStatus = labels[agent?.status] || 'Waiting for the company agent.';
  replace('#agent-status',`<span class="${agent?.status === 'thinking' ? 'spinner' : 'agent-symbol'}" aria-hidden="true">${agent?.status === 'thinking' ? '' : '✧'}</span><div><strong>${esc(own.label)}’s agent</strong><p>${esc(agentStatus)}</p>${agent?.lastSummary && !proposals().some(p => p.role === role && pending(p)) ? `<details class="agent-finding"><summary>Private finding</summary><p>${esc(agent.lastSummary)}</p></details>` : ''}</div>`);
  const ownProposals = proposals().filter(p => p.role === role);
  const waiting = ownProposals.filter(p => ['pending','approving'].includes(p.status));
  const history = ownProposals.filter(p => terminal.has(p.status)).slice(-4).reverse();
  let html = waiting.map(p => {
    const ready = pending(p) && !ui.busy.has(`review:${p.id}`) && !ui.coordinationError;
    const title = proposalTitle(p);
    const summary = plainContent(contentOf(p));
    const action = p.kind === 'disclosure' ? 'Review what to share' : 'Review this change';
    return `<article class="proposal"><div class="proposal-top"><p class="proposal-kind"><span aria-hidden="true">${p.kind === 'disclosure' ? '↗' : '↻'}</span>${p.kind === 'disclosure' ? 'Sharing permission' : 'Change permission'}</p><h3>${esc(title)}</h3><p class="proposal-copy">${esc(consequence(p))}</p></div>${summary ? `<div class="proposal-preview">${esc(summary)}</div>` : ''}<div class="proposal-actions"><button type="button" class="button button-primary" data-review="${esc(p.id)}"${ready ? '' : ' disabled'}>${p.status === 'approving' ? 'Verifying approval…' : expired(p) ? 'Review expired' : action}</button><button type="button" class="button" data-reject="${esc(p.id)}"${ready ? '' : ' disabled'}>Reject</button></div><div class="proposal-meta">${esc(own.owner)}’s approval only · ${p.kind === 'disclosure' ? 'exact finding' : 'exact change'} · expires ${esc(timestamp(p.expiresAt))}</div></article>`;
  }).join('');
  if (!waiting.length) {
    const other = proposals().find(p => p.role !== role && pending(p));
    html = `<div class="owner-empty"><span class="review-icon" aria-hidden="true">✓</span><h3>No decision waiting for ${esc(own.owner)}.</h3><p>${other ? `${roles[other.role].owner} has a decision waiting. Open the ${ownLabel(other.role)} desk to review it as that fictional owner.` : 'Your agent will bring you a specific finding to share or a change to approve.'}</p>${other ? `<button type="button" class="button switch-owner" data-open-role="${esc(other.role)}">Open ${esc(roles[other.role].owner)}’s desk →</button>` : ''}</div>`;
  }
  html += history.map(p => `<div class="proposal-history ${esc(p.status)}"><span class="history-mark" aria-hidden="true">${p.status === 'released' || p.status === 'executed' ? '✓' : '!'}</span><span><strong>${esc({released:'Shared',executed:'Change applied',rejected:'Rejected',expired:'Expired',failed:'Failed'}[p.status])}</strong> · ${esc(proposalTitle(p))}${p.receipt ? '<small>Owner approval verified through Switch</small>' : ''}</span></div>`).join('');
  replace('#owner-proposals',html);
}
function renderControls() {
  const engineOnline = Boolean(ui.engine) && !ui.engineError;
  const thinking = ui.coordination?.agents?.some(a => a.status === 'thinking');
  const activeReviews = proposals().some(p => pending(p) || p.status === 'approving');
  $('#start-burst').disabled = !engineOnline || ui.busy.has('burst') || Boolean(ui.engine?.burst?.running) || ui.busy.has('reset');
  $('#start-burst').innerHTML = ui.engine?.burst?.running ? '<span class="spinner" aria-hidden="true"></span> Busy morning running' : `<span aria-hidden="true">↗</span> ${ui.engine?.scenario?.phase === 'recovered' ? 'Test busy morning again' : 'Start busy morning'}`;
  $('#investigate').disabled = !engineOnline || !ui.coordination || Boolean(ui.coordinationError) || Boolean(thinking) || activeReviews || ui.busy.has('investigate') || ui.busy.has('reset');
  $('#investigate').innerHTML = thinking ? '<span class="spinner" aria-hidden="true"></span> Agents investigating' : activeReviews ? '<span class="agent-symbol" aria-hidden="true">✧</span> Owner review needed' : '<span class="agent-symbol" aria-hidden="true">✧</span> Ask the agents';
  const sending = [...ui.busy].some(key => key === 'new-message' || key.startsWith('send:'));
  $('#reset-demo').disabled = !engineOnline || ui.busy.has('reset') || sending || Boolean(ui.engine?.burst?.running) || Boolean(thinking) || proposals().some(p => p.status === 'approving');
  $('#message-input').disabled = !engineOnline || ui.busy.has('reset');
  $('.send-button').disabled = !engineOnline || ui.busy.has('new-message') || ui.busy.has('reset');
}
function renderEvidence() {
  if (!$('#evidence-drawer').open || !ui.engine) return;
  const state = ui.engine;
  const health = state.health || {};
  const metric = (value,label) => `<div class="evidence-metric"><strong>${esc(value ?? '—')}</strong><span>${esc(label)}</span></div>`;
  const verified = proposals().filter(p => p.receipt);
  const events = [...(ui.coordination?.events || [])].slice(-12).reverse();
  replace('#evidence-content',`<div class="evidence-metrics">${metric(health.attempted ? `${health.delivered}/${health.attempted}` : '—','Latest measured check · delivered')}${metric(health.p95LatencyMs != null ? `${health.p95LatencyMs} ms` : '—','Latest check · p95 HTTP latency')}${metric(state.app?.readyWorkers,'Ready chat workers')}${metric(verified.length,'Owner approvals with Switch receipts')}</div><div class="evidence-columns"><section><h3>Actual service state</h3><p>Cloud configuration and chat readiness are separate from end-to-end delivery. A change clears the previous green health result.</p><pre>${esc(JSON.stringify({health:state.health,app:state.app,cloud:state.cloud,burst:state.burst},null,2))}</pre></section><section><h3>Approval receipts</h3>${verified.length ? `<ul class="evidence-list">${verified.slice(-6).reverse().map(p => `<li><strong>${esc(ownLabel(p.role))} · ${esc(p.status)}</strong><br>${esc(proposalTitle(p))}<details><summary>Exact approved content and receipt</summary><pre>${esc(JSON.stringify({body:p.body,expectedRevision:p.expectedRevision,receipt:p.receipt,result:p.result},null,2))}</pre></details></li>`).join('')}</ul>` : '<p>No approved Switch receipt has been returned.</p>'}</section><section><h3>Agent activity</h3>${events.length ? `<ul class="evidence-list">${events.map(e => `<li><time>${esc(timestamp(e.at))}</time> · ${esc(ownLabel(e.role))}<br>${esc(e.detail)}</li>`).join('')}</ul>` : '<p>No coordination activity yet.</p>'}</section><section><h3>Real source, bounded adaptation</h3><p>Inspired by Slack’s January 4, 2021 outage: Slack and its cloud provider each had work to do. These companies, local capacity model and approvals are a fictional demonstration.</p><p><a href="https://slack.engineering/slacks-outage-on-january-4th-2021/" target="_blank" rel="noopener noreferrer">Read Slack’s engineering account ↗</a></p><p>This demo shows separate ownership and reviewed coordination. It does not establish that two agents outperform a single agent with equivalent access.</p></section></div>`);
}
function render() { renderConnection();renderSummary();renderMessages();renderFeed();renderOwner();renderControls();renderEvidence(); }
function selectRole(role, focus = false) {
  if (!roles[role]) return;
  ui.role = role;
  renderOwner();
  if (focus) $(`#tab-${role}`).focus();
}
function closeReview() {
  if (ui.busy.has('confirm-review')) return;
  $('#review-dialog').close();ui.review = null;
}
function openReview(id,reject = false) {
  const proposal = proposals().find(p => p.id === id);
  if (!proposal || proposal.role !== ui.role || !pending(proposal)) return toast('This decision is no longer available. Wait for a fresh review.',true);
  ui.review = {id,role:ui.role,digest:proposal.digest,reject};
  const own = roles[ui.role];
  const summary = plainContent(contentOf(proposal));
  const action = reject ? 'Reject this proposal' : proposal.kind === 'disclosure' ? 'Approve sharing' : proposal.role === 'harborcloud' ? 'Approve cloud repair' : 'Approve chat recovery';
  $('#review-content').innerHTML = `<p class="eyebrow">${reject ? 'REJECT PROPOSAL' : 'OWNER APPROVAL'}</p><h2 id="review-title">${esc(proposalTitle(proposal))}</h2><p class="dialog-role">You are playing ${esc(own.owner)}, the fictional ${esc(own.label)} owner.</p><p>${esc(reject ? 'This proposal will be rejected. Nothing in this proposal will be released or applied.' : consequence(proposal))}</p>${summary ? `<div class="review-preview">${esc(summary)}</div>` : ''}${!reject && proposal.kind === 'operation' ? '<p>The exact approved plan is shared through Switch before the owner’s change is applied. A real delivery check follows the change.</p>' : ''}<details class="review-binding"><summary>Exact approval details</summary><pre class="dialog-digest">${esc(JSON.stringify({owner:own.owner,company:own.label,expectedRevision:proposal.expectedRevision,digest:proposal.digest,expiresAt:proposal.expiresAt,content:proposal.body},null,2))}</pre></details><div id="review-error" role="alert" class="review-error" hidden></div><div class="dialog-actions"><button type="button" class="button" data-cancel-review>Cancel</button><button type="button" class="button ${reject ? 'button-danger' : 'button-primary'}" id="confirm-review">${esc(action)}</button></div>`;
  $('#review-dialog').showModal();
}
async function confirmReview() {
  if (!ui.review || ui.busy.has('confirm-review')) return;
  const review = {...ui.review};
  const fresh = proposals().find(p => p.id === review.id);
  if (!fresh || fresh.role !== review.role || fresh.digest !== review.digest || !pending(fresh)) return toast('The proposal changed or expired. Close this review and request current evidence.',true);
  ui.busy.add('confirm-review');ui.busy.add(`review:${review.id}`);
  $('#confirm-review').disabled = true;
  $('#confirm-review').textContent = review.reject ? 'Rejecting…' : 'Verifying through Switch…';
  $('#review-content [data-cancel-review]').disabled = true;
  try {
    await request(`/api/coordination/${review.reject ? 'reject' : 'approve'}`,{proposalId:review.id,role:review.role},125000);
    ui.busy.delete('confirm-review');
    closeReview();
    toast(review.reject ? 'Proposal rejected.' : 'Approval returned. The live result is shown in your company’s desk.');
  } catch (error) {
    $('#review-error').textContent = error.message;
    $('#review-error').hidden = false;
    $('#confirm-review').textContent = 'Check current state';
    // An ambiguous transport failure must never silently retry an owner action.
    $('#confirm-review').disabled = true;
    $('#review-content [data-cancel-review]').disabled = false;
    ui.busy.delete('confirm-review');
  } finally { ui.busy.delete(`review:${review.id}`);await poll(); }
}
async function sendMessage(message, retry = false) {
  const key = `send:${message.id}`;
  if (ui.busy.has(key)) return;
  ui.busy.add(key);if (!retry) ui.busy.add('new-message');
  ui.localMessages.set(message.id,{...message,status:'pending',error:null});
  renderMessages();renderControls();
  try {
    const response = await request('/api/messages',{id:message.id,text:message.text,author:message.author},15000);
    ui.localMessages.set(message.id,{...message,status:response.ok ? 'delivered' : 'failed',latencyMs:response.latencyMs,error:response.error});
    if (!retry) $('#message-input').value = '';
  } catch (error) {
    ui.localMessages.set(message.id,{...message,status:error.result?.ok === false ? 'failed' : 'unconfirmed',error:error.message});
    toast(`${error.message} Your original message can be retried with the same ID.`,true);
    if (!retry) $('#message-input').value = '';
  } finally { ui.busy.delete(key);ui.busy.delete('new-message');await poll(); }
}
async function startBurst() {
  if (ui.busy.has('burst')) return;
  ui.busy.add('burst');renderControls();
  try {
    const text = $('#message-input').value.trim() || 'Can anyone see this?';
    const message = {id:crypto.randomUUID(),text,author:'You'};
    await request('/api/demo/burst',{message});
    $('#message-input').value = '';
  }
  catch (error) { toast(error.message,true); }
  finally { ui.busy.delete('burst');await poll(); }
}
async function investigate() {
  ui.busy.add('investigate');renderControls();
  try { await request('/api/coordination/investigate',{},20000); }
  catch (error) { toast(error.message,true); }
  finally { ui.busy.delete('investigate');await poll(); }
}
function openReset() {
  const offline = Boolean(ui.coordinationError);
  ui.review = {reset:true,allowOfflineReset:offline};
  $('#review-content').innerHTML = `<p class="eyebrow">START OVER</p><h2 id="review-title">Reset this demonstration?</h2><p>${offline ? 'Switch is offline. This resets only the local chat messages and capacity changes. Agent reviews are not cleared; start a fresh investigation when Switch returns.' : 'This clears the local messages, capacity changes and current agent decisions. The live Switch audit history remains.'}</p><div class="dialog-actions"><button type="button" class="button" data-cancel-review>Keep this run</button><button type="button" class="button button-primary" id="confirm-reset">${offline ? 'Reset local demo' : 'Reset demo'}</button></div>`;
  $('#review-dialog').showModal();
}
async function resetDemo() {
  if (ui.busy.has('reset')) return;
  const offlineResetConfirmed = ui.review?.allowOfflineReset === true;
  ui.busy.add('reset');$('#confirm-reset').disabled = true;renderControls();
  try {
    // Coordination invalidates outstanding proposals before the local service resets.
    if (!ui.coordinationError || !offlineResetConfirmed) await request('/api/coordination/reset',{},20000);
    await request('/api/demo/reset',{},20000);
    ui.localMessages.clear();ui.lastRender.clear();ui.engine = null;ui.coordination = null;
    $('#message-input').value = 'Can anyone see this?';
    closeReview();toast('A fresh demonstration is ready.');
  } catch (error) { closeReview();toast(`Reset did not complete: ${error.message}`,true); }
  finally { ui.busy.delete('reset');await poll(); }
}

$('#message-form').addEventListener('submit',event => {
  event.preventDefault();
  const text = $('#message-input').value.trim();
  if (!text || ui.busy.has('new-message')) return;
  sendMessage({id:crypto.randomUUID(),text,author:'You',createdAt:new Date().toISOString()});
});
$('#chat-messages').addEventListener('click',event => {
  const button = event.target.closest('[data-retry]');
  if (!button) return;
  const id = button.dataset.retry;
  const message = ui.localMessages.get(id) || ui.engine?.messages?.find(item => item.id === id);
  if (message) sendMessage(message,true);
});
$('#start-burst').addEventListener('click',startBurst);
$('#investigate').addEventListener('click',investigate);
$('#reset-demo').addEventListener('click',openReset);
document.querySelectorAll('[data-role]').forEach(button => {
  button.addEventListener('click',() => selectRole(button.dataset.role));
  button.addEventListener('keydown',event => {
    if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
    event.preventDefault();
    selectRole(event.key === 'Home' ? 'teamchat' : event.key === 'End' ? 'harborcloud' : ui.role === 'teamchat' ? 'harborcloud' : 'teamchat',true);
  });
});
$('#owner-proposals').addEventListener('click',event => {
  const button = event.target.closest('button');
  if (!button) return;
  if (button.dataset.review) openReview(button.dataset.review);
  if (button.dataset.reject) openReview(button.dataset.reject,true);
  if (button.dataset.openRole) selectRole(button.dataset.openRole,true);
});
$('#review-dialog').addEventListener('click',event => {
  if (event.target.closest('[data-cancel-review]')) closeReview();
  if (event.target.closest('#confirm-review')) confirmReview();
  if (event.target.closest('#confirm-reset')) resetDemo();
});
$('#review-dialog').addEventListener('cancel',event => {
  if (ui.busy.has('confirm-review') || ui.busy.has('reset')) event.preventDefault();
  else ui.review = null;
});
$('#evidence-drawer').addEventListener('toggle',renderEvidence);
poll();
setInterval(poll,750);
