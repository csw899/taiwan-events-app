let currentRegion = '';

// ── 初始化 ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // 地區 Tab 切換
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      btn.classList.add('active');
      currentRegion = btn.dataset.region;
      loadEvents();
    });
  });

  loadEvents();

  // PWA Service Worker 註冊
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/sw.js').catch(() => {});
  }
});

// ── 載入活動 ─────────────────────────────────────────────
async function loadEvents() {
  showLoading(true);
  const btn = document.getElementById('refresh-btn');
  btn.classList.add('spinning');

  try {
    const params = currentRegion ? `?region=${encodeURIComponent(currentRegion)}` : '';
    const res = await fetch(`/api/events${params}`);
    if (!res.ok) throw new Error('載入失敗');
    const data = await res.json();
    renderEvents(data);
  } catch (e) {
    showToast('載入失敗，請確認伺服器是否啟動');
    showLoading(false);
  } finally {
    btn.classList.remove('spinning');
  }
}

// ── 渲染活動 ─────────────────────────────────────────────
function renderEvents(data) {
  const ongoing  = data.ongoing  || {};
  const upcoming = data.upcoming || {};

  const ongoingAll  = flattenEvents(ongoing);
  const upcomingAll = flattenEvents(upcoming);

  showLoading(false);

  if (ongoingAll.length === 0 && upcomingAll.length === 0) {
    document.getElementById('event-list').style.display = 'none';
    document.getElementById('empty-state').style.display = 'flex';
    return;
  }

  document.getElementById('empty-state').style.display = 'none';
  document.getElementById('event-list').style.display = 'block';

  document.getElementById('ongoing-count').textContent  = ongoingAll.length;
  document.getElementById('upcoming-count').textContent = upcomingAll.length;

  document.getElementById('ongoing-cards').innerHTML  = ongoingAll.map(ev => cardHTML(ev, 'ongoing')).join('');
  document.getElementById('upcoming-cards').innerHTML = upcomingAll.map(ev => cardHTML(ev, 'upcoming')).join('');

  // 沒有進行中活動時隱藏 section
  document.getElementById('ongoing-section').style.display  = ongoingAll.length  ? 'block' : 'none';
  document.getElementById('upcoming-section').style.display = upcomingAll.length ? 'block' : 'none';
}

function flattenEvents(regionMap) {
  return Object.values(regionMap).flat();
}

function cardHTML(ev, status) {
  const [title, category, start, end, location, city, url, region] = ev;
  const dateStr = start === end ? start : `${start} ~ ${end}`;
  const place   = location || city || '地點不明';
  const link    = url || 'https://cloud.culture.tw';
  const label   = status === 'ongoing' ? '進行中' : '即將開始';
  const regionLabel = region ? `・${region}` : '';

  return `
    <a class="event-card ${status}" href="${escHtml(link)}" target="_blank" rel="noopener">
      <span class="card-tag">${escHtml(label)}</span>
      <div class="card-title">${escHtml(title)}</div>
      <div class="card-meta">
        <span>📍 ${escHtml(place)}${regionLabel}</span>
        <span>📆 ${escHtml(dateStr)}</span>
      </div>
      <div class="card-source">${escHtml(category || '活動')}</div>
    </a>`;
}

// ── 手動更新資料 ─────────────────────────────────────────
async function triggerUpdate() {
  const btn = document.getElementById('update-btn');
  btn.textContent = '⏳ 更新中...';
  btn.disabled = true;

  try {
    const res = await fetch('/api/update', { method: 'POST' });
    const data = await res.json();
    showToast(data.message || '更新完成');
    await loadEvents();
  } catch (e) {
    showToast('更新失敗，請稍後再試');
  } finally {
    btn.textContent = '🔄 更新最新活動';
    btn.disabled = false;
  }
}

// ── 工具函式 ─────────────────────────────────────────────
function showLoading(show) {
  document.getElementById('loading').style.display    = show ? 'flex' : 'none';
  document.getElementById('event-list').style.display = show ? 'none' : 'block';
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
