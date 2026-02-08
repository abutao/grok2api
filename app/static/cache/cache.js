let currentPage = 1;
let pageSize = 20;
let totalItems = 0;

async function loadLocalStats() {
  try {
    const response = await apiRequest('/api/v1/admin/cache');
    document.getElementById('image-count').textContent = response.image_count || 0;
    document.getElementById('video-count').textContent = response.video_count || 0;
    document.getElementById('total-size').textContent = formatSize(response.total_size || 0);
  } catch (error) {
    console.error('Failed to load local stats:', error);
    showToast('加载本地缓存统计失败', 'error');
  }
}

async function loadOnlineStats() {
  try {
    const response = await apiRequest('/api/v1/admin/cache/online/stats');
    document.getElementById('online-image-count').textContent = response.image_count || 0;
    document.getElementById('online-video-count').textContent = response.video_count || 0;
    document.getElementById('online-total-count').textContent = response.total_count || 0;
  } catch (error) {
    console.error('Failed to load online stats:', error);
    showToast('加载在线缓存统计失败', 'error');
  }
}

async function loadLocalCache() {
  const cacheType = document.getElementById('cache-type').value;
  const cacheList = document.getElementById('cache-list');
  
  try {
    cacheList.innerHTML = '<div class="loading">加载中...</div>';
    
    const response = await apiRequest(`/api/v1/admin/cache/list?type=${cacheType}&page=${currentPage}&page_size=${pageSize}`);
    
    totalItems = response.total || 0;
    const items = response.items || [];
    
    if (items.length === 0) {
      cacheList.innerHTML = '<div class="text-center py-8 text-[var(--accents-4)]">暂无缓存文件</div>';
      return;
    }
    
    cacheList.innerHTML = items.map(item => `
      <div class="cache-item">
        <div class="cache-item-name" title="${item.name}">${item.name}</div>
        <div class="cache-item-size">${formatSize(item.size)}</div>
        <div class="cache-item-actions">
          <button onclick="deleteCacheItem('${cacheType}', '${item.name}')" class="geist-button-outline text-xs px-2 py-1 text-red-600">
            删除
          </button>
        </div>
      </div>
    `).join('');
    
    updatePagination();
  } catch (error) {
    console.error('Failed to load local cache:', error);
    cacheList.innerHTML = '<div class="text-center py-8 text-red-600">加载失败</div>';
    showToast('加载缓存列表失败', 'error');
  }
}

async function deleteCacheItem(type, name) {
  if (!confirm(`确定要删除 ${name} 吗？`)) {
    return;
  }
  
  try {
    await apiRequest('/api/v1/admin/cache/item/delete', {
      method: 'POST',
      body: JSON.stringify({ type, name })
    });
    
    showToast('删除成功', 'success');
    await loadLocalCache();
    await loadLocalStats();
  } catch (error) {
    console.error('Failed to delete cache item:', error);
    showToast('删除失败: ' + error.message, 'error');
  }
}

async function clearLocalCache(type) {
  if (!confirm(`确定要清理所有${type === 'image' ? '图片' : '视频'}缓存吗？`)) {
    return;
  }
  
  try {
    await apiRequest('/api/v1/admin/cache/clear', {
      method: 'POST',
      body: JSON.stringify({ type })
    });
    
    showToast('清理成功', 'success');
    await loadLocalCache();
    await loadLocalStats();
  } catch (error) {
    console.error('Failed to clear cache:', error);
    showToast('清理失败: ' + error.message, 'error');
  }
}

async function loadOnlineCache() {
  if (!confirm('确定要加载在线缓存吗？这可能需要一些时间。')) {
    return;
  }
  
  try {
    showToast('正在加载在线缓存...', 'info');
    
    const response = await apiRequest('/api/v1/admin/cache/online/load/async', {
      method: 'POST',
      body: JSON.stringify({})
    });
    
    showToast('在线缓存加载任务已创建', 'success');
    await loadOnlineStats();
  } catch (error) {
    console.error('Failed to load online cache:', error);
    showToast('加载失败: ' + error.message, 'error');
  }
}

async function clearOnlineCache() {
  if (!confirm('确定要清理所有在线缓存吗？此操作不可恢复！')) {
    return;
  }
  
  try {
    await apiRequest('/api/v1/admin/cache/online/clear', {
      method: 'POST',
      body: JSON.stringify({})
    });
    
    showToast('清理成功', 'success');
    await loadOnlineStats();
  } catch (error) {
    console.error('Failed to clear online cache:', error);
    showToast('清理失败: ' + error.message, 'error');
  }
}

function updatePagination() {
  const pagination = document.getElementById('pagination');
  const totalPages = Math.ceil(totalItems / pageSize);
  
  if (totalPages <= 1) {
    pagination.innerHTML = '';
    return;
  }
  
  let html = `
    <button onclick="goToPage(${currentPage - 1})" class="pagination-btn" ${currentPage === 1 ? 'disabled' : ''}>
      上一页
    </button>
    <span class="text-sm text-[var(--accents-4)]">
      ${currentPage} / ${totalPages}
    </span>
    <button onclick="goToPage(${currentPage + 1})" class="pagination-btn" ${currentPage === totalPages ? 'disabled' : ''}>
      下一页
    </button>
  `;
  
  pagination.innerHTML = html;
}

function goToPage(page) {
  currentPage = page;
  loadLocalCache();
}

function formatSize(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

async function apiRequest(url, options = {}) {
  const apiKey = localStorage.getItem('admin_api_key');
  const headers = {
    'Content-Type': 'application/json',
    'X-API-Key': apiKey
  };
  
  const config = {
    method: 'GET',
    ...options,
    headers: {
      ...headers,
      ...options.headers
    }
  };
  
  const response = await fetch(url, config);
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || error.message || '请求失败');
  }
  
  return response.json();
}

document.addEventListener('DOMContentLoaded', () => {
  loadLocalStats();
  loadOnlineStats();
  loadLocalCache();
});
