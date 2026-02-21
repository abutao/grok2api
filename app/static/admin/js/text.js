// text.js - Admin Task Creation Logic (Refactored for API Token Separation)

// --- State Management ---
const state = {
    pageAccessKey: null, // Admin Key for page access
    taskToken: null,     // API Token for task submission
    mainType: 'video',   // 'video' | 'image'
    subMode: 'text',     // 'text' | 'image'
    models: {
        video: [
            { id: 'grok-imagine-1.0-video', name: 'Grok Video 1.0', tags: ['文生视频', '图生视频'] }
        ],
        image: [
            { id: 'grok-imagine-1.0', name: 'Grok Imagine 1.0', tags: ['文生图'] },
            { id: 'grok-imagine-1.0-edit', name: 'Grok Edit 1.0', tags: ['图生图/编辑'] }
        ]
    },
    config: {
        model: '',
        prompt: '',
        imgPrompt: '', 
        refImage: null, 
        ratio: '3:2',
        resolution: '720p',
        duration: '6',
        preset: 'normal',
        taskName: ''
    },
    isSubmitting: false,
    pollInterval: null,
    currentTaskId: null
};

// --- DOM Elements ---
const els = {
    typeCards: document.querySelectorAll('.task-type-card'),
    subTabBtns: document.querySelectorAll('.sub-tab-btn'),
    subTabsContainer: document.getElementById('subTabsContainer'),
    tabTextLabel: document.getElementById('tabTextLabel'),
    tabImageLabel: document.getElementById('tabImageLabel'),
    textInputParams: document.getElementById('textInputParams'),
    imageInputParams: document.getElementById('imageInputParams'),
    promptInput: document.getElementById('promptInput'),
    imgPromptInput: document.getElementById('imgPromptInput'),
    charCount: document.getElementById('charCount'),
    imageFileInput: document.getElementById('imageFileInput'),
    uploadPlaceholder: document.getElementById('uploadPlaceholder'),
    uploadPreview: document.getElementById('uploadPreview'),
    previewImg: document.getElementById('previewImg'),
    clearImageBtn: document.getElementById('clearImageBtn'),
    modelSelect: document.getElementById('modelSelect'),
    modelDesc: document.getElementById('modelDesc'),
    ratioSelect: document.getElementById('ratioSelect'),
    resolutionSelect: document.getElementById('resolutionSelect'),
    durationSelect: document.getElementById('durationSelect'),
    presetSelect: document.getElementById('presetSelect'),
    taskNameInput: document.getElementById('taskNameInput'),
    resParam: document.getElementById('resParam'),
    durationParam: document.getElementById('durationParam'),
    presetParam: document.getElementById('presetParam'),
    previewType: document.getElementById('previewType'),
    previewModel: document.getElementById('previewModel'),
    previewParams: document.getElementById('previewParams'),
    estTime: document.getElementById('estTime'),
    submitBtn: document.getElementById('submitBtn'),
    resetBtn: document.getElementById('resetBtn'),
    recentTasksList: document.getElementById('recentTasksList'),
    apiKeyInput: document.getElementById('apiKeyInput'),
    toggleKeyVisibilityBtn: document.getElementById('toggleKeyVisibility'),
    verifyKeyBtn: document.getElementById('verifyKeyBtn'),
    keyStatusBadge: document.getElementById('keyStatusBadge'),
    lastVerifiedTime: document.getElementById('lastVerifiedTime'),
    apiKeyWarning: document.getElementById('apiKeyWarning')
};

// --- Initialization ---
document.addEventListener('DOMContentLoaded', async () => {
    // 1. Ensure Admin Access (Page Guard)
    state.pageAccessKey = await ensureAdminKey({ redirect: true });
    
    // 2. Load Task Token from separate storage
    const storedToken = localStorage.getItem('grok2api_task_token') || '';
    if (storedToken) {
        state.taskToken = storedToken;
        els.apiKeyInput.value = storedToken;
        verifyTaskToken(storedToken, true);
    } else {
        state.taskToken = null;
        updateTokenStatusUI('unconfigured');
    }

    initEventListeners();
    refreshUI();
    loadRecentTasks(); // Placeholder
});

function initEventListeners() {
    // API Key Events
    els.toggleKeyVisibilityBtn.addEventListener('click', () => {
        const type = els.apiKeyInput.getAttribute('type');
        els.apiKeyInput.setAttribute('type', type === 'password' ? 'text' : 'password');
    });

    els.verifyKeyBtn.addEventListener('click', () => {
        const key = els.apiKeyInput.value.trim();
        if (!key) return showToast('请输入 API Token', 'error');
        verifyTaskToken(key, false);
    });

    // Task Type Switching
    window.switchTaskType = (type) => {
        state.mainType = type;
        state.subMode = 'text'; 
        refreshUI();
    };

    // Sub Mode Switching
    window.switchSubMode = (mode) => {
        state.subMode = mode;
        refreshUI();
    };

    // Inputs
    els.promptInput.addEventListener('input', (e) => {
        state.config.prompt = e.target.value;
        els.charCount.innerText = e.target.value.length;
        updatePreview();
    });
    
    els.imgPromptInput.addEventListener('input', (e) => {
        state.config.imgPrompt = e.target.value;
    });

    els.taskNameInput.addEventListener('input', (e) => {
        state.config.taskName = e.target.value;
    });

    // File Upload
    els.imageFileInput.addEventListener('change', handleFileSelect);
    els.clearImageBtn.addEventListener('click', clearFile);

    // Param Selects
    ['model', 'ratio', 'resolution', 'duration', 'preset'].forEach(key => {
        const el = els[`${key}Select`];
        if (el) {
            el.addEventListener('change', (e) => {
                state.config[key] = e.target.value;
                updatePreview();
            });
        }
    });

    // Actions
    els.submitBtn.addEventListener('click', submitTask);
    els.resetBtn.addEventListener('click', resetConfig);
}

// --- UI Logic ---
function refreshUI() {
    // Type Cards
    els.typeCards.forEach(card => {
        if (card.dataset.type === state.mainType) card.classList.add('active');
        else card.classList.remove('active');
    });

    // Sub Tabs Labels
    if (state.mainType === 'video') {
        els.tabTextLabel.innerText = '文生视频 (Text-to-Video)';
        els.tabImageLabel.innerText = '图生视频 (Image-to-Video)';
    } else {
        els.tabTextLabel.innerText = '文生图 (Text-to-Image)';
        els.tabImageLabel.innerText = '图生图/编辑 (Image-to-Image)';
    }

    // Sub Tabs Active State
    els.subTabBtns.forEach(btn => {
        if (btn.dataset.mode === state.subMode) btn.classList.add('active');
        else btn.classList.remove('active');
    });

    // Toggle Input Areas
    if (state.subMode === 'text') {
        els.textInputParams.classList.remove('hidden');
        els.imageInputParams.classList.add('hidden');
    } else {
        els.textInputParams.classList.add('hidden');
        els.imageInputParams.classList.remove('hidden');
    }

    // Update Model Options
    updateModelOptions();

    // Toggle Advanced Params Visibility
    if (state.mainType === 'video') {
        els.resParam.classList.remove('hidden');
        els.durationParam.classList.remove('hidden');
        els.presetParam.classList.remove('hidden');
    } else {
        els.resParam.classList.add('hidden');
        els.durationParam.classList.add('hidden');
        els.presetParam.classList.add('hidden');
    }

    updatePreview();
}

function updateModelOptions() {
    const models = state.models[state.mainType] || [];
    let filteredModels = models;
    
    if (state.mainType === 'image') {
        if (state.subMode === 'image') {
            filteredModels = models.filter(m => m.id.includes('edit'));
        } else {
            filteredModels = models.filter(m => !m.id.includes('edit'));
        }
    }

    els.modelSelect.innerHTML = filteredModels.map(m => 
        `<option value="${m.id}" ${state.config.model === m.id ? 'selected' : ''}>${m.name}</option>`
    ).join('');
    
    if (!state.config.model && filteredModels.length > 0) {
        state.config.model = filteredModels[0].id;
    }
}

function handleFileSelect(e) {
    const file = e.target.files[0];
    if (!file) return;
    
    if (file.size > 10 * 1024 * 1024) {
        showToast('图片大小不能超过 10MB', 'error');
        return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
        state.config.refImage = e.target.result;
        els.previewImg.src = e.target.result;
        els.uploadPlaceholder.classList.add('hidden');
        els.uploadPreview.classList.remove('hidden');
    };
    reader.readAsDataURL(file);
}

function clearFile() {
    els.imageFileInput.value = '';
    state.config.refImage = null;
    els.uploadPlaceholder.classList.remove('hidden');
    els.uploadPreview.classList.add('hidden');
}

function updatePreview() {
    const subLabel = state.subMode === 'text' ? '文生' : '图生';
    const mainLabel = state.mainType === 'video' ? '视频' : '图片';
    els.previewType.innerText = `${subLabel}${mainLabel}`;

    const model = els.modelSelect.options[els.modelSelect.selectedIndex]?.text || '-';
    els.previewModel.innerText = model;

    const ratio = state.config.ratio;
    let details = `${ratio}`;
    if (state.mainType === 'video') {
        details += ` · ${state.config.resolution} · ${state.config.duration}s`;
    }
    els.previewParams.innerText = details;

    els.estTime.innerText = state.mainType === 'video' ? '~60s' : '~15s';
}

function resetConfig() {
    state.config = {
        model: state.config.model,
        prompt: '',
        imgPrompt: '',
        refImage: null,
        ratio: '3:2',
        resolution: '720p',
        duration: '5',
        preset: 'normal',
        taskName: ''
    };
    
    els.promptInput.value = '';
    els.imgPromptInput.value = '';
    els.taskNameInput.value = '';
    els.charCount.innerText = '0';
    clearFile();
    
    els.ratioSelect.value = '3:2';
    els.resolutionSelect.value = '720p';
    els.durationSelect.value = '6';
    els.presetSelect.value = 'normal';
    
    updatePreview();
    showToast('参数已重置', 'success');
}

// --- API Token Management ---
async function verifyTaskToken(token, silent = false) {
    if (!silent) {
        els.verifyKeyBtn.disabled = true;
        els.verifyKeyBtn.innerText = '验证中...';
    } else {
        els.keyStatusBadge.innerText = '验证中...';
        els.keyStatusBadge.className = 'text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-500';
    }

    try {
        // Verify against a public API endpoint (e.g. list models)
        // This ensures the token is valid for API usage
        const res = await fetch('/v1/models', { 
            headers: { 'Authorization': `Bearer ${token}` } 
        });
        
        if (res.ok) {
            state.taskToken = token;
            localStorage.setItem('grok2api_task_token', token);
            updateTokenStatusUI('valid');
            if (!silent) showToast('API Token 验证成功', 'success');
        } else {
            throw new Error('无效的 API Token');
        }
    } catch (e) {
        state.taskToken = null;
        updateTokenStatusUI('invalid');
        if (!silent) showToast('API Token 验证失败', 'error');
    } finally {
        if (!silent) {
            els.verifyKeyBtn.disabled = false;
            els.verifyKeyBtn.innerText = '验证并保存';
        }
    }
}

function updateTokenStatusUI(status) {
    if (status === 'valid') {
        els.keyStatusBadge.innerText = '有效';
        els.keyStatusBadge.className = 'text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700';
        els.apiKeyWarning.classList.add('hidden');
        els.lastVerifiedTime.innerText = `上次验证: ${new Date().toLocaleTimeString()}`;
        els.lastVerifiedTime.classList.remove('hidden');
    } else if (status === 'invalid') {
        els.keyStatusBadge.innerText = '无效';
        els.keyStatusBadge.className = 'text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700';
        els.apiKeyWarning.classList.remove('hidden');
    } else {
        els.keyStatusBadge.innerText = '未配置';
        els.keyStatusBadge.className = 'text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700';
        els.apiKeyWarning.classList.remove('hidden');
    }
}

window.focusApiKeyInput = () => {
    els.apiKeyInput.focus();
    els.apiKeyInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
};

// --- Task Submission ---
async function submitTask() {
    if (state.isSubmitting) return;

    // Validation
    if (!state.taskToken) {
        els.apiKeyWarning.classList.remove('hidden');
        els.apiKeyWarning.scrollIntoView({ behavior: 'smooth', block: 'start' });
        return showToast('请先配置有效的 API Token', 'error');
    }
    if (state.subMode === 'text' && !state.config.prompt.trim()) {
        return showToast('请输入提示词', 'error');
    }
    if (state.subMode === 'image' && !state.config.refImage) {
        return showToast('请上传参考图片', 'error');
    }

    state.isSubmitting = true;
    const btnHtml = els.submitBtn.innerHTML;
    els.submitBtn.disabled = true;
    els.submitBtn.innerHTML = `<svg class="animate-spin h-5 w-5 mr-2" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg> 提交中...`;

    try {
        let endpoint = '';
        let payload = {};
        
        if (state.mainType === 'video') {
            endpoint = '/v1/video/generations/async';
            payload = {
                model: state.config.model,
                video_config: {
                    aspect_ratio: state.config.ratio,
                    video_length: parseInt(state.config.duration),
                    resolution_name: state.config.resolution,
                    preset: state.config.preset
                }
            };
            
            // Construct messages for video
            if (state.subMode === 'image' && state.config.refImage) {
                payload.messages = [
                    { 
                        role: 'user', 
                        content: [
                            { type: 'image_url', image_url: { url: state.config.refImage } },
                            { type: 'text', text: state.config.imgPrompt || "Generate video from this image" }
                        ] 
                    }
                ];
            } else {
                 payload.messages = [
                    { 
                        role: 'user', 
                        content: state.config.prompt || "video generation"
                    }
                ];
                // Also support top-level prompt if model supports it, but messages is standard
                payload.prompt = state.config.prompt; 
            }
        } else {
            // Image - /v1/images/generations 仅支持 grok-imagine-1.0，size 需为 1280x720 等格式
            const ratioToSize = {
                '16:9': '1280x720', '9:16': '720x1280', '1:1': '1024x1024',
                '3:2': '1792x1024', '2:3': '1024x1792',
                '4:3': '1792x1024', '3:4': '1024x1792'
            };
            endpoint = '/v1/images/generations/async';
            payload = {
                model: 'grok-imagine-1.0',
                prompt: state.config.prompt,
                size: ratioToSize[state.config.ratio] || '1024x1024',
                n: 1,
                response_format: 'url'
            };
             if (state.subMode === 'image' && state.config.refImage) {
                 // For image editing/variation, structure might differ. 
                 // Assuming standard prompt for now as per current backend support.
                 // TODO: Support image input for image tasks if backend supports it.
             }
        }

        const res = await requestWithRetry(endpoint, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${state.taskToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        
        showToast('任务已提交', 'success');
        state.currentTaskId = data.data.taskId;
        
        addRecentTask({
            id: state.currentTaskId,
            type: state.mainType,
            status: 'pending',
            time: new Date().toLocaleTimeString(),
            name: state.config.taskName || '未命名任务'
        });
        
        startPolling(state.currentTaskId, state.mainType);

    } catch (e) {
        console.error(e);
        showToast(e.message || '提交失败', 'error');
    } finally {
        state.isSubmitting = false;
        els.submitBtn.disabled = false;
        els.submitBtn.innerHTML = btnHtml;
    }
}

// --- Polling Logic ---
function startPolling(taskId, type) {
    const interval = setInterval(async () => {
        try {
            // Use singular 'video' or plural 'images' based on type
            const endpoint = type === 'video' 
                ? `/v1/video/tasks/${taskId}` 
                : `/v1/images/tasks/${taskId}`;
                
            const res = await requestWithRetry(endpoint, {
                headers: { 'Authorization': `Bearer ${state.taskToken}` }
            }, { retryOnAuth: false });
            
            if (!res.ok) return;
            const data = await res.json();
            const task = data.data;
            
            updateTaskStatusInList(taskId, task.status);
            
            if (['success', 'completed', 'failed', 'cancelled'].includes(task.status)) {
                clearInterval(interval);
                if (task.status === 'success' || task.status === 'completed') {
                    showToast(`任务 ${taskId.substring(0,8)}... 完成`, 'success');
                } else {
                    showToast(`任务 ${taskId.substring(0,8)}... 失败`, 'error');
                }
            }
        } catch (e) {
            console.error(e);
        }
    }, 2000);
}

async function requestWithRetry(url, options, opts = {}) {
    const maxRetries = Number.isInteger(opts.retries) ? opts.retries : 2;
    const retryStatuses = new Set([429, 500, 502, 503, 504]);
    let attempt = 0;

    while (attempt <= maxRetries) {
        try {
            const res = await fetch(url, options);
            if (res.status === 401) {
                state.taskToken = null; // Mark token as invalid
                updateTokenStatusUI('invalid');
                showToast('鉴权失败：API Token 无效或已过期', 'error');
                els.apiKeyWarning.scrollIntoView({ behavior: 'smooth', block: 'start' });
                throw new Error('鉴权失败');
            }
            if (retryStatuses.has(res.status) && attempt < maxRetries) {
                await waitForRetry(attempt);
                attempt += 1;
                continue;
            }
            return res;
        } catch (e) {
            if (attempt >= maxRetries) throw e;
            await waitForRetry(attempt);
            attempt += 1;
        }
    }
}

function waitForRetry(attempt) {
    const delay = Math.min(2000, 300 * Math.pow(2, attempt));
    return new Promise(resolve => setTimeout(resolve, delay));
}

// --- Recent Tasks List ---
function addRecentTask(task) {
    const html = `
        <div class="p-4 flex items-center justify-between hover:bg-gray-50 transition-colors" id="task-${task.id}">
            <div class="flex items-center gap-3">
                <div class="status-dot w-2 h-2 rounded-full ${getStatusColor(task.status)}"></div>
                <div>
                    <div class="text-sm font-medium text-black">${task.name}</div>
                    <div class="text-xs text-[var(--accents-4)] font-mono">${task.id.substring(0, 8)} · ${task.type}</div>
                </div>
            </div>
            <div class="text-xs text-[var(--accents-4)]">${task.time}</div>
        </div>
    `;
    els.recentTasksList.insertAdjacentHTML('afterbegin', html);
}

function updateTaskStatusInList(taskId, status) {
    const el = document.getElementById(`task-${taskId}`);
    if (el) {
        const dot = el.querySelector('.status-dot');
        if (dot) {
            dot.className = `status-dot w-2 h-2 rounded-full ${getStatusColor(status)}`;
        }
    }
}

function getStatusColor(status) {
    if (status === 'success' || status === 'completed') return 'bg-green-500';
    if (status === 'failed' || status === 'cancelled') return 'bg-red-500';
    return 'bg-yellow-500 animate-pulse';
}

function loadRecentTasks() {
    els.recentTasksList.innerHTML = '<div class="p-4 text-center text-xs text-[var(--accents-4)]">暂无记录</div>';
}
