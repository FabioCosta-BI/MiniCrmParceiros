let config = null;
let currentGroups = [];
let currentTask = null;
let activeReason = 'Todos';

const el = (id) => document.getElementById(id);
const escapeHtml = (text) => String(text || '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

async function getConfig() {
  config = await fetch('/api/config').then(r => r.json());
  el('portfolio-date').textContent = formatPortfolioDate(config.data_carteira);
  renderStates();
}

function formatPortfolioDate(value) {
  const [year, month, day] = String(value || '').split('-');
  const months = ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ'];
  return year && month && day ? `${day} ${months[Number(month) - 1]} ${year}` : 'Sem carteira';
}

function renderStates() {
  const grupos = Object.entries(config.grupos_uf);
  el('state-options').innerHTML = grupos.map(([nome, ufs]) => `<button class="${currentGroups.includes(nome) ? 'selected' : ''}" data-group="${escapeHtml(nome)}"><strong>${escapeHtml(nome)}</strong><span>${ufs.length} UFs</span></button>`).join('');
  const allSelected = currentGroups.length === grupos.length;
  const ufsSelecionadas = currentGroups.flatMap(nome => config.grupos_uf[nome]);
  el('select-all-states').textContent = allSelected ? 'Limpar seleção' : 'Selecionar todos';
  el('selected-states-count').textContent = currentGroups.length === 0
    ? 'Nenhum grupo selecionado'
    : `${currentGroups.length} ${currentGroups.length === 1 ? 'grupo' : 'grupos'} · ${ufsSelecionadas.length} UFs`;
  document.querySelectorAll('[data-group]').forEach(button => button.onclick = () => {
    const grupo = button.dataset.group;
    currentGroups = currentGroups.includes(grupo) ? currentGroups.filter(item => item !== grupo) : [...currentGroups, grupo];
    el('start-work').disabled = currentGroups.length === 0;
    renderStates();
  });
}

async function beginWork() {
  el('start').hidden = true; el('workspace').hidden = false;
  const ufsSelecionadas = currentGroups.flatMap(nome => config.grupos_uf[nome]);
  el('consultant-name').textContent = currentGroups.join(' · ');
  el('states').textContent = `${ufsSelecionadas.length} UFs: ${ufsSelecionadas.join(' · ')}`;
  await loadTasks();
}

async function loadTasks() {
  const ufsSelecionadas = currentGroups.flatMap(nome => config.grupos_uf[nome]);
  const response = await fetch(`/api/carteira?ufs=${encodeURIComponent(ufsSelecionadas.join(','))}`);
  const data = await response.json();
  const tasks = data.tarefas || [];
  const reasons = ['Todos', 'Parceiro em destaque de vendas', 'Cidade estratégica', 'Aniversário da cidade', 'Aniversário do parceiro'];
  el('reason-filters').innerHTML = reasons.map(reason => `<button class="filter ${reason === activeReason ? 'active' : ''}" data-reason="${reason}">${reason}</button>`).join('');
  document.querySelectorAll('[data-reason]').forEach(button => button.onclick = () => { activeReason = button.dataset.reason; loadTasks(); });
  const shownTasks = activeReason === 'Todos' ? tasks : tasks.filter(task => task.motivos.includes(activeReason));
  const pending = tasks.filter(t => t.status === 'Pendente').length;
  const contacted = tasks.filter(t => t.status !== 'Pendente').length;
  el('metrics').innerHTML = metric(tasks.length, 'Parceiros na carteira') + metric(pending, 'Ainda pendentes') + metric(contacted, 'Contatados');
  el('count-label').textContent = `${shownTasks.length} parceiros`;
  el('tasks').innerHTML = shownTasks.map(task => {
    const completed = task.status !== 'Pendente';
    const badges = task.motivos.split(';').map(reason => {
      const clean = reason.trim();
      const kind = clean === 'Parceiro em destaque de vendas' ? 'champion' : clean === 'Cidade estratégica' ? 'strategic' : 'birthday';
      return `<span class="reason-badge ${kind}">${escapeHtml(clean)}</span>`;
    }).join('');
    const whatsapp = whatsappLink(task.telefone);
    const telefone = whatsapp ? `<a class="whatsapp-link" href="${whatsapp}" target="_blank" rel="noopener noreferrer" title="Abrir conversa no WhatsApp">${escapeHtml(task.telefone)}</a>` : escapeHtml(task.telefone);
    return `<tr><td class="partner">${escapeHtml(task.parceiro)}<small>${escapeHtml(task.cidade)} · ${escapeHtml(task.uf)}</small></td><td class="b2b-id">${escapeHtml(task.id_wfm_b2b)}</td><td>${telefone}</td><td class="sales">${escapeHtml(task.vendas_starlink)}</td><td class="reason"><div class="reason-badges">${badges}</div><small class="rule-detail">${escapeHtml(task.detalhe_regra)}</small></td><td><span class="priority ${task.prioridade === 'Alta' ? 'high' : 'normal'}">${escapeHtml(task.prioridade)}</span></td><td><span class="tag ${completed ? 'done' : 'pending'}">${escapeHtml(task.status)}</span></td><td><button class="register" data-task="${escapeHtml(task.id_tarefa)}">${completed ? 'Novo registro' : 'Registrar'}</button></td></tr>`;
  }).join('');
  document.querySelectorAll('[data-task]').forEach(button => button.onclick = () => openDialog(tasks.find(t => t.id_tarefa === button.dataset.task)));
}

function metric(value, label) { return `<div class="metric"><span>${label}</span><strong>${value}</strong></div>`; }
function whatsappLink(phone) {
  let digits = String(phone || '').replace(/\D/g, '');
  if (digits.startsWith('55') && [12, 13].includes(digits.length)) digits = digits.slice(2);
  return digits.length >= 10 ? `https://wa.me/55${digits}` : '';
}
function openDialog(task) { currentTask = task; el('modal-partner').textContent = task.parceiro; el('modal-subtitle').textContent = `${task.cidade} · ${task.uf} · ${task.motivos}`; el('interaction-form').reset(); el('form-error').textContent = ''; el('interaction-dialog').showModal(); }
function closeDialog() { el('interaction-dialog').close(); currentTask = null; }

el('start-work').onclick = beginWork;
el('select-all-states').onclick = () => {
  const grupos = Object.keys(config.grupos_uf);
  currentGroups = currentGroups.length === grupos.length ? [] : grupos;
  el('start-work').disabled = currentGroups.length === 0;
  renderStates();
};
el('change-consultant').onclick = () => { el('workspace').hidden = true; el('start').hidden = false; };
el('close-dialog').onclick = closeDialog; el('cancel-dialog').onclick = closeDialog;
el('interaction-form').onsubmit = async (event) => {
  event.preventDefault();
  const payload = {id_tarefa: currentTask.id_tarefa, consultor: el('contact-consultant').value, resultado: el('result').value, observacao: el('note').value, proximo_retorno: ''};
  const response = await fetch('/api/interacoes', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  const result = await response.json();
  if (!response.ok) { el('form-error').textContent = result.erro || 'Não foi possível salvar.'; return; }
  closeDialog(); await loadTasks();
};
getConfig();
