const API_BASE = '/api';

// --- UI Helpers ---
function showToast(message, isError = false) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast show ${isError ? 'error' : 'success'}`;
    setTimeout(() => toast.className = 'toast', 3000);
}

function setLoading(isLoading, btnId = 'btn-generate') {
    const btn = document.getElementById(btnId);
    btn.disabled = isLoading;
    document.getElementById('loading').classList.toggle('hidden', !isLoading);
}

// --- State ---
let currentPlaylist = null;

// --- Init ---
document.addEventListener('DOMContentLoaded', () => {
    fetchClients();
    fetchSyncStatus();
    setInterval(fetchSyncStatus, 5000); // Poll status periodically
});

// --- Fetch Clients ---
async function fetchClients() {
    try {
        const baseUrl = window.location.port === '3033' ? 'http://localhost:8033' : '';
        const res = await fetch(`${baseUrl}/api/clients`);
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
        const baseUrl = window.location.port === '3033' ? 'http://localhost:8033' : '';
        const res = await fetch(`${baseUrl}/api/sync/status`);
        if (!res.ok) return;
        const status = await res.json();
        
        const badge = document.getElementById('sync-status');
        const btn = document.getElementById('btn-sync');
        
        if (status.in_progress) {
            badge.textContent = `Syncing... ${status.synced_tracks} tracks`;
            badge.className = 'status-badge';
            btn.disabled = true;
        } else {
            badge.textContent = `Synced: ${status.synced_tracks} tracks`;
            badge.className = 'status-badge ok';
            btn.disabled = false;
        }
    } catch (err) {
        console.error('Sync status error:', err);
    }
}

document.getElementById('btn-sync').addEventListener('click', async () => {
    try {
        const baseUrl = window.location.port === '3033' ? 'http://localhost:8033' : '';
        const res = await fetch(`${baseUrl}/api/sync`, { method: 'POST' });
        if (!res.ok) throw new Error('Failed to start sync');
        showToast('Library sync started');
        fetchSyncStatus();
    } catch (err) {
        showToast('Error starting sync', true);
    }
});

// --- Generate Playlist ---
document.getElementById('btn-generate').addEventListener('click', async () => {
    const prompt = document.getElementById('prompt').value.trim();
    const trackCount = parseInt(document.getElementById('track-count').value, 10);
    
    if (!prompt) {
        showToast('Please enter a prompt', true);
        return;
    }

    setLoading(true);
    document.getElementById('results-container').classList.add('hidden');
    
    try {
        const baseUrl = window.location.port === '3033' ? 'http://localhost:8033' : '';
        const res = await fetch(`${baseUrl}/api/suggest`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt, track_count: trackCount })
        });
        
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.detail || `Server error: ${res.status}`);
        }
        
        const data = await res.json();
        currentPlaylist = data;
        displayResults(data);
        
    } catch (err) {
        console.error('Generate error:', err);
        showToast(err.message, true);
    } finally {
        setLoading(false);
    }
});

function displayResults(data) {
    document.getElementById('playlist-title').textContent = data.name;
    document.getElementById('playlist-desc').textContent = data.description;
    
    const list = document.getElementById('track-list');
    list.innerHTML = '';
    
    data.tracks.forEach(track => {
        const li = document.createElement('li');
        li.className = 'track-item';
        li.innerHTML = `
            <div class="track-title">${track.title}</div>
            <div class="track-artist">${track.artist}</div>
            <div class="track-reasoning">${track.reasoning}</div>
        `;
        list.appendChild(li);
    });
    
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
    btn.textContent = 'Playing...';
    
    try {
        const prompt = document.getElementById('prompt').value;
        const baseUrl = window.location.port === '3033' ? 'http://localhost:8033' : '';
        const res = await fetch(`${baseUrl}/api/playlist/play`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                prompt, 
                track_count: currentPlaylist.tracks.length,
                client_name: client
            })
        });
        
        if (!res.ok) throw new Error('Failed to start playback');
        showToast(`Playback started on ${client}`);
    } catch (err) {
        console.error('Play error:', err);
        showToast('Error starting playback', true);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Play';
    }
});

document.getElementById('btn-save').addEventListener('click', async () => {
    if (!currentPlaylist) return;

    const btn = document.getElementById('btn-save');
    btn.disabled = true;
    btn.textContent = 'Saving...';
    
    try {
        const prompt = document.getElementById('prompt').value;
        const baseUrl = window.location.port === '3033' ? 'http://localhost:8033' : '';
        const res = await fetch(`${baseUrl}/api/playlist/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                prompt, 
                track_count: currentPlaylist.tracks.length,
                playlist_name: currentPlaylist.name
            })
        });
        
        if (!res.ok) throw new Error('Failed to save playlist');
        showToast(`Playlist '${currentPlaylist.name}' saved`);
    } catch (err) {
        console.error('Save error:', err);
        showToast('Error saving playlist', true);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Save';
    }
});
