// MCM-ICM Agent GUI — zero-build Alpine app (spec §4.1)
// Talks to the local FastAPI server: config / workspace / workflow-control / artifacts APIs.

const PROVIDER_FOR_SECTION = {
  llm: "llm",
  search: "tavily",
  official_data: "fred",
  mineru: "mineru",
  humanizer: "humanizer",
  embedding: "embedding",
};

const STAGE_LABELS = {
  intake: "读题",
  mineru_extraction: "抽取",
  extraction_quality_gate: "抽取闸",
  problem_understanding: "题目理解",
  data_feasibility_scout: "数据可行性",
  research_reframing: "重构方向",
  user_discussion: "方向确认",
  methodology_rag: "方法RAG",
  modeling_council: "建模",
  model_judge: "选模型",
  modeling_quality_gate: "建模闸",
  search_data: "搜数据",
  source_verifier: "源核验",
  data_eda: "EDA",
  solver_coder: "求解",
  validation_gate: "验证",
  figure_planning: "图规划",
  visualization: "画图",
  figure_quality_gate: "图闸",
  claim_planning: "论点",
  paper_writer: "写作",
  paper_evidence_binding: "证据绑定",
  typesetting: "排版",
  pre_submission_review: "审稿",
  final_gatekeeper: "终审",
  submission_packager: "打包",
};
const CANONICAL_ORDER = [
  "intake", "problem_understanding", "data_feasibility_scout", "user_discussion",
  "methodology_rag", "modeling_council", "model_judge", "search_data", "data_eda",
  "solver_coder", "validation_gate", "visualization", "claim_planning", "paper_writer",
  "typesetting", "pre_submission_review", "submission_packager",
];

document.addEventListener("alpine:init", () => {
  Alpine.data("app", () => ({
    route: "settings",
    toast: { show: false, title: "", body: "", error: false },

    config: null,
    providerResults: {},

    newWorkspaceId: "",
    workspaces: [],
    currentWorkspaceId: "",
    extraRequirements: "",
    uploadedSummary: "",
    autoApprove: true,
    demoMode: true,

    run: { state: "idle", duration_s: 0, pending_checkpoint_id: null, resume_from: null, error: null },
    approveMessage: "",
    stages: [],
    feed: [],
    logs: [],
    _es: null,
    _poll: null,

    artifacts: [],
    artifactPath: "",
    artifactContent: null,

    kb: { files: [], extensions: [], ingestible_count: 0, knowledge_base_dir: "" },
    kbSubdir: "",
    kbPreview: null,

    planning: { understanding: "", feasibility: "", direction: "" },

    // ---- lifecycle ----
    init() {
      this.applyRoute();
      window.addEventListener("hashchange", () => this.applyRoute());
      this.loadConfig();
      this.refreshWorkspaces();
      this._poll = setInterval(() => {
        if (this.currentWorkspaceId && (this.run.state === "running" || this.run.state === "paused")) {
          this.refreshRun();
        }
      }, 2000);
    },
    applyRoute() {
      const r = (location.hash || "#/settings").replace(/^#\/?/, "") || "settings";
      this.route = r;
      if (r === "artifacts" && this.currentWorkspaceId) this.loadArtifacts();
      if (r === "knowledge") this.loadKnowledge();
      if (r === "planning" && this.currentWorkspaceId) this.loadPlanning();
    },
    go(r) { location.hash = "#/" + r; },

    // ---- http helper ----
    async api(path, opts = {}) {
      const res = await fetch(path, opts);
      const text = await res.text();
      let data = null;
      try { data = text ? JSON.parse(text) : null; } catch (e) { data = text; }
      if (!res.ok) {
        const detail = (data && data.detail) ? data.detail : res.statusText;
        throw new Error(detail);
      }
      return data;
    },
    showToast(title, body = "", error = false) {
      this.toast = { show: true, title, body, error };
      setTimeout(() => { this.toast.show = false; }, 3500);
    },

    // ---- settings ----
    isSecretKey(key) { return key === "api_key" || key.endsWith("_api_key"); },
    async loadConfig() {
      try { this.config = await this.api("/api/config"); }
      catch (e) { this.showToast("加载配置失败", e.message, true); }
    },
    cleanConfigForSave() {
      const out = {};
      for (const [section, fields] of Object.entries(this.config || {})) {
        if (fields && typeof fields === "object" && !Array.isArray(fields)) {
          out[section] = {};
          for (const [k, v] of Object.entries(fields)) {
            if (k.endsWith("_configured") || k.endsWith("_preview")) continue; // drop mask pseudo-fields
            if (this.isSecretKey(k) && (v === "" || v == null)) continue; // drop empty secrets -> preserved by merge
            out[section][k] = v;
          }
        } else {
          out[section] = fields;
        }
      }
      return out;
    },
    async saveConfig() {
      try {
        const payload = this.cleanConfigForSave();
        this.config = await this.api("/api/config", {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify(payload),
        });
        this.showToast("配置已保存");
      } catch (e) { this.showToast("保存失败", e.message, true); }
    },
    async testProvider(section) {
      const provider = PROVIDER_FOR_SECTION[section];
      if (!provider) { this.showToast("该分区无需测试"); return; }
      this.providerResults[section] = { status: "…", detail: "" };
      try {
        const r = await this.api("/api/config/test-provider", {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ provider }),
        });
        this.providerResults[section] = { status: r.status, detail: r.detail || "" };
      } catch (e) { this.providerResults[section] = { status: "failed", detail: e.message }; }
    },

    // ---- workspaces ----
    async refreshWorkspaces() {
      try { const r = await this.api("/api/workspaces"); this.workspaces = r.workspaces || []; }
      catch (e) { /* server may be empty */ }
    },
    async createWorkspace() {
      const id = (this.newWorkspaceId || "").trim();
      if (!id) { this.showToast("请填写 workspace id", "", true); return; }
      try {
        await this.api("/api/workspaces", {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ workspace_id: id }),
        });
        this.newWorkspaceId = "";
        await this.refreshWorkspaces();
        this.currentWorkspaceId = id;
        this.showToast("workspace 已创建", id);
      } catch (e) { this.showToast("创建失败", e.message, true); }
    },
    onSelectWorkspace() {
      this.resetRunView();
      if (this.currentWorkspaceId) this.refreshRun();
    },
    async upload(kind, event) {
      const files = event.target.files;
      if (!files || !files.length) return;
      const fd = new FormData();
      fd.append("kind", kind);
      for (const f of files) fd.append("files", f);
      try {
        const r = await this.api(`/api/workspaces/${this.currentWorkspaceId}/files`, { method: "POST", body: fd });
        this.uploadedSummary = `已上传 ${(r.saved || []).length} 个文件:${(r.saved || []).join(", ")}`;
        this.showToast("上传成功", this.uploadedSummary);
      } catch (e) { this.showToast("上传失败", e.message, true); }
    },

    // ---- run control ----
    resetRunView() {
      this.stages = []; this.feed = []; this.logs = [];
      this.run = { state: "idle", duration_s: 0, pending_checkpoint_id: null, resume_from: null, error: null };
      if (this._es) { this._es.close(); this._es = null; }
    },
    async startRun() {
      if (!this.currentWorkspaceId) { this.showToast("请先选择 workspace", "", true); return; }
      this.resetRunView();
      try {
        await this.api(`/api/workspaces/${this.currentWorkspaceId}/run`, {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ demo: this.demoMode, auto_approve: this.autoApprove }),
        });
        this.connectEvents();
        this.go("monitor");
        this.showToast("已启动运行");
      } catch (e) { this.showToast("启动失败", e.message, true); }
    },
    async stopRun() {
      try { await this.api(`/api/workspaces/${this.currentWorkspaceId}/stop`, { method: "POST" }); this.showToast("停止请求已发送", "将在当前阶段结束后生效"); }
      catch (e) { this.showToast("停止失败", e.message, true); }
    },
    async refreshRun() {
      if (!this.currentWorkspaceId) return;
      try { this.run = await this.api(`/api/workspaces/${this.currentWorkspaceId}/run`); }
      catch (e) { /* ignore transient */ }
    },
    async approve() {
      try {
        await this.api(`/api/workspaces/${this.currentWorkspaceId}/checkpoints/${this.run.pending_checkpoint_id}/approve`, {
          method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ user_message: this.approveMessage, auto_approve: this.autoApprove, demo: this.demoMode }),
        });
        this.approveMessage = "";
        this.connectEvents();
        this.showToast("已批准,继续运行");
      } catch (e) { this.showToast("批准失败", e.message, true); }
    },
    connectEvents() {
      if (this._es) { this._es.close(); this._es = null; }
      const es = new EventSource(`/api/workspaces/${this.currentWorkspaceId}/events`);
      this._es = es;
      es.addEventListener("stage_completed", (e) => {
        const rec = JSON.parse(e.data);
        this.stages.push(rec);
        const label = STAGE_LABELS[rec.stage_id] || rec.stage_id;
        const outs = (rec.outputs || []).join(", ");
        this.feed.push({ title: `✓ ${label}`, detail: outs ? `产出:${outs}` : (rec.next_stage ? `→ ${STAGE_LABELS[rec.next_stage] || rec.next_stage}` : "") });
      });
      es.addEventListener("status", (e) => { const d = JSON.parse(e.data); this.run.state = d.state; });
      es.addEventListener("log", (e) => { const d = JSON.parse(e.data); this.logs.push({ level: d.level, line: `${(d.ts || "").slice(11, 19)} ${d.message}` }); });
      es.addEventListener("checkpoint_pending", (e) => { const d = JSON.parse(e.data); this.run.state = "paused"; this.run.pending_checkpoint_id = d.checkpoint_id; this.run.resume_from = d.resume_from; es.close(); this._es = null; this.refreshRun(); });
      es.addEventListener("run_finished", (e) => { const d = JSON.parse(e.data); this.run.state = d.state; es.close(); this._es = null; this.refreshRun(); });
      es.onerror = () => { es.close(); this._es = null; };
    },

    // ---- run view helpers ----
    completedIds() { return new Set(this.stages.map((s) => s.stage_id)); },
    currentStageId() {
      if (this.run.state !== "running" || this.stages.length === 0) return null;
      return this.stages[this.stages.length - 1].next_stage;
    },
    stageList() {
      const done = this.completedIds();
      const cur = this.currentStageId();
      return CANONICAL_ORDER.map((id) => {
        let cls = "";
        if (done.has(id)) cls = "done";
        if (id === cur) cls = "active";
        return { id, label: STAGE_LABELS[id] || id, cls };
      });
    },
    runStateLabel() {
      return { running: "运行中", paused: "已暂停", done: "已完成", failed: "失败", stopped: "已停止", idle: "空闲" }[this.run.state] || this.run.state;
    },
    runPillClass() {
      return { running: "run", paused: "warn", done: "ok", failed: "err", stopped: "err", idle: "idle" }[this.run.state] || "idle";
    },
    runDotColor() {
      return { running: "#7C5CFF", paused: "#F59E0B", done: "#0EA5A4", failed: "#EF4444", stopped: "#EF4444", idle: "#8A8A95" }[this.run.state] || "#8A8A95";
    },
    formatDuration(s) {
      s = Math.floor(s || 0);
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
      if (h) return `${h}h ${m}m ${sec}s`;
      if (m) return `${m}m ${sec}s`;
      return `${sec}s`;
    },

    // ---- artifacts ----
    async loadArtifacts() {
      if (!this.currentWorkspaceId) return;
      try { const r = await this.api(`/api/workspaces/${this.currentWorkspaceId}/artifacts`); this.artifacts = r.artifacts || []; }
      catch (e) { this.showToast("加载产物失败", e.message, true); }
    },
    async viewArtifact(path) {
      this.artifactPath = path;
      this.artifactContent = null;
      try {
        const r = await this.api(`/api/workspaces/${this.currentWorkspaceId}/artifacts/content?path=${encodeURIComponent(path)}`);
        this.artifactContent = r.content;
      } catch (e) { this.artifactContent = `（无法以文本预览:${e.message}）`; }
    },
    downloadUrl(path) {
      return `/api/workspaces/${this.currentWorkspaceId}/artifacts/download?path=${encodeURIComponent(path)}`;
    },

    // ---- knowledge base ----
    async loadKnowledge() {
      try { this.kb = await this.api("/api/knowledge/files"); }
      catch (e) { this.showToast("加载知识库失败", e.message, true); }
    },
    async uploadKnowledge(event) {
      const files = event.target.files;
      if (!files || !files.length) return;
      const fd = new FormData();
      fd.append("subdir", this.kbSubdir || "");
      for (const f of files) fd.append("files", f);
      try {
        const r = await this.api("/api/knowledge/files", { method: "POST", body: fd });
        this.showToast("已上传", (r.saved || []).join(", "));
        this.kbSubdir = "";
        await this.loadKnowledge();
      } catch (e) { this.showToast("上传失败", e.message, true); }
    },
    async deleteKnowledge(path) {
      try {
        await this.api(`/api/knowledge/files?path=${encodeURIComponent(path)}`, { method: "DELETE" });
        await this.loadKnowledge();
      } catch (e) { this.showToast("删除失败", e.message, true); }
    },
    async previewIndex() {
      try { this.kbPreview = await this.api("/api/knowledge/index-preview"); this.showToast("索引预览完成", `${this.kbPreview.total_chunks} chunks`); }
      catch (e) { this.showToast("索引预览失败", e.message, true); }
    },
    formatBytes(n) {
      n = n || 0;
      if (n < 1024) return `${n} B`;
      if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
      return `${(n / 1048576).toFixed(1)} MB`;
    },

    // ---- planning / discussion ----
    async readDoc(path) {
      try {
        const r = await this.api(`/api/workspaces/${this.currentWorkspaceId}/artifacts/content?path=${encodeURIComponent(path)}`);
        return r.content;
      } catch (e) { return "(尚未生成)"; }
    },
    async loadPlanning() {
      if (!this.currentWorkspaceId) return;
      this.planning = {
        understanding: await this.readDoc("reports/problem_understanding.md"),
        feasibility: await this.readDoc("reports/data_feasibility_report.md"),
        direction: await this.readDoc("discussion/confirmed_direction.md"),
      };
    },
  }));
});
