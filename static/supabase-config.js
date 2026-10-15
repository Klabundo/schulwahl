/* ============================================================
   Schul-Wahlsystem – Supabase Client Konfiguration
   ============================================================ */
"use strict";

const SUPABASE_URL = "https://fhszzxxtvvqtdnqhnktk.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZoc3p6eHh0dnZxdGRucWhua3RrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTE5NjY0NjEsImV4cCI6MjEwNzU0MjQ2MX0.tSIwHT71-nv71Q1SQ0j-EDbkaLG-bYApgitRRTiD5g4";

const supabase = SupabaseJS.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmtUntil(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (h > 0) return `${h} Std. ${m} Min.`;
  if (m > 0) return `${m} Min. ${sec} Sek.`;
  return `${sec} Sek.`;
}

function fmtDe(v) {
  if (!v) return "";
  const d = new Date(v);
  const pad = n => String(n).padStart(2, "0");
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}., ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
