// ── 状态 ────────────────────────────────────────────────
let jobId = null;
let fileBytes = null;
let filename = '';
let allScreenshots = [];
let currentPage = 0;
let lightboxIndex = 0;
const PAGE_SIZE = 6;

// ── DOM 引用 ─────────────────────────────────────────────
const dropZone      = document.getElementById('drop-zone');
const fileInput     = document.getElementById('file-input');
const fileLabel     = document.getElementById('file-label');
const btnStart      = document.getElementById('btn-start');
const btnGenerate   = document.getElementById('btn-generate');
const btnDownload   = document.getElementById('btn-download');
const statusLabel   = document.getElementById('status-label');
const progressSection = document.getElementById('progress-section');
const progressBar   = document.getElementById('progress-bar');
const log           = document.getElementById('log');
const previewSection = document.getElementById('preview-section');
const previewGrid   = document.getElementById('preview-grid');
const previewCount  = document.getElementById('preview-count');
const pageLabel     = document.getElementById('page-label');
const btnPrev       = document.getElementById('btn-prev');
const btnNext       = document.getElementById('btn-next');
const historyPanel  = document.getElementById('history-panel');
const historyOverlay = document.getElementById('history-overlay');
const historyList   = document.getElementById('history-list');

// ── 参数折叠 ─────────────────────────────────────────────
const paramsToggle  = document.getElementById('params-toggle');
const paramsBody    = document.getElementById('params-body');
const paramsChevron = document.getElementById('params-chevron');
paramsToggle.addEventListener('click', () => {
  const open = !paramsBody.classList.contains('hidden');
  paramsBody.classList.toggle('hidden', open);
  paramsChevron.style.transform = open ? 'rotate(0deg)' : 'rotate(180deg)';
});

// ── 上传 ─────────────────────────────────────────────────
dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('dragover'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  const f = e.dataTransfer.files[0];
  if (f) handleFile(f);
});
fileInput.addEventListener('change', e => {
  const f = e.target.files[0];
  if (f) handleFile(f);
});

function handleFile(f) {
  filename = f.name;
  const reader = new FileReader();
  reader.onload = ev => {
    fileBytes = ev.target.result;
    const mb = (f.size / 1024 / 1024).toFixed(1);
    fileLabel.textContent = `已选择：${f.name}（${mb} MB）`;
    fileLabel.className = 'mt-2 text-xs text-indigo-600 font-medium';
    btnStart.disabled = false;
  };
  reader.readAsArrayBuffer(f);
}

// ── 开始处理 ─────────────────────────────────────────────
btnStart.addEventListener('click', async () => {
  if (!fileBytes) return;

  setButtons({ start: false, generate: false, download: false });
  logClear();
  setProgress(0);
  allScreenshots = [];
  currentPage = 0;
  previewGrid.innerHTML = '';
  previewSection.classList.add('hidden');
  progressSection.classList.remove('hidden');
  setStatus('正在上传视频…');

  try {
    const blob = new Blob([fileBytes]);
    const form = new FormData();
    form.append('file', blob, filename);

    const uploadRes = await fetch('./jobs/upload', { method: 'POST', body: form });
    if (!uploadRes.ok) throw new Error((await uploadRes.json()).detail);
    const { job_id } = await uploadRes.json();
    jobId = job_id;

    setStatus('上传成功，启动处理…');

    const params = {
      sample_fps:       parseInt(document.getElementById('p-fps').value),
      change_threshold: parseFloat(document.getElementById('p-threshold').value),
      stable_seconds:   parseFloat(document.getElementById('p-stable').value),
      hash_threshold:   parseInt(document.getElementById('p-hash').value),
    };
    const procRes = await fetch(`./jobs/${jobId}/process`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!procRes.ok) throw new Error((await procRes.json()).detail);

    listenSSE(jobId);
  } catch (err) {
    showToast(`错误：${err.message}`, 'error');
    setStatus(`错误：${err.message}`);
    setButtons({ start: true });
  }
});

// ── SSE 进度 ─────────────────────────────────────────────
function listenSSE(jid) {
  setStatus('处理中…');
  const es = new EventSource(`./jobs/${jid}/progress`);

  es.onmessage = async e => {
    const ev = JSON.parse(e.data);

    if (ev.type === 'progress') {
      if (ev.total > 0) setProgress(ev.current / ev.total * 100);
      logAppend(`${ev.message}  [已保存 ${ev.saved} 张]`);

    } else if (ev.type === 'done') {
      es.close();
      setProgress(100);
      logAppend(`✓ 处理完成，共提取 ${ev.saved} 张截图`);
      setStatus(`处理完成，共 ${ev.saved} 张截图`);
      setButtons({ generate: true });
      await loadScreenshots(jid);

    } else if (ev.type === 'error') {
      es.close();
      logAppend(`✗ 错误：${ev.message}`);
      setStatus(`处理失败：${ev.message}`);
      showToast(`处理失败：${ev.message}`, 'error');
      setButtons({ start: true });
    }
  };

  es.onerror = () => {
    es.close();
    setStatus('SSE 连接断开');
    setButtons({ start: true });
  };
}

// ── 截图预览 ─────────────────────────────────────────────
async function loadScreenshots(jid) {
  const res = await fetch(`./jobs/${jid}/screenshots`);
  if (!res.ok) return;
  const data = await res.json();
  allScreenshots = data.screenshots;
  currentPage = 0;
  previewSection.classList.remove('hidden');
  previewCount.textContent = `（共 ${allScreenshots.length} 张）`;
  renderPage(jid);
}

function renderPage(jid) {
  const total = allScreenshots.length;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const start = currentPage * PAGE_SIZE;
  const pageFiles = allScreenshots.slice(start, start + PAGE_SIZE);

  previewGrid.innerHTML = '';
  pageFiles.forEach((name, idx) => {
    const globalIdx = start + idx;
    const url = `./jobs/${jid}/screenshots/${name}`;
    const card = document.createElement('div');
    card.className = 'rounded-lg overflow-hidden border border-slate-200 bg-slate-50 cursor-pointer hover:border-indigo-400 hover:shadow-md transition-all';
    card.addEventListener('click', () => openLightbox(globalIdx));
    card.innerHTML = `
      <img src="${url}" alt="${name}" class="w-full object-cover aspect-video" loading="lazy"/>
      <p class="text-xs text-center text-slate-400 py-1 px-1 truncate">${name}</p>`;
    previewGrid.appendChild(card);
  });

  pageLabel.textContent = `${currentPage + 1} / ${totalPages}`;
  btnPrev.disabled = currentPage === 0;
  btnNext.disabled = currentPage >= totalPages - 1;
}

btnPrev.addEventListener('click', () => {
  if (currentPage > 0) { currentPage--; renderPage(jobId); }
});
btnNext.addEventListener('click', () => {
  const totalPages = Math.ceil(allScreenshots.length / PAGE_SIZE);
  if (currentPage < totalPages - 1) { currentPage++; renderPage(jobId); }
});

// ── 生成 DOCX ────────────────────────────────────────────
btnGenerate.addEventListener('click', async () => {
  if (!jobId) return;
  setButtons({ generate: false });
  setStatus('生成 DOCX 中…');
  try {
    const res = await fetch(`./jobs/${jobId}/generate-docx`, { method: 'POST' });
    if (!res.ok) throw new Error((await res.json()).detail);
    pollUntilDone(jobId);
  } catch (err) {
    showToast(`生成失败：${err.message}`, 'error');
    setStatus(`生成失败：${err.message}`);
    setButtons({ generate: true });
  }
});

async function pollUntilDone(jid) {
  for (let i = 0; i < 120; i++) {
    await sleep(1000);
    try {
      const res = await fetch(`./jobs/${jid}`);
      if (!res.ok) continue;
      const job = await res.json();
      if (job.status === 'done') {
        setStatus('DOCX 已生成');
        setButtons({ download: true });
        showToast('DOCX 生成完成！', 'success');
        openDocxModal(jid);
        return;
      } else if (job.status === 'error') {
        setStatus(`生成失败：${job.error_message}`);
        showToast(`生成失败：${job.error_message}`, 'error');
        setButtons({ generate: true });
        return;
      }
    } catch (_) {}
  }
  setStatus('生成超时，请重试');
  setButtons({ generate: true });
}

// ── 下载 ─────────────────────────────────────────────────
btnDownload.addEventListener('click', () => {
  if (jobId) window.open(`./jobs/${jobId}/download`, '_blank');
});

// ── 历史记录 ─────────────────────────────────────────────
document.getElementById('btn-history').addEventListener('click', openHistory);

function openHistory() {
  historyPanel.classList.remove('translate-x-full');
  historyOverlay.classList.remove('hidden');
  loadHistory();
}

function closeHistory() {
  historyPanel.classList.add('translate-x-full');
  historyOverlay.classList.add('hidden');
}

async function loadHistory() {
  historyList.innerHTML = '<p class="px-6 py-8 text-sm text-slate-400 text-center">加载中…</p>';
  try {
    const res = await fetch('./jobs');
    if (!res.ok) throw new Error('请求失败');
    const jobs = await res.json();

    if (jobs.length === 0) {
      historyList.innerHTML = '<p class="px-6 py-8 text-sm text-slate-400 text-center">暂无历史记录</p>';
      return;
    }

    historyList.innerHTML = '';
    jobs.forEach(job => {
      const dt = new Date(job.created_at).toLocaleString('zh-CN', { hour12: false });
      const badgeClass = {
        pending: 'bg-slate-100 text-slate-600',
        processing: 'bg-blue-100 text-blue-700',
        ready: 'bg-yellow-100 text-yellow-700',
        generating: 'bg-purple-100 text-purple-700',
        done: 'bg-green-100 text-green-700',
        error: 'bg-red-100 text-red-700',
      }[job.status] || 'bg-slate-100 text-slate-600';

      const statusLabel = {
        pending: '等待中', processing: '处理中', ready: '待生成',
        generating: '生成中', done: '完成', error: '错误',
      }[job.status] || job.status;

      const item = document.createElement('div');
      item.className = 'px-6 py-4 hover:bg-slate-50 transition-colors';
      item.innerHTML = `
        <div class="flex items-start justify-between gap-4">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-1">
              <span class="text-xs font-medium px-2 py-0.5 rounded-full ${badgeClass}">${statusLabel}</span>
              ${job.screenshot_count > 0
                ? `<span class="text-xs text-slate-400">${job.screenshot_count} 张截图</span>`
                : ''}
            </div>
            <p class="text-sm font-medium text-slate-700 truncate">${job.video_filename || '未知文件'}</p>
            <p class="text-xs text-slate-400 mt-0.5">${dt}</p>
            ${job.error_message
              ? `<p class="text-xs text-red-500 mt-1 truncate">${job.error_message}</p>`
              : ''}
          </div>
          <div class="flex items-center gap-1 shrink-0">
            ${job.has_screenshots
              ? `<button onclick="viewHistoryJob('${job.job_id}')"
                   class="text-xs px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200
                          text-slate-700 font-medium transition-colors">查看</button>`
              : ''}
            ${job.has_docx
              ? `<a href="./jobs/${job.job_id}/download" target="_blank"
                   class="text-xs px-3 py-1.5 rounded-lg bg-emerald-100 hover:bg-emerald-200
                          text-emerald-700 font-medium transition-colors">下载</a>`
              : ''}
            <button onclick="deleteJob('${job.job_id}', this)"
              class="text-xs px-3 py-1.5 rounded-lg bg-red-50 hover:bg-red-100
                     text-red-600 font-medium transition-colors">删除</button>
          </div>
        </div>`;
      historyList.appendChild(item);
    });
  } catch (err) {
    historyList.innerHTML = `<p class="px-6 py-8 text-sm text-red-400 text-center">加载失败：${err.message}</p>`;
  }
}

async function viewHistoryJob(jid) {
  closeHistory();
  jobId = jid;
  allScreenshots = [];
  currentPage = 0;

  // 根据任务状态启用对应按钮
  try {
    const res = await fetch(`./jobs/${jid}`);
    if (res.ok) {
      const job = await res.json();
      setButtons({
        start:    !!fileBytes,
        generate: job.has_screenshots,
        download: job.has_docx,
      });
      setStatus(`已加载历史记录：${job.video_filename || jid}`);
    }
  } catch (_) {}

  await loadScreenshots(jid);
  previewSection.scrollIntoView({ behavior: 'smooth' });
}

async function deleteJob(jid, btn) {
  btn.disabled = true;
  btn.textContent = '…';
  try {
    const res = await fetch(`./jobs/${jid}`, { method: 'DELETE' });
    if (!res.ok) throw new Error((await res.json()).detail);
    showToast('已删除', 'success');
    // 移除对应列表项
    btn.closest('div.px-6').remove();
    if (historyList.children.length === 0) {
      historyList.innerHTML = '<p class="px-6 py-8 text-sm text-slate-400 text-center">暂无历史记录</p>';
    }
    // 若删除的是当前正在展示的任务，则重置页面状态
    if (jid === jobId) {
      jobId = null;
      allScreenshots = [];
      currentPage = 0;
      previewSection.classList.add('hidden');
      progressSection.classList.add('hidden');
      previewGrid.innerHTML = '';
      logClear();
      setProgress(0);
      setStatus('');
      setButtons({ start: !!fileBytes, generate: false, download: false });
    }
  } catch (err) {
    showToast(`删除失败：${err.message}`, 'error');
    btn.disabled = false;
    btn.textContent = '删除';
  }
}

// ── 工具函数 ─────────────────────────────────────────────
function setStatus(text) { statusLabel.textContent = text; }

function setProgress(pct) {
  progressBar.style.width = `${Math.min(100, pct)}%`;
}

function logAppend(text) {
  log.textContent += text + '\n';
  log.scrollTop = log.scrollHeight;
}

function logClear() { log.textContent = ''; }

function setButtons({ start, generate, download } = {}) {
  if (start !== undefined)    btnStart.disabled    = !start;
  if (generate !== undefined) btnGenerate.disabled = !generate;
  if (download !== undefined) btnDownload.disabled = !download;
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── 灯箱 ──────────────────────────────────────────────
function openLightbox(idx) {
  lightboxIndex = idx;
  const lb = document.getElementById('lightbox');
  lb.classList.remove('hidden');
  lb.classList.add('flex');
  lbRender();
  document.addEventListener('keydown', lbKeyHandler);
}

function closeLightbox() {
  const lb = document.getElementById('lightbox');
  lb.classList.add('hidden');
  lb.classList.remove('flex');
  document.removeEventListener('keydown', lbKeyHandler);
}

function lbRender() {
  const total = allScreenshots.length;
  const name = allScreenshots[lightboxIndex];
  document.getElementById('lb-img').src = `./jobs/${jobId}/screenshots/${name}`;
  document.getElementById('lb-counter').textContent = `${lightboxIndex + 1} / ${total}`;
  document.getElementById('lb-name').textContent = name;
  document.getElementById('lb-prev').disabled = lightboxIndex === 0;
  document.getElementById('lb-next').disabled = lightboxIndex >= total - 1;
}

function lbNav(dir) {
  const next = lightboxIndex + dir;
  if (next >= 0 && next < allScreenshots.length) {
    lightboxIndex = next;
    lbRender();
  }
}

function lbBackdropClick(e) {
  if (e.target === document.getElementById('lightbox')) closeLightbox();
}

function lbKeyHandler(e) {
  if (e.key === 'ArrowLeft')  lbNav(-1);
  if (e.key === 'ArrowRight') lbNav(1);
  if (e.key === 'Escape')     closeLightbox();
}

// ── DOCX 完成弹窗 ───────────────────────────────────────
function openDocxModal(jid) {
  const modal = document.getElementById('docx-modal');
  document.getElementById('docx-modal-info').textContent =
    `共 ${allScreenshots.length} 张截图`;

  // 重置预览区状态
  const loading = document.getElementById('docx-preview-loading');
  const errEl   = document.getElementById('docx-preview-error');
  const body    = document.getElementById('docx-preview-body');
  loading.classList.remove('hidden'); loading.classList.add('flex');
  errEl.classList.add('hidden');      errEl.classList.remove('flex');
  body.classList.add('hidden');
  body.innerHTML = '';

  document.getElementById('docx-modal-dl').onclick = () => {
    window.open(`./jobs/${jid}/download`, '_blank');
  };

  modal.classList.remove('hidden');
  modal.classList.add('flex');

  // 异步加载并渲染 DOCX
  fetch(`./jobs/${jid}/download`)
    .then(r => { if (!r.ok) throw new Error(r.status); return r.arrayBuffer(); })
    .then(buf => {
      const options = {
        ignoreWidth: true,
        ignoreFonts: false,
        breakPages: true,
        useBase64URL: true,
      };
      return window.docx.renderAsync(buf, body, null, options);
    })
    .then(() => {
      loading.classList.add('hidden');   loading.classList.remove('flex');
      body.classList.remove('hidden');
    })
    .catch(err => {
      console.error('docx-preview error:', err);
      loading.classList.add('hidden');   loading.classList.remove('flex');
      errEl.classList.remove('hidden');  errEl.classList.add('flex');
    });
}

function closeDocxModal(e) {
  if (e && e.target !== document.getElementById('docx-modal')) return;
  const modal = document.getElementById('docx-modal');
  modal.classList.add('hidden');
  modal.classList.remove('flex');
}

function showToast(msg, type = 'success') {
  const toast = document.getElementById('toast');
  toast.textContent = msg;
  toast.className = [
    'fixed bottom-6 left-1/2 -translate-x-1/2 px-5 py-3 rounded-xl text-sm font-medium',
    'text-white shadow-lg z-50 transition-all duration-300',
    type === 'error' ? 'bg-red-500' : 'bg-emerald-500',
  ].join(' ');
  toast.style.opacity = '1';
  setTimeout(() => { toast.style.opacity = '0'; }, 3000);
}
