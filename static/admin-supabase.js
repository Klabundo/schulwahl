/* ============================================================
   Schul-Wahlsystem – Admin JavaScript (Supabase Edition)
   ============================================================ */
"use strict";

const $ = (id) => document.getElementById(id);
let currentElection = null;
let cachedBallots = null;

const CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789";

function generateCode() {
  function chunk() {
    let s = "";
    for (let i = 0; i < 4; i++) {
      s += CODE_ALPHABET[Math.floor(Math.random() * CODE_ALPHABET.length)];
    }
    return s;
  }
  return `${chunk()}-${chunk()}`;
}

function getAdminPw() {
  return sessionStorage.getItem("admin_pw") || "";
}

const statusText = { draft: "bereit", running: "läuft", closed: "beendet" };

function statusPill(status) {
  return `<span class="pill ${status}">${statusText[status] || status}</span>`;
}

async function refreshList() {
  const { data: list, error } = await supabase
    .from("elections")
    .select("*, candidates(count), ballots(count), votes(count)")
    .order("id", { ascending: false });

  if (error || !list) {
    $("election-list").innerHTML = '<p class="muted pad">Fehler beim Laden der Wahlen.</p>';
    return;
  }

  const plural = (n, s, p) => n === 1 ? s : p;
  $("election-list").innerHTML = list.map(e => {
    const cCount = e.candidates ? e.candidates[0]?.count || 0 : 0;
    const bCount = e.ballots ? e.ballots[0]?.count || 0 : 0;
    const vCount = e.votes ? e.votes[0]?.count || 0 : 0;

    return `
    <button class="list-item ${currentElection === e.id ? "active" : ""}" data-id="${e.id}">
      <span class="list-title">${esc(e.title)}${(e.round || 1) > 1 ? ' <span class="pill round sm">Finale</span>' : ""}</span>
      <span class="list-meta">${plural(cCount, "1 Option", cCount + " Optionen")}
        · ${bCount} Stimmzettel · ${plural(vCount, "1 Stimme", vCount + " Stimmen")}
        ${e.ends_at && e.status !== "closed" ? ` · bis ${fmtDe(e.ends_at)}` : ""}</span>
      ${statusPill(e.status)}
    </button>`;
  }).join("") || '<p class="muted pad">Noch keine Wahlen – oben links legst du die erste an.</p>';

  $("election-list").querySelectorAll(".list-item").forEach(btn =>
    btn.addEventListener("click", () => openElection(Number(btn.dataset.id))));
}

async function openElection(id) {
  currentElection = id;
  cachedBallots = null;
  $("new-panel").classList.add("hidden");
  $("placeholder").classList.add("hidden");
  await refreshList();
  await loadDetail();
}

async function loadDetail() {
  const pw = getAdminPw();
  const numEid = currentElection;

  const { data: el, error: elErr } = await supabase
    .from("elections")
    .select("*, candidates(*)")
    .eq("id", numEid)
    .single();

  if (elErr || !el) {
    alert("Wahl konnte nicht geladen werden.");
    return;
  }

  const { data: votes } = await supabase
    .from("votes")
    .select("candidate_id")
    .eq("election_id", numEid);

  const { data: bRes } = await supabase.rpc("admin_get_ballots", {
    p_pw: pw,
    p_election_id: numEid
  });

  const ballots = (bRes && bRes.ok) ? bRes.ballots : [];
  cachedBallots = ballots;

  const voteList = votes || [];
  const voteCounts = {};
  for (const v of voteList) {
    voteCounts[v.candidate_id] = (voteCounts[v.candidate_id] || 0) + 1;
  }

  const usedBallots = ballots.filter(b => b.used_at).length;
  const candidates = (el.candidates || []).map(c => ({
    id: c.id,
    name: c.name,
    slogan: c.slogan,
    votes: voteCounts[c.id] || 0
  }));
  candidates.sort((a, b) => (a.sort - b.sort) || (a.id - b.id));

  const electionData = {
    ...el,
    totals: {
      votes: voteList.length,
      ballots: ballots.length,
      used: usedBallots
    },
    candidates: candidates
  };

  const d = $("detail");
  d.classList.remove("hidden");
  const open = el.status === "running";

  d.innerHTML = `
    <div class="detail-head">
      <div>
        <h2>${esc(el.title)} ${statusPill(el.status)}
          ${(el.round || 1) > 1 ? `<span class="pill round">Runde ${el.round}</span>` : ""}
          ${el.hide_results ? `<span class="pill round sm" title="Ergebnisse erst nach Wahlschluss sichtbar">🔒 Blind-Voting</span>` : ""}
        </h2>
        ${el.description ? `<p class="muted">${esc(el.description)}</p>` : ""}
        ${el.ends_at ? `<p class="muted">Stichtag: ${fmtDe(el.ends_at)}</p>` : ""}
      </div>
      <div class="row-actions">
        ${el.status === "draft" ? `<button class="btn primary" id="start-btn">Starten</button>` : ""}
        ${open ? `<button class="btn danger" id="close-btn">Beenden</button>` : ""}
        <button class="btn ghost" id="toggle-hide-btn" title="Blind-Voting">${el.hide_results ? "🔓 Live aufdecken" : "🔒 Blind-Voting"}</button>
        ${el.status !== "closed"
          ? `<button class="btn ghost" id="deadline-btn" title="Stichtag setzen">Stichtag</button>` : ""}
        <button class="btn ghost" id="delete-btn" title="Löschen">Löschen</button>
      </div>
    </div>
    <div class="tabs">
      <button class="tab active" data-tab="cands">Optionen / Antworten</button>
      <button class="tab" data-tab="ballots">Stimmzettel</button>
      <button class="tab" data-tab="results">Ergebnisse</button>
    </div>
    <div id="tab-cands" class="tab-pane">
      <div class="add-row">
        <input id="cand-name" placeholder="Option / Antwort (z. B. Ja, Nein, Projekt)">
        <input id="cand-slogan" placeholder="Zusatzinfo / Beschreibung (optional)">
        <button class="btn" id="add-cand">Hinzufügen</button>
      </div>
      <div class="presets-row" style="display:flex; gap:0.5rem; margin-bottom:1rem; flex-wrap:wrap; align-items:center;">
        <span style="font-size:0.85rem; color:var(--muted); font-weight:600;">Schnellvorlagen:</span>
        <button class="btn ghost small" id="preset-yesno" type="button">+ Ja / Nein</button>
        <button class="btn ghost small" id="preset-yesnoabs" type="button">+ Ja / Nein / Enthaltung</button>
        <button class="btn ghost small" id="preset-grades" type="button">+ Noten 1 bis 6</button>
      </div>
      <div class="cand-list" id="cand-list"></div>
    </div>
    <div id="tab-ballots" class="tab-pane hidden">
      <div class="add-row">
        <label>Anzahl</label>
        <input id="ballot-count" type="number" min="1" max="500" value="20">
        <button class="btn" id="add-ballots">Erzeugen</button>
        <select id="print-filter">
          <option value="unused" selected>Nur unbenutzte drucken</option>
          <option value="all">Alle Zettel drucken</option>
          <option value="used">Nur benutzte drucken</option>
        </select>
        <select id="print-per" title="Stimmzettel pro Seite">
          <option value="25">25 / Seite</option>
          <option value="50" selected>50 / Seite</option>
          <option value="100">100 / Seite</option>
        </select>
        <label class="qr-host"><input type="checkbox" id="print-qr" checked> QR-Code</label>
        <button class="btn ghost" id="print-ballots" ${ballots.length ? "" : "disabled"}>Drucken</button>
      </div>
      <div class="ballot-grid" id="ballot-grid"></div>
    </div>
    <div id="tab-results" class="tab-pane hidden">
      <div class="result-stats">
        <div class="stat"><span id="res-votes">${electionData.totals.votes}</span><small>Stimmen</small></div>
        <div class="stat"><span id="res-part">${electionData.totals.ballots ? Math.round(100 * electionData.totals.used / electionData.totals.ballots) + " %" : "–"}</span><small>Beteiligung</small></div>
        <div class="stat"><span id="res-ballots">${electionData.totals.used}/${electionData.totals.ballots}</span><small>Stimmzettel</small></div>
      </div>
      <div class="bars" id="res-bars">${renderBars(electionData)}</div>
      <div class="row-actions">
        <button class="btn" id="refresh-results">Aktualisieren</button>
        <button class="btn" id="csv-btn">Als CSV laden</button>
      </div>
    </div>`;

  d.querySelectorAll(".tab").forEach(t =>
    t.addEventListener("click", () => switchTab(t.dataset.tab)));

  if (el.status === "draft") {
    $("start-btn").addEventListener("click", async () => {
      await supabase.rpc("admin_set_status", {
        p_pw: pw,
        p_election_id: numEid,
        p_status: "running"
      });
      await loadDetail();
      refreshList();
    });
  }

  if (open) {
    $("close-btn").addEventListener("click", async () => {
      if (confirm("Wahl wirklich beenden? Danach kann niemand mehr abstimmen.")) {
        await supabase.rpc("admin_set_status", {
          p_pw: pw,
          p_election_id: numEid,
          p_status: "closed"
        });
        await loadDetail();
        refreshList();
      }
    });
  }

  if ($("deadline-btn")) {
    $("deadline-btn").addEventListener("click", async () => {
      const cur = el.ends_at ? new Date(el.ends_at).toISOString().slice(0, 16) : "";
      const v = prompt("Stichtag als JJJJ-MM-TTTHH:MM (leer = ohne Stichtag):", cur);
      if (v === null) return;
      const ends_at = v.trim() ? new Date(v.trim()).toISOString() : null;
      await supabase.rpc("admin_set_deadline", {
        p_pw: pw,
        p_election_id: numEid,
        p_ends_at: ends_at
      });
      await loadDetail();
      refreshList();
    });
  }

  $("toggle-hide-btn").addEventListener("click", async () => {
    await supabase.rpc("admin_set_hide_results", {
      p_pw: pw,
      p_election_id: numEid,
      p_hide: !el.hide_results
    });
    await loadDetail();
  });

  $("delete-btn").addEventListener("click", async () => {
    if (confirm("Wahl samt Stimmzetteln und Stimmen wirklich löschen?")) {
      await supabase.rpc("admin_delete_election", {
        p_pw: pw,
        p_election_id: numEid
      });
      currentElection = null;
      $("detail").classList.add("hidden");
      $("placeholder").classList.remove("hidden");
      refreshList();
    }
  });

  $("add-cand").addEventListener("click", async () => {
    const name = $("cand-name").value.trim();
    if (!name) return;
    await supabase.rpc("admin_add_candidate", {
      p_pw: pw,
      p_election_id: numEid,
      p_name: name,
      p_slogan: $("cand-slogan").value.trim()
    });
    $("cand-name").value = "";
    $("cand-slogan").value = "";
    await loadDetail();
    refreshList();
  });

  async function addBatchOptions(opts) {
    for (const o of opts) {
      await supabase.rpc("admin_add_candidate", {
        p_pw: pw,
        p_election_id: numEid,
        p_name: o.name,
        p_slogan: o.slogan || ""
      });
    }
    await loadDetail();
    refreshList();
  }

  if ($("preset-yesno")) {
    $("preset-yesno").addEventListener("click", () => {
      addBatchOptions([{ name: "Ja" }, { name: "Nein" }]);
    });
  }
  if ($("preset-yesnoabs")) {
    $("preset-yesnoabs").addEventListener("click", () => {
      addBatchOptions([{ name: "Ja" }, { name: "Nein" }, { name: "Enthaltung" }]);
    });
  }
  if ($("preset-grades")) {
    $("preset-grades").addEventListener("click", () => {
      addBatchOptions([
        { name: "Note 1", slogan: "Sehr gut" },
        { name: "Note 2", slogan: "Gut" },
        { name: "Note 3", slogan: "Befriedigend" },
        { name: "Note 4", slogan: "Ausreichend" },
        { name: "Note 5", slogan: "Mangelhaft" },
        { name: "Note 6", slogan: "Ungenügend" }
      ]);
    });
  }

  $("add-ballots").addEventListener("click", async () => {
    const count = Number($("ballot-count").value);
    if (!count || count <= 0) return;
    const codes = [];
    for (let i = 0; i < count; i++) {
      codes.push(generateCode());
    }
    await supabase.rpc("admin_add_ballots", {
      p_pw: pw,
      p_election_id: numEid,
      p_codes: codes
    });
    await loadDetail();
    refreshList();
  });

  $("print-ballots").addEventListener("click", () => {
    const per = $("print-per").value;
    const qr = $("print-qr").checked ? "1" : "0";
    const filter = $("print-filter").value;
    window.open(`print.html?e=${numEid}&per=${per}&qr=${qr}&filter=${filter}`, "_blank");
  });

  $("refresh-results").addEventListener("click", loadDetail);

  $("csv-btn").addEventListener("click", () => {
    exportCsv(electionData);
  });

  loadCandidatesList(electionData);
  renderBallotsGrid(ballots, numEid, el.title);
}

function exportCsv(el) {
  let csv = "Option;Zusatzinfo;Stimmen;Prozent\n";
  const total = el.totals.votes || 0;
  el.candidates.forEach(c => {
    const pct = total ? (100 * c.votes / total).toFixed(1) : "0.0";
    csv += `"${c.name.replace(/"/g, '""')}";"${(c.slogan || "").replace(/"/g, '""')}";${c.votes};${pct}%\n`;
  });
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `abstimmung-${el.id}-ergebnisse.csv`;
  a.click();
  URL.revokeObjectURL(url);
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

function loadCandidatesList(el) {
  const list = $("cand-list");
  if (!el.candidates.length) {
    list.innerHTML = '<p class="muted">Noch keine Optionen / Antworten angelegt.</p>';
    return;
  }
  const pw = getAdminPw();
  list.innerHTML = el.candidates.map(c => `
    <div class="cand-row" data-id="${c.id}">
      <div><strong>${esc(c.name)}</strong>${c.slogan ? `<small class="muted"> · ${esc(c.slogan)}</small>` : ""}</div>
      <button class="btn ghost small del-cand" data-id="${c.id}">Entfernen</button>
    </div>`).join("");

  list.querySelectorAll(".del-cand").forEach(b =>
    b.addEventListener("click", async () => {
      if (confirm("Option wirklich entfernen? Auch bereits abgegebene Stimmen darauf werden gelöscht.")) {
        await supabase.rpc("admin_delete_candidate", {
          p_pw: pw,
          p_candidate_id: Number(b.dataset.id)
        });
        await loadDetail();
        refreshList();
      }
    }));
}

function getVoteUrlForAdmin(eid, code) {
  const origin = location.origin + location.pathname.replace("admin.html", "vote.html");
  return `${origin}?e=${eid}&code=${encodeURIComponent(code)}`;
}

let activeAdminLightboxQr = null;
function openAdminLightbox(title, code, url) {
  $("lightbox-title").textContent = title;
  $("lightbox-code").textContent = code;
  $("lightbox-link").href = url;

  const qrBox = $("lightbox-qr-container");
  qrBox.innerHTML = "";
  activeAdminLightboxQr = new QRCode(qrBox, {
    text: url,
    width: 280,
    height: 280,
    correctLevel: QRCode.CorrectLevel.H
  });

  const copyBtn = $("lightbox-copy-btn");
  copyBtn.textContent = "Code kopieren";
  copyBtn.onclick = () => {
    navigator.clipboard.writeText(code);
    copyBtn.textContent = "Kopiert!";
    setTimeout(() => { copyBtn.textContent = "Code kopieren"; }, 1500);
  };

  $("qr-lightbox").style.display = "flex";
}

function closeAdminLightbox() {
  $("qr-lightbox").style.display = "none";
}

function renderBallotsGrid(ballots, eid, title) {
  const grid = $("ballot-grid");
  if (!ballots.length) {
    grid.innerHTML = '<p class="muted">Noch keine Stimmzettel angelegt – oben kannst du welche anlegen.</p>';
    return;
  }
  grid.innerHTML = "";
  ballots.forEach(b => {
    const card = document.createElement("div");
    card.className = `ballot ${b.used_at ? "used" : ""}`;
    card.title = "Klicken zum Vergrößern";

    const voteUrl = getVoteUrlForAdmin(eid, b.code);

    const qrDiv = document.createElement("div");
    qrDiv.className = "ballot-qr";
    // 180x180 Pixel für scharfe Darstellung
    new QRCode(qrDiv, {
      text: voteUrl,
      width: 180,
      height: 180,
      correctLevel: QRCode.CorrectLevel.M
    });

    const info = document.createElement("div");
    info.style.textAlign = "center";
    info.innerHTML = `
      <code>${esc(b.code)}</code>
      <div style="margin-top:4px"><span class="pill ${b.used_at ? "closed" : "running"}">${b.used_at ? "verwendet" : "frei"}</span></div>
    `;

    card.appendChild(qrDiv);
    card.appendChild(info);
    card.addEventListener("click", () => openAdminLightbox(title, b.code, voteUrl));
    grid.appendChild(card);
  });
}

function switchTab(name) {
  $("detail").querySelectorAll(".tab").forEach(t =>
    t.classList.toggle("active", t.dataset.tab === name));
  $("detail").querySelectorAll(".tab-pane").forEach(p =>
    p.classList.toggle("hidden", p.id !== `tab-${name}`));
}

async function verifyAuth(pw) {
  const { data } = await supabase.rpc("check_admin_pass", { p_pw: pw });
  return data === true;
}

async function initAdminApp() {
  $("login-section").style.display = "none";
  $("admin-section").style.display = "grid";

  await refreshList();

  const fromUrl = new URLSearchParams(location.search).get("e");
  if (fromUrl && /^\d+$/.test(fromUrl)) {
    await openElection(Number(fromUrl));
  }

  $("new-election-btn").addEventListener("click", () => {
    currentElection = null;
    $("detail").classList.add("hidden");
    $("placeholder").classList.add("hidden");
    $("new-panel").classList.remove("hidden");
    $("new-title").focus();
  });

  $("create-election").addEventListener("click", async () => {
    const title = $("new-title").value.trim();
    if (!title) return;
    const pw = getAdminPw();
    const desc = $("new-desc").value.trim();
    const max = Number($("new-max").value) || 1;
    const dl = $("new-deadline").value ? new Date($("new-deadline").value).toISOString() : null;
    const hide = $("new-hide-results") ? $("new-hide-results").checked : false;

    const { data: res } = await supabase.rpc("admin_create_election", {
      p_pw: pw,
      p_title: title,
      p_description: desc,
      p_max_votes: max,
      p_ends_at: dl,
      p_hide_results: hide
    });

    if (res && res.ok && res.id) {
      $("new-title").value = "";
      $("new-desc").value = "";
      await openElection(res.id);
    } else {
      alert("Fehler beim Erstellen der Wahl.");
    }
  });

  $("change-pw-btn").addEventListener("click", async () => {
    const cur = prompt("Aktuelles Admin-Passwort:");
    if (!cur) return;
    const nw = prompt("Neues Admin-Passwort (mind. 4 Zeichen):");
    if (!nw) return;
    const { data: res } = await supabase.rpc("admin_change_password", {
      p_old_pw: cur,
      p_new_pw: nw
    });
    if (res && res.ok) {
      sessionStorage.setItem("admin_pw", nw);
      alert("Passwort erfolgreich geändert!");
    } else {
      alert((res && res.error) || "Fehler beim Ändern des Passworts.");
    }
  });

  $("logout-btn").addEventListener("click", () => {
    sessionStorage.removeItem("admin_pw");
    location.reload();
  });

  if ($("lightbox-backdrop")) $("lightbox-backdrop").addEventListener("click", closeAdminLightbox);
  if ($("lightbox-close-btn")) $("lightbox-close-btn").addEventListener("click", closeAdminLightbox);
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAdminLightbox();
  });
}

window.addEventListener("DOMContentLoaded", async () => {
  const pw = getAdminPw();
  if (pw && await verifyAuth(pw)) {
    initAdminApp();
  } else {
    $("admin-section").style.display = "none";
    $("login-section").style.display = "block";

    $("admin-login-btn").addEventListener("click", async () => {
      const inputPw = $("admin-login-pw").value;
      if (await verifyAuth(inputPw)) {
        sessionStorage.setItem("admin_pw", inputPw);
        initAdminApp();
      } else {
        const err = $("login-error");
        err.textContent = "Falsches Passwort.";
        err.style.display = "block";
      }
    });

    $("admin-login-pw").addEventListener("keydown", (e) => {
      if (e.key === "Enter") $("admin-login-btn").click();
    });
  }
});
