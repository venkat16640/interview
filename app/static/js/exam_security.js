/**
 * exam_security.js
 * ================
 * Client-side exam security / anti-cheat module.
 *
 * Protections implemented
 * -----------------------
 *  1. Fullscreen enforcement (request + violation on exit)
 *  2. Tab / window visibility detection
 *  3. Copy / cut / paste blocking
 *  4. Right-click context menu blocking
 *  5. Keyboard shortcut blocking (DevTools, PrintScreen, etc.)
 *  6. DevTools open detection (size heuristic)
 *  7. Screen-capture / print blocking
 *  8. Periodic heartbeat to server
 *  9. Security HUD overlay (live integrity score, violation counter)
 * 10. Auto-terminate when integrity score drops below threshold
 *
 * Usage (add to conduct.html after the page loads):
 *   ExamSecurity.init({ interviewId: 42, csrfToken: '…', terminalCb: fn });
 */

'use strict';

const ExamSecurity = (() => {

    // ── Config defaults (overridden by init options) ──────────────────
    let CFG = {
        interviewId: null,
        csrfToken: '',
        heartbeatInterval: 15_000,   // ms
        devToolsThreshold: 160,      // px – triggers devtools warning
        maxViolations: 10,       // violations before force-terminate
        minIntegrity: 20,       // integrity score floor (0-100)
        requireFullscreen: true,
        blockCopyPaste: true,
        blockRightClick: true,
        blockDevTools: true,
        blockShortcuts: true,
        onTerminate: null,     // callback(reason)
        apiBase: '/security',
    };

    let _heartbeatTimer = null;
    let _devToolsTimer = null;
    let _hudEl = null;
    let _totalViolations = 0;
    let _integrityScore = 100;
    let _initialized = false;

    // ══════════════════════════════════════════════════════════════════
    // Public API
    // ══════════════════════════════════════════════════════════════════

    function init(options = {}) {
        if (_initialized) return;
        Object.assign(CFG, options);
        _initialized = true;

        _buildHUD();
        _applyBodyLock();

        if (CFG.requireFullscreen) _attachFullscreenGuard();
        if (CFG.blockCopyPaste) _attachClipboardBlock();
        if (CFG.blockRightClick) _attachRightClickBlock();
        if (CFG.blockShortcuts) _attachKeyboardBlock();
        if (CFG.blockDevTools) _startDevToolsDetection();

        _attachVisibilityGuard();
        _startHeartbeat();
        _activateLockdown();

        // Request fullscreen immediately
        if (CFG.requireFullscreen) _requestFullscreen();

        console.info('[ExamSecurity] Initialised for interview', CFG.interviewId);
    }

    function destroy() {
        clearInterval(_heartbeatTimer);
        clearInterval(_devToolsTimer);
        if (_hudEl) _hudEl.remove();
        _releaseLockdown();
    }

    // ══════════════════════════════════════════════════════════════════
    // 1. Fullscreen Guard
    // ══════════════════════════════════════════════════════════════════

    function _requestFullscreen() {
        const el = document.documentElement;
        const fn = el.requestFullscreen || el.webkitRequestFullscreen || el.mozRequestFullScreen;
        if (fn) {
            fn.call(el).catch(() => { });
        }
    }

    function _attachFullscreenGuard() {
        const onFsChange = () => {
            const isFs = !!(document.fullscreenElement ||
                document.webkitFullscreenElement ||
                document.mozFullScreenElement);
            _hudUpdateFs(isFs);

            if (!isFs) {
                // User exited fullscreen
                _logViolation('fullscreen_exit', { message: 'Fullscreen was exited' });
                _showSecurityWarning(
                    '⚠ Fullscreen Exited',
                    'Please return to fullscreen to continue the exam. Click the button below.',
                    true,  // show restore button
                );
            }
        };
        document.addEventListener('fullscreenchange', onFsChange);
        document.addEventListener('webkitfullscreenchange', onFsChange);
        document.addEventListener('mozfullscreenchange', onFsChange);
    }

    // ══════════════════════════════════════════════════════════════════
    // 2. Tab / Visibility Guard
    // ══════════════════════════════════════════════════════════════════

    function _attachVisibilityGuard() {
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                _logViolation('tab_switch', { message: 'Tab was switched or window minimised' });
                _showSecurityWarning(
                    '⚠ Tab Switch Detected',
                    'Switching tabs or minimising the window is not allowed during exams.',
                    false,
                );
            }
        });

        window.addEventListener('blur', () => {
            _logViolation('window_blur', { message: 'Window lost focus' });
        });
    }

    // ══════════════════════════════════════════════════════════════════
    // 3. Clipboard Block
    // ══════════════════════════════════════════════════════════════════

    function _attachClipboardBlock() {
        document.addEventListener('copy', _blockClipboard);
        document.addEventListener('cut', _blockClipboard);
        document.addEventListener('paste', _blockPaste);
    }

    function _blockClipboard(e) {
        // Allow copy inside Monaco editor (it has its own container)
        if (_isMonacoTarget(e.target)) return;
        e.preventDefault();
        _logViolation('copy_attempt', { message: 'Copy/cut attempt blocked' });
        _hudFlash('⚑ Copy blocked', 'warn');
    }

    function _blockPaste(e) {
        if (_isMonacoTarget(e.target)) return;
        e.preventDefault();
        _logViolation('paste_attempt', { message: 'Paste attempt blocked' });
        _hudFlash('⚑ Paste blocked', 'warn');
    }

    function _isMonacoTarget(t) {
        return t && (
            t.closest('.monaco-editor') ||
            t.closest('[data-type="monaco"]') ||
            t.classList.contains('inputarea')
        );
    }

    // ══════════════════════════════════════════════════════════════════
    // 4. Right-click Block
    // ══════════════════════════════════════════════════════════════════

    function _attachRightClickBlock() {
        document.addEventListener('contextmenu', e => {
            e.preventDefault();
            _logViolation('right_click', { message: 'Right-click blocked' });
            _hudFlash('⚑ Right-click blocked', 'info');
        });
    }

    // ══════════════════════════════════════════════════════════════════
    // 5. Keyboard Shortcut Block
    // ══════════════════════════════════════════════════════════════════

    const _BLOCKED_COMBOS = [
        // DevTools
        { key: 'F12' },
        { ctrlKey: true, shiftKey: true, key: 'I' },
        { ctrlKey: true, shiftKey: true, key: 'J' },
        { ctrlKey: true, shiftKey: true, key: 'C' },
        { ctrlKey: true, key: 'U' },          // view-source
        // Screenshot / Print
        { key: 'PrintScreen' },
        { ctrlKey: true, key: 'P' },
        // Selection / clipboard
        { ctrlKey: true, key: 'A' },           // select all
        { ctrlKey: true, key: 'C' },           // copy
        { ctrlKey: true, key: 'X' },           // cut
        { ctrlKey: true, key: 'V' },           // paste
        // New tab / window
        { ctrlKey: true, key: 'T' },
        { ctrlKey: true, key: 'N' },
        { ctrlKey: true, shiftKey: true, key: 'N' },
        // Find
        { ctrlKey: true, key: 'F' },
    ];

    function _attachKeyboardBlock() {
        document.addEventListener('keydown', e => {
            // Allow Monaco editor shortcuts (code input)
            if (_isMonacoTarget(e.target)) return;

            for (const combo of _BLOCKED_COMBOS) {
                const match = Object.entries(combo).every(([prop, val]) =>
                    e[prop] === val || (prop === 'key' && e.key.toUpperCase() === val.toUpperCase())
                );
                if (match) {
                    e.preventDefault();
                    e.stopPropagation();
                    _logViolation('keyboard_shortcut', { key: e.key, combo: JSON.stringify(combo) });
                    _hudFlash(`⚑ Shortcut blocked: ${e.key}`, 'warn');
                    return;
                }
            }
        }, true);

        // Block text selection via keyboard
        document.addEventListener('selectstart', e => {
            if (_isMonacoTarget(e.target) || e.target.tagName === 'TEXTAREA' ||
                e.target.tagName === 'INPUT') return;
            e.preventDefault();
        });
    }

    // ══════════════════════════════════════════════════════════════════
    // 6. DevTools Detection
    // ══════════════════════════════════════════════════════════════════

    let _devToolsOpen = false;

    function _startDevToolsDetection() {
        _devToolsTimer = setInterval(() => {
            const threshold = CFG.devToolsThreshold;
            const open = (window.outerWidth - window.innerWidth > threshold) ||
                (window.outerHeight - window.innerHeight > threshold);

            if (open && !_devToolsOpen) {
                _devToolsOpen = true;
                _logViolation('devtools_open', { message: 'DevTools panel opened' });
                _showSecurityWarning(
                    '🚫 Developer Tools Detected',
                    'Using browser developer tools during exams is strictly prohibited.',
                    false,
                );
            } else if (!open) {
                _devToolsOpen = false;
            }
        }, 1500);

        // Debugger detection (pauses when DevTools is open and debugger runs)
        const _dtCheck = new Image();
        Object.defineProperty(_dtCheck, 'id', {
            get: function () {
                _logViolation('devtools_open', { message: 'Debugger detected' });
            }
        });
    }

    // ══════════════════════════════════════════════════════════════════
    // 7. Print block
    // ══════════════════════════════════════════════════════════════════

    window.addEventListener('beforeprint', e => {
        e.preventDefault();
        _logViolation('print_attempt', { message: 'Print dialog detected' });
    });

    // ══════════════════════════════════════════════════════════════════
    // 8. Heartbeat
    // ══════════════════════════════════════════════════════════════════

    function _startHeartbeat() {
        _heartbeatTimer = setInterval(_sendHeartbeat, CFG.heartbeatInterval);
        _sendHeartbeat();
    }

    async function _sendHeartbeat() {
        if (!CFG.interviewId) return;
        try {
            const isFs = !!(document.fullscreenElement ||
                document.webkitFullscreenElement);
            const res = await fetch(`${CFG.apiBase}/heartbeat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    interview_id: CFG.interviewId,
                    fullscreen: isFs,
                    tab_visible: !document.hidden,
                    screen_width: window.screen.width,
                    screen_height: window.screen.height,
                }),
            });
            if (res.ok) {
                const d = await res.json();
                if (d.integrity_score !== undefined) {
                    _integrityScore = d.integrity_score;
                    _hudUpdateScore(d.integrity_score, d.violations);
                }
            }
        } catch (_) {/*ignore network hiccups*/ }
    }

    // ══════════════════════════════════════════════════════════════════
    // 9. Violation Logger
    // ══════════════════════════════════════════════════════════════════

    async function _logViolation(type, details = {}) {
        _totalViolations++;
        _hudFlash(`⚠ ${_prettify(type)}`, 'danger');
        _hudUpdateScore(_integrityScore, _totalViolations);

        try {
            const res = await fetch(`${CFG.apiBase}/log-event`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': CFG.csrfToken || '',
                },
                body: JSON.stringify({
                    interview_id: CFG.interviewId,
                    event_type: type,
                    details: details,
                }),
            });
            if (res.ok) {
                const d = await res.json();
                _integrityScore = d.integrity_score ?? _integrityScore;
                _hudUpdateScore(_integrityScore, d.total_violations ?? _totalViolations);

                if (d.should_terminate) {
                    _terminate('Exam terminated: integrity score critically low.');
                }
            }
        } catch (_) {/*ignore*/ }
    }

    function _prettify(type) {
        return {
            tab_switch: 'Tab Switch',
            fullscreen_exit: 'Fullscreen Exit',
            copy_attempt: 'Copy Blocked',
            paste_attempt: 'Paste Blocked',
            right_click: 'Right-click Blocked',
            keyboard_shortcut: 'Shortcut Blocked',
            devtools_open: 'DevTools Detected',
            window_blur: 'Window Blur',
            print_attempt: 'Print Blocked',
            identity_mismatch: 'Identity Mismatch',
            multiple_faces: 'Multiple Faces',
            no_face: 'No Face Detected',
        }[type] || type;
    }

    // ══════════════════════════════════════════════════════════════════
    // 10. Auto-terminate
    // ══════════════════════════════════════════════════════════════════

    function _terminate(reason) {
        destroy();
        if (typeof CFG.onTerminate === 'function') {
            CFG.onTerminate(reason);
        } else {
            _showFatalOverlay(reason);
        }
    }

    // ══════════════════════════════════════════════════════════════════
    // Security HUD
    // ══════════════════════════════════════════════════════════════════

    function _buildHUD() {
        if (_hudEl) return;
        _hudEl = document.createElement('div');
        _hudEl.id = 'exam-security-hud';
        _hudEl.innerHTML = `
            <div class="esh-row">
                <span class="esh-icon">🛡</span>
                <span class="esh-label">Integrity</span>
                <span class="esh-score" id="esh-score">100</span>
                <div class="esh-bar-wrap"><div class="esh-bar" id="esh-bar"></div></div>
            </div>
            <div class="esh-row esh-row2">
                <span class="esh-vcount" id="esh-vcount">0 violations</span>
                <span class="esh-fs" id="esh-fs" title="Fullscreen">⛶</span>
                <span class="esh-flash" id="esh-flash"></span>
            </div>`;

        const style = document.createElement('style');
        style.textContent = `
            #exam-security-hud {
                position: fixed;
                top: 8px; right: 8px;
                background: rgba(10,11,20,0.92);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 10px;
                padding: 8px 12px;
                z-index: 99999;
                min-width: 210px;
                font-family: 'Inter', system-ui, sans-serif;
                font-size: 12px;
                color: #e2e8f0;
                backdrop-filter: blur(10px);
                box-shadow: 0 4px 20px rgba(0,0,0,0.5);
                user-select: none;
            }
            .esh-row { display:flex; align-items:center; gap:6px; }
            .esh-row2 { margin-top:5px; }
            .esh-icon { font-size:14px; }
            .esh-label { color:#94a3b8; font-size:11px; letter-spacing:.5px; text-transform:uppercase; }
            .esh-score { font-weight:800; font-size:15px; min-width:28px; text-align:right;
                         color:#10b981; transition:color .4s; }
            .esh-bar-wrap { flex:1; height:4px; background:rgba(255,255,255,0.07);
                            border-radius:4px; overflow:hidden; }
            .esh-bar { height:100%; border-radius:4px; background:#10b981;
                       width:100%; transition:width .6s,background .6s; }
            .esh-vcount { color:#64748b; font-size:11px; flex:1; }
            .esh-fs { font-size:15px; cursor:pointer; opacity:.5; transition:opacity .2s; }
            .esh-fs.ok { color:#10b981; opacity:1; }
            .esh-flash { font-size:11px; color:#f97316; font-weight:600;
                         transition:opacity .5s; opacity:0; max-width:120px;
                         overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }

            /* Security warning overlay */
            #esh-warn-overlay {
                position:fixed; inset:0; z-index:999999;
                background:rgba(0,0,0,0.85); backdrop-filter:blur(8px);
                display:flex; align-items:center; justify-content:center;
                animation:eshFadeIn .25s ease;
            }
            @keyframes eshFadeIn { from{opacity:0} to{opacity:1} }
            .esh-warn-card {
                background:rgba(20,20,35,0.98);
                border:1px solid rgba(239,68,68,0.4);
                border-radius:18px;
                padding:36px;
                max-width:440px;
                width:90%;
                text-align:center;
                box-shadow:0 0 60px rgba(239,68,68,0.15);
            }
            .esh-warn-card h2 { color:#f87171; font-size:1.4rem; margin-bottom:10px; }
            .esh-warn-card p  { color:#94a3b8; font-size:.9rem; line-height:1.6; }
            .esh-warn-btn {
                margin-top:20px;
                background:linear-gradient(135deg,#ef4444,#b91c1c);
                color:#fff; border:none; border-radius:10px;
                padding:10px 28px; font-size:.93rem; font-weight:700;
                cursor:pointer; transition:opacity .2s;
            }
            .esh-warn-btn:hover { opacity:.85; }
            .esh-restore-btn {
                background:linear-gradient(135deg,#6366f1,#4f46e5);
                margin-right:8px;
            }

            /* Fatal overlay */
            #esh-fatal-overlay {
                position:fixed; inset:0; z-index:9999999;
                background:rgba(5,5,10,0.97);
                display:flex; align-items:center; justify-content:center;
                flex-direction:column; gap:16px;
                font-family:'Inter',sans-serif;
            }
            .esh-fatal-icon { font-size:56px; }
            .esh-fatal-title { color:#ef4444; font-size:1.8rem; font-weight:800; }
            .esh-fatal-msg   { color:#94a3b8; font-size:.95rem; max-width:400px; text-align:center; }
        `;
        document.head.appendChild(style);
        document.body.appendChild(_hudEl);

        // Clicking the fullscreen icon re-requests it
        document.getElementById('esh-fs').addEventListener('click', _requestFullscreen);
    }

    let _flashTimer = null;
    function _hudFlash(msg, level = 'warn') {
        const el = document.getElementById('esh-flash');
        if (!el) return;
        el.textContent = msg;
        el.style.color = level === 'danger' ? '#ef4444' : level === 'warn' ? '#f97316' : '#94a3b8';
        el.style.opacity = '1';
        clearTimeout(_flashTimer);
        _flashTimer = setTimeout(() => { el.style.opacity = '0'; }, 3000);
    }

    function _hudUpdateScore(score, violations) {
        const sEl = document.getElementById('esh-score');
        const bEl = document.getElementById('esh-bar');
        const vEl = document.getElementById('esh-vcount');
        if (sEl) {
            sEl.textContent = Math.round(score);
            sEl.style.color = score >= 70 ? '#10b981' : score >= 40 ? '#f59e0b' : '#ef4444';
        }
        if (bEl) {
            bEl.style.width = Math.max(2, score) + '%';
            bEl.style.background = score >= 70 ? '#10b981' : score >= 40 ? '#f59e0b' : '#ef4444';
        }
        if (vEl) vEl.textContent = violations + ' violation' + (violations !== 1 ? 's' : '');
    }

    function _hudUpdateFs(isFs) {
        const el = document.getElementById('esh-fs');
        if (!el) return;
        el.className = 'esh-fs' + (isFs ? ' ok' : '');
        el.title = isFs ? 'Fullscreen active ✓' : 'Click to restore fullscreen';
    }

    // ── Warning modal ─────────────────────────────────────────────────

    let _warnEl = null;
    function _showSecurityWarning(title, body, showRestore = false) {
        if (_warnEl) return;
        _warnEl = document.createElement('div');
        _warnEl.id = 'esh-warn-overlay';
        _warnEl.innerHTML = `
            <div class="esh-warn-card">
                <h2>${title}</h2>
                <p>${body}</p>
                <div style="margin-top:20px;display:flex;gap:8px;justify-content:center;flex-wrap:wrap;">
                    ${showRestore ? `<button class="esh-warn-btn esh-restore-btn" onclick="ExamSecurity._restoreFs()">⛶ Restore Fullscreen</button>` : ''}
                    <button class="esh-warn-btn" onclick="ExamSecurity._dismissWarning()">I Understand — Continue</button>
                </div>
            </div>`;
        document.body.appendChild(_warnEl);
    }

    function _dismissWarning() {
        if (_warnEl) { _warnEl.remove(); _warnEl = null; }
    }

    function _restoreFs() {
        _requestFullscreen();
        _dismissWarning();
    }

    function _showFatalOverlay(reason) {
        document.body.innerHTML = `
            <div id="esh-fatal-overlay">
                <div class="esh-fatal-icon">🚫</div>
                <div class="esh-fatal-title">Exam Terminated</div>
                <div class="esh-fatal-msg">${reason}</div>
                <div class="esh-fatal-msg" style="color:#475569;font-size:.8rem;margin-top:8px;">
                    Your activity has been recorded. Please contact the exam administrator.
                </div>
            </div>`;
    }

    // ── CSS lock on body ──────────────────────────────────────────────

    function _applyBodyLock() {
        const s = document.createElement('style');
        s.id = 'exam-body-lock';
        s.textContent = `
            /* Prevent text selection everywhere except form inputs and Monaco */
            body *:not(input):not(textarea):not(.monaco-editor *):not(.inputarea) {
                -webkit-user-select: none !important;
                user-select: none !important;
            }
            /* Prevent drag of images/elements */
            img, a { -webkit-user-drag: none; user-drag: none; pointer-events: none; }
            a { pointer-events: auto; }
        `;
        document.head.appendChild(s);
    }

    // ── Lockdown API calls ────────────────────────────────────────────

    async function _activateLockdown() {
        if (!CFG.interviewId) return;
        const isFs = !!(document.fullscreenElement || document.webkitFullscreenElement);
        try {
            await fetch(`${CFG.apiBase}/lockdown/activate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CFG.csrfToken },
                body: JSON.stringify({ interview_id: CFG.interviewId, fullscreen: isFs }),
            });
        } catch (_) { }
    }

    async function _releaseLockdown() {
        if (!CFG.interviewId) return;
        try {
            await fetch(`${CFG.apiBase}/lockdown/release`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': CFG.csrfToken },
                body: JSON.stringify({ interview_id: CFG.interviewId }),
            });
        } catch (_) { }
    }

    // ── Expose limited public surface ─────────────────────────────────

    return { init, destroy, _dismissWarning, _restoreFs, _requestFullscreen };

})();

// Auto-release lockdown on page leave
window.addEventListener('beforeunload', () => ExamSecurity.destroy());
