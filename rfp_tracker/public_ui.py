"""Dependency-free presentation for the public, source-fact-only dashboard."""

PUBLIC_DASHBOARD_CSS = """
:root { --ink:#183136; --muted:#526970; --forest:#123f3c; --accent:#0b6257; --line:#d8e3e4; --background:#f3f7f7; }
* { box-sizing:border-box; }
html { scroll-behavior:smooth; }
body { margin:0; background:var(--background); color:var(--ink); font:15px/1.55 system-ui,-apple-system,"Segoe UI","Malgun Gothic",sans-serif; }
a { color:#0a5c69; } a:hover { text-decoration:underline; }
:focus-visible { outline:3px solid #db9900; outline-offset:3px; }
.skip-link { position:absolute; left:-10000px; top:8px; background:#fff; padding:9px 14px; z-index:20; }
.skip-link:focus { left:12px; }
.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
.shell { max-width:1280px; margin:0 auto; padding:24px 22px 60px; }
.hero { background:var(--forest); border-radius:18px; color:#fff; padding:28px 34px; }
.hero .eyebrow { color:#b8e5d9; font-size:12px; letter-spacing:.1em; font-weight:800; }
.hero h1 { max-width:760px; margin:9px 0 8px; font-size:clamp(25px,3vw,36px); line-height:1.23; }
.hero p { max-width:830px; margin:0; color:#e1f1eb; }
.hero-meta { display:flex; flex-wrap:wrap; gap:8px 20px; margin-top:17px; font-size:12px; color:#d2e8e1; }
.kpis { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:12px; margin:16px 0; }
.kpi { display:flex; flex-direction:column; min-height:118px; padding:16px 20px; background:#fff; border:1px solid var(--line); border-left:5px solid var(--accent); border-radius:12px; color:var(--ink); text-decoration:none; }
.kpi.focus { border-left-color:#176d63; } .kpi.support { border-left-color:#a06a1d; } .kpi.reference { border-left-color:#64748b; } .kpi.urgent { border-left-color:#ac5c24; }
.kpi span { font-size:13px; font-weight:700; color:#35545a; }
.kpi strong { font-size:30px; line-height:1.2; margin-top:3px; font-variant-numeric:tabular-nums; }
.kpi small { color:#0b6257; margin-top:auto; font-weight:700; }
.panel { background:#fff; border:1px solid var(--line); border-radius:16px; padding:24px; margin-top:16px; box-shadow:0 3px 14px rgba(15,52,50,.04); }
.section-head { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; margin-bottom:16px; }
h2 { margin:0; font-size:21px; line-height:1.3; } .section-head p { margin:5px 0 0; color:var(--muted); font-size:13px; }
.section-count { background:#e9f4f1; color:#0b6257; font-weight:800; border-radius:999px; padding:5px 11px; white-space:nowrap; }
.lead-list { display:grid; grid-template-columns:repeat(auto-fit,minmax(270px,1fr)); gap:12px; list-style:none; padding:0; margin:0; }
.lead-card { height:100%; border:1px solid #cbded8; border-radius:12px; padding:17px; background:#f9fcfb; }
.lead-card .eyebrow { color:#0b6257; font-size:11px; font-weight:800; letter-spacing:.08em; }
.lead-card h3 { margin:7px 0; font-size:16px; line-height:1.4; }
.lead-card h3 a { color:#153d42; } .lead-card p { margin:0 0 10px; color:var(--muted); font-size:13px; }
.lead-card dl { display:flex; flex-wrap:wrap; gap:10px 22px; margin:0; font-size:12px; }
.lead-card dt { color:var(--muted); } .lead-card dd { margin:0; font-weight:700; }
.detail-link { display:inline-block; margin-top:11px; font-size:12px; font-weight:700; }
.empty-lead { grid-column:1/-1; padding:20px; border:1px dashed #abcac2; border-radius:10px; background:#f7fbfa; color:#35545a; }
.filters { display:grid; grid-template-columns:minmax(220px,2fr) repeat(4,minmax(125px,1fr)); gap:10px; align-items:end; }
label { display:block; margin-bottom:5px; color:#35545a; font-size:12px; font-weight:800; }
input,select,button { min-height:42px; width:100%; padding:9px 11px; border:1px solid #aabec0; border-radius:8px; background:#fff; color:var(--ink); font:inherit; }
button { cursor:pointer; } .filter-actions { display:flex; align-items:center; gap:12px; margin:12px 0 0; }
.filter-actions button { width:auto; min-height:34px; padding:6px 12px; color:#0b6257; border-color:#a9c9bf; font-size:12px; font-weight:700; }
.advanced summary { cursor:pointer; color:#0a5c69; font-size:13px; font-weight:700; }
.advanced-grid { display:grid; grid-template-columns:repeat(2,minmax(170px,1fr)); gap:10px; max-width:520px; padding:12px 0 3px; }
.result-count { margin:17px 0 10px; font-weight:800; font-size:13px; color:#35545a; }
.table-wrap { border:1px solid var(--line); border-radius:10px; overflow-x:auto; }
table { width:100%; min-width:950px; border-collapse:collapse; table-layout:fixed; }
th { background:#eaf2f0; color:#23474c; text-align:left; font-size:12px; letter-spacing:.02em; padding:11px 13px; }
th:nth-child(1) { width:35%; } th:nth-child(2) { width:16%; } th:nth-child(3) { width:18%; } th:nth-child(4) { width:12%; } th:nth-child(5) { width:19%; }
td { border-top:1px solid var(--line); padding:12px 13px; vertical-align:top; font-size:13px; overflow-wrap:anywhere; }
tr:nth-child(even) td { background:#fbfdfc; } tr:hover td { background:#f2f8f6; }
tr[hidden], [hidden] { display:none !important; }
.notice-title { font-size:14px; font-weight:750; line-height:1.45; } .notice-title a { color:#143d46; text-decoration:none; } .notice-title a:hover { text-decoration:underline; }
.tier-tag { display:inline-block; margin-bottom:7px; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:800; }
.tier-tag.tier_1 { background:#e6f4ec; color:#206642; } .tier-tag.tier_2 { background:#fff3de; color:#80561b; } .tier-tag.tier_3 { background:#edf1f5; color:#43546b; }
.meta { color:var(--muted); font-size:12px; margin-top:5px; } .number { text-align:right; font-variant-numeric:tabular-nums; font-weight:700; }
.date { margin-top:6px; font-variant-numeric:tabular-nums; }
.active-status,.deadline-priority { display:inline-block; padding:2px 7px; border-radius:6px; font-size:11px; font-weight:800; white-space:nowrap; }
.active-status.active { background:#e6f4ec; color:#206642; } .active-status.inactive { background:#edf1f2; color:#52636a; }
.deadline-priority { margin-left:5px; border:1px solid; }
.row-details summary { cursor:pointer; color:#0a5c69; font-weight:800; font-size:12px; }
.docs { width:100%; margin-top:10px; padding:12px; background:#fff; border:1px solid var(--line); border-radius:8px; font-size:12px; font-weight:400; }
.docs p { margin:6px 0; } .document-card { border-top:1px solid var(--line); margin-top:10px; padding-top:8px; }
.document-header { display:flex; flex-wrap:wrap; gap:5px 9px; } .muted,.amount span { color:var(--muted); }
.more { display:block; width:auto; margin:17px auto 0; border-color:#0b6257; color:#0b6257; font-weight:800; }
.footnote { margin:20px 0 0; color:var(--muted); font-size:12px; }
@media (max-width:900px) { .filters { grid-template-columns:repeat(2,minmax(0,1fr)); } .kpis { grid-template-columns:repeat(2,minmax(0,1fr)); } }
@media (max-width:760px) {
  .shell { padding:12px 12px 42px; } .hero { padding:24px 20px; border-radius:14px; }
  .kpis { grid-template-columns:repeat(2,minmax(0,1fr)); gap:6px; } .kpi { padding:11px; min-height:104px; }
  .kpi span { font-size:11px; } .kpi strong { font-size:24px; } .kpi small { font-size:10px; }
  .panel { padding:16px; } .filters { grid-template-columns:1fr; }
  .table-wrap { border:0; overflow:visible; } table { min-width:0; } thead { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; }
  tbody,tr,td { display:block; width:100%; } tr { border:1px solid var(--line); border-radius:10px; margin:0 0 10px; overflow:hidden; }
  td { display:grid; grid-template-columns:86px minmax(0,1fr); gap:10px; border:0; border-top:1px solid #edf1f1; padding:9px 12px; }
  td::before { content:attr(data-label); color:var(--muted); font-size:11px; font-weight:800; }
  td.title { display:block; border-top:0; } td.title::before { display:none; } .number { text-align:left; }
  .docs { width:100%; } tr:nth-child(even) td { background:#fff; }
}
@media (max-width:430px) { .kpis { grid-template-columns:1fr 1fr; } }
"""

PUBLIC_DASHBOARD_JS = """
const rows = Array.from(document.querySelectorAll('.notice-row'));
const controls = ['search','tier','active','deadline-priority','source','document','deadline'].map(id => document.getElementById(id));
const resultCount = document.getElementById('result-count');
const empty = document.getElementById('empty');
const more = document.getElementById('more');
let limit = 25;
function matches(row) {
  const query = document.getElementById('search').value.trim().toLocaleLowerCase();
  const tier = document.getElementById('tier').value;
  const active = document.getElementById('active').value;
  const priority = document.getElementById('deadline-priority').value;
  const source = document.getElementById('source').value;
  const documentStatus = document.getElementById('document').value;
  const deadline = document.getElementById('deadline').value;
  return (!query || row.dataset.search.includes(query))
    && (!tier || row.dataset.tier === tier)
    && (!active || row.dataset.active === active)
    && (!priority || row.dataset.deadlinePriority === priority)
    && (!source || row.dataset.source === source)
    && (!documentStatus || row.dataset.document === documentStatus)
    && (!deadline || (row.dataset.deadline && row.dataset.deadline <= deadline));
}
function applyFilters(resetPage = false) {
  if (resetPage) limit = 25;
  const filtered = rows.filter(matches);
  const visible = new Set(filtered.slice(0,limit));
  rows.forEach(row => { row.hidden = !visible.has(row); });
  resultCount.textContent = filtered.length + '건 검색 · ' + visible.size + '건 표시';
  empty.hidden = filtered.length !== 0;
  more.hidden = filtered.length <= limit;
}
controls.forEach(control => { control.addEventListener('input', () => applyFilters(true)); });
document.getElementById('reset').addEventListener('click', () => {
  controls.forEach(control => { control.value = ''; });
  document.getElementById('active').value = 'active';
  applyFilters(true);
});
document.querySelectorAll('.kpi[data-tier-target]').forEach(card => {
  card.addEventListener('click', event => {
    event.preventDefault();
    controls.forEach(control => { control.value = ''; });
    document.getElementById('active').value = 'active';
    document.getElementById('tier').value = card.dataset.tierTarget;
    applyFilters(true);
    document.getElementById('notice-list').scrollIntoView({block:'start', inline:'nearest'});
  });
});
more.addEventListener('click', () => { limit += 25; applyFilters(); });
function revealPriorityCard() {
  const id = decodeURIComponent(location.hash.slice(1));
  if (!id.startsWith('notice-')) return;
  const target = document.getElementById(id);
  if (!target) return;
  controls.forEach(control => { control.value = ''; });
  document.getElementById('active').value = 'active';
  const index = rows.filter(matches).indexOf(target);
  limit = Math.max(25,index + 1);
  applyFilters();
  const details = target.querySelector('details');
  if (details) details.open = true;
  target.scrollIntoView({block:'center'});
}
window.addEventListener('hashchange', revealPriorityCard);
applyFilters();
revealPriorityCard();
"""
