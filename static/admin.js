const $ = (id) => document.getElementById(id);
let currentElection = null;
let ballots = null;

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function api(path, opts = {}) {
  const res = await fetch(path, Object.assign({
    headers: { "Content-Type": "application/json" },
  }, opts));
  if (res.status === 401) { location.href = "/login"; return null; }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Etwas ist schiefgelaufen.");
  return data;
}

const statusText = { draft: "bereit", running: "läuft", closed: "beendet" };

function statusPill(status) {
  return `<span class="pill ${status}">${statusText[status] || status}</span>`;
}

function fmtDe(v) {
  // „YYYY-MM-DD HH:MM:SS“ → „16.10., 12:00“
  if (!v) return "";
  const d = new Date(v.replace(" ", "T"));
  const pad = n => String(n).padStart(2, "0");
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

async function refreshList() {
  const list = await api("/api/admin/overview");
  const plural = (n, s, p) => n === 1 ? s : p;
  $("election-list").innerHTML = list.map(e => `
    <button class="list-item ${currentElection?.id === e.id ? "active" : ""}"
            data-id="${e.id}">
      <span class="list-title">${esc(e.title)}${(e.round || 1) > 1 ? ' <span class="pill round sm">Finale</span>' : ""}</span>
      <span class="list-meta">${plural(e.candidate_count, "1 Kandidat:in", e.candidate_count + " Kandidat:innen")}
        · ${e.ballot_count} Stimmzettel · ${plural(e.vote_count, "1 Stimme", e.vote_count + " Stimmen")}
        ${e.ends_at && e.status !== "closed" ? ` · bis ${fmtDe(e.ends_at)}` : ""}</span>
      ${statusPill(e.status)}
    </button>`).join("")
    || '<p class="muted pad">Noch keine Wahlen – oben links legst du die erste an.</p>';
  $("election-list").querySelectorAll(".list-item").forEach(btn =>
    btn.addEventListener("click", () => openElection(Number(btn.dataset.id))));
}

async function openElection(id) {
  currentElection = id;
  ballots = null;
  $("new-panel").classList.add("hidden");
  $("placeholder").classList.add("hidden");
  await refreshList();
  await loadDetail();
}

async function loadDetail() {
  const el = await api(`/api/election/${currentElection}/results`);
  const d = $("detail");
  d.classList.remove("hidden");
  const open = el.status === "running";
  d.innerHTML = `
    <div class="detail-head">
      <div>
        <h2>${esc(el.title)} ${statusPill(el.status)}
          ${(el.round || 1) > 1 ? `<span class="pill round">Finale · Runde ${el.round}</span>` : ""}
        </h2>
        <p class="muted">${esc(el.description || "")}</p>
        ${el.ends_at ? `<p class="muted">⏱ Stichtag: ${fmtDe(el.ends_at)} –
          danach beendet sich die Wahl automatisch.</p>` : ""}
      </div>
      <div class="row-actions">
        ${el.status === "draft" ? `<button class="btn primary" id="start-btn">Wahl starten</button>` : ""}
        ${open ? `<button class="btn danger" id="close-btn">Wahl beenden</button>` : ""}
        ${el.status !== "closed"
          ? `<button class="btn ghost" id="deadline-btn" title="Stichtag setzen oder entfernen">Stichtag</button>` : ""}
        ${el.status === "closed" && (el.round || 1) === 1
          ? `<button class="btn" id="final-btn">Finale anlegen</button>` : ""}
        <button class="btn ghost" id="delete-btn" title="Wahl samt Stimmzetteln und Stimmen löschen">Löschen</button>
      </div>
    </div>
    <div class="tabs">
      <button class="tab active" data-tab="cands">Kandidat:innen</button>
      <button class="tab" data-tab="ballots">Stimmzettel</button>
      <button class="tab" data-tab="results">Ergebnisse</button>
    </div>
    <div id="tab-cands" class="tab-pane">
      <div class="add-row">
        <input id="cand-name" placeholder="Name des Projekts / der Person">
        <input id="cand-slogan" placeholder="Kurzer Slogan (optional)">
        <button class="btn" id="add-cand">Hinzufügen</button>
      </div>
      <div class="cand-list" id="cand-list"></div>
    </div>
    <div id="tab-ballots" class="tab-pane hidden">
      <div class="add-row">
        <label>Stimmzettel anlegen</label>
        <input id="ballot-count" type="number" min="1" max="500" value="20">
        <button class="btn" id="add-ballots">Anlegen</button>
        <label class="qr-host">QR-Link-Basis (optional – sonst die Server-Adresse)
          <input id="qr-host" placeholder="z. B. https://kkgschule.duckdns.net"></label>
        <select id="print-per" title="Stimmzettel pro Seite">
          <option value="25">25 pro Seite</option>
          <option value="50" selected>50 pro Seite</option>
          <option value="100">100 pro Seite</option>
        </select>
        <label class="qr-host"><input type="checkbox" id="print-qr">
          QR-Code auf den Zetteln</label>
        <button class="btn ghost" id="print-ballots" disabled>Stimmzettel drucken</button>
      </div>
      <div class="ballot-grid" id="ballot-grid"><p class="muted">Noch keine Stimmzettel angelegt – oben kannst du welche anlegen.</p></div>
    </div>
    <div id="tab-results" class="tab-pane hidden">
      <div class="result-stats">
        <div class="stat"><span id="res-votes">${el.totals.votes}</span><small>Stimmen gesamt</small></div>
        <div class="stat"><span id="res-part">${el.totals.ballots ? Math.round(100 * el.totals.used / el.totals.ballots) + " %" : "–"}</span><small>Beteiligung</small></div>
        <div class="stat"><span id="res-ballots">${el.totals.used}/${el.totals.ballots || 0}</span><small>Stimmzettel ausgezählt</small></div>
      </div>
      <div class="bars" id="res-bars">${renderBars(el)}</div>
      <div class="row-actions">
        <button class="btn" id="refresh-results">Aktualisieren</button>
        <a class="btn" href="/api/admin/elections/${el.id}/results.csv">Als CSV laden</a>
      </div>
    </div>`;

  d.querySelectorAll(".tab").forEach(t =>
    t.addEventListener("click", () => switchTab(t.dataset.tab)));

  if (el.status === "draft")
    $("start-btn").addEventListener("click", async () => {
      await api(`/api/admin/elections/${el.id}/start`, { method: "POST" });
      await loadDetail(); refreshList();
    });
  if (open)
    $("close-btn").addEventListener("click", async () => {
      if (confirm("Wahl wirklich beenden? Danach kann niemand mehr abstimmen.")) {
        await api(`/api/admin/elections/${el.id}/close`, { method: "POST" });
        await loadDetail(); refreshList();
      }
    });
  if ($("final-btn"))
    $("final-btn").addEventListener("click", async () => {
      const n = prompt("Wie viele Kandidat:innen schaffen es ins Finale?", "2");
      const top = Number(n);
      if (!top || top < 2) return;
      try {
        const res = await api(`/api/admin/elections/${el.id}/final`, {
          method: "POST",
          body: JSON.stringify({ top }),
        });
        await openElection(res.id);
      } catch (e) {
        alert(e.message);
      }
    });
  $("delete-btn").addEventListener("click", async () => {
    if (confirm("Wahl samt Stimmzetteln und Stimmen wirklich löschen?")) {
      await api(`/api/admin/elections/${el.id}`, { method: "DELETE" });
      currentElection = null;
      $("detail").classList.add("hidden");
      $("placeholder").classList.remove("hidden");
      refreshList();
    }
  });

  $("add-cand").addEventListener("click", async () => {
    const name = $("cand-name").value.trim();
    if (!name) return;
    await api(`/api/admin/elections/${el.id}/candidates`, {
      method: "POST",
      body: JSON.stringify({ name, slogan: $("cand-slogan").value.trim() }),
    });
    $("cand-name").value = ""; $("cand-slogan").value = "";
    await loadDetail(); refreshList();
  });

  $("add-ballots").addEventListener("click", async () => {
    const count = Number($("ballot-count").value);
    if (!count) return;
    await api(`/api/admin/elections/${el.id}/ballots`, {
      method: "POST", body: JSON.stringify({ count }),
    });
    await loadBallots(); refreshList();
  });
  $("print-ballots").addEventListener("click", () => {
    const p = new URLSearchParams({
      per: $("print-per").value,
      qr: $("print-qr").checked ? "1" : "0",
    });
    const host = $("qr-host")?.value.trim();
    if (host) p.set("host", host);
    window.open(`/print/${currentElection}?${p}`, "_blank");
  });
  if ($("deadline-btn"))
    $("deadline-btn").addEventListener("click", async () => {
      const cur = el.ends_at ? el.ends_at.replace(" ", "T") : "";
      const v = prompt("Stichtag als JJJJ-MM-TT HH:MM (leer = ohne Stichtag):", cur);
      if (v === null) return;
      try {
        await api(`/api/admin/elections/${el.id}/deadline`, {
          method: "POST",
          body: JSON.stringify({ ends_at: v.trim() }),
        });
        await loadDetail(); refreshList();
      } catch (e) {
        alert(e.message);
      }
    });
  $("refresh-results").addEventListener("click", async () => {
    await api(`/api/election/${el.id}/results`).then(renderResults);
  });

  await loadCandidates(el);
}

function renderBars(el) {
  const max = Math.max(1, ...el.candidates.map(c => c.votes));
  const sorted = [...el.candidates].sort((a, b) => b.votes - a.votes);
  return sorted.map((c, i) => {
    const pct = el.totals.votes ? Math.round(100 * c.votes / el.totals.votes) : 0;
    return `
      <div class="bar-row">
        <div class="bar-label">
          ${i === 0 && c.votes > 0 ? '<span class="crown">★</span> ' : ""}
          <strong>${esc(c.name)}</strong>
          <span class="bar-num">${c.votes} · ${pct} %</span>
        </div>
        <div class="bar-track"><div class="bar-fill" style="width:${Math.round(100 * c.votes / max)}%"></div></div>
      </div>`;
  }).join("");
}

async function loadCandidates(el) {
  const list = $("cand-list");
  if (!el.candidates.length) {
    list.innerHTML = '<p class="muted">Noch keine Kandidat:innen.</p>';
    return;
  }
  list.innerHTML = el.candidates.map(c => `
    <div class="cand-row" data-id="${c.id}">
      <div><strong>${esc(c.name)}</strong>${c.slogan ? `<small class="muted"> · ${esc(c.slogan)}</small>` : ""}</div>
      <button class="btn ghost small del-cand" data-id="${c.id}">Entfernen</button>
    </div>`).join("");
  list.querySelectorAll(".del-cand").forEach(b =>
    b.addEventListener("click", async () => {
      if (confirm("Kandidatur wirklich entfernen? Auch bereits abgegebene Stimmen werden gelöscht.")) {
        await api(`/api/admin/elections/${el.id}/candidates/${b.dataset.id}`, { method: "DELETE" });
        await loadDetail(); refreshList();
      }
    }));
}

function switchTab(name) {
  $("detail").querySelectorAll(".tab").forEach(t =>
    t.classList.toggle("active", t.dataset.tab === name));
  $("detail").querySelectorAll(".tab-pane").forEach(p =>
    p.classList.toggle("hidden", p.id !== `tab-${name}`));
  if (name === "ballots" && !ballots) loadBallots();
}

async function loadBallots() {
  const host = $("qr-host")?.value.trim() || "";
  const params = host ? `?host=${encodeURIComponent(host)}` : "";
  ballots = await api(`/api/admin/elections/${currentElection}/ballots${params}`);
  const grid = $("ballot-grid");
  grid.innerHTML = ballots.map(b => `
    <div class="ballot ${b.used ? "used" : ""}">
      <img src="${b.qr}" alt="QR">
      <code>${esc(b.code)}</code>
      <span class="pill ${b.used ? "closed" : "running"}">${b.used ? "verwendet" : "frei"}</span>
    </div>`).join("");
  $("print-ballots").disabled = !ballots.length;
}

function renderResults(el) {
  $("res-votes").textContent = el.totals.votes;
  $("res-part").textContent = el.totals.ballots ?
    Math.round(100 * el.totals.used / el.totals.ballots) + " %" : "–";
  $("res-ballots").textContent = `${el.totals.used}/${el.totals.ballots || 0}`;
  $("res-bars").innerHTML = renderBars(el);
}

async function init() {
  await refreshList();
  const fromUrl = new URLSearchParams(location.search).get("e");
  if (fromUrl && /^\d+$/.test(fromUrl)) {
    await openElection(fromUrl);
    history.replaceState(null, "", "/admin");
  }
  $("new-election-btn").addEventListener("click", async () => {
    currentElection = null;
    await refreshList();
    $("detail").classList.add("hidden");
    $("placeholder").classList.add("hidden");
    $("new-panel").classList.remove("hidden");
    $("new-title").focus();
  });
  $("create-election").addEventListener("click", async () => {
    const title = $("new-title").value.trim();
    if (!title) return;
    const id = (await api("/api/admin/elections", {
      method: "POST",
      body: JSON.stringify({
        title,
        description: $("new-desc").value.trim(),
        max_votes: Number($("new-max").value) || 1,
        ends_at: $("new-deadline").value,
      }),
    })).id;
    $("new-title").value = ""; $("new-desc").value = "";
    $("new-max").value = 1; $("new-deadline").value = "";
    await openElection(id);
  });
  $("change-pw-btn").addEventListener("click", async () => {
    const oldPw = prompt("Aktuelles Passwort:");
    if (!oldPw) return;
    const newPw = prompt("Neues Passwort (min. 4 Zeichen):");
    if (!newPw) return;
    try {
      await api("/api/admin/password", {
        method: "POST",
        body: JSON.stringify({ old: oldPw, new: newPw }),
      });
      alert("Fertig! Melde dich mit dem neuen Passwort an.");
      location.href = "/login";
    } catch (e) {
      alert(e.message);
    }
  });
}

window.addEventListener("DOMContentLoaded", init);
