/* ── Samsung APK Downloader — App JavaScript ── */

// ═══════════════════════════════════════════════
//  NAVIGATION
// ═══════════════════════════════════════════════

function navigate(page) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
  
  const target = document.getElementById(`page-${page}`);
  if (target) target.classList.add('active');
  
  const link = document.querySelector(`.nav-link[data-page="${page}"]`);
  if (link) link.classList.add('active');
  
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function toggleMobileMenu() {
  document.querySelector('.nav-links').classList.toggle('open');
}

// ═══════════════════════════════════════════════
//  THEME
// ═══════════════════════════════════════════════

function toggleTheme() {
  const html = document.documentElement;
  const current = html.getAttribute('data-theme');
  html.setAttribute('data-theme', current === 'dark' ? 'light' : 'dark');
  localStorage.setItem('theme', current === 'dark' ? 'light' : 'dark');
}

// Load saved theme
const savedTheme = localStorage.getItem('theme');
if (savedTheme) document.documentElement.setAttribute('data-theme', savedTheme);

// ═══════════════════════════════════════════════
//  CONFIG
// ═══════════════════════════════════════════════

function toggleConfig() {
  const body = document.getElementById('config-body');
  const arrow = document.querySelector('.config-arrow');
  body.classList.toggle('open');
  arrow.style.transform = body.classList.contains('open') ? 'rotate(180deg)' : '';
}

function updateDevices() {
  const region = document.getElementById('region-select').value;
  fetch(`/api/devices?region=${region}`)
    .then(r => r.json())
    .then(data => {
      const sel = document.getElementById('device-select');
      sel.innerHTML = '<option value="">🔄 Auto (tous les appareils)</option>';
      data.devices.forEach(d => {
        const label = `${d.name} (${d.eu || d.cn || ''}) — One UI ${d.oneui}`;
        sel.innerHTML += `<option value="${d.eu || d.cn}">${label}</option>`;
      });
    });
}

// Init devices
updateDevices();

// ═══════════════════════════════════════════════
//  SEARCH TABS
// ═══════════════════════════════════════════════

function switchSearchTab(tab) {
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(`tab-${tab}`).classList.add('active');
  document.querySelector(`.tab-btn[data-tab="${tab}"]`).classList.add('active');
}

// ═══════════════════════════════════════════════
//  SEARCH
// ═══════════════════════════════════════════════

let searchTimeout = null;

function debounceSearch() {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(triggerSearch, 300);
}

function triggerSearch() {
  const q = document.getElementById('search-input').value.trim();
  const results = document.getElementById('search-results');
  
  if (!q) {
    results.classList.remove('show');
    results.innerHTML = '';
    return;
  }
  
  fetch(`/api/search?q=${encodeURIComponent(q)}`)
    .then(r => r.json())
    .then(data => {
      if (!data.results.length) {
        results.innerHTML = `<div class="search-result-item" style="justify-content:center;color:var(--text-muted)">
          Aucun résultat pour "${q}"</div>`;
        results.classList.add('show');
        return;
      }
      
      results.innerHTML = data.results.map(r => `
        <div class="search-result-item" onclick="selectPackage('${r.package}')">
          <span class="result-emoji">${r.emoji}</span>
          <div>
            <div class="result-name">${r.name}</div>
            <div class="result-package">${r.package}</div>
          </div>
          <div style="margin-left:auto">
            <span class="result-category">${r.category}</span>
          </div>
        </div>
      `).join('');
      results.classList.add('show');
    });
}

function showSearchResults() {
  if (document.getElementById('search-results').innerHTML) {
    document.getElementById('search-results').classList.add('show');
  }
}

// Close search results on click outside
document.addEventListener('click', (e) => {
  if (!e.target.closest('.search-box') && !e.target.closest('.search-results')) {
    document.getElementById('search-results').classList.remove('show');
  }
});

// ═══════════════════════════════════════════════
//  BROWSE CATEGORIES
// ═══════════════════════════════════════════════

fetch('/api/categories')
  .then(r => r.json())
  .then(data => {
    const grid = document.getElementById('categories-grid');
    grid.innerHTML = data.categories.map(c => `
      <div class="cat-item" onclick="showCategory('${c.name}')">
        <span class="cat-emoji">${c.emoji}</span>
        <div class="cat-name">${c.name}</div>
        <div class="cat-count">${c.count} apps</div>
      </div>
    `).join('');
    
    // Also populate scan category selector
    const scanCat = document.getElementById('scan-category');
    data.categories.forEach(c => {
      scanCat.innerHTML += `<option value="${c.name}">${c.emoji} ${c.name}</option>`;
    });
  });

function showCategory(name) {
  document.getElementById('categories-grid').style.display = 'none';
  document.getElementById('category-items').style.display = 'block';
  
  const list = document.getElementById('category-items-list');
  list.innerHTML = '<div class="loading-spinner">Chargement...</div>';
  
  fetch(`/api/category/${encodeURIComponent(name)}`)
    .then(r => r.json())
    .then(data => {
      list.innerHTML = data.results.map((r, i) => `
        <div class="search-result-item" onclick="selectPackage('${r.package}')">
          <span class="result-emoji">${r.emoji}</span>
          <div>
            <div class="result-name">${r.name}</div>
            <div class="result-package">${r.package}</div>
          </div>
        </div>
      `).join('');
    });
}

function backToCategories() {
  document.getElementById('categories-grid').style.display = 'grid';
  document.getElementById('category-items').style.display = 'none';
}

// ═══════════════════════════════════════════════
//  SELECT PACKAGE → CHECK
// ═══════════════════════════════════════════════

function selectPackage(pkg) {
  document.getElementById('search-results').classList.remove('show');
  checkPackage(pkg);
}

function checkManualPackage() {
  const pkg = document.getElementById('manual-input').value.trim();
  if (!pkg) {
    showToast('Veuillez entrer un package name', 'error');
    return;
  }
  checkPackage(pkg);
}

function checkPackage(package) {
  const panel = document.getElementById('result-panel');
  const content = document.getElementById('result-content');
  content.innerHTML = '<div class="loading-spinner">🔍 Recherche en cours...</div>';
  panel.style.display = 'block';
  panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
  
  const region = document.getElementById('region-select').value;
  const oneui = document.getElementById('oneui-select').value;
  const device = document.getElementById('device-select').value;
  
  fetch('/api/check', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ package, region, oneui, device_id: device }),
  })
    .then(r => r.json())
    .then(data => {
      if (!data.found) {
        content.innerHTML = `
          <div class="not-found-card">
            <div class="not-found-icon">😕</div>
            <div class="not-found-title">Application non trouvée</div>
            <div class="not-found-desc">
              "${package}" n'a pas été trouvée sur le Galaxy Store.<br>
              Essayez avec --sdk-all ou une autre région.
            </div>
          </div>`;
        return;
      }
      
      const r = data.result;
      const size = r.size_formatted || '?';
      
      content.innerHTML = `
        <div class="result-card animate-scale">
          <div class="result-header">
            <div>
              <div class="result-app-name">${r.name}</div>
              <div style="font-size:12px;color:var(--text-muted);font-family:var(--font-mono)">${r.package}</div>
            </div>
            <div class="result-version-badge">v${r.versionName}</div>
          </div>
          
          <div class="result-details">
            <div class="result-detail">
              <div class="detail-label">Version Code</div>
              <div class="detail-value">${r.versionCode}</div>
            </div>
            <div class="result-detail">
              <div class="detail-label">Taille</div>
              <div class="detail-value">${size}</div>
            </div>
            <div class="result-detail">
              <div class="detail-label">Appareil</div>
              <div class="detail-value">${r.device}</div>
            </div>
            <div class="result-detail">
              <div class="detail-label">CSC</div>
              <div class="detail-value">${r.csc}</div>
            </div>
            <div class="result-detail">
              <div class="detail-label">SDK</div>
              <div class="detail-value">${r.sdk}</div>
            </div>
          </div>
          
          <div class="result-actions">
            <button class="btn-primary" onclick="startDownload('${r.downloadURI}', '${r.package}', '${r.versionCode}')">
              ⬇️ Télécharger
            </button>
            <button class="btn-secondary" onclick="navigator.clipboard.writeText('${r.downloadURI}');showToast('URL copiée !','success')">
              🔗 Copier l'URL
            </button>
          </div>
          
          <div class="result-url">${r.downloadURI}</div>
        </div>`;
    })
    .catch(err => {
      content.innerHTML = `<div class="not-found-card">
        <div class="not-found-icon">❌</div>
        <div class="not-found-title">Erreur</div>
        <div class="not-found-desc">${err.message}</div>
      </div>`;
    });
}

// ═══════════════════════════════════════════════
//  DOWNLOAD
// ═══════════════════════════════════════════════

function startDownload(url, package, version) {
  const modal = document.getElementById('download-modal');
  modal.classList.add('show');
  document.getElementById('modal-title').textContent = `⬇️ ${package}`;
  document.getElementById('modal-result').style.display = 'none';
  document.querySelector('.download-progress').style.display = 'block';
  document.getElementById('dl-bar').style.width = '0%';
  document.getElementById('dl-size').textContent = 'Démarrage...';
  document.getElementById('dl-speed').textContent = '';
  
  fetch('/api/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, package, version }),
  })
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        showModalResult('❌', data.error);
        return;
      }
      
      const evtSource = new EventSource(`/api/download/stream/${data.task_id}`);
      evtSource.onmessage = (e) => {
        const d = JSON.parse(e.data);
        
        if (d.type === 'download_progress') {
          document.getElementById('dl-bar').style.width = `${d.percent}%`;
          document.getElementById('dl-size').textContent = `${d.size_done} / ${d.size_total}`;
          document.getElementById('dl-speed').textContent = `${d.percent}%`;
        } else if (d.type === 'complete') {
          evtSource.close();
          showModalResult('✅', `
            <div style="font-weight:700;font-size:18px;margin-bottom:8px">Téléchargement terminé !</div>
            <div style="color:var(--text-secondary);font-size:14px;font-family:var(--font-mono)">
              ${d.filename}<br>
              ${d.size_fmt} · ${d.speed} · ${d.elapsed}
            </div>
            <div style="margin-top:16px;display:flex;gap:8px;justify-content:center">
              <a href="/api/file/${d.filename}" class="btn-primary" style="text-decoration:none">
                📁 Ouvrir le fichier
              </a>
            </div>
          `);
          showToast(`✅ ${d.filename} téléchargé !`, 'success');
        } else if (d.type === 'error') {
          evtSource.close();
          showModalResult('❌', d.message);
          showToast(`❌ Erreur: ${d.message}`, 'error');
        }
      };
    });
}

function showModalResult(icon, html) {
  document.querySelector('.download-progress').style.display = 'none';
  const result = document.getElementById('modal-result');
  result.style.display = 'block';
  result.innerHTML = `<div class="modal-result-content animate-scale">
    <div class="modal-result-icon">${icon}</div>
    ${html}
  </div>`;
}

function closeModal() {
  document.getElementById('download-modal').classList.remove('show');
}

function closeModalOutside(e) {
  if (e.target === e.currentTarget) closeModal();
}

// ═══════════════════════════════════════════════
//  SCAN
// ═══════════════════════════════════════════════

let scanTaskId = null;
let scanResults = [];

function startScan() {
  const region = document.getElementById('scan-region').value;
  const oneui = document.getElementById('scan-oneui').value;
  const category = document.getElementById('scan-category').value;
  
  // Show progress
  document.getElementById('scan-progress').style.display = 'block';
  document.getElementById('scan-results').style.display = 'none';
  document.getElementById('scan-progress-bar').style.width = '0%';
  document.getElementById('scan-progress-text').textContent = '0 / 0';
  document.getElementById('scan-percent').textContent = '0%';
  document.getElementById('scan-current-app').textContent = 'Initialisation...';
  document.getElementById('scan-found-count').textContent = '0';
  document.getElementById('scan-notfound-count').textContent = '0';
  document.getElementById('scan-status').textContent = 'Démarrage...';
  
  fetch('/api/scan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ region, oneui, category }),
  })
    .then(r => r.json())
    .then(data => {
      scanTaskId = data.task_id;
      document.getElementById('scan-progress-text').textContent = `0 / ${data.total}`;
      
      const evtSource = new EventSource(`/api/scan/stream/${data.task_id}`);
      evtSource.onmessage = (e) => {
        const d = JSON.parse(e.data);
        
        if (d.type === 'progress') {
          document.getElementById('scan-progress-bar').style.width = `${d.percent}%`;
          document.getElementById('scan-progress-text').textContent = `${d.current} / ${d.total}`;
          document.getElementById('scan-percent').textContent = `${d.percent}%`;
          document.getElementById('scan-current-app').textContent = `${d.name} — ${d.package}`;
          document.getElementById('scan-status').textContent = d.found ? '✅ Trouvée' : '⏳ Scan...';
          
          // Update stats
          const foundEl = document.getElementById('scan-found-count');
          const nfEl = document.getElementById('scan-notfound-count');
          // We can't track exactly without server side state, approximate
          
        } else if (d.type === 'complete') {
          evtSource.close();
          scanResults = d.results;
          
          document.getElementById('scan-status').textContent = '✅ Terminé !';
          document.getElementById('scan-found-count').textContent = d.count;
          document.getElementById('scan-notfound-count').textContent = d.total - d.count;
          document.getElementById('scan-progress-bar').style.width = '100%';
          
          // Show results table
          showScanResults(d.results);
          showToast(`✅ Scan terminé — ${d.count} APKs trouvées`, 'success');
        }
      };
    });
}

function showScanResults(results) {
  const container = document.getElementById('scan-results-table');
  const panel = document.getElementById('scan-results');
  
  if (!results.length) {
    container.innerHTML = '<div class="empty-state"><div class="empty-icon">😕</div><div class="empty-title">Aucune APK trouvée</div></div>';
    panel.style.display = 'block';
    return;
  }
  
  container.innerHTML = `
    <table class="results-table">
      <thead>
        <tr>
          <th>#</th>
          <th>App</th>
          <th>Version</th>
          <th>Code</th>
          <th>Taille</th>
          <th>Appareil</th>
          <th>CSC</th>
          <th>Action</th>
        </tr>
      </thead>
      <tbody>
        ${results.map((r, i) => `
          <tr>
            <td style="color:var(--text-muted)">${i + 1}</td>
            <td class="table-name">${r.name || r.package}</td>
            <td class="table-version">v${r.versionName || '?'}</td>
            <td style="font-family:var(--font-mono);font-size:12px;color:var(--text-muted)">${r.versionCode || '-'}</td>
            <td class="table-size">${r.contentSize ? formatSize(parseInt(r.contentSize)) : '-'}</td>
            <td class="table-device">${r.device || '-'}</td>
            <td class="table-device">${r.csc || '-'}</td>
            <td>
              <button class="table-dl-btn" onclick="startDownload('${r.downloadURI}', '${r.package}', '${r.versionCode}')">
                ⬇️ DL
              </button>
            </td>
          </tr>
        `).join('')}
      </tbody>
    </table>`;
  
  panel.style.display = 'block';
}

function formatSize(bytes) {
  if (!bytes) return '-';
  if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + ' MB';
  return (bytes / 1024).toFixed(0) + ' KB';
}

function exportScanJSON() {
  const blob = new Blob([JSON.stringify(scanResults, null, 2)], { type: 'application/json' });
  downloadBlob(blob, 'scan_results.json');
  showToast('📥 JSON exporté', 'success');
}

function exportScanCSV() {
  const headers = ['App,Package,Version,VersionCode,Size,Device,CSC,SDK,URL'];
  const rows = scanResults.map(r =>
    `"${r.name || r.package}","${r.package}","${r.versionName || ''}","${r.versionCode || ''}","${r.contentSize || ''}","${r.device || ''}","${r.csc || ''}","${r.sdk || ''}","${r.downloadURI || ''}"`
  );
  const csv = [...headers, ...rows].join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  downloadBlob(blob, 'scan_results.csv');
  showToast('📊 CSV exporté', 'success');
}

function downloadBlob(blob, filename) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

// ═══════════════════════════════════════════════
//  HISTORY
// ═══════════════════════════════════════════════

function refreshHistory() {
  const list = document.getElementById('history-list');
  list.innerHTML = '<div class="loading-spinner">Chargement...</div>';
  
  fetch('/api/history')
    .then(r => r.json())
    .then(data => {
      const history = data.history;
      if (!history || !history.length) {
        list.innerHTML = `
          <div class="empty-state">
            <div class="empty-icon">📭</div>
            <div class="empty-title">Aucun téléchargement</div>
            <div class="empty-desc">Les APKs téléchargées apparaîtront ici.</div>
          </div>`;
        return;
      }
      
      list.innerHTML = history.map(h => `
        <div class="history-item animate-fade-up">
          <div class="history-info">
            <div class="history-name">${h.name || h.package}</div>
            <div class="history-meta">
              <span>📦 ${h.package}</span>
              <span>🏷️ v${h.version || '?'}</span>
              <span>📏 ${h.size_fmt || '?'}</span>
              <span>⚡ ${h.speed_fmt || '?'}</span>
              <span>📅 ${(h.timestamp || '').slice(0, 10)}</span>
            </div>
          </div>
          <div class="history-actions-item">
            <a href="/api/file/${h.filename || ''}" class="btn-secondary" style="text-decoration:none;font-size:12px;padding:6px 12px">
              📁 Ouvrir
            </a>
          </div>
        </div>
      `).join('');
    });
}

function clearHistory() {
  if (!confirm('Effacer tout l\'historique ?')) return;
  
  fetch('/api/history/clear', { method: 'POST' })
    .then(r => r.json())
    .then(() => {
      refreshHistory();
      showToast('🗑️ Historique effacé', 'info');
    });
}

// ═══════════════════════════════════════════════
//  TOASTS
// ═══════════════════════════════════════════════

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// ═══════════════════════════════════════════════
//  KEYBOARD SHORTCUTS
// ═══════════════════════════════════════════════

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeModal();
  
  // Ctrl+K → focus search
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    document.getElementById('search-input')?.focus();
  }
});

// ═══════════════════════════════════════════════
//  INIT
// ═══════════════════════════════════════════════

// Load history on page load
document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('page-history').classList.contains('active')) {
    refreshHistory();
  }
});

// Observer for history page activation
const historyObserver = new MutationObserver(() => {
  if (document.getElementById('page-history').classList.contains('active')) {
    refreshHistory();
  }
});
historyObserver.observe(document.getElementById('page-history'), { attributes: true, attributeFilter: ['class'] });
