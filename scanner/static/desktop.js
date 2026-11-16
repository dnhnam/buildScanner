(() => {
  const $ = (id) => document.getElementById(id);
  const MODE_LABELS = {
    color: "Màu, nền trắng",
    gray: "Xám",
    bw: "Đen trắng",
    original: "Giữ nguyên màu",
  };

  const state = { version: -1, pages: [], cards: new Map() };

  // ------------------------------------------------------------------ API
  async function api(method, url, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(url, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Lỗi " + res.status);
    return data;
  }

  let statusTimer;
  function setStatus(msg, sticky = false) {
    $("status").textContent = msg;
    clearTimeout(statusTimer);
    if (!sticky && msg) statusTimer = setTimeout(() => ($("status").textContent = ""), 4000);
  }

  // ------------------------------------------------------------------ QR
  async function loadInfo() {
    try {
      const info = await api("GET", "/api/info");
      $("qr").innerHTML = info.qr_svg || '<span class="muted small">Không tìm thấy mạng Wi-Fi/LAN. Hãy kết nối laptop vào Wi-Fi rồi tải lại trang.</span>';
      $("urls").innerHTML = "";
      for (const u of info.urls) {
        const li = document.createElement("li");
        li.textContent = u;
        $("urls").appendChild(li);
      }
    } catch (e) {
      $("qr").textContent = "Lỗi: " + e.message;
    }
  }

  // ------------------------------------------------------------------ Lưới trang
  async function refresh(force = false) {
    try {
      const data = await api("GET", "/api/pages");
      if (force || data.version !== state.version) {
        state.version = data.version;
        state.pages = data.pages;
        render();
      }
    } catch (_) { /* server đang bận, lần sau thử lại */ }
  }

  function render() {
    const grid = $("grid");
    $("empty").hidden = state.pages.length > 0;
    $("exportBtn").disabled = state.pages.length === 0;
    $("exportBtn").textContent = state.pages.length ? `Xuất PDF (${state.pages.length} trang)` : "Xuất PDF";

    const alive = new Set();
    state.pages.forEach((p, i) => {
      alive.add(p.id);
      let card = state.cards.get(p.id);
      if (!card) {
        card = makeCard(p.id);
        state.cards.set(p.id, card);
      }
      updateCard(card, p, i);
      if (grid.children[i] !== card) grid.insertBefore(card, grid.children[i] || null);
    });
    for (const [id, card] of state.cards) {
      if (!alive.has(id)) {
        card.remove();
        state.cards.delete(id);
      }
    }
  }

  function makeCard(id) {
    const card = document.createElement("div");
    card.className = "page";
    card.draggable = true;
    card.dataset.id = id;
    card.innerHTML = `
      <div class="thumb"><img alt=""><span class="num"></span><div class="busy">Đang xử lý…</div></div>
      <div class="warn" hidden>Không tìm thấy khung giấy — hãy bấm "Chỉnh khung"</div>
      <div class="controls">
        <select class="mode">${Object.entries(MODE_LABELS).map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select>
        <button class="rotl" title="Xoay trái">⟲</button>
        <button class="rotr" title="Xoay phải">⟳</button>
        <button class="edit" title="Chỉnh khung và mép giấy">Chỉnh khung</button>
        <button class="del danger" title="Xoá trang">✕</button>
      </div>`;
    const page = () => state.pages.find((p) => p.id === id);
    card.querySelector(".mode").addEventListener("change", (e) => patch(id, { mode: e.target.value }));
    card.querySelector(".rotl").addEventListener("click", () => patch(id, { rotate_by: 270 }));
    card.querySelector(".rotr").addEventListener("click", () => patch(id, { rotate_by: 90 }));
    card.querySelector(".edit").addEventListener("click", () => openEditor(page()));
    card.querySelector(".del").addEventListener("click", async () => {
      if (!confirm("Xoá trang này?")) return;
      await api("DELETE", `/api/pages/${id}`);
      refresh(true);
    });
    card.querySelector(".thumb").addEventListener("click", () => {
      const p = page();
      $("viewerImg").src = `/files/processed/${id}.jpg?v=${p.rev}`;
      $("viewer").hidden = false;
    });
    setupDrag(card);
    return card;
  }

  function updateCard(card, p, index) {
    const img = card.querySelector("img");
    const src = `/files/thumbs/${p.id}.jpg?v=${p.rev}`;
    if (img.getAttribute("src") !== src) img.src = src;
    card.querySelector(".num").textContent = index + 1;
    card.querySelector(".warn").hidden = p.auto_found;
    const sel = card.querySelector(".mode");
    if (document.activeElement !== sel) sel.value = p.mode;
  }

  async function patch(id, body) {
    const card = state.cards.get(id);
    card && card.classList.add("working");
    try {
      await api("PATCH", `/api/pages/${id}`, body);
      await refresh(true);
    } catch (e) {
      setStatus("Lỗi: " + e.message);
    } finally {
      card && card.classList.remove("working");
    }
  }

  // ------------------------------------------------------------------ Kéo thả đổi thứ tự
  let dragId = null;
  function setupDrag(card) {
    card.addEventListener("dragstart", (e) => {
      dragId = card.dataset.id;
      card.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", dragId);
    });
    card.addEventListener("dragend", () => {
      dragId = null;
      card.classList.remove("dragging");
      document.querySelectorAll(".drop-before").forEach((el) => el.classList.remove("drop-before"));
    });
    card.addEventListener("dragover", (e) => {
      if (!dragId || dragId === card.dataset.id) return;
      e.preventDefault();
      card.classList.add("drop-before");
    });
    card.addEventListener("dragleave", () => card.classList.remove("drop-before"));
    card.addEventListener("drop", async (e) => {
      if (!dragId) return;
      e.preventDefault();
      card.classList.remove("drop-before");
      const ids = state.pages.map((p) => p.id).filter((i) => i !== dragId);
      let at = ids.indexOf(card.dataset.id);
      // Thả vào nửa phải của thẻ thì đặt sau thẻ đó
      const r = card.getBoundingClientRect();
      if (e.clientX > r.left + r.width / 2) at += 1;
      ids.splice(at, 0, dragId);
      state.pages.sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id));
      render();
      await api("POST", "/api/pages/order", { ids });
      refresh(true);
    });
  }

  // ------------------------------------------------------------------ Tải ảnh từ laptop
  async function uploadFiles(files) {
    files = Array.from(files).filter((f) => /^image\//.test(f.type) || /\.(heic|heif)$/i.test(f.name));
    if (!files.length) return;
    let done = 0;
    const failed = [];
    for (const f of files) {
      setStatus(`Đang xử lý ảnh ${done + 1}/${files.length}: ${f.name}`, true);
      const fd = new FormData();
      fd.append("files", f, f.name);
      fd.append("mode", $("modeAll").value);
      try {
        const res = await fetch("/api/upload", { method: "POST", body: fd });
        if (!res.ok) failed.push(f.name);
      } catch (_) {
        failed.push(f.name);
      }
      done++;
      refresh();
    }
    setStatus(failed.length ? `Xong. Không đọc được: ${failed.join(", ")}` : `Đã thêm ${done} ảnh.`);
  }

  const dz = $("dropZone");
  $("fileInput").addEventListener("change", (e) => {
    uploadFiles(e.target.files);
    e.target.value = "";
  });
  dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("over"); });
  dz.addEventListener("dragleave", () => dz.classList.remove("over"));
  dz.addEventListener("drop", (e) => {
    e.preventDefault();
    dz.classList.remove("over");
    uploadFiles(e.dataTransfer.files);
  });
  // Thả ảnh vào bất kỳ đâu trong trang cũng được (trừ khi đang kéo đổi thứ tự trang)
  document.addEventListener("dragover", (e) => { if (!dragId) e.preventDefault(); });
  document.addEventListener("drop", (e) => {
    if (dragId || e.target.closest("#dropZone")) return;
    e.preventDefault();
    if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
  });

  // ------------------------------------------------------------------ Nút chung
  $("modeAllBtn").addEventListener("click", async () => {
    if (!state.pages.length) return;
    setStatus("Đang áp dụng chế độ màu cho tất cả trang…", true);
    try {
      await api("POST", "/api/pages/mode", { mode: $("modeAll").value });
      setStatus("Đã áp dụng.");
    } catch (e) {
      setStatus("Lỗi: " + e.message);
    }
    refresh(true);
  });

  $("clearBtn").addEventListener("click", async () => {
    if (!state.pages.length || !confirm(`Xoá tất cả ${state.pages.length} trang?`)) return;
    await api("DELETE", "/api/pages");
    refresh(true);
  });

  function filenameFrom(disposition) {
    const star = /filename\*=UTF-8''([^;]+)/i.exec(disposition || "");
    if (star) return decodeURIComponent(star[1]);
    const plain = /filename="?([^";]+)"?/i.exec(disposition || "");
    return plain ? plain[1] : "scan.pdf";
  }

  $("exportBtn").addEventListener("click", async () => {
    const btn = $("exportBtn");
    const q = new URLSearchParams({ size: $("pageSize").value, name: $("pdfName").value });
    btn.disabled = true;
    setStatus(`Đang tạo PDF (${state.pages.length} trang)…`, true);
    try {
      const res = await fetch("/api/export?" + q);
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || "Lỗi " + res.status);
      const name = filenameFrom(res.headers.get("Content-Disposition"));
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
      setStatus(`Đã tạo "${name}" — xem trong thư mục Downloads.`);
    } catch (e) {
      setStatus("Không tạo được PDF: " + e.message);
    } finally {
      btn.disabled = state.pages.length === 0;
    }
  });

  $("viewer").addEventListener("click", () => ($("viewer").hidden = true));
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    $("viewer").hidden = true;
    if (!$("editor").hidden) closeEditor();
  });

  // ------------------------------------------------------------------ Chỉnh khung (4 góc + mép cong)
  // ed.pts là vòng điểm theo chiều kim đồng hồ từ góc trên-trái: mỗi cạnh n điểm (kể cả 2 góc).
  const ed = { page: null, img: null, pts: null, n: 9, drag: -1, scale: 1, dpr: 1, w: 0, h: 0 };
  const canvas = $("editorCanvas");
  const ctx = canvas.getContext("2d");
  const R_CORNER = 11, R_EDGE = 6;

  const cornerIdx = () => [0, ed.n - 1, 2 * (ed.n - 1), 3 * (ed.n - 1)];
  const isCorner = (i) => i % (ed.n - 1) === 0;

  function straightRing(corners, n) {
    const ring = [];
    for (let k = 0; k < 4; k++) {
      const a = corners[k], b = corners[(k + 1) % 4];
      for (let j = 0; j < n - 1; j++) {
        const t = j / (n - 1);
        ring.push([a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])]);
      }
    }
    return ring;
  }

  function edgePoints(k) {  // n điểm của cạnh k
    const m = ed.n - 1, out = [];
    for (let j = 0; j <= m; j++) out.push(ed.pts[(k * m + j) % ed.pts.length]);
    return out;
  }

  function catmull(points, per = 12) {  // đường cong mượt đi qua các điểm
    const p = points, out = [];
    const get = (i) => i < 0 ? [2 * p[0][0] - p[1][0], 2 * p[0][1] - p[1][1]]
      : i >= p.length ? [2 * p[p.length - 1][0] - p[p.length - 2][0], 2 * p[p.length - 1][1] - p[p.length - 2][1]] : p[i];
    for (let i = 0; i < p.length - 1; i++) {
      const p0 = get(i - 1), p1 = p[i], p2 = p[i + 1], p3 = get(i + 2);
      for (let s = 0; s < per; s++) {
        const t = s / per, t2 = t * t, t3 = t2 * t;
        out.push([0, 1].map((d) => 0.5 * (2 * p1[d] + (-p0[d] + p2[d]) * t
          + (2 * p0[d] - 5 * p1[d] + 4 * p2[d] - p3[d]) * t2 + (-p0[d] + 3 * p1[d] - 3 * p2[d] + p3[d]) * t3)));
      }
    }
    out.push(p[p.length - 1]);
    return out;
  }

  function openEditor(page) {
    if (!page) return;
    ed.page = page;
    ed.pts = page.outline_norm.map((c) => c.slice());
    ed.n = ed.pts.length / 4 + 1;
    ed.img = new Image();
    ed.img.onload = () => { layoutEditor(); drawEditor(); };
    ed.img.src = `/files/previews/${page.id}.jpg?v=${page.rev}`;
    $("editor").hidden = false;
  }

  function closeEditor() {
    $("editor").hidden = true;
    ed.page = null;
  }

  function layoutEditor() {
    const maxW = Math.min(980, window.innerWidth - 60);
    const maxH = window.innerHeight - 200;
    ed.scale = Math.min(maxW / ed.img.width, maxH / ed.img.height, 1);
    ed.w = Math.round(ed.img.width * ed.scale);
    ed.h = Math.round(ed.img.height * ed.scale);
    ed.dpr = window.devicePixelRatio || 1;
    canvas.style.width = ed.w + "px";
    canvas.style.height = ed.h + "px";
    canvas.width = Math.round(ed.w * ed.dpr);
    canvas.height = Math.round(ed.h * ed.dpr);
  }

  const toPx = (p) => [p[0] * ed.w, p[1] * ed.h];

  function outlinePath() {
    const dense = [];
    for (let k = 0; k < 4; k++) dense.push(...catmull(edgePoints(k).map(toPx)).slice(0, -1));
    ctx.moveTo(...dense[0]);
    for (const p of dense.slice(1)) ctx.lineTo(...p);
    ctx.closePath();
  }

  function drawEditor() {
    if (!ed.page || !ed.img.complete) return;
    ctx.setTransform(ed.dpr, 0, 0, ed.dpr, 0, 0);
    ctx.clearRect(0, 0, ed.w, ed.h);
    ctx.drawImage(ed.img, 0, 0, ed.w, ed.h);

    ctx.save();  // làm tối vùng ngoài tờ giấy
    ctx.beginPath();
    ctx.rect(0, 0, ed.w, ed.h);
    outlinePath();
    ctx.fillStyle = "rgba(0,0,0,.45)";
    ctx.fill("evenodd");
    ctx.restore();

    ctx.beginPath();
    outlinePath();
    ctx.lineWidth = 2;
    ctx.strokeStyle = "#3d8bff";
    ctx.stroke();

    ed.pts.forEach((p, i) => {
      const [x, y] = toPx(p);
      ctx.beginPath();
      ctx.arc(x, y, isCorner(i) ? R_CORNER : R_EDGE, 0, Math.PI * 2);
      ctx.fillStyle = i === ed.drag ? "#ffb020" : isCorner(i) ? "rgba(61,139,255,.35)" : "#3d8bff";
      ctx.fill();
      ctx.lineWidth = isCorner(i) ? 2.5 : 1.5;
      ctx.strokeStyle = "#fff";
      ctx.stroke();
    });

    if (ed.drag >= 0) drawLoupe(toPx(ed.pts[ed.drag]));
  }

  // Kính lúp: phóng to vùng quanh điểm đang kéo, đặt ở góc đối diện cho khỏi che
  function drawLoupe([x, y]) {
    const R = 70, Z = 3;
    const cx = x < ed.w / 2 ? ed.w - R - 10 : R + 10;
    const cy = y < ed.h / 2 ? ed.h - R - 10 : R + 10;
    const sx = x / ed.scale, sy = y / ed.scale;
    const srcR = R / (Z * ed.scale);
    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, Math.PI * 2);
    ctx.clip();
    ctx.fillStyle = "#000";
    ctx.fillRect(cx - R, cy - R, 2 * R, 2 * R);
    ctx.drawImage(ed.img, sx - srcR, sy - srcR, 2 * srcR, 2 * srcR, cx - R, cy - R, 2 * R, 2 * R);
    ctx.strokeStyle = "#ffb020";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx - 12, cy); ctx.lineTo(cx + 12, cy);
    ctx.moveTo(cx, cy - 12); ctx.lineTo(cx, cy + 12);
    ctx.stroke();
    ctx.restore();
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, Math.PI * 2);
    ctx.lineWidth = 3;
    ctx.strokeStyle = "#fff";
    ctx.stroke();
  }

  function pointerPos(e) {
    const r = canvas.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  }

  function movePoint(i, np) {
    const clamp = (v) => Math.min(1, Math.max(0, v));
    np = [clamp(np[0]), clamp(np[1])];
    const old = ed.pts[i];
    const d = [np[0] - old[0], np[1] - old[1]];
    ed.pts[i] = np;
    if (!isCorner(i)) return;
    // Kéo góc: các điểm trên 2 cạnh kề dịch theo, càng xa góc càng ít
    const m = ed.n - 1, N = ed.pts.length;
    for (let j = 1; j < m; j++) {
      const w = 1 - j / m;
      for (const idx of [(i + j) % N, (i - j + N) % N]) {
        ed.pts[idx] = [clamp(ed.pts[idx][0] + d[0] * w), clamp(ed.pts[idx][1] + d[1] * w)];
      }
    }
  }

  canvas.addEventListener("pointerdown", (e) => {
    const [x, y] = pointerPos(e);
    let best = -1, bestD = Infinity;
    ed.pts.forEach((p, i) => {
      const [px, py] = toPx(p);
      const d = Math.hypot(px - x, py - y) - (isCorner(i) ? 10 : 0);  // ưu tiên góc
      if (d < bestD) { best = i; bestD = d; }
    });
    if (bestD > 30) return;
    ed.drag = best;
    canvas.setPointerCapture(e.pointerId);
    drawEditor();
  });
  canvas.addEventListener("pointermove", (e) => {
    if (ed.drag < 0) return;
    const [x, y] = pointerPos(e);
    movePoint(ed.drag, [x / ed.w, y / ed.h]);
    drawEditor();
  });
  const endDrag = () => { ed.drag = -1; drawEditor(); };
  canvas.addEventListener("pointerup", endDrag);
  canvas.addEventListener("pointercancel", endDrag);
  window.addEventListener("resize", () => { if (ed.page) { layoutEditor(); drawEditor(); } });

  $("edCancel").addEventListener("click", closeEditor);
  $("edFull").addEventListener("click", () => {
    ed.pts = straightRing([[0, 0], [1, 0], [1, 1], [0, 1]], ed.n);
    drawEditor();
  });
  $("edStraight").addEventListener("click", () => {
    ed.pts = straightRing(cornerIdx().map((i) => ed.pts[i]), ed.n);
    drawEditor();
  });
  $("edAuto").addEventListener("click", async () => {
    try {
      const p = await api("PATCH", `/api/pages/${ed.page.id}`, { redetect: true });
      ed.pts = p.outline_norm.map((c) => c.slice());
      ed.n = ed.pts.length / 4 + 1;
      drawEditor();
      if (!p.auto_found) setStatus("Máy không tìm thấy khung giấy, hãy kéo góc bằng tay.");
      refresh(true);
    } catch (e) {
      setStatus("Lỗi: " + e.message);
    }
  });
  $("edSave").addEventListener("click", async () => {
    const id = ed.page.id, pts = ed.pts;
    closeEditor();
    await patch(id, { outline_norm: pts });
  });

  // ------------------------------------------------------------------ Khởi động
  loadInfo();
  refresh(true);
  setInterval(refresh, 2000);  // ảnh mới từ điện thoại sẽ tự hiện
})();
