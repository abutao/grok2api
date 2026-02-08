(function () {
  const JOBS_TBODY = document.getElementById('jobs-tbody');
  const POLL_INTERVAL = 5000;
  let pollTimer = null;
  const selectedJobIds = new Set();
  let currentJobIds = [];

  function getApiKey() {
    var raw = (document.getElementById('tasks-api-key') || {}).value;
    if (typeof raw !== 'string') return null;
    raw = raw.trim();
    if (!raw) return null;
    return raw.startsWith('Bearer ') ? raw : 'Bearer ' + raw;
  }

  function showToast(message, type) {
    if (typeof window.showToast === 'function') {
      window.showToast(message, type || 'info');
    } else {
      alert(message);
    }
  }

  window.submitVideo = async function () {
    try {
      const apiKey = getApiKey();
      if (!apiKey) {
        showToast('请先填写 API Key（与调用接口时使用的 Key 一致）', 'error');
        return;
      }
      const prompt = (document.getElementById('video-prompt') || {}).value?.trim();
      if (!prompt) {
        showToast('请输入视频描述', 'error');
        return;
      }
      const refImageUrl = (document.getElementById('video-reference-image') || {}).value?.trim();
      const model = (document.getElementById('video-model') || {}).value || 'grok-imagine-1.0-video';
      const aspect = (document.getElementById('video-aspect') || {}).value || '16:9';
      const length = parseInt((document.getElementById('video-length') || {}).value || '6', 10);
      const resolution = (document.getElementById('video-resolution') || {}).value || '480p';
      const preset = (document.getElementById('video-preset') || {}).value || 'custom';
      const content = refImageUrl
        ? [{ type: 'text', text: prompt }, { type: 'image_url', image_url: { url: refImageUrl } }]
        : prompt;
      const body = {
        model: model,
        messages: [{ role: 'user', content: content }],
        stream: false,
        video_config: {
          aspect_ratio: aspect,
          video_length: length,
          resolution_name: resolution,
          preset: preset,
        },
      };
      const res = await fetch('/v1/video/generations/async', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': apiKey },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        showToast(data.detail || data.error || '提交失败', 'error');
        return;
      }
      showToast('已提交，job_id: ' + (data.job_id || data.task_id || '').slice(0, 8) + '...', 'success');
      loadJobs();
    } catch (e) {
      showToast('提交失败: ' + (e && e.message ? e.message : String(e)), 'error');
    }
  };

  window.submitImage = async function () {
    try {
      const apiKey = getApiKey();
      if (!apiKey) {
        showToast('请先填写 API Key（与调用接口时使用的 Key 一致）', 'error');
        return;
      }
      const prompt = (document.getElementById('image-prompt') || {}).value?.trim();
      if (!prompt) {
        showToast('请输入图片描述', 'error');
        return;
      }
      const model = (document.getElementById('image-model') || {}).value || 'grok-imagine-1.0';
      const n = parseInt((document.getElementById('image-n') || {}).value || '1', 10) || 1;
      const size = (document.getElementById('image-size') || {}).value || '1024x1024';
      const response_format = (document.getElementById('image-format') || {}).value || 'url';
      const body = { prompt, model: model, n: n, size: size, response_format: response_format, stream: false };
      const res = await fetch('/v1/images/generations/async', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': apiKey },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        showToast(data.detail || data.error || '提交失败', 'error');
        return;
      }
      showToast('已提交，job_id: ' + (data.job_id || '').slice(0, 8) + '...', 'success');
      loadJobs();
    } catch (e) {
      showToast('提交失败: ' + (e && e.message ? e.message : String(e)), 'error');
    }
  };

  function formatTime(ts) {
    if (ts == null) return '-';
    const d = new Date(ts * 1000);
    return d.toLocaleString('zh-CN');
  }

  function renderRequestPreview(payload) {
    if (!payload) return '-';
    if (payload.prompt) return payload.prompt.slice(0, 40) + (payload.prompt.length > 40 ? '…' : '');
    if (payload.messages && payload.messages[0]) {
      const c = payload.messages[0].content;
      return (typeof c === 'string' ? c : '[multimodal]').slice(0, 40) + '…';
    }
    return JSON.stringify(payload).slice(0, 30) + '…';
  }

  function renderResultPreview(job) {
    if (job.error) return '<span class="text-[var(--error)]">' + escapeHtml(job.error.slice(0, 80)) + '</span>';
    const r = job.result;
    if (!r) return '-';
    if (r.video_url) return '<a class="text-[var(--success)]" href="' + escapeHtml(r.video_url) + '" target="_blank">视频链接</a>';
    if (r.content && r.content.startsWith('http')) return '<a class="text-[var(--success)]" href="' + escapeHtml(r.content) + '" target="_blank">链接</a>';
    if (r.data && r.data[0]) {
      const first = r.data[0];
      if (first.url) return '<a href="' + escapeHtml(first.url) + '" target="_blank"><img src="' + escapeHtml(first.url) + '" alt="img" /></a>';
      if (first.b64_json) return '<span class="text-[var(--accents-5)]">base64 已生成</span>';
    }
    return '<span class="text-[var(--accents-5)]">' + escapeHtml(JSON.stringify(r).slice(0, 60)) + '…</span>';
  }

  function escapeHtml(s) {
    if (s == null) return '';
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }

  function updateSelectedCount() {
    const el = document.getElementById('selected-count');
    const btn = document.getElementById('btn-batch-delete');
    if (el) el.textContent = selectedJobIds.size;
    if (btn) btn.disabled = selectedJobIds.size === 0;
  }

  window.batchDeleteSelected = async function () {
    if (selectedJobIds.size === 0) return;
    if (!confirm('确定删除已选中的 ' + selectedJobIds.size + ' 项任务？')) return;
    const apiKey = getApiKey();
    if (!apiKey) return;
    const ids = Array.from(selectedJobIds);
    let ok = 0;
    let fail = 0;
    for (const jobId of ids) {
      try {
        const res = await fetch('/api/v1/admin/tasks/jobs/' + encodeURIComponent(jobId), {
          method: 'DELETE',
          headers: { 'Authorization': apiKey },
        });
        if (res.ok) ok++; else fail++;
      } catch (e) {
        fail++;
      }
    }
    selectedJobIds.clear();
    updateSelectedCount();
    showToast('已删除 ' + ok + ' 项' + (fail ? '，失败 ' + fail + ' 项' : ''), fail ? 'error' : 'success');
    loadJobs();
  };

  window.deleteJob = async function (jobId) {
    const apiKey = getApiKey();
    if (!apiKey) return;
    if (!confirm('确定删除该任务？')) return;
    try {
      const res = await fetch('/api/v1/admin/tasks/jobs/' + encodeURIComponent(jobId), {
        method: 'DELETE',
        headers: { 'Authorization': apiKey },
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        showToast(data.detail || '删除失败', 'error');
        return;
      }
      showToast('已删除', 'success');
      loadJobs();
    } catch (e) {
      showToast('请求失败: ' + e.message, 'error');
    }
  };

  window.clearAllJobs = async function () {
    const apiKey = getApiKey();
    if (!apiKey) return;
    if (!confirm('确定清空所有任务？此操作不可恢复。')) return;
    try {
      const res = await fetch('/api/v1/admin/tasks/jobs/clear', {
        method: 'POST',
        headers: { 'Authorization': apiKey },
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        showToast(data.detail || '清空失败', 'error');
        return;
      }
      const data = await res.json();
      const d = data.deleted || {};
      showToast('已清空：视频 ' + (d.video || 0) + ' 条，图片 ' + (d.image || 0) + ' 条', 'success');
      loadJobs();
    } catch (e) {
      showToast('请求失败: ' + e.message, 'error');
    }
  };

  window.showJobDetail = async function (jobId) {
    const apiKey = getApiKey();
    if (!apiKey) return;
    try {
      const res = await fetch('/api/v1/admin/tasks/jobs/' + encodeURIComponent(jobId), {
        headers: { 'Authorization': apiKey }
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        showToast(data.detail || '获取详情失败', 'error');
        return;
      }
      const job = await res.json();
      showJobDetailModal(job);
    } catch (e) {
      showToast('请求失败: ' + e.message, 'error');
    }
  };

  function showJobDetailModal(job) {
    const modal = document.createElement('div');
    modal.className = 'fixed inset-0 bg-black/50 flex items-center justify-center z-50';
    modal.onclick = function (e) {
      if (e.target === modal) modal.remove();
    };
    
    const typeLabel = job.type === 'video' ? '视频' : '图片';
    const statusClass = 'job-status-' + (job.status || 'pending');
    
    let resultHtml = '';
    if (job.error) {
      resultHtml = '<div class="mt-4 p-3 bg-red-50 border border-red-200 rounded text-red-700">' + 
                  '<div class="font-medium mb-1">错误信息</div>' +
                  '<div class="text-sm">' + escapeHtml(job.error) + '</div>' +
                  '</div>';
    } else if (job.result) {
      const r = job.result;
      if (r.video_url) {
        resultHtml = '<div class="mt-4">' +
                      '<div class="font-medium mb-2">视频结果</div>' +
                      '<a href="' + escapeHtml(r.video_url) + '" target="_blank" class="text-blue-600 hover:text-blue-800">' + escapeHtml(r.video_url) + '</a>' +
                      '</div>';
      } else if (r.content && r.content.startsWith('http')) {
        resultHtml = '<div class="mt-4">' +
                      '<div class="font-medium mb-2">结果链接</div>' +
                      '<a href="' + escapeHtml(r.content) + '" target="_blank" class="text-blue-600 hover:text-blue-800">' + escapeHtml(r.content) + '</a>' +
                      '</div>';
      } else if (r.data && r.data[0]) {
        const first = r.data[0];
        if (first.url) {
          resultHtml = '<div class="mt-4">' +
                        '<div class="font-medium mb-2">图片结果</div>' +
                        '<a href="' + escapeHtml(first.url) + '" target="_blank">' +
                        '<img src="' + escapeHtml(first.url) + '" alt="generated image" class="max-w-xs rounded" />' +
                        '</a>' +
                        '</div>';
        } else if (first.b64_json) {
          resultHtml = '<div class="mt-4">' +
                        '<div class="font-medium mb-2">图片结果</div>' +
                        '<span class="text-[var(--accents-5)]">base64 已生成</span>' +
                        '</div>';
        }
      } else {
        resultHtml = '<div class="mt-4 p-3 bg-gray-50 border border-gray-200 rounded">' +
                      '<div class="font-medium mb-1">原始结果</div>' +
                      '<pre class="text-xs overflow-auto max-h-40">' + escapeHtml(JSON.stringify(r, null, 2)) + '</pre>' +
                      '</div>';
      }
    }
    
    let requestPayloadHtml = '';
    if (job.request_payload) {
      requestPayloadHtml = '<div class="mt-4">' +
                        '<div class="font-medium mb-2">请求参数</div>' +
                        '<pre class="text-xs overflow-auto max-h-60 bg-gray-50 p-3 rounded">' + 
                        escapeHtml(JSON.stringify(job.request_payload, null, 2)) + 
                        '</pre>' +
                        '</div>';
    }
    
    modal.innerHTML = 
      '<div class="bg-white rounded-xl shadow-2xl max-w-3xl w-full mx-4 max-h-[90vh] overflow-y-auto">' +
        '<div class="flex justify-between items-center p-4 border-b">' +
          '<h3 class="text-lg font-semibold">任务详情</h3>' +
          '<button onclick="this.closest(\'.fixed\').remove()" class="text-gray-500 hover:text-gray-700 text-2xl">&times;</button>' +
        '</div>' +
        '<div class="p-4 space-y-3">' +
          '<div class="grid grid-cols-2 gap-4">' +
            '<div>' +
              '<div class="text-sm text-gray-500">任务类型</div>' +
              '<div class="font-medium">' + typeLabel + '</div>' +
            '</div>' +
            '<div>' +
              '<div class="text-sm text-gray-500">任务ID</div>' +
              '<div class="font-mono text-sm">' + escapeHtml(job.job_id || '') + '</div>' +
            '</div>' +
            '<div>' +
              '<div class="text-sm text-gray-500">状态</div>' +
              '<div class="font-medium ' + statusClass + '">' + escapeHtml(job.status || '-') + '</div>' +
            '</div>' +
            '<div>' +
              '<div class="text-sm text-gray-500">进度</div>' +
              '<div class="font-medium">' + (job.progress != null ? job.progress + '%' : '-') + '</div>' +
            '</div>' +
            '<div>' +
              '<div class="text-sm text-gray-500">创建时间</div>' +
              '<div class="text-sm">' + formatTime(job.created_at) + '</div>' +
            '</div>' +
            '<div>' +
              '<div class="text-sm text-gray-500">完成时间</div>' +
              '<div class="text-sm">' + formatTime(job.completed_at) + '</div>' +
            '</div>' +
          '</div>' +
          requestPayloadHtml +
          resultHtml +
        '</div>' +
      '</div>';
    
    document.body.appendChild(modal);
  }

  window.loadJobs = async function () {
    const apiKey = getApiKey();
    if (!apiKey) return;
    try {
      const res = await fetch('/api/v1/admin/tasks/jobs', { headers: { 'Authorization': apiKey } });
      if (!res.ok) {
        JOBS_TBODY.innerHTML = '<tr><td colspan="9" class="py-6 text-center text-[var(--error)]">加载失败</td></tr>';
        return;
      }
      const data = await res.json();
      const jobs = data.jobs || [];
      selectedJobIds.clear();
      currentJobIds = jobs.map(function (j) { return j.job_id; });
      updateSelectedCount();
      var selectAllEl = document.getElementById('select-all-jobs');
      if (selectAllEl) selectAllEl.checked = false;

      if (jobs.length === 0) {
        JOBS_TBODY.innerHTML = '<tr><td colspan="9" class="py-8 text-center text-[var(--accents-4)]">暂无任务</td></tr>';
        return;
      }
      JOBS_TBODY.innerHTML = jobs.map(function (j) {
        const typeClass = j.type === 'video' ? 'job-type-video' : 'job-type-image';
        const typeLabel = j.type === 'video' ? '视频' : '图片';
        const statusClass = 'job-status-' + (j.status || 'pending');
        const jobId = j.job_id || '';
        const jobIdAttr = escapeHtml(jobId).replace(/"/g, '&quot;');
        return (
          '<tr class="border-b border-[var(--border)] hover:bg-[var(--accents-1)]/50">' +
          '<td class="py-3 px-4 w-10"><input type="checkbox" class="job-cb rounded border-[var(--border)]" data-job-id="' + jobIdAttr + '" /></td>' +
          '<td class="py-3 px-4 ' + typeClass + '">' + typeLabel + '</td>' +
          '<td class="py-3 px-4 font-mono text-xs">' + escapeHtml(jobId.slice(0, 12)) + '…</td>' +
          '<td class="py-3 px-4 ' + statusClass + '">' + escapeHtml(j.status || '-') + '</td>' +
          '<td class="py-3 px-4">' + (j.progress != null ? j.progress + '%' : '-') + '</td>' +
          '<td class="py-3 px-4 job-request-preview" title="' + escapeHtml(JSON.stringify(j.request_payload || {})) + '">' + escapeHtml(renderRequestPreview(j.request_payload)) + '</td>' +
          '<td class="py-3 px-4 job-result-preview">' + renderResultPreview(j) + '</td>' +
          '<td class="py-3 px-4 text-[var(--accents-5)]">' + formatTime(j.created_at) + '</td>' +
          '<td class="py-3 px-4">' +
            '<button type="button" onclick="showJobDetail(\'' + jobIdAttr + '\')" class="geist-button-outline text-xs px-2 py-1">详情</button>' +
          '</td>' +
          '</tr>'
        );
      }).join('');

      JOBS_TBODY.querySelectorAll('.job-cb').forEach(function (cb) {
        cb.addEventListener('change', function () {
          var id = cb.getAttribute('data-job-id');
          if (cb.checked) selectedJobIds.add(id); else selectedJobIds.delete(id);
          updateSelectedCount();
          var sa = document.getElementById('select-all-jobs');
          if (sa) sa.checked = selectedJobIds.size === currentJobIds.length && currentJobIds.length > 0;
        });
      });
      if (selectAllEl) {
        selectAllEl.onchange = function () {
          var checked = this.checked;
          selectedJobIds.clear();
          if (checked) currentJobIds.forEach(function (id) { selectedJobIds.add(id); });
          JOBS_TBODY.querySelectorAll('.job-cb').forEach(function (cb) { cb.checked = checked; });
          updateSelectedCount();
        };
      }
    } catch (e) {
      JOBS_TBODY.innerHTML = '<tr><td colspan="8" class="py-6 text-center text-[var(--error)]">' + escapeHtml(e.message) + '</td></tr>';
    }
  };

  function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(loadJobs, POLL_INTERVAL);
  }

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') {
      loadJobs();
      startPolling();
    } else {
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = null;
    }
  });

  async function tryFillApiKeyFromConfig() {
    var getKey = window.tryGetApiKeyQuiet || window.ensureApiKey;
    if (typeof getKey !== 'function') return;
    try {
      var apiKey = await getKey();
      if (!apiKey) return;
      var input = document.getElementById('tasks-api-key');
      var block = document.getElementById('tasks-api-key-block');
      var hint = document.getElementById('tasks-api-key-auto-hint');
      if (input) {
        input.value = apiKey.startsWith('Bearer ') ? apiKey.slice(7) : apiKey;
      }
      if (block) block.classList.add('hidden');
      if (hint) hint.classList.remove('hidden');
    } catch (e) {
      /* ignore */
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      tryFillApiKeyFromConfig().then(function () {
        loadJobs();
        startPolling();
      });
    });
  } else {
    tryFillApiKeyFromConfig().then(function () {
      loadJobs();
      startPolling();
    });
  }
})();
