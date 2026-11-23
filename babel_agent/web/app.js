'use strict';
const $ = (id) => document.getElementById(id);
const token = document.querySelector('meta[name="babel-token"]').content;
let session = null;
let busy = false;
let conversations = [];
function icon(name) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.classList.add('icon'); svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS(svg.namespaceURI, 'use');
  use.setAttribute('href', '#i-' + name); svg.append(use); return svg;
}
async function api(path, data) {
  const response = await fetch('/api/' + path, {
    method: data === undefined ? 'GET' : 'POST',
    headers: {'X-Babel-Token': token, 'Content-Type': 'application/json'},
    body: data === undefined ? undefined : JSON.stringify(data)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Não foi possível completar a operação.');
  return result;
}
function text(tag, value, className) {
  const element = document.createElement(tag);
  element.textContent = value;
  if (className) element.className = className;
  return element;
}
function feedback(message, error = false) {
  $('feedback').textContent = message;
  $('feedback').className = error ? 'error' : '';
}
function setBusy(value) {
  busy = value;
  document.querySelectorAll('button,select,textarea').forEach(el => {el.disabled = value;});
  for (const id of ['menu', 'environment-open', 'environment-close']) $(id).disabled = false;
  $('send').disabled = value || !!session?.pending || !$('model').value;
  $('send').setAttribute('aria-label', value ? 'Pensando…' : 'Enviar mensagem');
  $('conversation').setAttribute('aria-busy', String(value));
}
async function history() {
  conversations = await api('sessions');
  renderHistory();
}
function renderHistory() {
  const query = $('search').value.trim().toLocaleLowerCase('pt-BR');
  const list = conversations.filter(item => item.title.toLocaleLowerCase('pt-BR').includes(query));
  $('sessions').replaceChildren();
  list.forEach(item => {
    const button = text('button', '');
    button.append(icon('chat'), text('span', item.title));
    button.setAttribute('aria-current', String(item.id === session?.id));
    button.disabled = busy;
    button.onclick = () => perform(async () => { session = await api('sessions/' + item.id); render(); await history(); closeMenu(); });
    $('sessions').append(button);
  });
  if (!list.length) $('sessions').append(text('p', query ? 'Nenhuma conversa encontrada.' : 'Nenhuma conversa ainda.', 'empty-history'));
}
function render() {
  $('page-title').textContent = session?.messages.length ? session.title : 'Nova conversa';
  $('welcome').hidden = !!session?.messages.length;
  $('messages').replaceChildren();
  for (const message of session?.messages || []) {
    if (message.role === 'tool') {
      const details = document.createElement('details');
      details.append(text('summary', 'Resultado · ' + message.tool_name), text('pre', message.content));
      $('messages').append(details);
    } else if (message.content) {
      const article = text('article', '', 'message ' + message.role);
      article.append(text('h3', message.role === 'user' ? 'Você' : 'Babel'), text('div', message.content, 'content'));
      $('messages').append(article);
    }
  }
  $('approval').replaceChildren();
  $('approval').hidden = !session?.pending;
  if (session?.pending) {
    const fn = session.pending.call.function;
    $('approval').append(text('h2', 'Uma ação precisa de você'),
      text('p', fn.name === 'create_file' ? 'Criar o arquivo abaixo com este conteúdo?' : 'Mover este arquivo para o destino indicado?'),
      text('pre', JSON.stringify(fn.arguments, null, 2)));
    const actions = text('div', '', 'actions');
    for (const [label, approved] of [['Aprovar ação', true], ['Recusar ação', false]]) {
      const button = text('button', label, approved ? 'primary' : 'secondary');
      button.onclick = () => perform(async () => {
        feedback(approved ? 'Executando a ação aprovada…' : 'Registrando sua decisão…');
        session = await api('approve', {session: session.id, approval: session.pending.id, approved});
        render(); await history(); feedback(session.pending ? 'Revise a próxima ação.' : 'Pronto.');
      });
      actions.append(button);
    }
    $('approval').append(actions);
  }
  setBusy(busy);
}
async function perform(operation) {
  if (busy) return;
  setBusy(true);
  try { await operation(); }
  catch (error) {
    feedback(error.message, true);
    if (session) {
      try { session = await api('sessions/' + session.id); render(); } catch { /* Keep original error. */ }
    }
  } finally { setBusy(false); }
}
async function refresh() {
  const previous = $('model').value || localStorage.getItem('babel-model');
  const status = await api('status');
  $('model').replaceChildren();
  status.models.forEach(name => { const option = text('option', name); option.value = name; $('model').append(option); });
  if (!status.models.length) {
    const option = text('option', 'Nenhum modelo disponível'); option.value = ''; $('model').append(option);
  } else if (status.models.includes(previous)) $('model').value = previous;
  else if (status.models.includes('qwen3:4b')) $('model').value = 'qwen3:4b';
  $('workspace').textContent = status.workspace;
  $('status').textContent = status.error ? 'Ollama desconectado' : 'Ollama conectado';
  $('status').className = status.error ? '' : 'online';
  if (status.error) feedback(status.error, true);
  else if (!status.models.length) feedback('Instale um modelo: ollama pull qwen3:4b. Depois atualize a lista.', true);
}
$('new').onclick = () => perform(async () => { session = await api('sessions', {}); render(); await history(); closeMenu(); feedback('Nova conversa pronta.'); $('message').value = ''; });
$('search').oninput = renderHistory;
function closeMenu() { document.body.classList.remove('menu-open'); $('menu').setAttribute('aria-expanded', 'false'); }
$('menu').onclick = () => { const open = document.body.classList.toggle('menu-open'); $('menu').setAttribute('aria-expanded', String(open)); };
$('environment-open').onclick = () => $('environment').showModal();
$('environment-close').onclick = () => $('environment').close();
$('refresh').onclick = () => perform(refresh);
$('model').onchange = () => { localStorage.setItem('babel-model', $('model').value); setBusy(false); };
$('composer').onsubmit = (event) => {
  event.preventDefault();
  if (busy || session?.pending || !$('model').value || !$('message').value.trim()) return;
  perform(async () => {
    if (!session) session = await api('sessions', {});
    const message = $('message').value.trim();
    $('message').value = '';
    session.messages.push({role: 'user', content: message}); render();
    $('conversation').scrollTop = $('conversation').scrollHeight;
    feedback('Babel está analisando seu pedido. O primeiro uso pode demorar enquanto o modelo carrega.');
    session = await api('chat', {session: session.id, message, model: $('model').value});
    render(); await history(); feedback(session.pending ? 'Revise a ação antes de aprovar.' : 'Pronto.');
    $('conversation').scrollTop = $('conversation').scrollHeight;
  });
};
$('message').onkeydown = (event) => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {event.preventDefault(); $('composer').requestSubmit();} };
document.querySelectorAll('[data-prompt]').forEach(button => { button.onclick = () => {$('message').value = button.dataset.prompt; $('message').focus();}; });
$('export').onclick = () => {
  if (!session?.messages.length) return feedback('Envie uma mensagem antes de exportar.');
  const markdown = '# ' + session.title + '\n\n' + session.messages.filter(m => m.content).map(m => '## ' + ({user:'Você', assistant:'Babel', tool:'Ferramenta: ' + m.tool_name}[m.role]) + '\n\n' + m.content).join('\n\n');
  const url = URL.createObjectURL(new Blob([markdown], {type:'text/markdown;charset=utf-8'}));
  const link = document.createElement('a'); link.href = url; link.download = 'babel-' + session.id.slice(0,8) + '.md'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
perform(async () => { await refresh(); await history(); });
