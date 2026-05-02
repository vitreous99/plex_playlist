const API_BASE = '/api';

// --- State ---
let currentPlaylist = null;
let currentGenerationId = null;
// Per-step timings collected from SSE events
let stepTimings = {};
// Track generation start time for elapsed time display
let generationStartTime = null;

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

    // Setup control panel toggle button
    const cpToggle = document.getElementById('cp-toggle');
    if (cpToggle) {
        cpToggle.addEventListener('click', () => {
            const cpBody = document.getElementById('cp-body');
            const isHidden = cpBody.style.display === 'none';
            
            if (isHidden) {
                // Show control panel
                cpBody.style.display = 'block';
                cpToggle.textContent = 'Hide Details';
                // Re-open all phase sections
                document.getElementById('phase-prompt').setAttribute('open', '');
                document.getElementById('phase-llm').setAttribute('open', '');
                document.getElementById('phase-matching').setAttribute('open', '');
                document.getElementById('phase-sonic').setAttribute('open', '');
            } else {
                // Hide control panel
                cpBody.style.display = 'none';
                cpToggle.textContent = 'Show Details';
            }
        });
    }
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

// Map phases to their container divs
function getPhaseContainer(phase) {
    switch(phase) {
        case 'prompt': return document.querySelector('#phase-prompt .phase-feed');
        case 'llm': return document.querySelector('#phase-llm .phase-feed');
        case 'matching': return document.querySelector('#phase-matching .phase-feed');
        case 'sonic': 
        case 'complete': return document.querySelector('#phase-sonic .phase-feed');
        case 'error': return document.querySelector('#phase-sonic .phase-feed'); // Default to sonic for errors
        default: return null;
    }
}

function addFeedLine(event) {
    // Record step timing and completion timestamp for summary
    try {
        stepTimings[event.step] = {
            timing_ms: event.timing_ms || 0,
            completed_at: event.completed_at || null,
        };
    } catch (e) {
        // ignore malformed events
    }

    // Get the correct phase feed container
    const feed = getPhaseContainer(event.phase);
    if (!feed) return;

    let icon = '•', iconClass = 'feed-icon step';
    
    if (event.step.includes('_start') || event.step.includes('_complete') || event.step.includes('_warning')) {
        icon = event.step.includes('_start') ? '▶' : (event.step.includes('_warning') ? '⚠' : '✓');
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
    
    // Special renderer for LLM-suggested tracks (revealed)
    if (event.step.includes('revealed') && event.detail) {
        const d = event.detail;
        html += `<div class="track-card">
            <div class="track-card-title">${escapeHtml(d.title)}</div>
            <div class="track-card-artist">${escapeHtml(d.artist)}</div>
            ${d.reasoning ? `<div class="track-card-match" style="color: #8892b0; margin-top: 4px; font-style: italic;">"${escapeHtml(d.reasoning)}"</div>` : ''}
        </div>`;
    }
    
    // Special renderer for matched/unmatched tracks
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

    // Special renderer for context_pool event - show actual artists, genres, and sample tracks
    if (event.step === 'context_pool' && event.detail) {
        const d = event.detail;
        
        // Artists pills
        if (d.artists && d.artists.length > 0) {
            html += `<div class="context-pills">
                ${d.artists.map(a => `<div class="context-pill">${escapeHtml(a)}</div>`).join('')}
            </div>`;
        }

        // Genres pills
        if (d.genres && d.genres.length > 0) {
            html += `<div class="context-pills">
                ${d.genres.map(g => `<div class="context-pill genre">${escapeHtml(g)}</div>`).join('')}
            </div>`;
        }

        // Sample tracks list
        if (d.sample_tracks && d.sample_tracks.length > 0) {
            html += `<div class="sample-tracks-list">
                ${d.sample_tracks.map(t => `
                    <div class="sample-track-item">
                        <div class="sample-track-title">${escapeHtml(t.title)}</div>
                        <div class="sample-track-artist">${escapeHtml(t.artist)}${t.album ? ` • ${escapeHtml(t.album)}` : ''}</div>
                    </div>
                `).join('')}
            </div>`;
        }
    }

    // Special renderer for prompt_ready event - show full system prompt in nested details
    if (event.step === 'prompt_ready' && event.detail && event.detail.system_prompt) {
        const prompt = event.detail.system_prompt;
        html += `<details class="system-prompt-details">
            <summary>📋 Full System Prompt (click to expand)</summary>
            <pre class="system-prompt-code">${escapeHtml(prompt)}</pre>
        </details>`;
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
    const timingDiv = document.getElementById('phase-timing');
    const detail = event.detail || {};
    const totalTime = detail.total_time_ms || 0;
    const totalSeconds = (totalTime / 1000).toFixed(2);
    let perStepHtml = '';
    const orderedSteps = [
        ['prompt_start', 'Prompt start'],
        ['keywords', 'Keywords extracted'],
        ['context_pool', 'Context pool built'],
        ['prompt_ready', 'System prompt ready'],
        ['llm_call', 'LLM call started'],
        ['llm_complete', 'LLM complete'],
        ['matching_start', 'Matching started'],
        ['matching_complete', 'Matching complete'],
        ['sonic_start', 'Sonic expansion started'],
        ['sonic_complete', 'Sonic expansion complete'],
        ['generation_complete', 'Generation complete'],
        ['done', 'Ready'],
    ];

    orderedSteps.forEach(([key, label]) => {
        const info = stepTimings[key];
        if (info) {
            const ms = info.timing_ms || 0;
            perStepHtml += `<div class="summary-step"><span class="summary-step-label">${label}</span><span class="summary-step-value">${ms}ms</span></div>`;
        }
    });

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
        <div class="summary-steps">${perStepHtml}</div>
    </div>`;
    
    const card = document.createElement('div');
    card.innerHTML = html;
    timingDiv.appendChild(card.firstChild);
    
    const container = document.getElementById('activity-feed-container');
    container.scrollTop = container.scrollHeight;
    
    // Attach event listeners to the new buttons
    attachPlaySaveListeners().catch(err => console.error('Error in attachPlaySaveListeners:', err));
}

async function attachPlaySaveListeners() {
    const playBtn = document.getElementById('btn-play-top');
    const saveBtn = document.getElementById('btn-save-top');
    
    if (playBtn) {
        playBtn.addEventListener('click', handlePlay);
    }
    
    if (saveBtn) {
        saveBtn.addEventListener('click', handleSave);
    }
    
    // Refresh available Plex Amp instances before activating the play button
    await fetchClientsAndSelectPlexAmp();
    
    // Show the action buttons container
    const actionButtonsContainer = document.getElementById('action-buttons');
    if (actionButtonsContainer) {
        actionButtonsContainer.style.display = 'flex';
    }
}

// --- Fetch Clients and Auto-Select Plex Amp ---
async function fetchClientsAndSelectPlexAmp() {
    try {
        const res = await fetch(`${getBaseUrl()}/api/clients`);
        if (!res.ok) throw new Error('Failed to fetch clients');
        const clients = await res.json();
        
        const select = document.getElementById('client');
        const previousValue = select.value; // Store previously selected value
        select.innerHTML = clients.length ? '' : '<option value="">No devices found</option>';
        
        let plexampClient = null;
        
        clients.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.name;
            opt.textContent = `${c.name} (${c.product})`;
            select.appendChild(opt);
            
            // Look for Plex Amp instance
            if (c.product && c.product.toLowerCase().includes('plexamp')) {
                plexampClient = c.name;
            }
        });
        
        // Auto-select Plex Amp if found, otherwise restore previous selection or select first available
        if (plexampClient) {
            select.value = plexampClient;
        } else if (previousValue && Array.from(select.options).some(opt => opt.value === previousValue)) {
            select.value = previousValue;
        } else if (clients.length > 0) {
            select.value = clients[0].name;
        }
    } catch (err) {
        console.error('Error fetching clients:', err);
        const select = document.getElementById('client');
        select.innerHTML = '<option value="">Error loading devices</option>';
    }
}

async function handlePlay() {
    if (!currentPlaylist) return;
    
    const client = document.getElementById('client').value;
    if (!client) {
        showToast('Please select a playback device', true);
        return;
    }

    const btn = document.getElementById('btn-play-top');
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
}

async function handleSave() {
    if (!currentPlaylist) return;

    const btn = document.getElementById('btn-save-top');
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
}

// --- Generate Playlist (Streaming) ---
document.getElementById('btn-generate').addEventListener('click', async () => {
    const prompt = document.getElementById('prompt').value.trim();
    const trackCount = parseInt(document.getElementById('track-count').value, 10);

    if (!prompt) {
        showToast('Please enter a prompt', true);
        return;
    }

    if (isNaN(trackCount) || trackCount < 1) {
        showToast('Please enter a valid track count', true);
        return;
    }

    currentPlaylist = null;
    currentGenerationId = null;
    clearState();
    
    document.getElementById('activity-feed-container').classList.remove('hidden');
    document.getElementById('results-container').classList.add('hidden');
    document.getElementById('action-buttons').style.display = 'none';
    
    // Clear all phase feeds
    document.querySelectorAll('.phase-feed').forEach(feed => feed.innerHTML = '');
    document.getElementById('phase-timing').innerHTML = '';
    
    // Reset control panel to visible and open
    document.getElementById('cp-body').style.display = 'block';
    document.getElementById('cp-toggle').textContent = 'Hide Details';
    document.getElementById('phase-prompt').setAttribute('open', '');
    document.getElementById('phase-llm').setAttribute('open', '');
    document.getElementById('phase-matching').setAttribute('open', '');
    document.getElementById('phase-sonic').setAttribute('open', '');
    
    document.getElementById('progress-bar').style.width = '0%';
    
    const btn = document.getElementById('btn-generate');
    btn.disabled = true;
    
    // Track generation start time
    generationStartTime = Date.now();
    
    try {
        const res = await fetch(`${getBaseUrl()}/api/playlist/generate-stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt, track_count: trackCount }),
            keepalive: true,  // Prevent browser from terminating connection when tab loses focus
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
                                    source: t.source || 'sonic',
                                })),
                            };
                            saveState();
                            displaySummaryCard(eventData);
                            displayResults(currentPlaylist, false);
                            addFeedLine(eventData);
                            
                            // Collapse control panel after completion
                            const cpBody = document.getElementById('cp-body');
                            const cpToggle = document.getElementById('cp-toggle');
                            cpBody.style.display = 'none';
                            cpToggle.textContent = 'Show Details';
                            
                            // Close all phase sections
                            document.getElementById('phase-prompt').removeAttribute('open');
                            document.getElementById('phase-llm').removeAttribute('open');
                            document.getElementById('phase-matching').removeAttribute('open');
                            document.getElementById('phase-sonic').removeAttribute('open');
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

function displayResults(data, hideFeed = true) {
    document.getElementById('playlist-title').textContent = data.name;
    document.getElementById('playlist-desc').textContent = data.description;
    
    const list = document.getElementById('track-list');
    list.innerHTML = '';
    
    if (data.tracks && data.tracks.length > 0) {
        data.tracks.forEach((track, idx) => {
            const li = document.createElement('li');
            li.className = 'track-item';
            li.style.animation = `slideIn 0.3s ease-out ${idx * 0.05}s backwards`;
            
            let descriptionHtml = '';
            if (track.source === 'llm' && track.reasoning) {
                // LLM-suggested track with reasoning
                descriptionHtml = `<div class="track-reasoning">${escapeHtml(track.reasoning)}</div>`;
            } else if (track.source === 'sonic') {
                // Sonic-expanded track
                descriptionHtml = `<div class="track-source-sonic">Added via sonic analysis</div>`;
            }
            
            li.innerHTML = `
                <div class="track-title">${escapeHtml(track.title)}</div>
                <div class="track-artist">${escapeHtml(track.artist)}</div>
                ${descriptionHtml}
            `;
            list.appendChild(li);
        });
    }
    
    if (hideFeed) {
        document.getElementById('activity-feed-container').classList.add('hidden');
    }
    document.getElementById('results-container').classList.remove('hidden');
}

// --- Play / Save Actions (moved to displaySummaryCard where buttons are created) ---
