// tasks.js - Task management logic

let currentPage = 1;
let pageSize = 20;
let totalTasks = 0;
let currentFilterStatus = '';
let currentFilterType = '';
let pollInterval = null;
let selectedIds = new Set();

document.addEventListener('DOMContentLoaded', () => {
  loadTasks();
  startPolling();
  makeDraggable('batch-actions');
});

function startPolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(() => {
    loadTasks(true); // silent load
  }, 5000);
}

function stopPolling() {
  if (pollInterval) clearInterval(pollInterval);
}

async function loadTasks(silent = false) {
  const loadingEl = document.getElementById('loading');
  const emptyEl = document.getElementById('empty-state');
  const tbody = document.getElementById('tasks-table-body');
  
  if (!silent) {
    loadingEl.classList.remove('hidden');
    emptyEl.classList.add('hidden');
    tbody.innerHTML = '';
  }

  try {
    const type = document.getElementById('type-filter').value;
    const params = new URLSearchParams({
      page: currentPage,
      size: pageSize,
      sort_by: 'created_at',
      order: 'desc'
    });
    
    if (currentFilterStatus) params.append('status', currentFilterStatus);
    if (type) params.append('type', type);

    const adminKey = await ensureAdminKey({ redirect: true });
    const res = await fetch(`/v1/admin/tasks?${params.toString()}`, {
      headers: buildAuthHeaders(adminKey)
    });

    if (res.status === 401) {
      window.location.href = '/admin/login';
      return;
    }

    const data = await res.json();
    totalTasks = data.total;
    renderTable(data.data);
    updatePagination(data);
    
    if (!silent) loadingEl.classList.add('hidden');
    if (data.data.length === 0 && !silent) {
        emptyEl.classList.remove('hidden');
    } else {
        emptyEl.classList.add('hidden');
    }

  } catch (err) {
    console.error('Failed to load tasks:', err);
    if (!silent) {
        loadingEl.innerText = '加载失败，请重试';
        showToast('加载失败: ' + err.message, 'error');
    }
  }
}

function renderTable(tasks) {
  const tbody = document.getElementById('tasks-table-body');
  // 更新全选状态
  updateSelectAllState(tasks);
  
  tbody.innerHTML = tasks.map(task => {
    const statusBadge = getStatusBadge(task.status);
    const typeIcon = getTypeIcon(task.type);
    const payloadSummary = getPayloadSummary(task.payload);
    const resultPreview = getResultPreview(task);
    const progress = task.progress || 0;
    const date = new Date(task.created_at * 1000).toLocaleString();
    const isChecked = selectedIds.has(task.task_id) ? 'checked' : '';
    const rowClass = isChecked ? 'row-selected' : '';

    return `
      <tr class="hover:bg-gray-50 transition-colors ${rowClass}">
        <td class="text-center">
            <input type="checkbox" class="checkbox" value="${task.task_id}" 
                   onchange="toggleSelect('${task.task_id}')" ${isChecked}>
        </td>
        <td class="text-center">
            <div class="flex justify-center" title="${task.type}">${typeIcon}</div>
        </td>
        <td class="text-left font-mono text-xs select-all">${task.task_id}</td>
        <td class="text-center">${statusBadge}</td>
        <td class="text-center">
          <div class="w-full max-w-[100px] mx-auto">
            <div class="flex justify-between text-[10px] mb-1 text-gray-500">
              <span>${progress}%</span>
            </div>
            <div class="progress-bar-bg">
              <div class="progress-bar-fill" style="width: ${progress}%"></div>
            </div>
          </div>
        </td>
        <td class="text-left text-xs text-gray-600 truncate max-w-[200px]" title="${escapeHtml(JSON.stringify(task.payload))}">
            ${payloadSummary}
        </td>
        <td class="text-center">
            ${resultPreview}
        </td>
        <td class="text-center text-xs text-gray-500">${date}</td>
        <td class="text-center">
          <button onclick="showDetail('${task.task_id}')" class="geist-button-outline px-2 py-1 text-xs" title="查看详情">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
              <circle cx="12" cy="12" r="3"></circle>
            </svg>
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

function getStatusBadge(status) {
  const map = {
    'pending': '<span class="badge badge-gray">等待中</span>',
    'running': '<span class="badge badge-blue text-blue-600 bg-blue-50">进行中</span>',
    'completed': '<span class="badge badge-green">成功</span>',
    'failed': '<span class="badge badge-red">失败</span>'
  };
  return map[status] || `<span class="badge badge-gray">${status}</span>`;
}

function getTypeIcon(type) {
  if (type === 'video') {
    return `<svg class="text-purple-500" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polygon points="23 7 16 12 23 17 23 7"></polygon>
              <rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect>
            </svg>`;
  }
  return `<svg class="text-green-500" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
            <circle cx="8.5" cy="8.5" r="1.5"></circle>
            <polyline points="21 15 16 10 5 21"></polyline>
          </svg>`;
}

function getPayloadSummary(payload) {
  if (!payload) return '-';
  if (payload.prompt) return escapeHtml(payload.prompt.substring(0, 30) + (payload.prompt.length > 30 ? '...' : ''));
  if (payload.messages && payload.messages.length > 0) {
     const content = payload.messages[payload.messages.length-1].content;
     if (typeof content === 'string') return escapeHtml(content.substring(0, 30) + (content.length > 30 ? '...' : ''));
     return '[多模态内容]';
  }
  return '查看详情';
}

// 从视频任务 result 对象中提取视频 URL（兼容多种格式）
function extractVideoUrl(result) {
  if (!result) return null;
  // 直接字段
  if (result.video_url) return result.video_url;
  if (result.downloadUrl) return result.downloadUrl;
  // chat.completion 格式: choices[0].message.content
  let content = null;
  if (result.choices && result.choices.length > 0) {
    content = (result.choices[0]?.message?.content) || '';
  } else if (typeof result.content === 'string') {
    content = result.content;
  }
  if (!content) return null;
  // <video src="...">
  if (content.includes('<video')) {
    const m = content.match(/src="([^"]+)"/);
    if (m) return m[1];
  }
  // [video](url)
  const mdMatches = [...content.matchAll(/\[video\]\(([^)]+)\)/g)];
  if (mdMatches.length) return mdMatches[mdMatches.length - 1][1];
  // 裸 URL
  const urlMatches = content.match(/https?:\/\/[^\s<)"]+/g);
  if (urlMatches) return urlMatches[urlMatches.length - 1];
  return null;
}

// 从视频任务 result 对象中提取缩略图 URL
function extractThumbnailUrl(result) {
  if (!result) return null;
  if (result.thumbnail_url) return result.thumbnail_url;
  let content = null;
  if (result.choices && result.choices.length > 0) {
    content = (result.choices[0]?.message?.content) || '';
  }
  if (!content) return null;
  const m = content.match(/poster="([^"]+)"/);
  return m ? m[1] : null;
}

function getResultPreview(task) {
  if (task.status !== 'completed' || !task.result) return '-';

  // Video
  if (task.type === 'video') {
    const url = extractVideoUrl(task.result);
    const thumb = extractThumbnailUrl(task.result);
    if (!url) return '<span class="text-xs text-gray-400">无链接</span>';
    const safeUrl = escapeHtml(url);
    const thumbHtml = thumb
      ? `<img src="${escapeHtml(thumb)}" class="task-preview-img" style="width:56px;height:40px;">`
      : `<div class="flex items-center justify-center w-14 h-10 rounded border border-gray-200 bg-gray-50">
           <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#888" stroke-width="2">
             <polygon points="5 3 19 12 5 21 5 3"></polygon>
           </svg>
         </div>`;
    return `<div class="flex flex-col items-center gap-1 cursor-pointer" onclick="openVideoPreview('${safeUrl}')" title="点击预览视频">
              ${thumbHtml}
              <span class="text-[10px] text-blue-500 hover:underline leading-none">预览</span>
            </div>`;
  }

  // Image
  if (task.type === 'image') {
    if (task.result.data && task.result.data.length > 0) {
      const first = task.result.data[0];
      if (first.url) {
        return `<img src="${first.url}" class="task-preview-img" onclick="openImagePreview('${escapeHtml(first.url)}')" title="点击预览图片">`;
      }
      if (first.b64_json) {
        return `<img src="data:image/png;base64,${first.b64_json}" class="task-preview-img" onclick="openBase64Image('${first.b64_json}')" title="点击预览图片">`;
      }
    }
    return '<span class="text-xs text-gray-400">无图片</span>';
  }
  return '-';
}

function updatePagination(data) {
  const info = document.getElementById('pagination-info');
  const totalPages = Math.ceil(data.total / data.size) || 1;
  info.innerText = `第 ${data.page} / ${totalPages} 页 · 共 ${data.total} 条`;
  
  document.getElementById('page-prev').disabled = data.page <= 1;
  document.getElementById('page-next').disabled = data.page >= totalPages;
}

function changePage(delta) {
  const totalPages = Math.ceil(totalTasks / pageSize) || 1;
  const newPage = currentPage + delta;
  if (newPage >= 1 && newPage <= totalPages) {
    currentPage = newPage;
    loadTasks();
  }
}

function changePageSize() {
  pageSize = parseInt(document.getElementById('page-size').value);
  currentPage = 1;
  loadTasks();
}

function filterStatus(status) {
    currentFilterStatus = status;
    // Update tabs UI
    document.querySelectorAll('#status-tabs .tab-item').forEach(btn => {
        if (btn.dataset.status === status) btn.classList.add('active');
        else btn.classList.remove('active');
    });
    currentPage = 1;
    loadTasks();
}

// Selection Logic
function toggleSelect(taskId) {
    if (selectedIds.has(taskId)) {
        selectedIds.delete(taskId);
    } else {
        selectedIds.add(taskId);
    }
    updateUI();
}

function toggleSelectAll() {
    const checkboxes = document.querySelectorAll('#tasks-table-body .checkbox');
    const allChecked = Array.from(checkboxes).every(cb => cb.checked);
    
    checkboxes.forEach(cb => {
        if (!allChecked) {
            selectedIds.add(cb.value);
        } else {
            selectedIds.delete(cb.value);
        }
    });
    updateUI();
}

function updateSelectAllState(tasks) {
    const selectAllBtn = document.getElementById('select-all');
    if (!tasks || tasks.length === 0) {
        selectAllBtn.checked = false;
        selectAllBtn.indeterminate = false;
        return;
    }
    
    // Check if all visible tasks are selected
    const allSelected = tasks.every(t => selectedIds.has(t.task_id));
    // Check if some are selected
    const someSelected = tasks.some(t => selectedIds.has(t.task_id));
    
    selectAllBtn.checked = allSelected;
    selectAllBtn.indeterminate = !allSelected && someSelected;
}

function clearSelection() {
    selectedIds.clear();
    updateUI();
}

function updateUI() {
    // Re-render only checkbox states to avoid full reload flickering?
    // Better just update DOM elements directly for performance
    const checkboxes = document.querySelectorAll('#tasks-table-body .checkbox');
    checkboxes.forEach(cb => {
        cb.checked = selectedIds.has(cb.value);
        const tr = cb.closest('tr');
        if (cb.checked) tr.classList.add('row-selected');
        else tr.classList.remove('row-selected');
    });
    
    // Update Batch Bar
    const count = selectedIds.size;
    document.getElementById('selected-count').innerText = count;
    
    const batchBar = document.getElementById('batch-actions');
    if (count > 0) {
        batchBar.classList.remove('hidden');
    } else {
        batchBar.classList.add('hidden');
    }
    
    // Update select all checkbox visual state
    // We need current page tasks for this. 
    // Since loadTasks calls renderTable which calls updateSelectAllState, 
    // we might need to store current tasks globally or fetch from DOM
    const currentTaskIds = Array.from(checkboxes).map(cb => cb.value);
    if (currentTaskIds.length > 0) {
        const selectAllBtn = document.getElementById('select-all');
        const allSelected = currentTaskIds.every(id => selectedIds.has(id));
        const someSelected = currentTaskIds.some(id => selectedIds.has(id));
        selectAllBtn.checked = allSelected;
        selectAllBtn.indeterminate = !allSelected && someSelected;
    }
}

// Batch Actions
async function batchDelete() {
    if (selectedIds.size === 0) return;
    
    showConfirm(`确定要删除选中的 ${selectedIds.size} 个任务吗？此操作不可恢复。`, async () => {
        try {
            const adminKey = await ensureAdminKey({ redirect: true });
            const res = await fetch('/v1/admin/tasks/batch/delete', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...buildAuthHeaders(adminKey)
                },
                body: JSON.stringify({ task_ids: Array.from(selectedIds) })
            });
            
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || '删除失败');
            
            showToast(data.message || '删除成功', 'success');
            clearSelection();
            loadTasks();
        } catch (e) {
            showToast(e.message, 'error');
        }
    });
}

async function clearAllTasks() {
    const type = document.getElementById('type-filter').value;
    const typeText = type ? (type === 'video' ? '视频' : '图片') : '所有';
    const statusText = currentFilterStatus ? (currentFilterStatus === 'pending' ? '等待中' : currentFilterStatus) : '所有状态';
    
    showConfirm(`确定要清空【${typeText} - ${statusText}】下的所有任务吗？<br><br><span class="text-red-600 font-bold">⚠️ 警告：此操作将永久删除匹配筛选条件的所有任务！</span>`, async () => {
        try {
            const adminKey = await ensureAdminKey({ redirect: true });
            const payload = {};
            if (type) payload.type = type;
            if (currentFilterStatus) payload.status = currentFilterStatus;
            
            const res = await fetch('/v1/admin/tasks/clear', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...buildAuthHeaders(adminKey)
                },
                body: JSON.stringify(payload)
            });
            
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || '清空失败');
            
            showToast(data.message || '清空成功', 'success');
            clearSelection();
            loadTasks();
        } catch (e) {
            showToast(e.message, 'error');
        }
    });
}

// Confirm Dialog Helper
function showConfirm(message, onConfirm) {
    const dialog = document.getElementById('confirm-dialog');
    const msgEl = document.getElementById('confirm-message');
    const okBtn = document.getElementById('confirm-ok');
    const cancelBtn = document.getElementById('confirm-cancel');
    
    msgEl.innerHTML = message;
    dialog.classList.remove('hidden');
    requestAnimationFrame(() => dialog.classList.add('is-open'));
    
    const close = () => {
        dialog.classList.remove('is-open');
        setTimeout(() => dialog.classList.add('hidden'), 200);
        okBtn.onclick = null;
        cancelBtn.onclick = null;
    };
    
    okBtn.onclick = () => {
        close();
        onConfirm();
    };
    
    cancelBtn.onclick = close;
}

// Modal Logic
const modal = document.getElementById('detail-modal');

async function showDetail(taskId) {
  // Fetch fresh detail
  try {
      const adminKey = await ensureAdminKey({ redirect: true });
      const res = await fetch(`/v1/admin/tasks/${taskId}`, {
        headers: buildAuthHeaders(adminKey)
      });
      if (!res.ok) throw new Error('Failed to fetch details');
      const task = await res.json();
      
      document.getElementById('detail-id').innerText = task.task_id;
      document.getElementById('detail-time').innerText = new Date(task.created_at * 1000).toLocaleString();
      document.getElementById('detail-type').innerText = task.type.toUpperCase();
      document.getElementById('detail-status').innerHTML = getStatusBadge(task.status);
      document.getElementById('detail-payload').innerText = JSON.stringify(task.payload, null, 2);
      
      // Result
      const resContainer = document.getElementById('detail-result-container');
      const resContent = document.getElementById('detail-result');
      if (task.status === 'completed' && task.result) {
          resContainer.classList.remove('hidden');
          if (task.type === 'video') {
             const url = extractVideoUrl(task.result);
             const thumb = extractThumbnailUrl(task.result);
             if (url) {
                 resContent.innerHTML = `
                   <div class="space-y-2 w-full">
                     <video src="${escapeHtml(url)}" ${thumb ? `poster="${escapeHtml(thumb)}"` : ''} controls preload="metadata" class="max-w-full max-h-[300px] rounded border"></video>
                     <div class="text-xs text-gray-500 break-all font-mono">${escapeHtml(url)}</div>
                     <a href="${escapeHtml(url)}" target="_blank" class="text-xs text-blue-500 hover:underline">在新标签页打开</a>
                   </div>`;
             } else {
                 resContent.innerText = JSON.stringify(task.result, null, 2);
             }
          } else {
             // Image
             if (task.result.data && task.result.data.length > 0) {
                 const imgs = task.result.data.map(img => {
                     if (img.url) return `<img src="${img.url}" class="max-w-[200px] m-2 rounded border">`;
                     if (img.b64_json) return `<img src="data:image/png;base64,${img.b64_json}" class="max-w-[200px] m-2 rounded border">`;
                     return '';
                 }).join('');
                 resContent.innerHTML = `<div class="flex flex-wrap justify-center">${imgs}</div>`;
             } else {
                 resContent.innerText = JSON.stringify(task.result, null, 2);
             }
          }
      } else {
          resContainer.classList.add('hidden');
      }

      // Error
      const errContainer = document.getElementById('detail-error-container');
      if (task.status === 'failed' && task.error) {
          errContainer.classList.remove('hidden');
          document.getElementById('detail-error').innerText = task.error;
      } else {
          errContainer.classList.add('hidden');
      }

      modal.classList.remove('hidden');
      requestAnimationFrame(() => modal.classList.add('is-open'));
      
      // Pause polling while modal is open to avoid UI jumpiness? 
      // Actually real-time update in modal would be nice, but let's keep it simple.

  } catch (e) {
      showToast('获取详情失败', 'error');
  }
}

function closeDetailModal() {
  modal.classList.remove('is-open');
  setTimeout(() => modal.classList.add('hidden'), 200);
}

// Utils
function escapeHtml(text) {
  if (!text) return '';
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function openBase64Image(b64) {
    const win = window.open();
    win.document.write(`<iframe src="data:image/png;base64,${b64}" frameborder="0" style="border:0; top:0px; left:0px; bottom:0px; right:0px; width:100%; height:100%;" allowfullscreen></iframe>`);
}

function openImagePreview(url) {
    const modal = document.getElementById('preview-modal');
    const container = document.getElementById('preview-modal-body');
    container.innerHTML = `<img src="${url}" style="max-width:100%;max-height:80vh;border-radius:6px;display:block;margin:auto;">`;
    document.getElementById('preview-modal-link').href = url;
    modal.classList.remove('hidden');
    requestAnimationFrame(() => modal.classList.add('is-open'));
}

function openVideoPreview(url) {
    const modal = document.getElementById('preview-modal');
    const container = document.getElementById('preview-modal-body');
    container.innerHTML = `<video src="${url}" controls autoplay preload="metadata" style="max-width:100%;max-height:75vh;border-radius:6px;display:block;margin:auto;"></video>`;
    document.getElementById('preview-modal-link').href = url;
    modal.classList.remove('hidden');
    requestAnimationFrame(() => modal.classList.add('is-open'));
}

function closePreviewModal() {
    const modal = document.getElementById('preview-modal');
    // 暂停视频避免后台继续播放
    const video = modal.querySelector('video');
    if (video) video.pause();
    modal.classList.remove('is-open');
    setTimeout(() => {
        modal.classList.add('hidden');
        document.getElementById('preview-modal-body').innerHTML = '';
    }, 200);
}

// ESC to close
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const previewModal = document.getElementById('preview-modal');
        if (previewModal && !previewModal.classList.contains('hidden')) {
            closePreviewModal();
        } else if (!modal.classList.contains('hidden')) {
            closeDetailModal();
        }
    }
});
