let ws = null;
let currentVideoPath = null;
let currentVideoMetadata = null;

function addLog(containerId, message, className = '') {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    const entry = document.createElement('div');
    entry.className = `log-entry ${className}`;
    
    // Format time
    const now = new Date();
    const timeStr = now.toLocaleTimeString('ko-KR', { hour12: false });
    
    entry.textContent = `[${timeStr}] ${message}`;
    container.appendChild(entry);
    container.scrollTop = container.scrollHeight;
}

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        addLog('agentLog', 'WebSocket 연결됨', '');
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if (data.type === 'agent_message') {
            const agent = data.agent;
            const action = data.action;
            const message = data.message;
            
            if (action === 'generate') {
                addLog('agentLog', `🤖 ${agent}: 프롬프트 생성`, 'planner');
                addLog('agentLog', `   "${message}"`, 'planner');
            } else if (action === 'review') {
                const status = data.status;
                const score = data.score;
                const feedback = data.feedback;
                
                addLog('agentLog', `🔍 ${agent}: 프롬프트 검토`, 'reviewer');
                addLog('agentLog', `   상태: ${status} (점수: ${score}/100)`, status === 'APPROVED' ? 'reviewer' : 'error');
                if (feedback) {
                    addLog('agentLog', `   피드백: ${feedback}`, 'reviewer');
                }
            }
        } else if (data.type === 'video_status') {
            const status = data.status;
            const message = data.message;
            
            addLog('videoLog', message, 'video');
            
            if (status === 'completed') {
                const videoStatus = document.getElementById('videoStatus');
                if (videoStatus) {
                    videoStatus.textContent = '완료';
                    videoStatus.className = 'status-badge completed';
                }
                
                // video_filename이 있으면 우선 사용, 없으면 final_video_path에서 파일명 추출
                const videoFile = data.video_filename || (data.final_video_path ? data.final_video_path.split(/[\\/]/).pop() : null);
                if (videoFile) {
                    // currentVideoPath를 올바른 형식으로 설정 (output/filename.mp4)
                    currentVideoPath = `output/${videoFile}`;
                    console.log('[DEBUG] 비디오 생성 완료, currentVideoPath 설정:', currentVideoPath);
                    showVideoPreview(videoFile);
                    
                    // YouTube 메타데이터 설정
                    if (data.youtube_metadata) {
                        currentVideoMetadata = data.youtube_metadata;
                        console.log('[DEBUG] YouTube 메타데이터 설정:', currentVideoMetadata);
                        
                        const titleInput = document.getElementById('uploadTitle');
                        const descriptionInput = document.getElementById('uploadDescription');
                        const tagsInput = document.getElementById('uploadTags');
                        
                        if (titleInput) {
                            titleInput.value = data.youtube_metadata.title || '';
                        }
                        if (descriptionInput) {
                            descriptionInput.value = data.youtube_metadata.description || '';
                        }
                        if (tagsInput) {
                            tagsInput.value = data.youtube_metadata.tags ? data.youtube_metadata.tags.join(', ') : '';
                        }
                    }
                    
                    // YouTube 업로드 섹션 표시
                    const uploadSection = document.getElementById('youtubeUploadSection');
                    if (uploadSection) {
                        uploadSection.style.display = 'block';
                        // 스크롤 이동
                        uploadSection.scrollIntoView({ behavior: 'smooth' });
                        
                        console.log('[DEBUG] YouTube 업로드 섹션 표시됨');
                        
                        // 업로드 버튼 이벤트 리스너 재설정
                        setupUploadButton();
                    }
                }
            } else if (status === 'error') {
                const videoStatus = document.getElementById('videoStatus');
                if (videoStatus) {
                    videoStatus.textContent = '오류';
                    videoStatus.className = 'status-badge failed';
                }
            }
        } else if (data.type === 'youtube_upload_status') {
            const status = data.status;
            const message = data.message;
            
            addLog('videoLog', message, 'video');
            
            const uploadStatusDiv = document.getElementById('youtubeUploadStatus');
            const uploadBtn = document.getElementById('uploadYoutubeBtn');
            
            if (status === 'upload_complete') {
                if (uploadStatusDiv) {
                    uploadStatusDiv.innerHTML = `<p style="color: var(--success-color); font-weight: 600;">✅ ${message}</p>`;
                    if (data.youtube_url) {
                        uploadStatusDiv.innerHTML += `<p style="margin-top: 10px;"><a href="${data.youtube_url}" target="_blank" style="color: #ff0000; text-decoration: none; font-weight: 600;">YouTube에서 보기 →</a></p>`;
                    }
                }
                if (uploadBtn) {
                    uploadBtn.disabled = false;
                    uploadBtn.textContent = '📺 YouTube에 업로드 완료';
                }
            } else if (status === 'upload_failed') {
                if (uploadStatusDiv) {
                    uploadStatusDiv.innerHTML = `<p style="color: var(--error-color); font-weight: 600;">❌ ${message}</p>`;
                }
                if (uploadBtn) uploadBtn.disabled = false;
            } else if (status === 'uploading') {
                if (uploadStatusDiv) {
                    uploadStatusDiv.innerHTML = `<p style="color: var(--text-secondary);">⏳ ${message}</p>`;
                }
                if (uploadBtn) {
                    uploadBtn.disabled = true;
                    uploadBtn.textContent = '⏳ 업로드 중...';
                }
            }
        }
    };
    
    ws.onerror = (error) => {
        addLog('agentLog', 'WebSocket 오류 발생', 'error');
    };
    
    ws.onclose = () => {
        addLog('agentLog', 'WebSocket 연결 종료', '');
        // 자동 재연결 시도
        setTimeout(() => {
            addLog('agentLog', 'WebSocket 재연결 시도...', '');
            connectWebSocket();
        }, 3000);
    };
}

function showVideoPreview(videoPath) {
    const preview = document.getElementById('videoPreview');
    if (!preview) return;
    
    // 파일명만 추출
    const fileName = videoPath.split(/[\\/]/).pop();
    const videoUrl = `/videos/${fileName}`;
    
    preview.innerHTML = `
        <h3 style="margin-bottom: 15px;">생성된 비디오</h3>
        <video controls autoplay loop style="width: 100%; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.3);">
            <source src="${videoUrl}" type="video/mp4">
            비디오를 재생할 수 없습니다.
        </video>
        <div style="margin-top: 15px; background: #2d2d2d; padding: 10px; border-radius: 8px;">
            <p style="color: var(--text-color); font-weight: 500;">${fileName}</p>
            <p style="margin-top: 5px; color: var(--text-secondary); font-size: 12px;">URL: <a href="${videoUrl}" target="_blank" style="color: var(--primary-color);">${videoUrl}</a></p>
        </div>
    `;
}

async function createShorts() {
    const topicInput = document.getElementById('topic');
    const durationInput = document.getElementById('videoDuration');
    
    const topic = topicInput.value;
    const videoDuration = parseFloat(durationInput.value) || 30.0;
    
    if (!topic) {
        alert('비디오 주제를 입력하세요.');
        topicInput.focus();
        return;
    }
    
    if (videoDuration < 1 || videoDuration > 300) {
        alert('비디오 길이는 1초에서 300초 사이여야 합니다.');
        durationInput.focus();
        return;
    }
    
    if (videoDuration < 15) {
        if (!confirm(`비디오 길이가 ${videoDuration}초입니다. YouTube Shorts는 최소 15초를 권장하지만, 계속 진행하시겠습니까?`)) {
            return;
        }
    }
    
    // UI 초기화
    document.getElementById('statusSection').style.display = 'flex';
    document.getElementById('agentLog').innerHTML = '';
    document.getElementById('videoLog').innerHTML = '';
    document.getElementById('videoPreview').innerHTML = '';
    document.getElementById('youtubeUploadSection').style.display = 'none';
    document.getElementById('youtubeUploadStatus').innerHTML = '';
    
    const createBtn = document.getElementById('createBtn');
    createBtn.disabled = true;
    createBtn.innerHTML = '<span class="spinner"></span> 처리 중...';
    
    const agentStatus = document.getElementById('agentStatus');
    const videoStatus = document.getElementById('videoStatus');
    
    agentStatus.textContent = '처리 중';
    agentStatus.className = 'status-badge processing';
    
    videoStatus.textContent = '대기 중';
    videoStatus.className = 'status-badge waiting';
    
    // WebSocket 연결 확인
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        connectWebSocket();
        await new Promise(resolve => setTimeout(resolve, 500));
    }
    
    // API 호출
    try {
        const response = await fetch('/v1/create_shorts', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                topic: topic,
                video_duration: videoDuration,
                upload_to_youtube: false  // 업로드는 나중에 버튼으로
            })
        });
        
        const result = await response.json();
        
        if (result.status === 'processing') {
            addLog('agentLog', '✅ 프롬프트 승인 완료!', 'planner');
            addLog('agentLog', `   반복 횟수: ${result.conversation_log?.length || 0}`, '');
            
            agentStatus.textContent = '완료';
            agentStatus.className = 'status-badge completed';
            
            videoStatus.textContent = '처리 중';
            videoStatus.className = 'status-badge processing';
            
            // YouTube 메타데이터 저장
            if (result.youtube_metadata) {
                currentVideoMetadata = result.youtube_metadata;
            }
        } else {
            addLog('agentLog', `❌ 오류: ${result.message}`, 'error');
            agentStatus.textContent = '실패';
            agentStatus.className = 'status-badge failed';
        }
    } catch (error) {
        addLog('agentLog', `❌ 요청 실패: ${error.message}`, 'error');
        agentStatus.textContent = '실패';
        agentStatus.className = 'status-badge failed';
    } finally {
        createBtn.disabled = false;
        createBtn.textContent = '✨ Shorts 생성 시작';
    }
}

// 업로드 버튼 설정 함수
function setupUploadButton() {
    const uploadBtn = document.getElementById('uploadYoutubeBtn');
    if (!uploadBtn) return;
    
    // 기존 리스너 제거를 위해 노드 복제
    const newUploadBtn = uploadBtn.cloneNode(true);
    uploadBtn.parentNode.replaceChild(newUploadBtn, uploadBtn);
    
    newUploadBtn.addEventListener('click', async (e) => {
        e.preventDefault();
        await uploadToYouTube();
    });
    
    newUploadBtn.disabled = false;
}

// 통합된 YouTube 업로드 함수
async function uploadToYouTube() {
    if (!currentVideoPath) {
        alert('업로드할 비디오가 없습니다. 먼저 비디오를 생성하거나 목록에서 선택하세요.');
        return;
    }
    
    const uploadBtn = document.getElementById('uploadYoutubeBtn');
    const uploadStatus = document.getElementById('youtubeUploadStatus');
    
    if (!uploadBtn || !uploadStatus) return;
    
    uploadBtn.disabled = true;
    uploadBtn.textContent = '⏳ 업로드 중...';
    uploadStatus.innerHTML = '<p style="color: var(--primary-color);">YouTube에 업로드 중입니다...</p>';
    
    // 입력 필드에서 메타데이터 가져오기
    const titleInput = document.getElementById('uploadTitle');
    const descriptionInput = document.getElementById('uploadDescription');
    const tagsInput = document.getElementById('uploadTags');
    
    const title = titleInput?.value?.trim() || currentVideoMetadata?.title || null;
    const description = descriptionInput?.value?.trim() || currentVideoMetadata?.description || null;
    const tagsValue = tagsInput?.value?.trim();
    const tags = tagsValue ? tagsValue.split(',').map(t => t.trim()).filter(t => t) : (currentVideoMetadata?.tags || null);
    
    try {
        const requestBody = {
            video_path: currentVideoPath,
            title: title || null,
            description: description || null,
            tags: tags,
            privacy_status: 'public'
        };
        
        const response = await fetch('/v1/upload_youtube', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestBody)
        });
        
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`서버 오류 (${response.status}): ${errorText}`);
        }
        
        const result = await response.json();
        
        if (result.status === 'processing') {
            uploadStatus.innerHTML = '<p style="color: var(--success-color);">✅ YouTube 업로드가 시작되었습니다. 완료되면 알림을 받습니다.</p>';
            addLog('videoLog', 'YouTube 업로드 시작됨', 'video');
        } else {
            throw new Error(result.message || '업로드 실패');
        }
    } catch (error) {
        console.error('업로드 오류:', error);
        addLog('videoLog', `❌ YouTube 업로드 요청 실패: ${error.message}`, 'error');
        uploadStatus.innerHTML = `<p style="color: var(--error-color);">❌ 업로드 요청 실패: ${error.message}</p>`;
        uploadBtn.disabled = false;
        uploadBtn.textContent = '📺 YouTube에 업로드';
    }
}

// 영상 목록 불러오기
async function loadVideoList() {
    const container = document.getElementById('videoListContainer');
    if (!container) return;
    
    container.innerHTML = '<p style="color: var(--text-secondary); text-align: center; padding: 20px;">영상 목록을 불러오는 중...</p>';
    
    try {
        const response = await fetch('/v1/list_videos');
        const result = await response.json();
        
        if (result.status === 'success' && result.videos && result.videos.length > 0) {
            container.innerHTML = '';
            
            result.videos.forEach(video => {
                const videoItem = document.createElement('div');
                videoItem.className = 'video-list-item';
                
                // 비디오 경로와 파일명을 안전하게 이스케이프
                const safePath = video.path.replace(/'/g, "\\'").replace(/"/g, '&quot;');
                const safeFilename = video.filename.replace(/'/g, "\\'").replace(/"/g, '&quot;');
                
                videoItem.innerHTML = `
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px;">
                        <div style="flex: 1; min-width: 200px;">
                            <div class="video-title">${video.filename}</div>
                            <div class="video-meta">
                                크기: ${video.size_mb} MB | 수정: ${video.modified_time_str}
                            </div>
                            <video controls style="width: 100%; max-height: 200px; margin-top: 10px; border-radius: 5px; background: #000;" src="${video.url || '/videos/' + video.filename}"></video>
                        </div>
                        <div>
                            <button class="video-upload-btn" 
                                    data-video-path="${safePath}"
                                    data-video-filename="${safeFilename}"
                                    style="background: #ff0000; padding: 10px 20px; font-size: 0.9rem;">
                                📺 YouTube 업로드
                            </button>
                        </div>
                    </div>
                `;
                
                // 버튼 이벤트 리스너
                const uploadBtn = videoItem.querySelector('.video-upload-btn');
                if (uploadBtn) {
                    uploadBtn.addEventListener('click', function(e) {
                        e.preventDefault();
                        const videoPath = this.getAttribute('data-video-path');
                        const filename = this.getAttribute('data-video-filename');
                        selectVideoForUpload(videoPath, filename);
                    });
                }
                
                container.appendChild(videoItem);
            });
        } else {
            container.innerHTML = '<p style="color: var(--text-secondary); text-align: center; padding: 20px;">저장된 영상이 없습니다.</p>';
        }
    } catch (error) {
        container.innerHTML = `<p style="color: var(--error-color); text-align: center; padding: 20px;">영상 목록을 불러오는데 실패했습니다: ${error.message}</p>`;
    }
}

// 영상 선택 및 YouTube 업로드 섹션 표시
function selectVideoForUpload(videoPath, filename) {
    currentVideoPath = videoPath;
    
    // YouTube 업로드 섹션 표시
    const uploadSection = document.getElementById('youtubeUploadSection');
    if (uploadSection) {
        uploadSection.style.display = 'block';
        uploadSection.scrollIntoView({ behavior: 'smooth' });
        
        // 메타데이터 필드 초기화 (파일명 기반 기본값)
        const titleInput = document.getElementById('uploadTitle');
        const descriptionInput = document.getElementById('uploadDescription');
        const tagsInput = document.getElementById('uploadTags');
        
        if (titleInput) {
            titleInput.value = filename.replace('.mp4', '').replace(/_/g, ' ');
        }
        if (descriptionInput) {
            descriptionInput.value = '';
        }
        if (tagsInput) {
            tagsInput.value = 'healing, asmr, nature, relaxation';
        }
        
        setupUploadButton();
    }
}

// 페이지 로드 시 초기화
window.addEventListener('load', () => {
    connectWebSocket();
    
    const createBtn = document.getElementById('createBtn');
    if (createBtn) {
        createBtn.addEventListener('click', createShorts);
    }
    
    const refreshBtn = document.getElementById('refreshVideoListBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadVideoList);
    }
    
    setupUploadButton();
    loadVideoList();
});
