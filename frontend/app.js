const API_BASE = '/api';

// --- State ---
let currentPlaylist = null;
let currentGenerationId = null;

// --- UI Helpers ---
function showToast(message, isError = false) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast show ${isError ? 'error' : 'success'}`;
    setTimeout(() => toast.className = 'toast', 3000);
}

function getBaseUrl() {
    // Always use relative URLs — nginx proxies /api/ to the backend.
    return '';
}

function escapeHtml(text) {
    if (!text) return '';
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
    return text.replace(/[&<>"']/g, m => map[m]);
}

// --- State Persistence ---
function saveState() {
    try {
        const state = {
            playlist: currentPlaylist,
            generationId: currentGenerationId,
            timestamp: Date.now(),
        };
        localStorage.setItem('plex_playlist_state', JSON.stringify(state));
    } catch (err) {
        console.error('Error saving state to localStorage:', err);
    }
}

function restoreState() {
    try {
        const stored = localStorage.getItem('plex_playlist_state');
        if (stored) {
            const state = JSON.parse(stored);
            currentPlaylist = state.playlist;
            currentGenerationId = state.generationId;
            
            if (currentPlaylist) {
                document.getElementById('activity-feed-container').classList.add('hidden');
                displayResults(currentPlaylist);
            }
        }
    } catch (err) {
        console.error('Error restoring state from localStorage:', err);
    }
}

function clearState() {
    try {
        localStorage.removeItem('plex_playlist_state');
    } catch (err) {
        console.error('Error clearing state from localStorage:', err);
    }
}

// --- Init ---
document.addEventListener('DOMContentLoaded', () => {
    restoreState();
    fetchClients();
    fetchSyncStatus();
    setInterval(fetchSyncStatus, 5000);
    
    // Handle tab visibility changes to restore state if needed
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden && !currentPlaylist) {
            restoreState();
        }
    });
});

// --- Fetch Clients ---
async function fetchClients() {
    try {
        const res = await fetch(`${getBaseUrl()}/api/clients`);
        if (!res.ok) throw new Error('Failed to fetch clients');
        const clients = await res.json();
        
        const select = document.getElementById('client');
        select.innerHTML = clients.length ? '' : '<option value="">No devices found</option>';
        clients.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.name;
            opt.textContent = `${c.name} (${c.product})`;
            select.appendChild(opt);
        });
    } catch (err) {
        console.error('Error fetching clients:', err);
        const select = document.getElementById('client');
        select.innerHTML = '<option value="">Error loading devices</option>';
    }
}

// --- Sync Management ---
async function fetchSyncStatus() {
    try {
        const res = await fetch(`${getBaseUrl()}/api/sync/status`);
        if (!res.ok) return;
        const status = await res.json();
        
        const badge = document.getElementById('sync-status');
        const btn = document.getElementById('btn-sync');
        
        if (status.in_progress) {
            badge.textContent = `Syncing... ${status.synced_tracks} tracks`;
            badge.className = 'status-badge';
            btn.disabled = true;
        } else {
            let persisted = status.synced_tracks;
            try {
                const cRes = await fetch(`${getBaseUrl()}/api/sync/count`);
                if (cRes.ok) {
                    const cData = await cRes.json();
                    persisted = cData.persisted_tracks ?? persisted;
                }
            } catch (e) {}

            badge.textContent = `Synced: ${persisted} tracks`;
            badge.className = 'status-badge ok';
            btn.disabled = false;
        }
    } catch (err) {
        console.error('Sync status error:', err);
    }
}

document.getElementById('btn-sync').addEventListener('click', async () => {
    try {
        const res = await fetch(`${getBaseUrl()}/api/sync`, { method: 'POST' });
        if (!res.ok) throw new Error('Failed to start sync');
        showToast('Library sync started');
        fetchSyncStatus();
    } catch (err) {
        showToast('Error starting sync', true);
    }
});

// --- Wake Shield ---
document.getElementById('btn-wake').addEventListener('click', async () => {
    const btn = document.getElementById('btn-wake');
    btn.disabled = true;
    const originalText = btn.textContent;
    btn.textContent = 'Waking...';
    
    try {
        const res = await fetch(`${getBaseUrl()}/api/wake`, { method: 'POST' });
        if (!res.ok) throw new Error('Failed to wake device');
        
        const data = await res.json();
        
        if (data.status === 'awake') {
            if (data.clients && data.clients.length > 0) {
                const select = document.getElementById('client');
                select.innerHTML = '';
                data.clients.forEach(c => {
                    const opt = document.createElement('option');
                    opt.value = c.name;
                    opt.textContent = `${c.name} (${c.product})`;
                    select.appendChild(opt);
                });
                const plexampOption = Array.from(select.options).find(opt => 
                    opt.textContent.toLowerCase().includes('plexamp')
                );
                if (plexampOption) select.value = plexampOption.value;
            }
            showToast(data.message);
        } else {
            showToast(`Shield wake failed: ${data.message}`, true);
        }
    } catch (err) {
        console.error('Wake error:', err);
        showToast('Error waking device. Is ADB bridge running?', true);
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
});

// --- Activity Feed Functions ---
function addFeedLine(event) {
    const feed = document.getElementById('activity-feed');
    let icon = '•', iconClass = 'feed-icon step';
    
    if (event.step.includes('phase_start') || event.step.includes('phase_complete')) {
        icon = event.step.includes('start') ? '▶' : '✓';
        iconClass = 'feed-icon phase-marker';
    } else if (event.step.includes('revealed')) {
        icon = '♪';
        iconClass = 'feed-icon track';
    } else if (event.step.includes('matched')) {
        icon = '✓';
        iconClass = 'feed-icon success';
    } else if (event.step.includes('unmatched')) {
        icon = '✗';
        iconClass = 'feed-icon error';
    } else if (event.phase === 'error') {
        icon = '❌';
        iconClass = 'feed-icon error';
    }
    
    let html = `<div class="feed-line">
        <div class="${iconClass}">${icon}</div>
        <div class="feed-content">
            <div class="feed-message">${escapeHtml(event.message)}</div>`;
    
    if (event.step.includes('revealed') && event.detail) {
        const d = event.detail;
        html += `<div class="track-card">
            <div class="track-card-title">${escapeHtml(d.title)}</div>
            <div class="track-card-artist">${escapeHtml(d.artist)}</div>
            ${d.reasoning ? `<div class="track-card-match" style="color: #8892b0; margin-top: 4px; font-style: italic;">"${escapeHtml(d.reasoning)}"</div>` : ''}
        </div>`;
    }
    
    if ((event.step.includes('matched') || event.step.includes('unmatched')) && event.detail) {
        const d = event.detail;
        const matched = !event.step.includes('unmatched');
        const matchClass = matched ? 'matched' : 'unmatched';
        html += `<div class="track-card ${matchClass}">
            <div class="track-card-title">${escapeHtml(d.suggested_title)}</div>
            <div class="track-card-artist">${escapeHtml(d.suggested_artist)}</div>
            <div class="track-card-match">
                ${matched 
                    ? `→ ${escapeHtml(d.matched_title)} by ${escapeHtml(d.matched_artist)} <span style="color: #6b7b93;">(${d.match_type}, ${d.score})</span>`
                    : `No match found (best score: ${d.best_score})`
                }
            </div>
        </div>`;
    }
    
    html += `</div>
        <div class="feed-timing">${event.timing_ms ? event.timing_ms + 'ms' : ''}</div>
    </div>`;
    
    const line = document.createElement('div');
    line.innerHTML = html;
    feed.appendChild(line.firstChild);
    
    const container = document.getElementById('activity-feed-container');
    container.scrollTop = container.scrollHeight;
}

function updateProgressBar(progress) {
    const bar = document.getElementById('progress-bar');
    bar.style.width = (progress * 100) + '%';
}

function displaySummaryCard(event) {
    const feed = document.getElementById('activity-feed');
    const detail = event.detail || {};
    const totalTime = detail.total_time_ms || 0;
    const totalSeconds = (totalTime / 1000).toFixed(2);
    
    let html = `<div class="summary-card">
        <div class="summary-title">✨ Generation Complete</div>
        <div class="summary-stat">
            <span class="summary-stat-label">Total Time</span>
            <span class="summary-stat-value">${totalSeconds}s</span>
        </div>
        ${detail.final_track_count ? `<div class="summary-stat">
            <span class="summary-stat-label">Tracks Generated</span>
            <span class="summary-stat-value">${detail.final_track_count}</span>
        </div>` : ''}
        <div class="timing-breakdown">
            <div class="timing-segment prompt" style="width: 25%; min-width: 20px;"></div>
            <div class="timing-segment llm" style="width: 25%; min-width: 20px;"></div>
            <div class="timing-segment matching" style="width: 25%; min-width: 20px;"></div>
            <div class="timing-segment sonic" style="width: 25%; min-width: 20px;"></div>
        </div>
    </div>`;
    
    const card = document.createElement('div');
    card.innerHTML = html;
    feed.appendChild(card.firstChild);
    
    const container = document.getElementById('activity-feed-container');
    container.scrollTop = container.scrollHeight;
}

// --- Generate Playlist (Streaming) ---
document.getElementById('btn-generate').addEventListener('click', async () => {
    const prompt = document.getElementById('prompt').value.trim();
    const trackCount = parseInt(document.getElementById('track-count').value, 10);
    
    if (!prompt) {
        showToast('Please enter a prompt', true);
        return;
    }

    currentPlaylist = null;
    currentGenerationId = null;
    clearState();
    
    document.getElementById('activity-feed-container').classList.remove('hidden');
    document.getElementById('results-container').classList.add('hidden');
    document.getElementById('activity-feed').innerHTML = '';
    document.getElementById('progress-bar').style.width = '0%';
    
    const btn = document.getElementById('btn-generate');
    btn.disabled = true;
    
    try {
        const res = await fetch(`${getBaseUrl()}/api/playlist/generate-stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt, track_count: trackCount }),
        });
        
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.detail || `Server error: ${res.status}`);
        }
        
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines[lines.length - 1];
            
            for (let i = 0; i < lines.length - 1; i++) {
                const line = lines[i].trim();
                
                if (line.startsWith('data: ')) {
                    try {
                        const eventData = JSON.parse(line.slice(6));
                        updateProgressBar(eventData.progress);
                        
                        if (eventData.phase === 'complete' && eventData.step === 'done') {
                            currentGenerationId = eventData.detail?.generation_id;
                            currentPlaylist = {
                                name: eventData.detail?.playlist_name,
                                description: eventData.detail?.playlist_description,
                                tracks: (eventData.detail?.tracks || []).map(t => ({
                                    title: t.title,
                                    artist: t.artist,
                                    reasoning: t.reasoning || '',
                                })),
                            };
                            saveState();
                            displaySummaryCard(eventData);
                            addFeedLine(eventData);
                            setTimeout(() => displayResults(currentPlaylist), 300);
                        } else if (eventData.phase === 'error') {
                            addFeedLine(eventData);
                            showToast(`Error: ${eventData.message}`, true);
                        } else {
                            addFeedLine(eventData);
                        }
                    } catch (e) {
                        console.error('Error parsing event:', e);
                    }
                }
            }
        }
        
    } catch (err) {
        console.error('Generate error:', err);
        showToast(err.message, true);
        document.getElementById('activity-feed-container').classList.add('hidden');
    } finally {
        btn.disabled = false;
    }
});

function displayResults(data) {
    document.getElementById('playlist-title').textContent = data.name;
    document.getElementById('playlist-desc').textContent = data.description;
    
    const list = document.getElementById('track-list');
    list.innerHTML = '';
    
    if (data.tracks && data.tracks.length > 0) {
        data.tracks.forEach((track, idx) => {
            const li = document.createElement('li');
            li.className = 'track-item';
            li.style.animation = `slideIn 0.3s ease-out ${idx * 0.05}s backwards`;
            li.innerHTML = `
                <div class="track-title">${escapeHtml(track.title)}</div>
                <div class="track-artist">${escapeHtml(track.artist)}</div>
                ${track.reasoning ? `<div class="track-reasoning">${escapeHtml(track.reasoning)}</div>` : ''}
            `;
            list.appendChild(li);
        });
    }
    
    document.getElementById('activity-feed-container').classList.add('hidden');
    document.getElementById('results-container').classList.remove('hidden');
}

// --- Play / Save Actions ---
document.getElementById('btn-play').addEventListener('click', async () => {
    if (!currentPlaylist) return;
    
    const client = document.getElementById('client').value;
    if (!client) {
        showToast('Please select a playback device', true);
        return;
    }

    const btn = document.getElementById('btn-play');
    btn.disabled = true;
    const originalText = btn.textContent;
    btn.textContent = 'Playing...';
    
    try {
        const prompt = document.getElementById('prompt').value;
        const res = await fetch(`${getBaseUrl()}/api/playlist/play`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                prompt, 
                track_count: currentPlaylist.tracks.length,
                client_name: client,
                generation_id: currentGenerationId,
            })
        });
        
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.detail || 'Failed to start playback');
        }
        showToast(`Playback started on ${client}`);
    } catch (err) {
        console.error('Play error:', err);
        showToast(err.message, true);
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
});

document.getElementById('btn-save').addEventListener('click', async () => {
    if (!currentPlaylist) return;

    const btn = document.getElementById('btn-save');
    btn.disabled = true;
    const originalText = btn.textContent;
    btn.textContent = 'Saving...';
    
    try {
        const prompt = document.getElementById('prompt').value;
        const res = await fetch(`${getBaseUrl()}/api/playlist/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                prompt, 
                track_count: currentPlaylist.tracks.length,
                playlist_name: currentPlaylist.name,
                generation_id: currentGenerationId,
            })
        });
        
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.detail || 'Failed to save playlist');
        }
        showToast(`Playlist '${currentPlaylist.name}' saved`);
    } catch (err) {
        console.error('Save error:', err);
        showToast(err.message, true);
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
});
