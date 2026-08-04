/**
 * Aurora Better Asset Manager — Frontend (class-based)
 * Talks to the FastAPI backend engine. All UI logic lives in AuroraApp;
 * ApiClient, ThemeManager, ToastManager and Lightbox are focused helpers.
 */

const API_BASE = "http://127.0.0.1:8000/api";
const $ = (id) => document.getElementById(id);
const refreshIcons = () => { if (window.lucide) lucide.createIcons(); };

/* ═══════════════════════════════════════════════════════════════
   ApiClient — thin wrapper over the backend REST endpoints
   ═══════════════════════════════════════════════════════════════ */
class ApiClient {
    constructor(base) { this.base = base; }

    async getJSON(path) {
        const res = await fetch(`${this.base}${path}`);
        return { ok: res.ok, data: await res.json() };
    }
    async postJSON(path, body) {
        const res = await fetch(`${this.base}${path}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body || {}),
        });
        return { ok: res.ok, data: await res.json() };
    }
    async postForm(path, formData) {
        const res = await fetch(`${this.base}${path}`, { method: "POST", body: formData });
        let data = {};
        try { data = await res.json(); } catch (_) { /* non-json */ }
        return { ok: res.ok, data };
    }

    status()               { return this.getJSON("/status"); }
    ftpConfig()            { return this.getJSON("/ftp/config"); }
    saveFtpConfig(cfg)     { return this.postJSON("/ftp/config", cfg); }
    testFtp(cfg)           { return this.postJSON("/ftp/test", cfg); }
    downloadDb(cfg)        { return this.postJSON("/ftp/download-db", cfg); }
    parseDbFile(fd)        { return this.postForm("/db/parse-file", fd); }
    assetStatus(games)     { return this.postJSON("/library/asset-status", { games }); }
    setGameInfo(info)      { return this.postJSON("/game/set-info", info); }
    pullTitleName(cfg)     { return this.postJSON("/ftp/pull-title-name", cfg); }
    pushTitleName(payload) { return this.postJSON("/ftp/push-title-name", payload); }
    pullGameAssets(cfg)    { return this.postJSON("/ftp/pull-game-assets", cfg); }
    syncGameAssets(cfg)    { return this.postJSON("/ftp/sync-game-assets", cfg); }
    pushAllAssets(payload) { return this.postJSON("/ftp/push-all-assets", payload); }
    downloadGameMissing(p) { return this.postJSON("/ftp/download-game-missing-assets", p); }
    detectChanges(payload) { return this.postJSON("/ftp/detect-changes", payload); }
    replaceImage(fd)       { return this.postForm("/asset/replace-image", fd); }
    replaceImageUrl(fd)    { return this.postForm("/asset/replace-image-url", fd); }
    revertAsset(payload)   { return this.postJSON("/asset/revert", payload); }
    searchUnity(q)         { return this.getJSON(`/search/unity?query=${encodeURIComponent(q)}`); }
    searchMedia(q, cat)    { return this.getJSON(`/search/media?query=${encodeURIComponent(q)}&category=${encodeURIComponent(cat)}`); }
}

/* ═══════════════════════════════════════════════════════════════
   ThemeManager — light / dark persistence
   ═══════════════════════════════════════════════════════════════ */
class ThemeManager {
    constructor() { this.KEY = "abam-theme"; }
    get current() { return document.documentElement.getAttribute("data-theme") || "dark"; }
    apply(theme) {
        document.documentElement.setAttribute("data-theme", theme);
        try { localStorage.setItem(this.KEY, theme); } catch (_) {}
        document.querySelectorAll("[data-set-theme]").forEach(b =>
            b.classList.toggle("active", b.getAttribute("data-set-theme") === theme));
        refreshIcons();
    }
    toggle() { this.apply(this.current === "dark" ? "light" : "dark"); }
    init() {
        let stored = "dark";
        try { stored = localStorage.getItem(this.KEY) || "dark"; } catch (_) {}
        this.apply(stored);
    }
}

/* ═══════════════════════════════════════════════════════════════
   ToastManager
   ═══════════════════════════════════════════════════════════════ */
class ToastManager {
    constructor(containerId) { this.container = $(containerId); }
    show(msg, type = "info", duration = 3500) {
        if (!this.container) return;
        const icons = { info: "info", success: "check-circle", error: "alert-circle", warning: "alert-triangle" };
        const toast = document.createElement("div");
        toast.className = `toast-message ${type}`;
        toast.innerHTML = `<i data-lucide="${icons[type] || "info"}"></i> <span>${msg}</span>`;
        this.container.appendChild(toast);
        refreshIcons();
        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateY(-10px)";
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }
}

/* ═══════════════════════════════════════════════════════════════
   Lightbox — zoom / pan image viewer
   ═══════════════════════════════════════════════════════════════ */
class Lightbox {
    constructor() {
        this.s = { scale: 1, min: 0.25, max: 8, x: 0, y: 0, dragging: false, sx: 0, sy: 0, tx: 0, ty: 0 };
        this.lastTouchDist = null;
    }
    init() {
        this.overlay = $("imgLightbox");
        this.img = $("lightboxImg");
        this.stage = $("lightboxStage");
        if (!this.overlay) return;

        $("lightboxClose").addEventListener("click", () => this.close());
        $("lightboxZoomIn").addEventListener("click", () => this.zoom(1.25));
        $("lightboxZoomOut").addEventListener("click", () => this.zoom(0.8));
        $("lightboxReset").addEventListener("click", () => { this.s.scale = 1; this.s.x = 0; this.s.y = 0; this.apply(); });
        this.replaceBtn = $("lightboxReplace");
        if (this.replaceBtn) this.replaceBtn.addEventListener("click", () => {
            const cb = this.onReplace; this.close();
            if (typeof cb === "function") cb();
        });

        this.overlay.addEventListener("click", (e) => { if (e.target === this.stage) this.close(); });
        document.addEventListener("keydown", (e) => { if (e.key === "Escape") this.close(); });

        this.stage.addEventListener("wheel", (e) => {
            e.preventDefault();
            this.zoom(e.deltaY < 0 ? 1.12 : 0.9, e.clientX, e.clientY);
        }, { passive: false });

        this.stage.addEventListener("mousedown", (e) => {
            if (e.button !== 0) return;
            this.s.dragging = true; this.s.sx = e.clientX; this.s.sy = e.clientY;
            this.s.tx = this.s.x; this.s.ty = this.s.y; this.stage.classList.add("dragging");
        });
        window.addEventListener("mousemove", (e) => {
            if (!this.s.dragging) return;
            this.s.x = this.s.tx + (e.clientX - this.s.sx);
            this.s.y = this.s.ty + (e.clientY - this.s.sy);
            this.apply();
        });
        window.addEventListener("mouseup", () => { this.s.dragging = false; this.stage.classList.remove("dragging"); });

        this.stage.addEventListener("touchstart", (e) => {
            if (e.touches.length === 1) {
                this.s.dragging = true; this.s.sx = e.touches[0].clientX; this.s.sy = e.touches[0].clientY;
                this.s.tx = this.s.x; this.s.ty = this.s.y;
            }
            if (e.touches.length === 2) {
                this.lastTouchDist = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
            }
        }, { passive: true });
        this.stage.addEventListener("touchmove", (e) => {
            e.preventDefault();
            if (e.touches.length === 1 && this.s.dragging) {
                this.s.x = this.s.tx + (e.touches[0].clientX - this.s.sx);
                this.s.y = this.s.ty + (e.touches[0].clientY - this.s.sy);
                this.apply();
            }
            if (e.touches.length === 2 && this.lastTouchDist) {
                const dist = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
                const cx = (e.touches[0].clientX + e.touches[1].clientX) / 2;
                const cy = (e.touches[0].clientY + e.touches[1].clientY) / 2;
                this.zoom(dist / this.lastTouchDist, cx, cy);
                this.lastTouchDist = dist;
            }
        }, { passive: false });
        this.stage.addEventListener("touchend", () => { this.s.dragging = false; this.lastTouchDist = null; });
    }
    open(src, title, onReplace = null) {
        $("lightboxTitle").innerText = title || "";
        this.img.src = src;
        this.onReplace = onReplace;
        if (this.replaceBtn) { this.replaceBtn.hidden = !onReplace; refreshIcons(); }
        this.s.scale = 1; this.s.x = 0; this.s.y = 0; this.apply();
        this.overlay.classList.add("active");
    }
    close() { this.overlay.classList.remove("active"); this.onReplace = null; }
    apply() {
        this.img.style.transform = `translate(${this.s.x}px, ${this.s.y}px) scale(${this.s.scale})`;
        this.img.style.transformOrigin = "center";
        $("lightboxZoomLevel").innerText = Math.round(this.s.scale * 100) + "%";
    }
    zoom(delta, cx, cy) {
        const rect = this.stage.getBoundingClientRect();
        const ox = (cx ?? rect.left + rect.width / 2) - rect.left - rect.width / 2;
        const oy = (cy ?? rect.top + rect.height / 2) - rect.top - rect.height / 2;
        const prev = this.s.scale;
        this.s.scale = Math.min(this.s.max, Math.max(this.s.min, this.s.scale * delta));
        const ratio = this.s.scale / prev;
        this.s.x = ox + (this.s.x - ox) * ratio;
        this.s.y = oy + (this.s.y - oy) * ratio;
        this.apply();
    }
}

/* ═══════════════════════════════════════════════════════════════
   AuroraApp — main controller
   ═══════════════════════════════════════════════════════════════ */
class AuroraApp {
    constructor() {
        this.api = new ApiClient(API_BASE);
        this.theme = new ThemeManager();
        this.toast = new ToastManager("toastContainer");
        this.lightbox = new Lightbox();

        this.previewCacheVersion = Date.now();
        this.assetStatusTimer = null;

        this.state = {
            currentGame: this.blankGame(),
            installedGames: [],
            ftpConfig: { ip: "", username: "xbox", password: "xbox", port: 21 },
            ftpConnected: false,
        };

        this.missing = { data: [], filter: "all", sortCol: "title", sortAsc: true };
        this.search = { game: null, category: "boxart" };
        this.pending = this.loadPending();
    }

    blankGame() {
        return {
            title_name: "No Game Selected", description: "", publisher: "", developer: "",
            release_date: "", title_id: "00000000", media_id: "00000000", db_id: "00000000",
            disc_num: 1, folder_path: "00000000_00000000",
        };
    }

    /* ── URL / lookup helpers ─────────────────────────────────── */
    buildPreviewUrl(category, assetIndex) {
        return this.buildTitlePreviewUrl(category, assetIndex,
            this.state.currentGame?.title_id || "00000000",
            this.state.currentGame?.db_id || "00000000");
    }
    buildTitlePreviewUrl(category, assetIndex, titleId, dbId = "00000000") {
        const params = new URLSearchParams();
        if (titleId && titleId !== "00000000") params.set("title", titleId);
        if (dbId && dbId !== "00000000") params.set("db", dbId);
        params.set("v", String(this.previewCacheVersion));
        return `${API_BASE}/asset/preview/${category}/${assetIndex}?${params.toString()}`;
    }
    getGameKey(game) { return (game?.db_id || "00000000").toUpperCase(); }
    findGameByDbId(dbId) {
        const key = (dbId || "00000000").toUpperCase();
        return this.state.installedGames.find(g => this.getGameKey(g) === key);
    }
    buildMissingThumbnailUrl(game) {
        if (game.has_boxart) return this.buildTitlePreviewUrl("boxart", 2, game.title_id, game.db_id);
        if (game.has_background) return this.buildTitlePreviewUrl("background", 4, game.title_id, game.db_id);
        if (game.has_icon) return this.buildTitlePreviewUrl("icon_banner", 0, game.title_id, game.db_id);
        if (game.has_banner) return this.buildTitlePreviewUrl("icon_banner", 1, game.title_id, game.db_id);
        if ((game.screenshot_count || 0) > 0) return this.buildTitlePreviewUrl("screenshots", 5, game.title_id, game.db_id);
        return null;
    }

    /* ── Bootstrap ────────────────────────────────────────────── */
    init() {
        this.theme.init();
        this.lightbox.init();
        this.initNavigation();
        this.initDragAndDrop();
        this.initEventListeners();
        this.initRouter();
        this.updatePendingUI();
        this.fetchAppStatus();
        this.fetchFtpConfig();
    }

    initNavigation() {
        this.navBtns = document.querySelectorAll(".nav-btn");
        this.navBtns.forEach(btn => btn.addEventListener("click", () => this.goToTab(btn.getAttribute("data-tab"))));

        document.querySelectorAll(".sub-tab-btn").forEach(btn =>
            btn.addEventListener("click", () => this.goToSubtab(btn.getAttribute("data-subtab"))));
    }
    goToTab(name, { push = true } = {}) {
        this.navBtns.forEach(b => b.classList.toggle("active", b.getAttribute("data-tab") === name));
        document.querySelectorAll(".tab-page").forEach(p => p.classList.remove("active"));
        const page = $(`tab-${name}`);
        if (page) page.classList.add("active");
        if (name === "missing" && this.state.installedGames.length > 0) this.fetchAssetStatus();
        if (push) this.pushUrl(name);
    }

    /* ── Client-side routing ──────────────────────────────────── */
    pathForTab(name) {
        switch (name) {
            case "studio": {
                const t = this.state.currentGame?.title_id;
                return (t && t !== "00000000") ? `/editor/${t}` : "/editor";
            }
            case "missing": return "/coverage";
            case "search": return "/search";
            case "ftp": return "/console";
            default: return "/library";
        }
    }
    tabForPath(pathname) {
        const p = (pathname || "/").replace(/\/+$/, "") || "/";
        if (p === "/" || p === "/library") return { tab: "library" };
        if (p === "/coverage") return { tab: "missing" };
        if (p === "/search") return { tab: "search" };
        if (p === "/console") return { tab: "ftp" };
        const m = p.match(/^\/editor(?:\/([^/]+))?$/);
        if (m) return { tab: "studio", titleId: m[1] || null };
        return { tab: "library" };
    }
    pushUrl(name) {
        const path = this.pathForTab(name);
        if (location.pathname !== path) history.pushState({ tab: name }, "", path);
    }
    initRouter() {
        window.addEventListener("popstate", () => this.applyRoute(location.pathname));
        this.applyRoute(location.pathname);
    }
    applyRoute(pathname) {
        const { tab, titleId } = this.tabForPath(pathname);
        if (tab === "studio") {
            if (titleId) {
                const game = this.state.installedGames.find(
                    g => (g.title_id || "").toUpperCase() === titleId.toUpperCase());
                if (game) { this.selectGame(game, "boxart"); return; }
                this.pendingTitleId = titleId;
            }
            this.goToTab("studio", { push: false });
            return;
        }
        this.goToTab(tab, { push: false });
    }
    resolvePendingEditor() {
        if (!this.pendingTitleId) return false;
        const game = this.state.installedGames.find(
            g => (g.title_id || "").toUpperCase() === this.pendingTitleId.toUpperCase());
        this.pendingTitleId = null;
        if (game) { this.selectGame(game, "boxart"); return true; }
        return false;
    }
    goToSubtab(name) {
        document.querySelectorAll(".sub-tab-btn").forEach(b => b.classList.toggle("active", b.getAttribute("data-subtab") === name));
        document.querySelectorAll(".sub-page").forEach(sp => sp.classList.toggle("active", sp.id === `subtab-${name}`));
    }

    async fetchAppStatus() {
        try {
            const { ok, data } = await this.api.status();
            if (!ok) return;
            const b = $("demoModeBadge");
            if (b) {
                b.hidden = !data.demo_mode;
                if (data.demo_mode) refreshIcons();
            }
            if (data.demo_mode) {
                this.downloadXboxContentDb({ keepTab: true });
            }
            if (data.game) this.updateCurrentGameUI(data.game);
        } catch (err) { console.warn("API starting or offline:", err); }
    }

    async fetchFtpConfig() {
        try {
            const { ok, data: cfg } = await this.api.ftpConfig();
            if (!ok) return;
            this.state.ftpConfig = cfg;
            $("ftpIp").value = cfg.ip || "";
            $("ftpUser").value = cfg.username || "xboxftp";
            $("ftpPass").value = cfg.password || "xboxftp";
            $("ftpPort").value = cfg.port || 21;
            if ($("quickFtpIp")) {
                $("quickFtpIp").value = cfg.ip || "";
                $("quickFtpUser").value = cfg.username || "xboxftp";
                $("quickFtpPass").value = cfg.password || "xboxftp";
                $("quickFtpPort").value = cfg.port || 21;
            }
            if (cfg.ip && cfg.ip.trim()) {
                const connected = await this.testFtpConnection(true);
                if (connected) { this.logConsole(`Xbox auto-connected to ${cfg.ip}`, "success"); this.downloadXboxContentDb(); }
            }
        } catch (err) { console.error("Error fetching FTP config:", err); }
    }

    /* ── Event wiring ─────────────────────────────────────────── */
    initEventListeners() {
        const on = (id, ev, fn) => { const el = $(id); if (el) el.addEventListener(ev, fn); };

        // Theme
        on("btnThemeToggle", "click", () => this.theme.toggle());
        document.querySelectorAll("[data-set-theme]").forEach(b =>
            b.addEventListener("click", () => this.theme.apply(b.getAttribute("data-set-theme"))));

        // Header / details
        on("btnEditGameInfo", "click", () => this.openEditGameModal());
        on("btnStudioSaveMeta", "click", () => this.saveModalGameInfo());
        on("btnStudioPullTitle", "click", () => this.pullTitleNameFromXbox());
        on("btnStudioPushTitle", "click", () => this.pushTitleNameToXbox());

        // Quick FTP modal
        on("ftpStatusPill", "click", () => this.handleQuickConnectClick());
        on("btnQuickConnectFtp", "click", () => this.handleQuickConnectClick());
        on("btnCloseModalQuickFtp", "click", () => this.closeQuickFtpModal());
        on("btnCancelModalQuickFtp", "click", () => this.closeQuickFtpModal());
        on("btnConnectModalQuickFtp", "click", () => this.handleModalQuickFtpConnect());

        // Cover search modal
        on("btnCloseModalCoverSearch", "click", () => this.closeCardCoverSearchModal());
        on("btnCancelModalCoverSearch", "click", () => this.closeCardCoverSearchModal());
        on("btnDoModalCoverSearch", "click", () => this.doModalCoverSearch());
        on("btnSelectAllScreenshots", "click", () => this.selectAllSearchScreenshots(true));
        on("btnDeselectAllScreenshots", "click", () => this.selectAllSearchScreenshots(false));
        on("btnApplySelectedScreenshots", "click", () => this.applySelectedScreenshots());

        document.querySelectorAll(".modal-cat-btn").forEach(btn => btn.addEventListener("click", () => {
            document.querySelectorAll(".modal-cat-btn").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            this.search.category = btn.getAttribute("data-cat");
            this.doModalCoverSearch();
        }));

        // Per-category online search buttons
        on("btnSearchOnlineBackground", "click", () => this.openCardCoverSearchModal(this.state.currentGame, "background"));
        on("btnSearchOnlineIcon", "click", () => this.openCardCoverSearchModal(this.state.currentGame, "icon"));
        on("btnSearchOnlineBanner", "click", () => this.openCardCoverSearchModal(this.state.currentGame, "banner"));
        on("btnSearchOnlineScreenshots", "click", () => this.openCardCoverSearchModal(this.state.currentGame, "screenshots"));

        // FTP controls
        on("btnTestFtp", "click", () => this.testFtpConnection());
        on("btnSaveFtp", "click", () => this.saveFtpConfig());
        on("btnFetchXboxDb", "click", () => this.downloadXboxContentDb());
        on("btnFtpPullDb", "click", () => this.downloadXboxContentDb());
        on("btnDownloadAllMissingAssets", "click", () => this.downloadAllMissingAssetsFromXbox());
        on("btnPullAssetsFromFtp", "click", () => this.pullCurrentGameAssetsFromFtp());
        on("btnSyncCurrentToFtp", "click", () => this.pushCurrentAssetsToFtp());
        on("btnFtpSyncAllAssets", "click", () => this.pushAllAssetsToFtp());
        on("btnPushPending", "click", () => this.pushPendingChanges());
        on("btnClearPending", "click", () => this.discardPendingChanges());
        on("btnDetectChanges", "click", () => this.detectPendingChanges());
        on("btnClearLog", "click", () => {
            const box = $("ftpConsoleLog");
            if (box) box.innerHTML = `<div class="log-line info">[System]: Log cleared.</div>`;
        });

        // Library
        on("fileDbUpload", "change", (e) => this.handleDbFileUpload(e));
        on("librarySearchInput", "input", (e) => this.renderGamesGrid(e.target.value));

        // Online search tab
        on("btnDoOnlineSearch", "click", () => this.performOnlineSearch());
        on("onlineSearchQuery", "keydown", (e) => { if (e.key === "Enter") this.performOnlineSearch(); });
        on("btnSearchUnityBoxart", "click", () => {
            this.goToTab("search");
            $("onlineSearchQuery").value = this.state.currentGame.title_id;
            this.performOnlineSearch();
        });

        // Export asset buttons
        on("btnExportBoxartAsset", "click", () => this.downloadAssetFile("boxart"));
        on("btnExportBackgroundAsset", "click", () => this.downloadAssetFile("background"));
        on("btnExportIconBannerAsset", "click", () => this.downloadAssetFile("icon_banner"));
        on("btnExportScreenshotsAsset", "click", () => this.downloadAssetFile("screenshots"));

        // Coverage
        on("btnRefreshAssetStatus", "click", () => this.fetchAssetStatus());
        on("btnMissingFilterAll", "click", () => this.setMissingFilter("all"));
        on("btnMissingFilterIncomplete", "click", () => this.setMissingFilter("incomplete"));
        on("btnAutoSearchMissingOnline", "click", () => this.autoSearchMissingAssetsOnline());
        on("btnMissingDownloadAll", "click", () => this.downloadAllMissingAssetsFromXbox());
        document.querySelectorAll(".missing-table thead th[data-sort]").forEach(th =>
            th.addEventListener("click", () => this.sortMissingTable(th.getAttribute("data-sort"))));

        // Preview lightbox triggers
        [["imgBoxartPreview", "Boxart"], ["imgBackgroundPreview", "Background"],
         ["imgIconPreview", "Icon"], ["imgBannerPreview", "Banner"]].forEach(([id, label]) => {
            const el = $(id);
            if (el) el.addEventListener("click", () => this.lightbox.open(el.src, label));
        });

        // Coverage table delegation (row select + search-art button)
        const missingBody = $("missingTableBody");
        if (missingBody) missingBody.addEventListener("click", (e) => {
            const navBtn = e.target.closest("[data-nav]");
            if (navBtn) {
                e.stopPropagation();
                const game = this.findGameByDbId(navBtn.dataset.dbid);
                const subtab = navBtn.dataset.subtab || "boxart";
                const cat = navBtn.dataset.searchcat || "boxart";
                const img = navBtn.querySelector("img");
                if (img && !navBtn.classList.contains("missing")) {
                    const label = `${game ? game.title_name : ""} — ${cat}`;
                    this.lightbox.open(img.src, label, () => this.openCardCoverSearchModal(game, cat));
                } else if (game) {
                    this.selectGame(game, subtab);
                }
                return;
            }
            const searchBtn = e.target.closest("[data-action='search-art']");
            if (searchBtn) {
                e.stopPropagation();
                const game = this.findGameByDbId(searchBtn.dataset.dbid)
                    || { db_id: searchBtn.dataset.dbid, title_id: searchBtn.dataset.titleid, title_name: searchBtn.dataset.name };
                this.openCardCoverSearchModal(game, "boxart");
                return;
            }
            const tr = e.target.closest("tr[data-dbid]");
            if (!tr) return;
            const game = this.findGameByDbId(tr.getAttribute("data-dbid"));
            if (game) this.selectGame(game);
        });
    }

    /* ── Coverage ─────────────────────────────────────────────── */
    async fetchAssetStatus() {
        if (this.state.installedGames.length === 0) {
            this.toast.show("No games loaded. Fetch from console or load a Content.db first.", "warning");
            return;
        }
        const btn = $("btnRefreshAssetStatus");
        const orig = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = `<i class="animate-spin" data-lucide="loader-2"></i> Scanning…`;
        refreshIcons();
        try {
            const { ok, data } = await this.api.assetStatus(this.state.installedGames);
            if (!ok) throw new Error(data.detail || "Scan failed");
            this.missing.data = data.results || [];
            this.state.assetStatus = {};
            (data.results || []).forEach(r => {
                if (r.title_id) this.state.assetStatus[r.title_id.toUpperCase()] = r;
            });
            $("missingTotal").innerText = data.total;
            $("missingComplete").innerText = data.complete;
            $("missingCount").innerText = data.missing_any;

            const badge = $("navMissingBadge");
            if (data.missing_any > 0) { badge.innerText = data.missing_any; badge.hidden = false; }
            else badge.hidden = true;

            this.renderMissingTable();
            this.updateCardBadges();
            this.logConsole(`Asset scan complete: ${data.complete}/${data.total} games fully covered.`, "success", false);
        } catch (e) {
            this.logConsole(`Asset scan error: ${e.message}`, "error");
        } finally {
            btn.disabled = false; btn.innerHTML = orig; refreshIcons();
        }
    }

    setMissingFilter(filter) {
        this.missing.filter = filter;
        $("btnMissingFilterAll").classList.toggle("btn-filter-active", filter === "all");
        $("btnMissingFilterIncomplete").classList.toggle("btn-filter-active", filter === "incomplete");
        this.renderMissingTable();
    }

    sortMissingTable(col) {
        if (this.missing.sortCol === col) this.missing.sortAsc = !this.missing.sortAsc;
        else { this.missing.sortCol = col; this.missing.sortAsc = true; }
        document.querySelectorAll(".missing-table thead th[data-sort]").forEach(th => {
            th.classList.remove("sort-asc", "sort-desc");
            if (th.getAttribute("data-sort") === col) th.classList.add(this.missing.sortAsc ? "sort-asc" : "sort-desc");
        });
        this.renderMissingTable();
    }

    updateCardBadges() {
        document.querySelectorAll(".game-card [data-badge]").forEach(badge => {
            badge.className = "game-badge";
            badge.innerHTML = "";
        });
    }

    renderMissingTable() {        const tbody = $("missingTableBody");
        if (!tbody) return;
        let rows = [...this.missing.data];
        if (this.missing.filter === "incomplete") {
            rows = rows.filter(r => !r.has_boxart || !r.has_background || !r.has_icon || !r.has_banner || r.screenshot_count === 0);
        }
        const col = this.missing.sortCol, asc = this.missing.sortAsc;
        rows.sort((a, b) => {
            let va, vb;
            switch (col) {
                case "id": va = a.title_id; vb = b.title_id; break;
                case "boxart": va = +a.has_boxart; vb = +b.has_boxart; break;
                case "background": va = +a.has_background; vb = +b.has_background; break;
                case "icon": va = +a.has_icon; vb = +b.has_icon; break;
                case "banner": va = +a.has_banner; vb = +b.has_banner; break;
                case "screenshots": va = a.screenshot_count; vb = b.screenshot_count; break;
                default: va = a.title_name.toLowerCase(); vb = b.title_name.toLowerCase();
            }
            if (va < vb) return asc ? -1 : 1;
            if (va > vb) return asc ? 1 : -1;
            return 0;
        });

        if (rows.length === 0) {
            tbody.innerHTML = `<tr><td colspan="9" class="empty-row">${
                this.missing.filter === "incomplete" ? "🎉 All games have complete assets!" : "No games found. Load your library first."
            }</td></tr>`;
            return;
        }
        const noImg = `data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='36' height='36'%3E%3Crect width='36' height='36' rx='4' fill='%23222838'/%3E%3Ctext x='50%25' y='55%25' fill='%23606a80' text-anchor='middle' dominant-baseline='middle' font-size='10'%3E?%3C/text%3E%3C/svg%3E`;
        const covCell = (present, url, subtab, dbid, opts = {}) => {
            const w = opts.wide ? " wide" : "";
            const cat = opts.searchcat || subtab;
            const attrs = `data-nav data-dbid="${dbid}" data-subtab="${subtab}" data-searchcat="${cat}"`;
            if (present) {
                const badge = opts.count != null ? `<span class="cov-count">${opts.count}</span>` : "";
                return `<td><button class="cov-cell${w}" ${attrs} title="View / replace ${cat}"><img src="${url}" alt="" loading="lazy" onerror="this.parentNode.classList.add('missing');this.parentNode.innerHTML='✕'">${badge}</button></td>`;
            }
            return `<td><button class="cov-cell missing${w}" ${attrs} title="Add ${cat}">✕</button></td>`;
        };
        tbody.innerHTML = rows.map(r => {
            const complete = r.has_boxart && r.has_background && r.has_icon && r.has_banner && r.screenshot_count > 0;
            const cover = this.buildMissingThumbnailUrl(r) || noImg;
            const safeName = (r.title_name || "").replace(/"/g, "&quot;");
            const tid = r.title_id, db = r.db_id;
            return `
            <tr class="${complete ? "row-complete" : "row-incomplete"}" data-dbid="${r.db_id}">
                <td class="col-cover"><img class="missing-cover-thumb" src="${cover}" alt="" onerror="this.src='${noImg}'"></td>
                <td class="col-title">${r.title_name}</td>
                <td class="col-id"><code>${r.title_id}</code></td>
                ${covCell(r.has_boxart, this.buildTitlePreviewUrl("boxart", 2, tid, db), "boxart", db, { searchcat: "boxart" })}
                ${covCell(r.has_background, this.buildTitlePreviewUrl("background", 4, tid, db), "background", db, { wide: true, searchcat: "background" })}
                ${covCell(r.has_icon, this.buildTitlePreviewUrl("icon_banner", 0, tid, db), "iconbanner", db, { searchcat: "icon" })}
                ${covCell(r.has_banner, this.buildTitlePreviewUrl("icon_banner", 1, tid, db), "iconbanner", db, { wide: true, searchcat: "banner" })}
                ${covCell(r.screenshot_count > 0, this.buildTitlePreviewUrl("screenshots", 5, tid, db), "screenshots", db, { count: r.screenshot_count, searchcat: "screenshots" })}
                <td class="col-actions">
                    <button class="btn btn-ghost btn-xs" data-action="search-art"
                        data-dbid="${r.db_id}" data-titleid="${r.title_id}" data-name="${safeName}">Search Art</button>
                </td>
            </tr>`;
        }).join("");
        refreshIcons();
    }

    /* ── Drag & drop upload ───────────────────────────────────── */
    initDragAndDrop() {
        const setup = (zoneId, inputId, category, assetIndex) => {
            const zone = $(zoneId), input = $(inputId);
            if (!zone || !input) return;
            zone.addEventListener("click", () => input.click());
            zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("drag-over"); });
            zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
            zone.addEventListener("drop", (e) => {
                e.preventDefault(); zone.classList.remove("drag-over");
                if (e.dataTransfer.files.length) this.uploadImageFile(e.dataTransfer.files[0], category, assetIndex);
            });
            input.addEventListener("change", (e) => { if (e.target.files.length) this.uploadImageFile(e.target.files[0], category, assetIndex); });
        };
        setup("dropZoneBoxart", "fileBoxartInput", "boxart", 2);
        setup("dropZoneBackground", "fileBackgroundInput", "background", 4);
        setup("dropZoneIcon", "fileIconInput", "icon_banner", 0);
        setup("dropZoneBanner", "fileBannerInput", "icon_banner", 1);

        // Screenshots add (appends to next free slot 0)
        const ssInput = $("fileScreenshotInput");
        if (ssInput) ssInput.addEventListener("change", (e) => {
            if (e.target.files.length) this.uploadImageFile(e.target.files[0], "screenshots", 0);
        });
    }

    async uploadImageFile(file, category, assetIndex) {
        const fd = new FormData();
        fd.append("category", category);
        fd.append("asset_index", assetIndex);
        fd.append("file", file);
        fd.append("compress", $("chkUseCompression").checked);
        // Pin this upload to the game that was selected when the user picked
        // the file. If the server's active game has since changed (slow
        // upload, quick game switch), it rejects instead of silently writing
        // to whatever's currently loaded -- see _assert_game_context.
        if (this.state.currentGame) {
            fd.append("title_id", this.state.currentGame.title_id);
            fd.append("db_id", this.state.currentGame.db_id);
        }
        try {
            this.logConsole(`Uploading ${file.name} (${(file.size/1024).toFixed(0)} KB) → ${this.catLabel(category, assetIndex)} for "${this.state.currentGame.title_name}"…`, "info", false, "Upload");
            const { ok, data } = await this.api.replaceImage(fd);
            if (ok) { this.logConsole(`Updated ${this.catLabel(category, assetIndex)} asset.`, "success", true, "Upload"); this.markPending(category, assetIndex); this.refreshAssetPreviews(); }
            else this.logConsole(`Error updating image: ${data.detail}`, "error", true, "Upload");
        } catch (e) { this.logConsole(`Error: ${e.message}`, "error", true, "Upload"); }
    }

    /* ── Previews ─────────────────────────────────────────────── */
    refreshAssetPreviews() {
        this.previewCacheVersion = Date.now();
        const set = (id, url) => { const el = $(id); if (el) el.src = url; };
        set("imgBoxartPreview", this.buildPreviewUrl("boxart", 2));
        set("imgBackgroundPreview", this.buildPreviewUrl("background", 4));
        set("imgIconPreview", this.buildPreviewUrl("icon_banner", 0));
        set("imgBannerPreview", this.buildPreviewUrl("icon_banner", 1));

        const g = this.state.currentGame;
        if (g && g.title_id !== "00000000") {
            const cardImg = document.querySelector(`.game-card[data-dbid="${g.db_id}"] .game-cover-box img`);
            if (cardImg) cardImg.src = this.buildTitlePreviewUrl("boxart", 2, g.title_id, g.db_id);
        }

        const grid = $("screenshotsGrid");
        if (grid) {
            grid.innerHTML = "";
            let loaded = 0;
            const countEl = $("screenshotsTabCount");
            if (countEl) countEl.innerText = "0";
            for (let i = 0; i < 20; i++) {
                const src = this.buildPreviewUrl("screenshots", i + 5);
                const card = document.createElement("div");
                card.className = "screenshot-card";
                card.innerHTML = `<img src="${src}" alt="Screenshot ${i + 1}">`;
                const img = card.querySelector("img");
                img.addEventListener("load", () => { loaded++; if (countEl) countEl.innerText = String(loaded); });
                img.addEventListener("error", () => { card.style.display = "none"; });
                img.addEventListener("click", () => this.lightbox.open(src, `Screenshot ${i + 1}`));
                grid.appendChild(card);
            }
        }
    }

    downloadAssetFile(category) { window.location.href = `${API_BASE}/asset/download/${category}`; }

    /* ── Studio metadata ──────────────────────────────────────── */
    collectStudioGameFormData() {
        const g = this.state.currentGame || {};
        return {
            title_name: $("studioTitleName").value.trim() || "Unknown Game",
            description: $("studioDescription").value.trim(),
            publisher: g.publisher || "",
            developer: g.developer || "",
            release_date: g.release_date || "",
            title_id: g.title_id || "00000000",
            media_id: g.media_id || "00000000",
            db_id: g.db_id || "00000001",
            disc_num: g.disc_num || 1,
        };
    }
    populateStudioGameForm(game) {
        $("studioTitleName").value = game.title_name || "";
        $("studioDescription").value = game.description || "";
        $("studioFolderBadge").innerText = `Folder: ${game.folder_path || "00000000_00000000"}`;
    }
    refreshDownloadedGameVisuals(game) {
        this.previewCacheVersion = Date.now();
        const cardImg = document.querySelector(`.game-card[data-dbid="${game.db_id}"] .game-cover-box img`);
        if (cardImg) cardImg.src = this.buildTitlePreviewUrl("boxart", 2, game.title_id, game.db_id);
        if (this.state.currentGame && this.getGameKey(this.state.currentGame) === this.getGameKey(game)) this.refreshAssetPreviews();
    }

    openEditGameModal() {
        this.goToTab("studio");
        this.goToSubtab("details");
        this.populateStudioGameForm(this.state.currentGame);
        $("studioTitleName").focus();
    }

    async saveModalGameInfo() {
        const previousName = this.state.currentGame?.title_name || "";
        const previousDescription = this.state.currentGame?.description || "";
        const formData = this.collectStudioGameFormData();
        try {
            const { ok, data } = await this.api.setGameInfo(formData);
            if (ok) {
                this.updateCurrentGameUI(data.game);
                // updateCurrentGameUI patches the currently-rendered card's text
                // in place, but every card's click handler closed over the game
                // object as it was at grid-render time. Without rebuilding the
                // grid, that closure still holds the pre-edit title_name, so
                // clicking the card again re-selects the OLD name and pushes it
                // back to the server, silently reverting the edit. Re-render so
                // new closures pick up the saved data.
                this.renderGamesGrid($("librarySearchInput") ? $("librarySearchInput").value : "");
                this.toast.show(`Saved game data for "${data.game.title_name}".`, "success");
                // Title/synopsis edits only live in memory/Content.db (not an
                // .asset file), so they don't naturally show up in the pending
                // queue like an image swap does. Queue them explicitly, along
                // with the pre-edit value, so they're visible on the Console
                // tab, get pushed with everything else, and can be reverted
                // to the exact original text if discarded.
                if (formData.title_name && formData.title_name !== previousName) {
                    this.markPending("title", 0, data.game, { previousValue: previousName });
                }
                if ((formData.description || "") !== previousDescription) {
                    this.markPending("synopsis", 0, data.game, { previousValue: previousDescription });
                }
            }
        } catch (e) { this.toast.show("Failed to save game info: " + e.message, "error"); }
    }

    async pullTitleNameFromXbox() {
        const btn = $("btnStudioPullTitle");
        const cfg = this.getFtpConfigFromForm();
        if (!cfg.ip) { this.logConsole("No Xbox console IP configured. Open Console settings first.", "error"); return; }
        const orig = btn.innerHTML; btn.disabled = true;
        btn.innerHTML = `<i class="animate-spin" data-lucide="loader-2"></i> Pulling…`; refreshIcons();
        try {
            const { ok, data } = await this.api.pullTitleName(cfg);
            if (!ok) throw new Error(data.detail || "Pull failed");
            const dbIdHex = (this.state.currentGame.db_id || "").toLowerCase();
            const titleIdHex = this.state.currentGame.title_id.toLowerCase();
            const match = (data.games || []).find(g =>
                ((g.db_id || "").toLowerCase() === dbIdHex) || (!dbIdHex && (g.title_id || "").toLowerCase() === titleIdHex));
            if (match) {
                const name = match.custom_title_name || match.title_name || match.db_title || "";
                $("studioTitleName").value = name;
                this.logConsole(`Pulled title from console: "${name}"`, "success");
                this.toast.show(`Pulled: "${name}" from Xbox!`, "success");
            } else {
                this.logConsole(`No matching game found for TitleID ${this.state.currentGame.title_id}.`, "warning");
                this.toast.show(`Game ${this.state.currentGame.title_id} not found in console Content.db.`, "warning");
            }
        } catch (e) {
            this.logConsole(`Failed to pull title name: ${e.message}`, "error");
            this.toast.show(`Pull failed: ${e.message}`, "error");
        } finally { btn.disabled = false; btn.innerHTML = orig; refreshIcons(); }
    }

    async pushTitleNameToXbox() {
        const btn = $("btnStudioPushTitle");
        const newName = $("studioTitleName").value.trim();
        const titleId = this.state.currentGame?.title_id || "00000000";
        if (!newName) { this.toast.show("Title name is empty — nothing to push.", "warning"); return; }
        const cfg = this.getFtpConfigFromForm();
        if (!cfg.ip) { this.logConsole("No Xbox console IP configured. Open Console settings first.", "error"); return; }
        const orig = btn.innerHTML; btn.disabled = true;
        btn.innerHTML = `<i class="animate-spin" data-lucide="loader-2"></i> Pushing…`; refreshIcons();
        try {
            const description = $("studioDescription") ? $("studioDescription").value : undefined;
            const payload = { ip: cfg.ip, username: cfg.username, password: cfg.password, port: cfg.port,
                db_id: this.state.currentGame?.db_id || "00000001", title_id: titleId, new_name: newName, description };
            const { ok, data } = await this.api.pushTitleName(payload);
            if (data.partial) {
                this.logConsole(data.message || "Title DB edited locally but upload blocked.", "warning");
                const url = `${API_BASE.replace("/api", "")}${data.download_url}`;
                this.toast.show(`⚠️ Upload blocked.<br><br>${data.message ? data.message.replace('\n', '<br>') + '<br><br>' : ''}` +
                    `<a href="${url}" download="Content.db" style="color:#fbbf24;text-decoration:underline;font-weight:700;">Download modified Content.db</a> to copy it manually.`,
                    "warning", 15000);
                return;
            }
            if (!ok) throw new Error(data.detail || "Push failed");
            this.logConsole(data.message || `Title name pushed to console: "${newName}"`, "success");
            this.toast.show(`✅ "${newName}" written to Aurora Content.db! Restart Aurora to see it.`, "success", 7000);
            // This action covers both fields (Content.db only really has one
            // "push metadata" round-trip), so clear whichever of the two are
            // still pending for this game now that they're both on the console.
            if (this.state.currentGame) this.clearPendingCategoriesForGame(this.state.currentGame.db_id, ["title", "synopsis"]);
        } catch (e) {
            this.logConsole(`Failed to push title name: ${e.message}`, "error");
            this.toast.show(`Push failed: ${e.message}`, "error");
        } finally { btn.disabled = false; btn.innerHTML = orig; refreshIcons(); }
    }

    updateCurrentGameUI(game) {
        this.state.currentGame = { description: "", publisher: "", developer: "", release_date: "", ...this.state.currentGame, ...game };
        const g = this.state.currentGame;
        if ($("headerTitleName")) $("headerTitleName").innerText = g.title_name;
        if ($("studioGameTitle")) $("studioGameTitle").innerText = g.title_name;

        const idx = this.state.installedGames.findIndex(x => this.getGameKey(x) === this.getGameKey(g));
        if (idx !== -1) this.state.installedGames[idx] = { ...this.state.installedGames[idx], ...g };

        const cardTitle = document.querySelector(`.game-card[data-dbid="${g.db_id}"] .game-title-text`);
        const cardSub = document.querySelector(`.game-card[data-dbid="${g.db_id}"] .game-sub-text`);
        if (cardTitle) { cardTitle.innerText = g.title_name; cardTitle.title = g.title_name; }
        if (cardSub) cardSub.innerText = `ID: ${g.title_id}`;

        this.populateStudioGameForm(g);
        this.refreshAssetPreviews();
    }

    /* ── Library ──────────────────────────────────────────────── */
    renderGamesGrid(searchQuery = "") {
        const grid = $("gamesGrid");
        grid.innerHTML = "";
        const q = searchQuery.toLowerCase();
        const filtered = this.state.installedGames.filter(g =>
            g.title_name.toLowerCase().includes(q) || g.title_id.toLowerCase().includes(q));
        $("libraryStatsCount").innerText = `${filtered.length} games`;

        if (filtered.length === 0) {
            grid.innerHTML = `<div class="empty-state"><i data-lucide="box"></i><h3>No games found</h3>
                <p>Clear your search, or fetch Content.db from the console.</p></div>`;
            refreshIcons();
            return;
        }
        const noCover = `data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='260'%3E%3Crect width='200' height='260' fill='%23222838'/%3E%3Ctext x='50%25' y='50%25' fill='%23606a80' text-anchor='middle' dominant-baseline='middle'%3ENo Cover%3C/text%3E%3C/svg%3E`;
        filtered.forEach(game => {
            const card = document.createElement("div");
            card.className = "game-card";
            card.setAttribute("data-dbid", game.db_id);
            card.innerHTML = `
                <div class="game-cover-box">
                    <div class="game-badge" data-badge></div>
                    <img src="${this.buildTitlePreviewUrl("boxart", 2, game.title_id, game.db_id)}" alt="${game.title_name}" onerror="this.src='${noCover}'">
                    <button class="card-fab-search" title="Search covers"><i data-lucide="search"></i></button>
                </div>
                <div class="game-info">
                    <div class="game-title-text" title="${game.title_name}">${game.title_name}</div>
                    <div class="game-sub-text">ID: ${game.title_id}</div>
                </div>`;
            card.querySelector(".card-fab-search").addEventListener("click", (e) => { e.stopPropagation(); this.openCardCoverSearchModal(game); });
            card.addEventListener("click", () => this.selectGame(game));
            grid.appendChild(card);
        });
        refreshIcons();

        clearTimeout(this.assetStatusTimer);
        this.assetStatusTimer = setTimeout(() => this.fetchAssetStatus(), 1200);
    }

    async selectGame(game, subtab = "boxart") {
        this.updateCurrentGameUI(game);
        this.goToTab("studio");
        this.goToSubtab(subtab);
        this.logConsole(`Selected game: ${game.title_name} (${game.title_id})`, "info", false);
        try {
            await this.api.setGameInfo({
                title_name: game.title_name, description: game.description || "", publisher: game.publisher || "",
                developer: game.developer || "", release_date: game.release_date || "", title_id: game.title_id,
                media_id: game.media_id || "00000000", db_id: game.db_id || "00000001", disc_num: game.disc_num || 1,
            });
            this.refreshAssetPreviews();
        } catch (e) { console.error("Error setting game info:", e); }
    }

    /* ── FTP: assets ──────────────────────────────────────────── */
    async pullCurrentGameAssetsFromFtp() {
        const btn = $("btnPullAssetsFromFtp"); const orig = btn ? btn.innerHTML : "";
        const cfg = this.getFtpConfigFromForm();
        if (!cfg.ip) { this.logConsole("FTP IP not set. Open Console settings.", "error"); this.openQuickFtpModal(); return; }
        if (btn) { btn.disabled = true; btn.innerHTML = `<i class="animate-spin" data-lucide="loader-2"></i> Pulling…`; refreshIcons(); }
        try {
            const { ok, data } = await this.api.pullGameAssets(cfg);
            if (ok) {
                let n = 0;
                for (const info of Object.values(data.results)) if (info.success) n++;
                if (n > 0) { this.logConsole(`Pulled ${n} asset file(s) from console for "${this.state.currentGame.title_name}".`, "success", true, "Pull"); this.clearPendingForGame(this.state.currentGame.db_id); }
                else this.logConsole(`No asset files found on console for ${this.state.currentGame.title_name}. Assign new artwork!`, "warning", true, "Pull");
                this.refreshAssetPreviews();
            } else this.logConsole(`Failed to pull assets: ${data.detail}`, "error", true, "Pull");
        } catch (e) { this.logConsole(`Error pulling assets: ${e.message}`, "error", true, "Pull"); }
        finally { if (btn) { btn.disabled = false; btn.innerHTML = orig; refreshIcons(); } }
    }

    /* ── Quick FTP modal ──────────────────────────────────────── */
    openQuickFtpModal() {
        $("quickFtpIp").value = $("ftpIp").value || this.state.ftpConfig.ip || "";
        $("quickFtpUser").value = $("ftpUser").value || "xboxftp";
        $("quickFtpPass").value = $("ftpPass").value || "xboxftp";
        $("quickFtpPort").value = $("ftpPort").value || 21;
        $("quickFtpFeedback").innerText = "";
        $("modalQuickFtp").classList.add("active");
    }
    closeQuickFtpModal() { $("modalQuickFtp").classList.remove("active"); }
    handleQuickConnectClick() {
        const ip = $("ftpIp").value.trim() || this.state.ftpConfig.ip;
        if (!ip) this.openQuickFtpModal(); else this.testFtpConnection();
    }
    async handleModalQuickFtpConnect() {
        const ip = $("quickFtpIp").value.trim();
        const feedback = $("quickFtpFeedback");
        if (!ip) { feedback.innerText = "Please enter an IP address."; feedback.style.color = "var(--danger)"; return; }
        $("ftpIp").value = ip;
        $("ftpUser").value = $("quickFtpUser").value.trim() || "xboxftp";
        $("ftpPass").value = $("quickFtpPass").value.trim() || "xboxftp";
        $("ftpPort").value = parseInt($("quickFtpPort").value) || 21;
        feedback.innerText = `Connecting to ${ip}…`; feedback.style.color = "var(--accent)";
        await this.saveFtpConfig();
        await this.testFtpConnection();
        if (this.state.ftpConnected) {
            feedback.innerText = "Connected successfully!"; feedback.style.color = "var(--success)";
            setTimeout(() => this.closeQuickFtpModal(), 800);
        } else { feedback.innerText = "Connection failed. Verify console IP and power state."; feedback.style.color = "var(--danger)"; }
    }

    getFtpConfigFromForm() {
        const g = this.state.currentGame;
        return {
            ip: $("ftpIp").value.trim() || $("quickFtpIp").value.trim(),
            username: $("ftpUser").value.trim() || "xboxftp",
            password: $("ftpPass").value.trim() || "xboxftp",
            port: parseInt($("ftpPort").value) || 21,
            title_id: g ? g.title_id : "00000000",
            db_id: g ? g.db_id : "00000001",
            media_id: g ? g.media_id : "00000000",
            title_name: g ? g.title_name : "",
        };
    }

    async testFtpConnection(silent = false) {
        const cfg = this.getFtpConfigFromForm();
        if (!silent) this.logConsole(`Testing FTP connection to ${cfg.ip}…`, "info", false);
        try {
            const { data } = await this.api.testFtp(cfg);
            const pill = $("ftpStatusPill");
            if (data.success) {
                this.state.ftpConnected = true;
                pill.classList.remove("disconnected"); pill.classList.add("connected");
                pill.title = `FTP connected (${cfg.ip})`;
                if (!silent) this.logConsole(`FTP success: ${data.message}`, "success");
                return true;
            }
            this.state.ftpConnected = false;
            pill.classList.remove("connected"); pill.classList.add("disconnected");
            pill.title = "FTP disconnected — click to connect";
            if (!silent) this.logConsole(`FTP failed: ${data.message}`, "error");
            return false;
        } catch (e) {
            this.state.ftpConnected = false;
            if (!silent) this.logConsole(`FTP error: ${e.message}`, "error");
            return false;
        }
    }

    async saveFtpConfig() {
        try {
            const { ok } = await this.api.saveFtpConfig(this.getFtpConfigFromForm());
            if (ok) this.logConsole("FTP settings saved.", "success", false);
        } catch (e) { this.logConsole("Failed to save FTP config: " + e.message, "error"); }
    }

    async downloadXboxContentDb(opts = {}) {
        const cfg = this.getFtpConfigFromForm();
        this.logConsole("Connecting to Xbox to download Content.db…", "info", false);
        try {
            const { data } = await this.api.downloadDb(cfg);
            if (data.success) {
                this.logConsole(data.message, "success");
                this.state.installedGames = data.games;
                this.renderGamesGrid();
                if (!this.resolvePendingEditor() && !opts.keepTab) this.goToTab("library");
            } else this.logConsole(`Failed to fetch database: ${data.detail}`, "error");
        } catch (e) { this.logConsole(`Error: ${e.message}`, "error"); }
    }

    async handleDbFileUpload(e) {
        if (e.target.files.length === 0) return;
        const file = e.target.files[0];
        const fd = new FormData(); fd.append("file", file);
        this.logConsole(`Parsing local database file ${file.name}…`, "info", false);
        try {
            const { data } = await this.api.parseDbFile(fd);
            if (data.success) {
                this.state.installedGames = data.games;
                this.renderGamesGrid();
                this.logConsole(`Loaded ${data.count} games.`, "success");
            }
        } catch (err) { this.logConsole(`Failed to parse file: ${err.message}`, "error"); }
    }

    async pushCurrentAssetsToFtp() {
        const btn = $("btnSyncCurrentToFtp"); const orig = btn ? btn.innerHTML : "";
        const cfg = this.getFtpConfigFromForm();
        if (!cfg.ip) { this.logConsole("FTP IP not set. Open Console settings.", "error"); this.openQuickFtpModal(); return; }
        if (btn) { btn.disabled = true; btn.innerHTML = `<i class="animate-spin" data-lucide="loader-2"></i> Pushing…`; refreshIcons(); }
        this.logConsole(`Pushing assets for "${this.state.currentGame.title_name}" to ${cfg.ip}…`, "info", false, "Push");
        try {
            const { ok, data } = await this.api.syncGameAssets(cfg);
            if (ok) {
                let n = 0;
                data.results.forEach(r => { this.logConsole(`${r.file}: ${r.message}`, r.success ? "success" : "error", false, "Push"); if (r.success) n++; });
                if (data.results.length === 0) this.logConsole("No modified asset files to push.", "warning", true, "Push");
                else {
                    // Only clear the asset categories this actually pushed --
                    // this button doesn't touch title/synopsis, so leave those
                    // (and any category that failed to upload) queued.
                    const pushedCats = [...new Set(
                        data.results.filter(r => r.success).map(r => this.categoryFromAssetFilename(r.file)).filter(Boolean)
                    )];
                    if (pushedCats.length) this.clearPendingCategoriesForGame(this.state.currentGame.db_id, pushedCats);
                    this.logConsole(`Pushed ${n}/${data.results.length} file(s) for "${this.state.currentGame.title_name}".`, "success", false, "Push");
                    if (n > 0) this.toast.show("Assets uploaded! On your Xbox, press Start → Restart Aurora to refresh covers.", "info", 6000);
                }
            } else this.logConsole(`Sync failed: ${data.detail}`, "error", true, "Push");
        } catch (e) { this.logConsole(`Sync error: ${e.message}`, "error", true, "Push"); }
        finally { if (btn) { btn.disabled = false; btn.innerHTML = orig; refreshIcons(); } }
    }

    async pushAllAssetsToFtp() {
        const btn = $("btnFtpSyncAllAssets"); const orig = btn ? btn.innerHTML : "";
        const cfg = this.getFtpConfigFromForm();
        if (!cfg.ip) { this.logConsole("FTP IP not set. Open Console settings.", "error"); this.openQuickFtpModal(); return; }
        if (this.state.installedGames.length === 0) { this.logConsole("No installed games. Fetch database from console first.", "warning"); return; }
        if (btn) { btn.disabled = true; btn.innerHTML = `<i class="animate-spin" data-lucide="loader-2"></i> Pushing All…`; refreshIcons(); }
        this.logConsole(`Pushing all cached assets across ${this.state.installedGames.length} games…`, "info", false, "Push");
        try {
            const { ok, data } = await this.api.pushAllAssets({ ...cfg, games: this.state.installedGames });
            if (ok) { this.clearAllPending(); this.logConsole(data.message, "success", true, "Push"); this.toast.show("All game assets pushed! Restart Aurora on your console to see new artwork.", "info", 7000); }
            else { const msg = typeof data.detail === "object" ? JSON.stringify(data.detail) : data.detail; this.logConsole(`Push All failed: ${msg}`, "error", true, "Push"); }
        } catch (e) { this.logConsole(`Push All error: ${e.message}`, "error", true, "Push"); }
        finally { if (btn) { btn.disabled = false; btn.innerHTML = orig; refreshIcons(); } }
    }

    /* ── Online search (tab) ──────────────────────────────────── */
    async performOnlineSearch() {
        const query = $("onlineSearchQuery").value.trim();
        if (!query) return;
        const grid = $("unityResultsGrid");
        grid.innerHTML = `<div class="empty-state"><p>Searching Xbox Unity for "${query}"…</p></div>`;
        try {
            const { data } = await this.api.searchUnity(query);
            grid.innerHTML = "";
            if (!data.results.length) { grid.innerHTML = `<div class="empty-state"><p>No covers found for "${query}".</p></div>`; return; }
            data.results.forEach(item => {
                const card = document.createElement("div");
                card.className = "online-cover-card";
                card.innerHTML = `
                    <img src="${item.cover_url}" alt="${item.title_name}" onerror="this.src='${item.thumbnail_url}'">
                    <div class="online-cover-info">
                        <strong>${item.title_name}</strong>
                        <div>Rating: ${item.rating || "N/A"}</div>
                        <button class="btn btn-primary btn-xs full-width mt-2">Apply Cover</button>
                    </div>`;
                card.querySelector("button").addEventListener("click", () => this.applyOnlineCover(item.cover_url));
                grid.appendChild(card);
            });
        } catch (e) { grid.innerHTML = `<div class="empty-state"><p>Error searching Xbox Unity: ${e.message}</p></div>`; }
    }

    async applyOnlineCover(url) {
        this.logConsole(`Applying online cover → Boxart for "${this.state.currentGame.title_name}"…`, "info", false, "Online");
        const fd = new FormData();
        fd.append("category", "boxart"); fd.append("asset_index", 2); fd.append("url", url);
        fd.append("compress", $("chkUseCompression").checked);
        if (this.state.currentGame) {
            fd.append("title_id", this.state.currentGame.title_id);
            fd.append("db_id", this.state.currentGame.db_id);
        }
        try {
            const { ok, data } = await this.api.replaceImageUrl(fd);
            if (ok) { this.logConsole("Cover updated.", "success", true, "Online"); this.markPending("boxart", 2); this.refreshAssetPreviews(); this.goToTab("studio"); this.goToSubtab("boxart"); }
            else this.logConsole(`Error applying cover: ${data.detail}`, "error", true, "Online");
        } catch (e) { this.logConsole(`Error applying cover: ${e.message}`, "error", true, "Online"); }
    }

    /* ── Cover search modal ───────────────────────────────────── */
    openCardCoverSearchModal(game, category = "boxart") {
        this.search.game = game || this.state.currentGame;
        this.search.category = category || "boxart";
        if (!this.search.selectedUrls) this.search.selectedUrls = new Set();
        this.search.selectedUrls.clear();
        if (game) this.selectGame(game);

        const names = { boxart: "Boxart Covers", background: "Background Artwork", icon: "Game Icons (64×64)",
            banner: "Game Banners (420×96)", icon_banner: "Icons & Banners", screenshots: "Screenshots" };
        const g = this.search.game;
        $("modalCoverSearchTitle").innerText = `Search ${names[this.search.category] || "Media"} for ${g ? g.title_name : "Game"}`;
        $("modalCoverSearchQuery").value = (g ? g.title_name : "") || (g ? g.title_id : "");
        document.querySelectorAll(".modal-cat-btn").forEach(b => b.classList.toggle("active", b.getAttribute("data-cat") === this.search.category));
        $("modalCardCoverSearch").classList.add("active");
        this.updateSearchSelectionUI();
        this.doModalCoverSearch();
    }
    closeCardCoverSearchModal() { $("modalCardCoverSearch").classList.remove("active"); }

    updateSearchSelectionUI() {
        const bar = $("modalSearchSelectionBar");
        if (!bar) return;
        const isScreenshotMode = this.search.category === "screenshots";
        bar.hidden = !isScreenshotMode;
        if (!isScreenshotMode) return;

        const count = this.search.selectedUrls ? this.search.selectedUrls.size : 0;
        const countPill = $("modalSelectedCount"); if (countPill) countPill.innerText = `${count} selected`;
        const applyCount = $("modalApplyCount"); if (applyCount) applyCount.innerText = count;
        const applyBtn = $("btnApplySelectedScreenshots"); if (applyBtn) applyBtn.disabled = count === 0;
    }

    selectAllSearchScreenshots(select = true) {
        if (this.search.category !== "screenshots") return;
        const cards = document.querySelectorAll("#modalCoverSearchResultsGrid .online-cover-card");
        cards.forEach(card => {
            const url = card.getAttribute("data-url");
            if (!url) return;
            if (select) {
                this.search.selectedUrls.add(url);
                card.classList.add("selected");
            } else {
                this.search.selectedUrls.delete(url);
                card.classList.remove("selected");
            }
        });
        this.updateSearchSelectionUI();
    }

    async applySelectedScreenshots() {
        const urls = Array.from(this.search.selectedUrls || []);
        if (!urls.length) return;
        const btn = $("btnApplySelectedScreenshots");
        const orig = btn ? btn.innerHTML : "";
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = `<i class="animate-spin" data-lucide="loader-2"></i> Downloading ${urls.length} shots…`;
            refreshIcons();
        }

        this.toast.show(`Downloading & applying ${urls.length} screenshot(s)…`, "info");
        let count = 0;
        for (let i = 0; i < urls.length; i++) {
            const url = urls[i];
            try {
                await this.applyOnlineMedia(url, "screenshots", i);
                count++;
            } catch (e) {
                this.logConsole(`Failed to apply screenshot ${i + 1}: ${e.message}`, "error");
            }
        }
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = orig;
            refreshIcons();
        }

        this.closeCardCoverSearchModal();
        this.toast.show(`Successfully downloaded & applied ${count} screenshot(s)!`, "success");
        this.renderGamesGrid($("librarySearchInput") ? $("librarySearchInput").value : "");
    }

    async doModalCoverSearch() {
        const query = $("modalCoverSearchQuery").value.trim();
        if (!query) return;
        const grid = $("modalCoverSearchResultsGrid");
        grid.setAttribute("data-cat", this.search.category);
        if (this.search.selectedUrls) this.search.selectedUrls.clear();
        this.updateSearchSelectionUI();

        const names = { boxart: "Boxart", background: "Backgrounds", icon: "Icons", banner: "Banners", screenshots: "Screenshots" };
        grid.innerHTML = `<div class="empty-state"><p><i class="animate-spin" data-lucide="loader-2"></i> Searching for ${names[this.search.category] || "Media"} ("${query}")…</p></div>`;
        refreshIcons();
        try {
            const { data } = await this.api.searchMedia(query, this.search.category);
            grid.innerHTML = "";
            if (!data.results || !data.results.length) { grid.innerHTML = `<div class="empty-state"><p>No ${names[this.search.category] || "media"} found for "${query}".</p></div>`; return; }
            const isScreenshotMode = this.search.category === "screenshots";

            data.results.forEach((item, index) => {
                const card = document.createElement("div");
                card.className = "online-cover-card" + (isScreenshotMode ? " selectable" : "");
                card.setAttribute("data-url", item.image_url);
                card.innerHTML = `
                    ${isScreenshotMode ? `<div class="select-checkbox"><i data-lucide="check"></i></div>` : ""}
                    <img src="${item.image_url}" alt="${item.title_name}" onerror="this.src='${item.thumbnail_url}'">
                    <div class="online-cover-info">
                        <strong>${item.title_name}</strong>
                        <div>${item.source || "Online"} · ${item.rating || "HD"}</div>
                        <button class="btn btn-primary btn-xs full-width mt-2 btn-apply-single">${isScreenshotMode ? "Apply Single" : "Apply"}</button>
                    </div>`;

                if (isScreenshotMode) {
                    card.addEventListener("click", (e) => {
                        if (e.target.closest(".btn-apply-single")) return;
                        const isSelected = this.search.selectedUrls.has(item.image_url);
                        if (isSelected) {
                            this.search.selectedUrls.delete(item.image_url);
                            card.classList.remove("selected");
                        } else {
                            this.search.selectedUrls.add(item.image_url);
                            card.classList.add("selected");
                        }
                        this.updateSearchSelectionUI();
                    });
                }

                card.querySelector(".btn-apply-single").addEventListener("click", async (e) => {
                    e.stopPropagation();
                    this.toast.show(`Applying ${this.search.category}…`, "info");
                    let cat = this.search.category, idx = 2;
                    if (cat === "background") idx = 4;
                    else if (cat === "icon") { cat = "icon_banner"; idx = 0; }
                    else if (cat === "banner") { cat = "icon_banner"; idx = 1; }
                    else if (cat === "screenshots") { cat = "screenshots"; idx = 0; }
                    await this.applyOnlineMedia(item.image_url, cat, idx);
                    this.closeCardCoverSearchModal();
                    this.toast.show("Artwork applied!", "success");
                    this.renderGamesGrid($("librarySearchInput").value);
                });
                grid.appendChild(card);
            });
            refreshIcons();
        } catch (e) { grid.innerHTML = `<div class="empty-state"><p>Error searching media: ${e.message}</p></div>`; }
    }

    async applyOnlineMedia(url, category = "boxart", assetIndex = 2) {
        this.logConsole(`Applying online ${this.catLabel(category, assetIndex)} for "${this.state.currentGame.title_name}"…`, "info", false, "Online");
        const fd = new FormData();
        fd.append("category", category); fd.append("asset_index", assetIndex); fd.append("url", url);
        fd.append("compress", $("chkUseCompression").checked);
        if (this.state.currentGame) {
            fd.append("title_id", this.state.currentGame.title_id);
            fd.append("db_id", this.state.currentGame.db_id);
        }
        try {
            const { ok, data } = await this.api.replaceImageUrl(fd);
            if (ok) { this.logConsole(`${this.catLabel(category, assetIndex)} updated.`, "success", false, "Online"); this.markPending(category, assetIndex); this.refreshAssetPreviews(); this.goToTab("studio"); }
            else this.logConsole(`Error applying ${category}: ${data.detail}`, "error", true, "Online");
        } catch (e) { this.logConsole(`Error applying ${category}: ${e.message}`, "error", true, "Online"); }
    }

    /* ── Batch download ───────────────────────────────────────── */
    async autoSearchMissingAssetsOnline() {
        const btn = $("btnAutoSearchMissingOnline");
        if (!this.state.installedGames || this.state.installedGames.length === 0) {
            this.logConsole("No games loaded. Fetch from console or load a Content.db first.", "warning");
            this.toast.show("No games loaded. Load a database or connect to Xbox first.", "warning");
            return;
        }

        const origText = btn ? btn.innerHTML : "";
        if (btn) {
            btn.disabled = true;
            btn.style.setProperty("--btn-progress", "0%");
        }

        this.logConsole("Starting auto-search for missing artwork across library online…", "info", true, "Online");
        this.toast.show("Checking library for missing assets…", "info");

        if (!this.state.assetStatus || Object.keys(this.state.assetStatus).length === 0) {
            if (btn) { btn.innerHTML = `<i class="animate-spin" data-lucide="loader-2"></i> Checking coverage…`; refreshIcons(); }
            await this.fetchAssetStatus();
        }

        let totalApplied = 0;
        let gamesProcessed = 0;
        const total = this.state.installedGames.length;

        for (let i = 0; i < total; i++) {
            const game = this.state.installedGames[i];
            const percent = Math.round(((i + 1) / total) * 100);
            if (btn) {
                btn.style.setProperty("--btn-progress", `${percent}%`);
                btn.innerHTML = `<i class="animate-spin" data-lucide="loader-2"></i> Searching ${percent}% (${i + 1}/${total})`;
                refreshIcons();
            }

            const titleId = (game.title_id || "").toUpperCase();
            const status = (this.state.assetStatus || {})[titleId] || {};

            const missingCats = [];
            if (status.has_boxart === false) missingCats.push({ cat: "boxart", idx: 2 });
            if (status.has_background === false) missingCats.push({ cat: "background", idx: 4 });
            if (status.has_icon === false) missingCats.push({ cat: "icon_banner", subcat: "icon", idx: 0 });
            if (status.has_banner === false) missingCats.push({ cat: "icon_banner", subcat: "banner", idx: 1 });
            
            // Ensure a minimum of 3 screenshots per game
            const currentSsCount = status.screenshot_count || 0;
            if (currentSsCount < 3) {
                for (let sIdx = currentSsCount; sIdx < 3; sIdx++) {
                    missingCats.push({ cat: "screenshots", subcat: "screenshots", idx: sIdx, ssIndex: sIdx });
                }
            }

            if (missingCats.length === 0) continue;
            gamesProcessed++;

            // Ensure server CURRENT_GAME_INFO matches current target game context
            try {
                await this.api.setGameInfo({
                    title_name: game.title_name, description: game.description || "", publisher: game.publisher || "",
                    developer: game.developer || "", release_date: game.release_date || "", title_id: game.title_id,
                    media_id: game.media_id || "00000000", db_id: game.db_id || "00000001", disc_num: game.disc_num || 1,
                });
            } catch (_) {}

            this.logConsole(`[${i + 1}/${total}] Auto-searching artwork for "${game.title_name}"…`, "info", false, "Online");

            for (const item of missingCats) {
                const searchCat = item.subcat || item.cat;
                try {
                    const { ok, data } = await this.api.searchMedia(game.title_name, searchCat);
                    if (ok && data.results && data.results.length > 0) {
                        const resIndex = (item.cat === "screenshots" && item.ssIndex !== undefined)
                            ? Math.min(item.ssIndex, data.results.length - 1)
                            : 0;
                        const targetResult = data.results[resIndex] || data.results[0];
                        if (targetResult && targetResult.image_url) {
                            const fd = new FormData();
                            fd.append("category", item.cat);
                            fd.append("asset_index", item.idx);
                            fd.append("url", targetResult.image_url);
                            fd.append("compress", $("chkUseCompression") ? $("chkUseCompression").checked : true);
                            fd.append("title_id", game.title_id);
                            if (game.db_id) fd.append("db_id", game.db_id);

                            const { ok: repOk, data: repData } = await this.api.replaceImageUrl(fd);
                            if (repOk) {
                                totalApplied++;
                                const activeGameObj = {
                                    ...game,
                                    db_id: game.db_id || "00000001"
                                };
                                this.markPending(item.cat, item.idx, activeGameObj);
                                this.logConsole(`   ✓ Found & applied ${searchCat} #${item.idx + 1} for "${game.title_name}".`, "success", false, "Online");
                            } else {
                                this.logConsole(`   ✗ Could not apply ${searchCat} for "${game.title_name}": ${repData ? (repData.detail || repData.message) : "Unknown error"}`, "warning", false, "Online");
                            }
                        }
                    } else {
                        this.logConsole(`   - No online ${searchCat} found for "${game.title_name}".`, "info", false, "Online");
                    }
                } catch (e) {
                    this.logConsole(`   ✗ Search error for ${searchCat}: ${e.message}`, "error", false, "Online");
                }
            }
        }

        if (btn) {
            btn.style.setProperty("--btn-progress", "100%");
            btn.innerHTML = `<i data-lucide="check"></i> Auto-search Complete!`;
            refreshIcons();
        }

        if (gamesProcessed === 0) {
            this.logConsole("All games in your library already have complete assets! No missing artwork found.", "success", true, "Online");
        } else {
            this.logConsole(`Auto-search complete! Applied ${totalApplied} missing artwork file(s) across ${gamesProcessed} game(s).`, totalApplied > 0 ? "success" : "warning", true, "Online");
            this.toast.show(`Auto-search complete! ${totalApplied} asset(s) updated.`, totalApplied > 0 ? "success" : "info");
        }

        await this.fetchAssetStatus();

        setTimeout(() => {
            if (btn) {
                btn.disabled = false;
                btn.style.setProperty("--btn-progress", "0%");
                btn.innerHTML = origText;
                refreshIcons();
            }
        }, 3000);
    }

    async downloadAllMissingAssetsFromXbox() {
        const btn = $("btnDownloadAllMissingAssets"); const subtext = $("btnDownloadSubtext");
        const cfg = this.getFtpConfigFromForm();
        if (!cfg.ip) { this.logConsole("FTP IP not set. Open Console settings.", "error"); this.openQuickFtpModal(); return; }
        if (this.state.installedGames.length === 0) { this.logConsole("No games loaded. Fetch from console or load a Content.db first.", "warning"); return; }

        const total = this.state.installedGames.length;
        btn.disabled = true; btn.style.setProperty("--btn-progress", "0%");
        let totalDownloaded = 0;
        for (let i = 0; i < total; i++) {
            const game = this.state.installedGames[i];
            const percent = Math.round(((i + 1) / total) * 100);
            btn.style.setProperty("--btn-progress", `${percent}%`);
            if (subtext) subtext.innerText = `${percent}% (${i + 1}/${total})`;
            try {
                const { ok, data } = await this.api.downloadGameMissing({ ...cfg, title_id: game.title_id, db_id: game.db_id || "00000001", title_name: game.title_name });
                if (ok) { const n = data.downloaded || 0; totalDownloaded += n; if (n > 0) this.refreshDownloadedGameVisuals(game); }
            } catch (_) { /* per-game noise ignored */ }
        }
        btn.style.setProperty("--btn-progress", "100%");
        if (subtext) subtext.innerText = "Complete! (100%)";
        this.logConsole(`Download complete! Cached ${totalDownloaded} asset files across ${total} games.`, "success");
        this.renderGamesGrid($("librarySearchInput").value);
        setTimeout(() => { btn.disabled = false; btn.style.setProperty("--btn-progress", "0%"); if (subtext) subtext.innerText = ""; }, 3000);
    }

    /* ── Logging ──────────────────────────────────────────────── */
    /* ── Pending local changes ────────────────────────────────── */
    static CATEGORY_LABELS = {
        boxart: "Boxart", background: "Background", icon: "Icon",
        banner: "Banner", icon_banner: "Icon/Banner", screenshots: "Screenshot",
        title: "Title", synopsis: "Synopsis",
    };
    catLabel(cat, idx) {
        const base = AuroraApp.CATEGORY_LABELS[cat] || cat;
        if (cat === "icon_banner") return idx === 1 ? "Banner" : "Icon";
        return base;
    }
    static ASSET_FILENAME_PREFIXES = { GC: "boxart", BK: "background", GL: "icon_banner", SS: "screenshots" };
    categoryFromAssetFilename(fname) {
        return AuroraApp.ASSET_FILENAME_PREFIXES[(fname || "").slice(0, 2).toUpperCase()] || null;
    }
    loadPending() {
        try {
            const raw = JSON.parse(localStorage.getItem("abam-pending") || "[]");
            return new Map(raw.map(e => [`${e.db_id}|${e.category}|${e.asset_index}`, e]));
        } catch { return new Map(); }
    }
    savePending() {
        localStorage.setItem("abam-pending", JSON.stringify([...this.pending.values()]));
    }
    markPending(category, assetIndex, game = this.state.currentGame, extra = {}) {
        if (!game || (game.db_id || "00000000") === "00000000") return;
        const key = `${game.db_id}|${category}|${assetIndex}`;
        this.pending.set(key, {
            db_id: game.db_id, title_id: game.title_id, title_name: game.title_name,
            category, asset_index: assetIndex, ts: Date.now(), ...extra,
        });
        this.savePending();
        this.updatePendingUI();
        this.logConsole(`Queued ${this.catLabel(category, assetIndex)} for "${game.title_name}" — ${this.pending.size} change(s) awaiting push.`, "info", false, "Local");
    }
    clearPendingForGame(dbId) {
        let removed = 0;
        for (const [k, v] of this.pending) if (v.db_id === dbId) { this.pending.delete(k); removed++; }
        if (removed) { this.savePending(); this.updatePendingUI(); }
        return removed;
    }
    clearPendingCategoriesForGame(dbId, categories) {
        const catSet = new Set(categories);
        let removed = 0;
        for (const [k, v] of this.pending) if (v.db_id === dbId && catSet.has(v.category)) { this.pending.delete(k); removed++; }
        if (removed) { this.savePending(); this.updatePendingUI(); }
        return removed;
    }
    clearAllPending() {
        const n = this.pending.size;
        this.pending.clear(); this.savePending(); this.updatePendingUI();
        return n;
    }
    pendingGames() {
        const map = new Map();
        for (const v of this.pending.values()) {
            if (!map.has(v.db_id)) map.set(v.db_id, { db_id: v.db_id, title_id: v.title_id, title_name: v.title_name, count: 0 });
            map.get(v.db_id).count++;
        }
        return [...map.values()];
    }
    updatePendingUI() {
        const count = this.pending.size;
        const pill = $("pendingCountPill"); if (pill) pill.innerText = count;
        const navBadge = $("navPendingBadge");
        if (navBadge) { if (count > 0) { navBadge.innerText = count; navBadge.hidden = false; } else navBadge.hidden = true; }
        const pushBtn = $("btnPushPending"); if (pushBtn) pushBtn.disabled = count === 0;
        const clearBtn = $("btnClearPending"); if (clearBtn) clearBtn.hidden = count === 0;
        const emptyHint = $("pendingEmptyHint"); const list = $("pendingList");
        if (emptyHint) emptyHint.hidden = count > 0;
        if (list) {
            list.hidden = count === 0;
            if (count > 0) {
                const groups = {};
                for (const v of this.pending.values()) (groups[v.db_id] ||= { name: v.title_name, items: [] }).items.push(v);
                list.innerHTML = Object.values(groups).map(g => `
                    <div class="pending-game">
                        <div class="pending-game-name"><i data-lucide="gamepad-2"></i> ${g.name}</div>
                        <div class="pending-chips">${g.items.map(it =>
                            `<span class="pending-chip">${this.catLabel(it.category, it.asset_index)}</span>`).join("")}</div>
                    </div>`).join("");
                refreshIcons();
            } else {
                list.innerHTML = "";
            }
        }
    }
    async detectPendingChanges() {
        const cfg = this.getFtpConfigFromForm();
        if (!cfg.ip) { this.logConsole("FTP IP not set. Open Console settings.", "error", true, "Detect"); this.openQuickFtpModal(); return; }
        const games = this.state.installedGames || [];
        if (games.length === 0) { this.logConsole("No games in your library to scan.", "warning", true, "Detect"); return; }

        const btn = $("btnDetectChanges"); const orig = btn ? btn.innerHTML : "";
        if (btn) { btn.disabled = true; btn.innerHTML = `<i class="animate-spin" data-lucide="loader-2"></i> Scanning…`; refreshIcons(); }
        this.logConsole(`Scanning ${games.length} game(s) against the console for local edits or drift…`, "info", false, "Detect");
        try {
            const { ok, data } = await this.api.detectChanges({
                ...cfg,
                games: games.map(g => ({
                    title_id: g.title_id, db_id: g.db_id, folder_path: g.folder_path, title_name: g.title_name,
                })),
            });
            if (!ok) { this.logConsole(`Detect changes failed: ${data.detail || "unknown error"}`, "error", true, "Detect"); return; }

            let queued = 0;
            for (const g of (data.games || [])) {
                const game = this.findGameByDbId(g.db_id) || { db_id: g.db_id, title_id: g.title_id, title_name: g.title_name };
                for (const c of g.changes) {
                    this.markPending(c.category, c.category === "icon_banner" ? 0 : (c.category === "boxart" ? 2 : (c.category === "background" ? 4 : 0)), game);
                    queued++;
                    if (c.category === "title") {
                        this.logConsole(`   ${g.title_name}: title differs (console: "${c.console_value}", local: "${c.local_value}")`, "info", false, "Detect");
                    } else {
                        this.logConsole(`   ${g.title_name}: ${this.catLabel(c.category, 0)} differs from console.`, "info", false, "Detect");
                    }
                }
            }
            this.logConsole(data.message || `Scan complete. ${queued} change(s) queued.`, queued > 0 ? "success" : "info", true, "Detect");
            if (queued > 0) this.toast.show(`Found ${queued} change(s) not yet on the console.`, "info");
            else this.toast.show("Everything matches the console.", "success");
        } catch (e) {
            this.logConsole(`Detect changes error: ${e.message}`, "error", true, "Detect");
        } finally {
            if (btn) { btn.disabled = false; btn.innerHTML = orig; refreshIcons(); }
        }
    }

    async pushPendingChanges() {
        const cfg = this.getFtpConfigFromForm();
        if (!cfg.ip) { this.logConsole("FTP IP not set. Open Console settings.", "error", true, "FTP"); this.openQuickFtpModal(); return; }
        const games = this.pendingGames();
        if (games.length === 0) return;
        const btn = $("btnPushPending"); const orig = btn ? btn.innerHTML : "";
        if (btn) { btn.disabled = true; btn.innerHTML = `<i class="animate-spin" data-lucide="loader-2"></i> Pushing…`; refreshIcons(); }
        const restore = this.state.currentGame;
        this.logConsole(`Pushing pending changes: ${this.pending.size} asset(s) across ${games.length} game(s)…`, "info", false, "Push");
        let pushedFiles = 0;
        try {
            for (const g of games) {
                const full = this.findGameByDbId(g.db_id) || g;
                const pendingForGame = [...this.pending.values()].filter(v => v.db_id === g.db_id);
                // "title"/"synopsis" aren't .asset files -- they live in Content.db
                // and go out through push-title-name, not sync-game-assets. Split
                // them out so we only ask sync-game-assets for the categories it
                // actually knows how to push (e.g. just "icon_banner" if that's
                // the only asset that changed), instead of re-uploading everything.
                const hasTitle = pendingForGame.some(v => v.category === "title");
                const hasSynopsis = pendingForGame.some(v => v.category === "synopsis");
                const categories = [...new Set(pendingForGame.map(v => v.category).filter(c => c !== "title" && c !== "synopsis"))];
                this.logConsole(`→ ${g.title_name}: syncing ${g.count} change(s)…`, "info", false, "Push");
                let gameOk = true;
                try {
                    await this.api.setGameInfo({
                        title_name: full.title_name || g.title_name, description: full.description || "",
                        publisher: full.publisher || "", developer: full.developer || "", release_date: full.release_date || "",
                        title_id: g.title_id, media_id: full.media_id || "00000000", db_id: g.db_id, disc_num: full.disc_num || 1,
                    });
                    if (hasTitle || hasSynopsis) {
                        const { ok: titleOk, data: titleData } = await this.api.pushTitleName({
                            ip: cfg.ip, username: cfg.username, password: cfg.password, port: cfg.port,
                            db_id: g.db_id, title_id: g.title_id, new_name: full.title_name || g.title_name,
                            description: hasSynopsis ? (full.description || "") : undefined,
                        });
                        if (titleOk && !titleData.partial) {
                            this.logConsole(`   ${titleData.message || `Metadata pushed for "${full.title_name || g.title_name}".`}`, "success", false, "Push");
                        } else {
                            gameOk = false;
                            this.logConsole(`   Title/synopsis push failed: ${titleData.message || titleData.detail || "unknown error"}`, "error", false, "Push");
                        }
                    }
                    if (categories.length > 0) {
                        const { ok, data } = await this.api.syncGameAssets({
                            ...cfg, title_id: g.title_id, db_id: g.db_id,
                            media_id: full.media_id || "00000000", title_name: full.title_name || g.title_name,
                            categories,
                        });
                        if (ok && data.results) {
                            let n = 0;
                            data.results.forEach(r => { this.logConsole(`   ${r.file}: ${r.message}`, r.success ? "success" : "error", false, "Push"); if (r.success) n++; });
                            pushedFiles += n;
                        } else {
                            gameOk = false;
                            this.logConsole(`   ${g.title_name} push failed: ${data.detail || "unknown error"}`, "error", false, "Push");
                        }
                    }
                    if (gameOk) this.clearPendingForGame(g.db_id);
                } catch (e) { this.logConsole(`   ${g.title_name} error: ${e.message}`, "error", false, "Push"); }
            }
            this.logConsole(`Pending push complete: ${pushedFiles} file(s) uploaded, ${this.pending.size} change(s) remaining.`, pushedFiles > 0 ? "success" : "warning", false, "Push");
            if (pushedFiles > 0) this.toast.show("Pending changes pushed! Restart Aurora on your console to see them.", "success", 6000);
        } finally {
            if (restore && (restore.db_id || "00000000") !== "00000000") {
                await this.api.setGameInfo({
                    title_name: restore.title_name, description: restore.description || "", publisher: restore.publisher || "",
                    developer: restore.developer || "", release_date: restore.release_date || "", title_id: restore.title_id,
                    media_id: restore.media_id || "00000000", db_id: restore.db_id, disc_num: restore.disc_num || 1,
                }).catch(() => {});
            }
            if (btn) { btn.disabled = this.pending.size === 0; btn.innerHTML = orig; refreshIcons(); }
        }
    }

    async discardPendingChanges() {
        const entries = [...this.pending.values()];
        if (!entries.length) return;
        const btn = $("btnClearPending"); const orig = btn ? btn.innerHTML : "";
        if (btn) { btn.disabled = true; btn.innerHTML = `<i class="animate-spin" data-lucide="loader-2"></i> Discarding…`; refreshIcons(); }
        const restore = this.state.currentGame;
        this.logConsole(`Discarding ${entries.length} local change(s) — reverting assets…`, "warning", false, "Local");

        // Group by game so we only switch the active game once per title.
        const byGame = new Map();
        for (const e of entries) {
            if (!byGame.has(e.db_id)) byGame.set(e.db_id, []);
            byGame.get(e.db_id).push(e);
        }
        let reverted = 0;
        let textReverted = 0;
        try {
            for (const [dbId, items] of byGame) {
                const g = this.findGameByDbId(dbId) || items[0];
                // Title/synopsis aren't asset files, so there's nothing for
                // /api/asset/revert to undo -- restore the field locally from
                // the pre-edit value the pending entry carried, *before* the
                // setGameInfo call below, so it's the reverted text (not the
                // still-edited text sitting in installedGames) that gets sent
                // back to the server as this game's current state.
                const titleItem = items.find(it => it.category === "title");
                const synopsisItem = items.find(it => it.category === "synopsis");
                if (titleItem && typeof titleItem.previousValue === "string") {
                    g.title_name = titleItem.previousValue; textReverted++;
                }
                if (synopsisItem && typeof synopsisItem.previousValue === "string") {
                    g.description = synopsisItem.previousValue; textReverted++;
                }
                // Keep the currently-selected game's live object in step: it's a
                // different object reference from the installedGames entry, so
                // mutating `g` above doesn't touch it on its own.
                if (restore && this.getGameKey(restore) === this.getGameKey(g)) {
                    restore.title_name = g.title_name;
                    restore.description = g.description;
                }
                try {
                    await this.api.setGameInfo({
                        title_name: g.title_name, description: g.description || "", publisher: g.publisher || "",
                        developer: g.developer || "", release_date: g.release_date || "", title_id: g.title_id,
                        media_id: g.media_id || "00000000", db_id: dbId, disc_num: g.disc_num || 1,
                    });
                    if (titleItem) this.logConsole(`   Reverted title for "${g.title_name}".`, "success", false, "Local");
                    if (synopsisItem) this.logConsole(`   Reverted synopsis for "${g.title_name}".`, "success", false, "Local");
                    for (const it of items) {
                        if (it.category === "title" || it.category === "synopsis") continue;
                        try {
                            const { ok } = await this.api.revertAsset({ category: it.category, asset_index: it.asset_index });
                            if (ok) { reverted++; this.logConsole(`   Reverted ${this.catLabel(it.category, it.asset_index)} for "${g.title_name}".`, "success", false, "Local"); }
                            else this.logConsole(`   Revert failed for ${this.catLabel(it.category, it.asset_index)} ("${g.title_name}").`, "error", false, "Local");
                        } catch (err) { this.logConsole(`   Revert error (${this.catLabel(it.category, it.asset_index)}): ${err.message}`, "error", false, "Local"); }
                    }
                    this.clearPendingForGame(dbId);
                } catch (e) { this.logConsole(`   Could not select "${g.title_name}" to revert: ${e.message}`, "error", false, "Local"); }
            }
        } finally {
            if (restore && (restore.db_id || "00000000") !== "00000000") {
                await this.api.setGameInfo({
                    title_name: restore.title_name, description: restore.description || "", publisher: restore.publisher || "",
                    developer: restore.developer || "", release_date: restore.release_date || "", title_id: restore.title_id,
                    media_id: restore.media_id || "00000000", db_id: restore.db_id, disc_num: restore.disc_num || 1,
                }).catch(() => {});
                // Re-sync header/studio-form text in case the current game's
                // title or synopsis was one of the reverted fields above.
                this.updateCurrentGameUI(restore);
            }
            this.clearAllPending();
            this.refreshAssetPreviews();
            this.renderGamesGrid($("librarySearchInput") ? $("librarySearchInput").value : "");
            if ($("tab-missing") && $("tab-missing").classList.contains("active")) this.fetchAssetStatus();
            if (btn) { btn.disabled = this.pending.size === 0; btn.innerHTML = orig; refreshIcons(); }
        }
        this.logConsole(`Discard complete — ${reverted} asset(s) and ${textReverted} text field(s) reverted to their previous state.`, (reverted || textReverted) ? "success" : "warning", true, "Local");
    }

    logConsole(msg, type = "info", showToast = true, source = null) {
        const box = $("ftpConsoleLog");
        if (box) {
            const line = document.createElement("div");
            line.className = `log-line ${type}`;
            const tag = source ? `[${source}] ` : "";
            line.innerText = `[${new Date().toLocaleTimeString()}] ${tag}${msg}`;
            box.appendChild(line);
            box.scrollTop = box.scrollHeight;
            while (box.childElementCount > 500) box.removeChild(box.firstChild);
        }
        if (showToast) this.toast.show(msg, type);
    }
}

/* ── Bootstrap ────────────────────────────────────────────────── */
window.addEventListener("DOMContentLoaded", () => {
    window.auroraApp = new AuroraApp();
    window.auroraApp.init();
    refreshIcons();
});
