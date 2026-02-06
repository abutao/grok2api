const API_BASE = 'http://localhost:8000';
const API_KEY = 'sk-D2jm4Z0kSTML2eovGrpGyehCXkr_aYS45JIxGYwYTAg';

let tasks = [];
let selectedTasks = new Set();
let refreshInterval = null;
let currentPage = 1;
let pageSize = 20;

async function apiRequest(url, options = {}) {
    const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${API_KEY}`,
        ...options.headers
    };

    const response = await fetch(`${API_BASE}${url}`, {
        ...options,
        headers
    });

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return response.json();
}

async function getTask(taskId) {
    return apiRequest(`/v1/video/tasks/${taskId}`);
}

async function listTasks() {
    return apiRequest('/v1/video/tasks');
}

async function cancelTask(taskId) {
    return apiRequest(`/v1/video/tasks/${taskId}`, {
        method: 'DELETE'
    });
}

function getStatusBadge(status) {
    const statusMap = {
        'pending': { class: 'pending', text: '等待中' },
        'running': { class: 'running', text: '生成中' },
        'completed': { class: 'completed', text: '已完成' },
        'failed': { class: 'failed', text: '失败' },
        'cancelled': { class: 'cancelled', text: '已取消' }
    };
    const info = statusMap[status] || { class: 'pending', text: status };
    return `<span class="task-status ${info.class}">${info.text}</span>`;
}

function formatTimestamp(timestamp) {
    if (!timestamp) return '-';
    const date = new Date(timestamp * 1000);
    return date.toLocaleString('zh-CN');
}

function renderTask(task) {
    const progressWidth = task.progress || 0;
    const canCancel = task.status === 'pending' || task.status === 'running';
    const isSelected = selectedTasks.has(task.task_id);
    
    return `
        <div class="task-item" data-task-id="${task.task_id}">
            <div class="task-checkbox">
                <input type="checkbox" 
                       class="task-select" 
                       value="${task.task_id}" 
                       ${isSelected ? 'checked' : ''} 
                       onchange="toggleTaskSelection('${task.task_id}')">
            </div>
            <div class="task-content">
                <div class="task-header">
                    <span class="task-id">${task.task_id}</span>
                    ${getStatusBadge(task.status)}
                </div>
                <div class="task-prompt">${task.prompt || '无提示词'}</div>
                <div class="task-info">
                    <div class="task-progress">
                        <div>进度: ${progressWidth}%</div>
                        <div class="task-progress-bar">
                            <div class="task-progress-bar-fill" style="width: ${progressWidth}%"></div>
                        </div>
                    </div>
                    <div>创建: ${formatTimestamp(task.created_at)}</div>
                </div>
                <div class="task-actions">
                    <button class="btn btn-secondary" onclick="showTaskDetail('${task.task_id}')">详情</button>
                    ${canCancel ? `<button class="btn btn-danger" onclick="cancelTaskHandler('${task.task_id}')">取消</button>` : ''}
                    ${task.status === 'completed' ? `<button class="btn btn-success" onclick="downloadVideo('${task.video_url}')">下载</button>` : ''}
                </div>
            </div>
        </div>
    `;
}

function renderTasks() {
    const taskList = document.getElementById('taskList');
    
    if (tasks.length === 0) {
        taskList.innerHTML = '<div class="empty-state">暂无任务</div>';
        updatePaginationControls(0, 1);
        return;
    }

    const totalCount = tasks.length;
    const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
    if (currentPage > totalPages) currentPage = totalPages;
    
    const startIndex = (currentPage - 1) * pageSize;
    const visibleTasks = tasks.slice(startIndex, startIndex + pageSize);
    
    taskList.innerHTML = visibleTasks.map(renderTask).join('');
    updatePaginationControls(totalCount, totalPages);
}

async function loadTasks() {
    try {
        const data = await listTasks();
        tasks = data.tasks || [];
        renderTasks();
        
        const hasRunningTasks = tasks.some(t => t.status === 'running' || t.status === 'pending');
        if (hasRunningTasks && !refreshInterval) {
            startAutoRefresh();
        }
    } catch (error) {
        console.error('加载任务失败:', error);
        alert('加载任务失败: ' + error.message);
    }
}

async function handleCreateTask(event) {
    event.preventDefault();
    
    const form = event.target;
    
    const data = {
        model: document.getElementById('model').value,
        prompt: document.getElementById('prompt').value,
        aspect_ratio: document.getElementById('aspectRatio').value,
        video_length: parseInt(document.getElementById('videoLength').value),
        resolution: document.getElementById('resolution').value,
        preset: document.getElementById('preset').value,
        image_url: document.getElementById('imageUrl').value || null
    };

    console.log('表单数据:', data);
    
    if (!data.prompt || data.prompt.trim() === '') {
        alert('请输入提示词');
        return;
    }
    
    try {
        const result = await apiRequest('/v1/video/tasks', {
            method: 'POST',
            body: JSON.stringify(data)
        });
        
        alert(`任务创建成功！\n任务 ID: ${result.task_id}`);
        form.reset();
        await loadTasks();
        startAutoRefresh();
    } catch (error) {
        console.error('创建任务失败:', error);
        alert('创建任务失败: ' + error.message);
    }
}

async function cancelTaskHandler(taskId) {
    if (!confirm('确定要取消这个任务吗？')) {
        return;
    }
    
    try {
        await cancelTask(taskId);
        alert('任务已取消');
        await loadTasks();
    } catch (error) {
        console.error('取消任务失败:', error);
        alert('取消任务失败: ' + error.message);
    }
}

function downloadVideo(url) {
    window.open(url, '_blank');
}

async function showTaskDetail(taskId) {
    try {
        const task = await getTask(taskId);
        const modal = document.getElementById('taskModal');
        const modalBody = document.getElementById('modalBody');
        
        let content = `
            <div class="detail-row">
                <div class="detail-label">任务 ID:</div>
                <div class="detail-value">${task.task_id}</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">状态:</div>
                <div class="detail-value">${getStatusBadge(task.status)}</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">进度:</div>
                <div class="detail-value">${task.progress}%</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">提示词:</div>
                <div class="detail-value">${task.prompt || '无'}</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">消息:</div>
                <div class="detail-value">${task.message || '-'}</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">创建时间:</div>
                <div class="detail-value">${formatTimestamp(task.created_at)}</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">开始时间:</div>
                <div class="detail-value">${formatTimestamp(task.started_at)}</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">完成时间:</div>
                <div class="detail-value">${formatTimestamp(task.completed_at)}</div>
            </div>
        `;
        
        if (task.error) {
            content += `
                <div class="error-message">
                    <strong>错误信息:</strong><br>
                    ${task.error}
                </div>
            `;
        }
        
        if (task.video_url) {
            content += `
                <div class="detail-row">
                    <div class="detail-label">视频链接:</div>
                    <div class="detail-value">
                        <a href="${task.video_url}" target="_blank" class="video-link">${task.video_url}</a>
                        <button class="copy-btn" onclick="copyToClipboard('${task.video_url}')" title="复制链接">复制</button>
                    </div>
                </div>
                <div class="video-preview">
                    <strong>视频预览:</strong>
                    <video controls>
                        <source src="${task.video_url}" type="video/mp4">
                    </video>
                </div>
            `;
        }
        
        if (task.thumbnail_url) {
            content += `
                <div class="detail-row">
                    <div class="detail-label">缩略图链接:</div>
                    <div class="detail-value">
                        <a href="${task.thumbnail_url}" target="_blank" class="video-link">${task.thumbnail_url}</a>
                        <button class="copy-btn" onclick="copyToClipboard('${task.thumbnail_url}')" title="复制链接">复制</button>
                    </div>
                </div>
                <div class="thumbnail-preview">
                    <strong>缩略图:</strong>
                    <img src="${task.thumbnail_url}" alt="缩略图">
                </div>
            `;
        }
        
        modalBody.innerHTML = content;
        modal.classList.add('show');
    } catch (error) {
        console.error('获取任务详情失败:', error);
        alert('获取任务详情失败: ' + error.message);
    }
}

function closeModal() {
    const modal = document.getElementById('taskModal');
    modal.classList.remove('show');
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        alert('链接已复制到剪贴板');
    }).catch(err => {
        console.error('复制失败:', err);
        alert('复制失败，请手动复制');
    });
}

function toggleTaskSelection(taskId) {
    if (selectedTasks.has(taskId)) {
        selectedTasks.delete(taskId);
    } else {
        selectedTasks.add(taskId);
    }
    updateDeleteButton();
}

function toggleSelectAll() {
    const selectAll = document.getElementById('selectAll');
    const checkboxes = document.querySelectorAll('.task-select');
    
    if (selectAll.checked) {
        checkboxes.forEach(cb => {
            selectedTasks.add(cb.value);
            cb.checked = true;
        });
    } else {
        checkboxes.forEach(cb => {
            selectedTasks.delete(cb.value);
            cb.checked = false;
        });
    }
    updateDeleteButton();
}

function updateDeleteButton() {
    const deleteSelectedBtn = document.getElementById('deleteSelectedBtn');
    if (selectedTasks.size > 0) {
        deleteSelectedBtn.style.display = 'inline-block';
        deleteSelectedBtn.textContent = `删除选中 (${selectedTasks.size})`;
    } else {
        deleteSelectedBtn.style.display = 'none';
    }
}

async function deleteSelectedTasks() {
    if (selectedTasks.size === 0) {
        alert('请先选择要删除的任务');
        return;
    }
    
    if (!confirm(`确定要删除选中的 ${selectedTasks.size} 个任务吗？`)) {
        return;
    }
    
    try {
        const result = await apiRequest('/v1/video/tasks', {
            method: 'DELETE',
            body: JSON.stringify({ task_ids: Array.from(selectedTasks) })
        });
        
        alert(result.message);
        selectedTasks.clear();
        document.getElementById('selectAll').checked = false;
        updateDeleteButton();
        await loadTasks();
    } catch (error) {
        console.error('删除任务失败:', error);
        alert('删除任务失败: ' + error.message);
    }
}

async function deleteFailedTasks() {
    if (!confirm('确定要清除所有失败的任务吗？')) {
        return;
    }
    
    try {
        const result = await apiRequest('/v1/video/tasks/status/failed', {
            method: 'DELETE'
        });
        
        alert(result.message);
        await loadTasks();
    } catch (error) {
        console.error('清除失败任务失败:', error);
        alert('清除失败任务失败: ' + error.message);
    }
}

async function clearAllTasks() {
    if (!confirm('确定要清除所有任务吗？此操作不可恢复！')) {
        return;
    }
    
    try {
        const result = await apiRequest('/v1/video/tasks/all', {
            method: 'DELETE'
        });
        
        alert(result.message);
        selectedTasks.clear();
        document.getElementById('selectAll').checked = false;
        updateDeleteButton();
        await loadTasks();
    } catch (error) {
        console.error('清除所有任务失败:', error);
        alert('清除所有任务失败: ' + error.message);
    }
}

function startAutoRefresh() {
    stopAutoRefresh();
    
    refreshInterval = setInterval(async () => {
        const hasRunningTasks = tasks.some(t => t.status === 'running' || t.status === 'pending');
        
        if (hasRunningTasks) {
            await loadTasks();
        } else {
            stopAutoRefresh();
        }
    }, 2000);
}

function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('createTaskForm').addEventListener('submit', handleCreateTask);
    document.getElementById('refreshBtn').addEventListener('click', loadTasks);
    document.getElementById('deleteSelectedBtn').addEventListener('click', deleteSelectedTasks);
    document.getElementById('deleteFailedBtn').addEventListener('click', deleteFailedTasks);
    document.getElementById('clearAllBtn').addEventListener('click', clearAllTasks);
    
    loadTasks();
    
    window.addEventListener('click', (event) => {
        const modal = document.getElementById('taskModal');
        if (event.target === modal) {
            closeModal();
        }
    });
    
    window.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            closeModal();
        }
    });
});

function updatePaginationControls(totalCount, totalPages) {
    const info = document.getElementById('pagination-info');
    const prevBtn = document.getElementById('page-prev');
    const nextBtn = document.getElementById('page-next');
    const sizeSelect = document.getElementById('page-size');

    if (sizeSelect && String(sizeSelect.value) !== String(pageSize)) {
        sizeSelect.value = String(pageSize);
    }

    if (info) {
        info.textContent = `第 ${totalCount === 0 ? 0 : currentPage} / ${totalPages} 页 · 共 ${totalCount} 条`;
    }
    if (prevBtn) prevBtn.disabled = totalCount === 0 || currentPage <= 1;
    if (nextBtn) nextBtn.disabled = totalCount === 0 || currentPage >= totalPages;
}

function goPrevPage() {
    if (currentPage <= 1) return;
    currentPage -= 1;
    renderTasks();
}

function goNextPage() {
    const totalCount = tasks.length;
    const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
    if (currentPage >= totalPages) return;
    currentPage += 1;
    renderTasks();
}

function changePageSize() {
    const sizeSelect = document.getElementById('page-size');
    const value = sizeSelect ? parseInt(sizeSelect.value, 10) : 0;
    if (!value || value === pageSize) return;
    pageSize = value;
    currentPage = 1;
    renderTasks();
}

function selectVisibleAll() {
    const totalCount = tasks.length;
    const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
    const startIndex = (currentPage - 1) * pageSize;
    const endIndex = Math.min(startIndex + pageSize, totalCount);
    
    for (let i = startIndex; i < endIndex; i++) {
        selectedTasks.add(tasks[i].task_id);
    }
    
    updateTaskCheckboxes();
    updateDeleteButton();
}

function selectAllFiltered() {
    tasks.forEach(task => {
        selectedTasks.add(task.task_id);
    });
    
    updateTaskCheckboxes();
    updateDeleteButton();
}

function clearAllSelection() {
    selectedTasks.clear();
    document.getElementById('selectAll').checked = false;
    updateTaskCheckboxes();
    updateDeleteButton();
}

function updateTaskCheckboxes() {
    const checkboxes = document.querySelectorAll('.task-select');
    checkboxes.forEach(cb => {
        cb.checked = selectedTasks.has(cb.value);
    });
}
