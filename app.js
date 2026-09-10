
const state = {
  jobs: [],
  seen: new Set(JSON.parse(localStorage.getItem('seenJobs') || '[]'))
};

function esc(s='') {
  return String(s).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
}

function card(job, isNew=false) {
  const tags = [job.location, job.pay, job.posted].filter(Boolean);
  return `
    <article class="card">
      <div class="card-top">
        <div>
          <div class="company">${esc(job.company)}</div>
          <div class="title">${esc(job.title)}</div>
        </div>
        ${isNew ? '<div class="new-badge">NEW</div>' : ''}
      </div>
      <div class="meta">${tags.map(t=>`<span>${esc(t)}</span>`).join('')}</div>
      ${job.reason ? `<div class="reason"><strong>Why it fits:</strong> ${esc(job.reason)}</div>` : ''}
      ${job.apply_url ? `<a class="apply" target="_blank" rel="noopener" href="${esc(job.apply_url)}">View job</a>` : ''}
    </article>`;
}

function render() {
  const newJobs = state.jobs.filter(j => !state.seen.has(j.id));
  document.querySelector('#newJobs').innerHTML = newJobs.map(j => card(j, true)).join('');
  document.querySelector('#newCount').textContent = `${newJobs.length} new listing${newJobs.length === 1 ? '' : 's'}`;
  document.querySelector('#newEmpty').classList.toggle('hidden', newJobs.length !== 0);

  const q = document.querySelector('#searchInput').value.trim().toLowerCase();
  const filtered = state.jobs.filter(j => [j.title,j.company,j.location].join(' ').toLowerCase().includes(q));
  document.querySelector('#allJobs').innerHTML = filtered.map(j => card(j, !state.seen.has(j.id))).join('');
}

async function loadJobs() {
  try {
    const res = await fetch(`jobs.json?ts=${Date.now()}`, {cache:'no-store'});
    if (!res.ok) throw new Error('feed unavailable');
    state.jobs = await res.json();
    render();
  } catch(e) {
    state.jobs = [];
    render();
  }
}

document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(b=>b.classList.remove('active'));
    document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(btn.dataset.target).classList.add('active');
    if (btn.dataset.target === 'allView') {
      state.jobs.forEach(j=>state.seen.add(j.id));
      localStorage.setItem('seenJobs', JSON.stringify([...state.seen]));
      render();
    }
  });
});

document.querySelector('#refreshBtn').addEventListener('click', loadJobs);
document.querySelector('#searchInput').addEventListener('input', render);
document.querySelector('#notifyBtn').addEventListener('click', async () => {
  if (!('Notification' in window)) return alert('Notifications are not supported in this browser.');
  const result = await Notification.requestPermission();
  alert(result === 'granted' ? 'Browser notifications enabled.' : 'Notification permission was not granted.');
});

if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js');
loadJobs();
