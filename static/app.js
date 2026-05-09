let currentRegion = '';
let currentMode   = 'all';   // 'all' | 'recommend'

// ── 初始化 ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      btn.classList.add('active');
      currentRegion = btn.dataset.region || '';
    });
  });
  loadEvents();

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/sw.js').catch(() => {});
  }
});

// ── 模式切換（推薦 / 一般）────────────────────────────
function switchMode(mode) {
  currentMode = mode;
  if (mode === 'recommend') {
    loadRecommend();
  } else {
    loadEvents();
  }
}

// ── 載入推薦活動 ─────────────────────────────────────────
async function loadRecommend() {
  showLoading(true);
  const btn = document.getElementById('refresh-btn');
  btn.classList.add('spinning');
  try {
    const res = await fetch('/api/recommend');
    if (!res.ok) throw new Error();
    const data = await res.json();
    renderRecommend(data);
  } catch {
    showToast('載入失敗，請稍後再試');
    showLoading(false);
  } finally {
    btn.classList.remove('spinning');
  }
}

function renderRecommend(data) {
  const REGION_ORDER = ['北部', '中部', '南部', '東部'];
  const REGION_EMOJI = { '北部': '🏙️', '中部': '🌄', '南部': '🌞', '東部': '🌊' };
  const rec = data.recommend || {};

  showLoading(false);
  document.getElementById('event-list').style.display    = 'none';
  document.getElementById('empty-state').style.display   = 'none';
  document.getElementById('recommend-list').style.display = 'block';

  const container = document.getElementById('recommend-cards');
  let html = '';

  REGION_ORDER.forEach(region => {
    const events = rec[region] || [];
    if (events.length === 0) return;
    html += `
      <div class="rec-region-header">
        ${REGION_EMOJI[region] || '📍'} ${region}
        <span class="count-badge">${events.length}</span>
      </div>
      <div class="cards-wrap">
        ${events.map(ev => recCardHTML(ev, region)).join('')}
      </div>`;
  });

  container.innerHTML = html || '<p class="empty-state">暫無推薦活動</p>';
}

function recCardHTML(ev, region) {
  const [title, category, start, end, location, city, url] = ev;
  const dateStr = start === end ? start : `${start} ~ ${end}`;
  const place   = location || city || '地點不明';
  const link    = url || 'https://cloud.culture.tw';
  return `
    <a class="event-card recommend" href="${escHtml(link)}" target="_blank" rel="noopener">
      <span class="card-tag">⭐ 推薦</span>
      <div class="card-title">${escHtml(title)}</div>
      <div class="card-meta">
        <span>📍 ${escHtml(place)}・${escHtml(region)}</span>
        <span>📆 ${escHtml(dateStr)}</span>
      </div>
      <div class="card-source">${escHtml(category || '活動')}</div>
    </a>`;
}

// ── 載入一般活動 ─────────────────────────────────────────
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

function renderEvents(data) {
  const ongoing  = data.ongoing  || {};
  const upcoming = data.upcoming || {};

  const ongoingAll  = flattenEvents(ongoing);
  const upcomingAll = flattenEvents(upcoming);

  showLoading(false);
  document.getElementById('recommend-list').style.display = 'none';

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
    if (currentMode === 'recommend') {
      await loadRecommend();
    } else {
      await loadEvents();
    }
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
  if (!show) return;
  document.getElementById('event-list').style.display    = 'none';
  document.getElementById('recommend-list').style.display = 'none';
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
