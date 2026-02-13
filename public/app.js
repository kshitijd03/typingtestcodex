const loginView = document.getElementById('loginView');
const appView = document.getElementById('appView');
const adminView = document.getElementById('adminView');
const logoutBtn = document.getElementById('logoutBtn');
const welcomeText = document.getElementById('welcomeText');

let sessionUser = null;
let settings = {};
let mode = 'timed_words';
let words = [];
let currentWordIdx = 0;
let correctCount = 0;
let typedCount = 0;
let timerId = null;
let timeLeft = 60;
let started = false;

async function api(url, opts = {}) {
  const res = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...opts });
  if (!res.ok) throw new Error((await res.json()).message || 'Request failed');
  return res.json();
}

async function bootstrap() {
  const { user } = await api('/api/session');
  if (!user) return;
  sessionUser = user;
  welcomeText.textContent = `Welcome to ${user.userName}`;
  logoutBtn.classList.remove('hidden');
  settings = await api('/api/settings');
  document.getElementById('bonusBtn').textContent = settings.bonus_text || 'Click here for bonus';

  if (user.role === 'admin') {
    loginView.classList.add('hidden');
    adminView.classList.remove('hidden');
    loadAdmin();
  } else {
    loginView.classList.add('hidden');
    appView.classList.remove('hidden');
    loadContent();
  }
}

document.getElementById('loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  try {
    await api('/api/login', { method: 'POST', body: JSON.stringify({ userId: fd.get('userId'), password: fd.get('password') }) });
    bootstrap();
  } catch (err) {
    document.getElementById('loginMessage').textContent = err.message;
  }
});

logoutBtn.addEventListener('click', async () => {
  await api('/api/logout', { method: 'POST' });
  location.reload();
});

async function loadContent() {
  const language = document.getElementById('languageSelect').value;
  const { content } = await api(`/api/content?mode=${mode}&language=${language}`);
  words = content.split(/\s+/).filter(Boolean);
  resetTest();
}

function renderWords() {
  const win = document.getElementById('textWindow');
  win.innerHTML = words.map((w, i) => `<span class="word ${i === currentWordIdx ? 'current' : ''}" data-i="${i}">${w}</span>`).join(' ');
  const current = win.querySelector('.current');
  if (current) win.scrollTop = Math.max(0, current.offsetTop - 20);
}

function resetTest() {
  currentWordIdx = 0; correctCount = 0; typedCount = 0; started = false;
  timeLeft = parseInt(document.getElementById('durationSelect').value, 10);
  clearInterval(timerId); document.getElementById('timer').textContent = timeLeft;
  document.getElementById('typingInput').value = '';
  document.getElementById('resultPanel').textContent = '';
  renderWords(); updateStats();
}

function updateStats() {
  const elapsedMin = Math.max(1 / 60, (parseInt(document.getElementById('durationSelect').value, 10) - timeLeft) / 60);
  const wpm = Math.round(correctCount / elapsedMin);
  const accuracy = typedCount ? Math.round((correctCount / typedCount) * 100) : 100;
  document.getElementById('wpm').textContent = wpm;
  document.getElementById('accuracy').textContent = accuracy;
  return { wpm, accuracy };
}

async function finishTest() {
  clearInterval(timerId);
  const { wpm, accuracy } = updateStats();
  const rating = Math.max(4, Math.round((wpm / 10 + accuracy / 20)));
  document.getElementById('resultPanel').innerHTML = `Result: WPM ${wpm}, Accuracy ${accuracy}%<br>Motivational Rating: ${rating}/10`;
  await api('/api/results', { method: 'POST', body: JSON.stringify({ mode, language: document.getElementById('languageSelect').value, wpm, accuracy, rawSpeed: typedCount, duration: parseInt(document.getElementById('durationSelect').value, 10) }) });
}

document.getElementById('typingInput').addEventListener('input', async (e) => {
  if (!started) {
    started = true;
    timerId = setInterval(() => {
      timeLeft -= 1;
      document.getElementById('timer').textContent = timeLeft;
      if (timeLeft <= 0) finishTest();
    }, 1000);
  }

  const val = e.target.value;
  if (!val.endsWith(' ')) return;
  const typed = val.trim();
  const current = words[currentWordIdx];
  typedCount += 1;
  if (typed === current) {
    correctCount += 1;
    document.querySelector(`[data-i='${currentWordIdx}']`)?.classList.add('correct');
  } else {
    document.querySelector(`[data-i='${currentWordIdx}']`)?.classList.add('incorrect');
  }
  currentWordIdx += 1;
  e.target.value = '';
  if (currentWordIdx >= words.length) await loadContent();
  else renderWords();
  updateStats();
});

document.querySelectorAll('.sidebar button[data-mode]').forEach(btn => btn.addEventListener('click', () => {
  mode = btn.dataset.mode;
  loadContent();
}));

document.getElementById('durationSelect').addEventListener('change', resetTest);
document.getElementById('languageSelect').addEventListener('change', () => {
  document.getElementById('typingInput').classList.toggle('hindi-font', document.getElementById('languageSelect').value === 'hindi');
  loadContent();
});
document.getElementById('bonusBtn').addEventListener('click', () => window.open(settings.bonus_url || '#', '_blank'));

async function loadAdmin() {
  const [users, logs, content, currentSettings] = await Promise.all([
    api('/api/admin/users'), api('/api/admin/logs'), api('/api/admin/content'), api('/api/settings')
  ]);
  settings = currentSettings;
  renderUsers(users); renderLogs(logs);
  const contentEl = document.getElementById('contentForm').elements;
  const found = content.find(c => c.mode === contentEl.mode.value && c.language === contentEl.language.value);
  contentEl.content.value = found?.content || '';
  document.getElementById('bonusForm').elements.bonusText.value = settings.bonus_text || '';
  document.getElementById('bonusForm').elements.bonusUrl.value = settings.bonus_url || '';
}

function renderUsers(users) {
  const t = document.getElementById('usersTable');
  t.innerHTML = '<tr><th>UserID</th><th>Name</th><th>Role</th><th>Valid Upto</th><th>Action</th></tr>' + users.map(u =>
    `<tr><td>${u.user_id}</td><td>${u.user_name}</td><td>${u.role}</td><td><input type='date' value='${u.valid_upto || ''}' onchange='updateValid(${u.id}, this.value)' /></td><td>${u.role === 'admin' ? '' : `<button onclick='deleteUser(${u.id})'>Delete</button>`}</td></tr>`).join('');
}

function renderLogs(logs) {
  const t = document.getElementById('logsTable');
  t.innerHTML = '<tr><th>UserID</th><th>Login</th><th>Logout</th><th>Duration(s)</th></tr>' + logs.map(l =>
    `<tr><td>${l.user_id}</td><td>${l.login_time || ''}</td><td>${l.logout_time || ''}</td><td>${l.session_duration || ''}</td></tr>`).join('');
}

window.updateValid = async (id, validUpto) => {
  await api(`/api/admin/users/${id}/valid-upto`, { method: 'PUT', body: JSON.stringify({ validUpto }) });
};
window.deleteUser = async (id) => {
  await api(`/api/admin/users/${id}`, { method: 'DELETE' });
  loadAdmin();
};

document.getElementById('createUserForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  await api('/api/admin/users', { method: 'POST', body: JSON.stringify(Object.fromEntries(fd.entries())) });
  e.target.reset();
  loadAdmin();
});

document.getElementById('downloadTemplate').addEventListener('click', () => window.open('/api/admin/users/template'));
document.getElementById('bulkForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const res = await fetch('/api/admin/users/bulk', { method: 'POST', body: fd });
  const data = await res.json();
  document.getElementById('bulkOutput').textContent = JSON.stringify(data, null, 2);
  loadAdmin();
});

document.getElementById('contentForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  await api('/api/admin/content', { method: 'POST', body: JSON.stringify(Object.fromEntries(fd.entries())) });
  alert('Content saved');
});
document.getElementById('contentForm').elements.mode.addEventListener('change', loadAdmin);
document.getElementById('contentForm').elements.language.addEventListener('change', loadAdmin);

document.getElementById('bonusForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  await api('/api/admin/settings', { method: 'POST', body: JSON.stringify(Object.fromEntries(fd.entries())) });
  alert('Bonus settings saved');
});

document.getElementById('certForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  await fetch('/api/admin/certificate', { method: 'POST', body: fd });
  alert('Certificate uploaded');
  loadAdmin();
});

const certificateDialog = document.getElementById('certificateDialog');
document.getElementById('certificateBtn').addEventListener('click', () => certificateDialog.showModal());

let certCanvas;
document.getElementById('previewCert').addEventListener('click', async () => {
  const pwd = document.getElementById('certPassword').value.trim();
  const name = document.getElementById('certName').value.trim();
  if (pwd !== sessionUser.userId) return alert('Invalid password');
  const el = document.getElementById('certificatePreview');
  el.style.backgroundImage = settings.certificate_bg ? `url(${settings.certificate_bg})` : 'none';
  el.innerHTML = `<div class='cert-text'>${name}</div>`;
  certCanvas = await html2canvas(el, { scale: 2 });
});

document.getElementById('downloadJPG').addEventListener('click', () => {
  if (!certCanvas) return;
  const a = document.createElement('a');
  a.href = certCanvas.toDataURL('image/jpeg', 0.95);
  a.download = 'certificate.jpg';
  a.click();
});

document.getElementById('downloadPDF').addEventListener('click', () => {
  if (!certCanvas) return;
  const { jsPDF } = window.jspdf;
  const pdf = new jsPDF('landscape', 'pt', [certCanvas.width, certCanvas.height]);
  pdf.addImage(certCanvas.toDataURL('image/png'), 'PNG', 0, 0, certCanvas.width, certCanvas.height);
  pdf.save('certificate.pdf');
});

bootstrap();
