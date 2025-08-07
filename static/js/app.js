let currentPlaylist = null;
let statusCheckInterval = null;

// DOM 元素
const cookieInput = document.getElementById('cookieInput');
const playlistUrl = document.getElementById('playlistUrl');
const qualitySelect = document.getElementById('qualitySelect');
const concurrentRange = document.getElementById('concurrentRange');
const concurrentValue = document.getElementById('concurrentValue');
const downloadLyrics = document.getElementById('downloadLyrics');
const parseBtn = document.getElementById('parseBtn');
const downloadBtn = document.getElementById('downloadBtn');
const pauseBtn = document.getElementById('pauseBtn');
const resumeBtn = document.getElementById('resumeBtn');
const cancelBtn = document.getElementById('cancelBtn');
const songList = document.getElementById('songList');
const totalProgress = document.getElementById('totalProgress');
const totalProgressText = document.getElementById('totalProgressText');
const currentSong = document.getElementById('currentSong');
const downloadSpeed = document.getElementById('downloadSpeed');
const downloadComplete = document.getElementById('downloadComplete');
const downloadZipBtn = document.getElementById('downloadZipBtn');

// 事件监听器
concurrentRange.addEventListener('input', (e) => {
    concurrentValue.textContent = e.target.value;
});

parseBtn.addEventListener('click', parsePlaylist);
downloadBtn.addEventListener('click', startDownload);
pauseBtn.addEventListener('click', pauseDownload);
resumeBtn.addEventListener('click', resumeDownload);
cancelBtn.addEventListener('click', cancelDownload);
downloadZipBtn.addEventListener('click', downloadZip);

// 解析歌单
async function parsePlaylist() {
    const url = playlistUrl.value.trim();
    const cookie = cookieInput.value.trim();
    
    if (!url) {
        alert('请输入歌单 URL');
        return;
    }
    
    if (!cookie) {
        alert('请输入 Cookie');
        return;
    }
    
    parseBtn.disabled = true;
    parseBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> 解析中...';
    
    try {
        const response = await fetch('/api/parse_playlist', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ url, cookie })
        });
        
        const result = await response.json();
        
        if (result.success) {
            currentPlaylist = result.playlist;
            displayPlaylist(result.playlist);
            downloadBtn.disabled = false;
        } else {
            alert(result.message);
        }
    } catch (error) {
        alert('解析失败：' + error.message);
    } finally {
        parseBtn.disabled = false;
        parseBtn.innerHTML = '<i class="bi bi-search"></i> 解析歌单';
    }
}

// 显示歌单
function displayPlaylist(playlist) {
    songList.innerHTML = '';
    
    const header = document.createElement('div');
    header.className = 'mb-3';
    header.innerHTML = `
        <h4>${playlist.name}</h4>
        <p class="text-muted">共 ${playlist.tracks.length} 首歌曲</p>
    `;
    songList.appendChild(header);
    
    playlist.tracks.forEach(track => {
        const songItem = document.createElement('div');
        songItem.className = 'song-item d-flex align-items-center';
        songItem.innerHTML = `
            <img src="${track.picUrl || '/static/img/default-cover.png'}" 
                 alt="封面" class="song-image me-3" 
                 onerror="this.src='/static/img/default-cover.png'">
            <div class="flex-grow-1">
                <h6 class="mb-1">${track.name}</h6>
                <small class="text-muted">${track.artists} - ${track.album}</small>
            </div>
        `;
        songList.appendChild(songItem);
    });
}

// 开始下载
async function startDownload() {
    const url = playlistUrl.value.trim();
    const cookie = cookieInput.value.trim();
    const quality = qualitySelect.value;
    const concurrent_count = parseInt(concurrentRange.value);
    const download_lyrics = downloadLyrics.checked;
    
    try {
        const response = await fetch('/api/start_download', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                url, cookie, quality, concurrent_count, download_lyrics
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            downloadBtn.disabled = true;
            pauseBtn.disabled = false;
            cancelBtn.disabled = false;
            downloadComplete.style.display = 'none';
            
            // 开始状态检查
            startStatusCheck();
        } else {
            alert(result.message);
        }
    } catch (error) {
        alert('启动下载失败：' + error.message);
    }
}

// 暂停下载
async function pauseDownload() {
    try {
        await fetch('/api/pause_download', { method: 'POST' });
        pauseBtn.disabled = true;
        resumeBtn.disabled = false;
    } catch (error) {
        alert('暂停失败：' + error.message);
    }
}

// 继续下载
async function resumeDownload() {
    try {
        await fetch('/api/resume_download', { method: 'POST' });
        pauseBtn.disabled = false;
        resumeBtn.disabled = true;
    } catch (error) {
        alert('继续失败：' + error.message);
    }
}

// 取消下载
async function cancelDownload() {
    try {
        await fetch('/api/cancel_download', { method: 'POST' });
        resetDownloadUI();
        stopStatusCheck();
    } catch (error) {
        alert('取消失败：' + error.message);
    }
}

// 下载压缩包
function downloadZip() {
    if (currentPlaylist) {
        window.open(`/api/download_zip/${encodeURIComponent(currentPlaylist.name)}`);
    }
}

// 开始状态检查
function startStatusCheck() {
    statusCheckInterval = setInterval(async () => {
        try {
            const response = await fetch('/api/download_status');
            const status = await response.json();
            updateDownloadStatus(status);
        } catch (error) {
            console.error('获取状态失败：', error);
        }
    }, 1000);
}

// 停止状态检查
function stopStatusCheck() {
    if (statusCheckInterval) {
        clearInterval(statusCheckInterval);
        statusCheckInterval = null;
    }
}

// 更新下载状态
function updateDownloadStatus(status) {
    // 更新进度条
    if (status.total_tracks > 0) {
        const progress = (status.completed_count / status.total_tracks) * 100;
        totalProgress.style.width = progress + '%';
        totalProgressText.textContent = `${status.completed_count}/${status.total_tracks}`;
    }
    
    // 更新当前歌曲
    currentSong.textContent = status.current_song || '等待开始...';
    
    // 更新下载速度
    downloadSpeed.textContent = `下载速度: ${status.download_speed} 首/秒`;
    
    // 检查是否完成
    if (!status.is_downloading && status.completed_count > 0) {
        resetDownloadUI();
        stopStatusCheck();
        downloadComplete.style.display = 'block';
    }
    
    // 检查错误
    if (status.error_message) {
        alert('下载错误：' + status.error_message);
        resetDownloadUI();
        stopStatusCheck();
    }
}

// 重置下载 UI
function resetDownloadUI() {
    downloadBtn.disabled = false;
    pauseBtn.disabled = true;
    resumeBtn.disabled = true;
    cancelBtn.disabled = true;
}

// 页面加载完成后的初始化
document.addEventListener('DOMContentLoaded', () => {
    // 从 localStorage 恢复 Cookie
    const savedCookie = localStorage.getItem('netease_cookie');
    if (savedCookie) {
        cookieInput.value = savedCookie;
    }
    
    // 保存 Cookie 到 localStorage
    cookieInput.addEventListener('blur', () => {
        localStorage.setItem('netease_cookie', cookieInput.value);
    });
});
