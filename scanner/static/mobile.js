(() => {
  const token = window.SCAN_TOKEN;
  const log = document.getElementById("log");
  const summary = document.getElementById("summary");
  const queue = [];
  let sent = 0;
  let running = false;

  function addRow(name) {
    const li = document.createElement("li");
    li.innerHTML = '<span class="name"></span><span class="state muted">Đang chờ…</span>';
    li.querySelector(".name").textContent = name;
    log.prepend(li);
    return li.querySelector(".state");
  }

  function uploadOne(file, stateEl) {
    return new Promise((resolve) => {
      const fd = new FormData();
      fd.append("files", file, file.name || "anh.jpg");
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/upload?t=" + encodeURIComponent(token));
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) stateEl.textContent = "Đang gửi " + Math.round((e.loaded / e.total) * 100) + "%";
      };
      xhr.upload.onload = () => { stateEl.textContent = "Đang xử lý…"; };
      xhr.onload = () => {
        let msg = "Lỗi " + xhr.status;
        try {
          const r = JSON.parse(xhr.responseText);
          if (xhr.status === 200) {
            sent += r.added.length;
            stateEl.textContent = "✓ Đã gửi";
            stateEl.className = "state ok";
            return resolve();
          }
          msg = r.error || (r.errors && r.errors[0] && r.errors[0].error) || msg;
        } catch (_) { /* phản hồi không phải JSON */ }
        if (xhr.status === 403) msg = "Mã truy cập hết hạn, hãy quét lại mã QR";
        stateEl.textContent = "✗ " + msg;
        stateEl.className = "state err";
        resolve();
      };
      xhr.onerror = () => {
        stateEl.textContent = "✗ Mất kết nối tới laptop";
        stateEl.className = "state err";
        resolve();
      };
      xhr.send(fd);
    });
  }

  async function pump() {
    if (running) return;
    running = true;
    while (queue.length) {
      const { file, stateEl } = queue.shift();
      await uploadOne(file, stateEl);
      summary.textContent = "Đã gửi " + sent + " trang" + (queue.length ? " — còn " + queue.length + " ảnh đang chờ" : "");
    }
    running = false;
  }

  function enqueue(files) {
    for (const file of files) {
      queue.push({ file, stateEl: addRow(file.name || "Ảnh chụp") });
    }
    pump();
  }

  for (const id of ["camInput", "pickInput"]) {
    const input = document.getElementById(id);
    input.addEventListener("change", () => {
      enqueue(Array.from(input.files));
      input.value = "";  // cho phép chụp/chọn tiếp
    });
  }
})();
