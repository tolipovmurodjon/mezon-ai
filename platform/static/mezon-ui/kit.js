/* ==========================================================================
   Mezon UI — kit behaviour: chart rendering + demo interactions.
   Plain JS, no dependencies. Chart builders are reusable: call
   Mezon.pixelChart(el, data) etc. All sample data is synthetic.
   ========================================================================== */
(function () {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const NBSP = ' ';

  // Uzbek number formatting: space thousands, comma decimals.
  function fmt(n, d = 0) {
    const s = Number(n).toFixed(d).split('.');
    s[0] = s[0].replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
    return s.join(',');
  }
  function axisFmt(n, max) {
    if (max >= 10000) return n === 0 ? '0' : fmt(n / 1000, n % 1000 ? 1 : 0) + NBSP + 'ming';
    return fmt(n);
  }
  function rng(seed) { // mulberry32
    return function () {
      seed |= 0; seed = seed + 0x6D2B79F5 | 0;
      let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function svgEl(tag, attrs) {
    const n = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  }
  function icon(name, cls = 'icon') {
    const s = svgEl('svg', { class: cls, 'aria-hidden': 'true' });
    s.appendChild(svgEl('use', { href: '#i-' + name }));
    return s;
  }

  /* ---------- Toasts ---------------------------------------------------- */
  function toast(title, sub, undo) {
    const host = $('#toastHost'); if (!host) return;
    const t = el('div', 'toast'); t.setAttribute('role', 'status');
    const ok = el('span', 'toast-ok'); ok.appendChild(icon('check')); t.appendChild(ok);
    const tx = el('span', 'toast-text', title);
    if (sub) tx.appendChild(el('small', null, sub));
    t.appendChild(tx);
    if (undo) {
      const b = el('button', 'btn btn-ghost', 'Bekor qilish');
      b.addEventListener('click', () => { undo(); t.remove(); });
      t.appendChild(b);
    }
    host.appendChild(t);
    setTimeout(() => t.remove(), 4200);
  }
  function copy(text, label) {
    const done = () => toast(label || 'Nusxa olindi', text.length > 60 ? null : text);
    try {
      if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(done, done);
      else {
        const ta = el('textarea'); ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
        document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); } catch (e) {} ta.remove(); done();
      }
    } catch (e) { done(); }
  }

  /* ---------- Mezon matrix mark ----------------------------------------- */
  const M_ON = (r, c) => c === 0 || c === 4 || (r === 1 && (c === 1 || c === 3)) || (r === 2 && c === 2);
  function hydrateMatrix(node) {
    if (node.childElementCount) return;
    for (let r = 0; r < 5; r++) for (let c = 0; c < 5; c++) {
      const i = document.createElement('i');
      if (M_ON(r, c)) i.className = 'on';
      i.style.setProperty('--d', r + c);
      node.appendChild(i);
    }
  }

  /* ---------- Tick sparkline + tick meter ------------------------------- */
  function tickSpark(node) {
    const vals = (node.dataset.values || '').split(',').map(Number).filter(v => !isNaN(v));
    if (!vals.length) return;
    const min = Math.min(...vals), max = Math.max(...vals);
    const lo = min - (max - min) * 0.35;
    node.textContent = '';
    vals.forEach((v, i) => {
      const s = document.createElement('span');
      s.style.height = Math.max(10, ((v - lo) / (max - lo)) * 100) + '%';
      if (i === vals.length - 1) s.className = node.dataset.alert === 'last' ? 'is-alert' : 'is-now';
      node.appendChild(s);
    });
  }
  function tickMeter(node) {
    const v = parseFloat(node.dataset.meter), plan = parseFloat(node.dataset.plan);
    const n = parseInt(node.dataset.count || '60', 10);
    node.textContent = '';
    const planIdx = isNaN(plan) ? -1 : Math.round((plan / 100) * (n - 1));
    for (let i = 0; i < n; i++) {
      const s = document.createElement('span');
      const pos = ((i + 0.5) / n) * 100;
      if (i === planIdx) s.className = 'plan';
      else if (pos <= v) s.className = 'on';
      else if (!isNaN(plan) && pos <= plan) s.className = 'gap';
      node.appendChild(s);
    }
  }

  /* ---------- Data (synthetic) ------------------------------------------ */
  const MONTHS = ['Yan', 'Fev', 'Mar', 'Apr', 'May', 'Iyn', 'Iyl', 'Avg', 'Sen', 'Okt', 'Noy', 'Dek'];
  const MONTHS_FULL = ['Yanvar', 'Fevral', 'Mart', 'Aprel', 'May', 'Iyun', 'Iyul', 'Avgust', 'Sentabr', 'Oktabr', 'Noyabr', 'Dekabr'];
  const DATA = (function () {
    const r = rng(2026);
    const season = m => 1 + 0.12 * Math.sin((m - 1) / 11 * Math.PI * 2) + m * 0.012;
    const decade = [];
    for (let m = 0; m < 12; m++) for (let d = 0; d < 3; d++) {
      if (m === 11 || (m === 10 && d === 2)) { decade.push({ a: 0, b: 0, t: MONTHS[m] + ' · ' + (d + 1) + '-dekada', future: true }); continue; }
      const tot = Math.round(3650 * season(m) + (r() - 0.5) * 700);
      const surge = m === 9 ? (d === 0 ? 0.4 : d === 1 ? 0.7 : 1) : m === 10 ? 1.2 : 0;
      const open = Math.round(tot * (0.08 + r() * 0.04 + surge * 0.12));
      const od = surge ? Math.round(open * (0.55 + surge * 0.2)) : Math.round(open * r() * 0.04);
      decade.push({ a: tot - open, b: open, o: od, t: MONTHS[m] + ' · ' + (d + 1) + '-dekada' });
    }
    const month = [];
    for (let m = 0; m < 12; m++) {
      if (m === 11) { month.push({ a: 0, b: 0, t: MONTHS_FULL[m], future: true }); continue; }
      const parts = decade.slice(m * 3, m * 3 + 3);
      month.push({ a: parts.reduce((s, x) => s + x.a, 0), b: parts.reduce((s, x) => s + x.b, 0), o: parts.reduce((s, x) => s + x.o, 0), t: MONTHS_FULL[m] });
    }
    const week = [];
    for (let w = 24; w <= 47; w++) {
      const tot = Math.round(2700 + 260 * Math.sin(w / 3.1) + (r() - 0.5) * 420 + (w - 24) * 14);
      const open = Math.round(tot * (0.08 + r() * 0.08));
      const surge = w >= 41 ? Math.min(1.3, (w - 40) * 0.22) : 0;
      const open2 = Math.round(open * (1 + surge * 1.4));
      week.push({ a: tot - open2, b: open2, o: surge ? Math.round(open2 * (0.5 + surge * 0.25)) : Math.round(open * r() * 0.04), t: w + '-hafta' });
    }
    const xorazm = [41, 44, 39, 47, 52, 49, 55, 58, 61, 64, 64, 88].map((v, i) => ({ a: v, b: 0, t: (36 + i) + '-hafta', c: i === 11 }));
    const xorazm2 = [212, 224, 205, 231, 240, 236, 251, 247, 262, 270, 268, 301].map((t, i) => {
      const open = [22, 25, 21, 27, 31, 30, 34, 36, 41, 44, 45, 71][i];
      return { a: t - open, b: open, t: (36 + i) + '-hafta' };
    });
    const weekday = ['Du', 'Se', 'Ch', 'Pa', 'Ju', 'Sh', 'Ya'].map((d, i) => ({ a: [2310, 2040, 1980, 1910, 1720, 690, 310][i], b: 0, t: ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba'][i] }));
    return {
      appeals: {
        decade: { cols: decade, labels: MONTHS, group: 3, now: 10 },
        month: { cols: month, labels: MONTHS, group: 1, now: 10 },
        week: { cols: week, labels: ['Iyn', 'Iyl', 'Avg', 'Sen', 'Okt', 'Noy'], group: 4, now: 5 },
        series: ['Hal qilingan', 'Ochiq', 'shundan muddati o‘tgan']
      },
      xorazm: { cols: xorazm, labels: xorazm.map((x, i) => i % 3 === 0 ? String(36 + i) : ''), group: 1, now: 11, series: ['Muddati o‘tgan'] },
      xorazm2: { cols: xorazm2, labels: xorazm2.map((x, i) => i % 3 === 0 ? String(36 + i) : ''), group: 1, now: 11, series: ['Hal qilingan', 'Ochiq'] },
      weekday: { cols: weekday, labels: ['Du', 'Se', 'Ch', 'Pa', 'Ju', 'Sh', 'Ya'], group: 1, now: -1, series: ['Murojaatlar'] }
    };
  })();

  /* ---------- Pixel bar chart ------------------------------------------- */
  function niceUnit(max, rows) {
    const raw = max / rows;
    const pow = Math.pow(10, Math.floor(Math.log10(raw)));
    const steps = [1, 1.25, 2, 2.5, 4, 5, 10];
    for (const s of steps) if (s * pow >= raw) return s * pow;
    return 10 * pow;
  }
  function pixelChart(node, spec, series) {
    const rows = parseInt(node.dataset.rows || '12', 10);
    const cols = spec.cols;
    const max = Math.max(...cols.map(c => c.a + c.b));
    const unit = niceUnit(max, rows);
    node.textContent = '';
    node.style.setProperty('--cols', cols.length);
    node.style.setProperty('--rows', rows);
    node.style.setProperty('--groups', Math.ceil(cols.length / spec.group));
    node.style.position = 'relative';

    const y = el('div', 'pc-y');
    [rows, Math.round(rows * 2 / 3), Math.round(rows / 3), 0].forEach(k => y.appendChild(el('span', null, axisFmt(k * unit, unit * rows))));
    node.appendChild(y);

    const plot = el('div', 'pc-plot');
    plot.tabIndex = 0;
    plot.setAttribute('aria-label', 'Ustunlar bo‘yicha qiymatlar: chap va o‘ng strelkalar bilan harakatlaning');
    const colEls = [];
    cols.forEach((c, idx) => {
      const col = el('div', 'pc-col');
      col.tabIndex = -1;
      const na = c.a ? Math.max(1, Math.round(c.a / unit)) : 0;
      let no = c.o ? Math.round(c.o / unit) : 0;
      if (c.o && !no && c.o >= unit * 0.35) no = 1;
      const nt = c.a + c.b ? Math.max(na + no + (c.b > (c.o || 0) ? 1 : 0), Math.round((c.a + c.b) / unit)) : 0;
      for (let r = rows - 1; r >= 0; r--) {
        const i = document.createElement('i');
        if (r < na) i.className = c.c ? 'c' : 'a';
        else if (r < na + no) i.className = 'c';
        else if (r < Math.min(nt, rows)) i.className = 'b';
        col.appendChild(i);
      }
      const vals = [c.a, c.b, c.o || 0];
      const label = c.future ? c.t + ': ma’lumot yo‘q' : c.t + ': ' + series.map((s, k) => s + ' ' + fmt(vals[k])).join(', ');
      col.setAttribute('aria-label', label);
      col.dataset.idx = idx;
      plot.appendChild(col);
      colEls.push(col);
    });
    node.appendChild(plot);

    const x = el('div', 'pc-x');
    spec.labels.forEach((l, i) => { const s = el('span', null, l); if (i === spec.now) s.className = 'is-now'; x.appendChild(s); });
    node.appendChild(x);

    const tip = el('div', 'viz-tip'); tip.setAttribute('aria-hidden', 'true');
    node.appendChild(tip);
    const dense = () => {
      const spans = Array.from(x.children); if (!spans.length) return;
      x.classList.remove('is-dense');
      const need = Math.max(...spans.map(s => s.scrollWidth));
      x.classList.toggle('is-dense', need + 6 > x.clientWidth / spans.length);
    };
    requestAnimationFrame(dense);
    if (window.ResizeObserver) { if (node._ro) node._ro.disconnect(); node._ro = new ResizeObserver(dense); node._ro.observe(node); }

    function show(col) {
      const c = cols[+col.dataset.idx];
      tip.textContent = '';
      tip.appendChild(el('div', 'viz-tip-title', c.t));
      if (c.future) tip.appendChild(el('div', 'muted', 'Ma’lumot yo‘q'));
      else series.forEach((s, k) => {
        const row = el('div', 'viz-tip-row');
        const key = el('span', 'viz-key'); if (k === 1) key.dataset.k = '2'; if (k === 2 || c.c) key.dataset.k = 'critical';
        row.append(key, el('b', null, fmt([c.a, c.b, c.o || 0][k])), el('span', null, s));
        tip.appendChild(row);
      });
      tip.classList.add('is-on');
      const nb = node.getBoundingClientRect(), cb = col.getBoundingClientRect();
      const tw = tip.offsetWidth, th = tip.offsetHeight;
      let left = cb.left - nb.left + cb.width / 2 - tw / 2;
      left = Math.max(0, Math.min(nb.width - tw, left));
      const firstFilled = col.querySelector('i.a, i.b, i.c');
      const topRef = firstFilled ? firstFilled.getBoundingClientRect().top : cb.bottom - 20;
      let top = topRef - nb.top - th - 10;
      if (top < -th / 2) top = 0;
      tip.style.left = left + 'px'; tip.style.top = top + 'px';
    }
    function hide() { tip.classList.remove('is-on'); }
    colEls.forEach(col => {
      col.addEventListener('pointerenter', () => show(col));
      col.addEventListener('focus', () => { plot.classList.add('has-focus'); show(col); });
      col.addEventListener('blur', () => { plot.classList.remove('has-focus'); hide(); });
    });
    plot.addEventListener('pointerleave', hide);
    plot.addEventListener('focus', () => { const last = [...colEls].reverse().find(c => !cols[+c.dataset.idx].future) || colEls[0]; last.focus(); });
    plot.addEventListener('keydown', e => {
      const cur = document.activeElement.closest('.pc-col'); if (!cur) return;
      let i = +cur.dataset.idx;
      if (e.key === 'ArrowRight') i = Math.min(colEls.length - 1, i + 1);
      else if (e.key === 'ArrowLeft') i = Math.max(0, i - 1);
      else if (e.key === 'Escape') { plot.focus(); hide(); return; }
      else return;
      e.preventDefault(); colEls[i].focus();
    });
    return { max, total: cols.reduce((s, c) => s + c.a + c.b, 0) };
  }
  function chartTable(spec, series) {
    const wrap = el('div', 'table-wrap'); wrap.style.maxHeight = '300px'; wrap.style.overflow = 'auto';
    wrap.style.border = '1px solid var(--line)'; wrap.style.borderRadius = '12px';
    const t = el('table', 'table table-compact');
    const thr = el('tr'); ['Davr', ...series, 'Jami'].forEach((h, i) => { const th = el('th', i ? 'num' : null, h); thr.appendChild(th); });
    const thead = el('thead'); thead.appendChild(thr); t.appendChild(thead);
    const tb = el('tbody');
    spec.cols.filter(c => !c.future).forEach(c => {
      const tr = el('tr');
      tr.append(el('td', null, c.t), el('td', 'num td-num', fmt(c.a)));
      if (series.length > 1) tr.appendChild(el('td', 'num td-num', fmt(c.b)));
      if (series.length > 2) tr.appendChild(el('td', 'num td-num', fmt(c.o || 0)));
      tr.appendChild(el('td', 'num td-num', fmt(c.a + c.b)));
      tb.appendChild(tr);
    });
    t.appendChild(tb); wrap.appendChild(t);
    return wrap;
  }
  function chartStats(set) {
    const cols = DATA.appeals[set].cols.filter(c => !c.future);
    const peak = cols.reduce((m, c) => (c.a + c.b > m.a + m.b ? c : m), cols[0]);
    const sum = cols.reduce((s, c) => s + c.a + c.b, 0), open = cols.reduce((s, c) => s + c.b, 0);
    const put = (k, v) => { const n = document.querySelector('[data-stat="' + k + '"]'); if (n) n.textContent = v; };
    put('peak', fmt(peak.a + peak.b)); put('peak-at', peak.t);
    put('avg', fmt(sum / cols.length)); put('avg-per', { decade: 'dekadasiga', week: 'haftasiga', month: 'oyiga' }[set]);
    put('open', fmt(open / sum * 100, 1));
  }
  function initPixelCharts() {
    $$('.pixel-chart[data-chart]').forEach(node => {
      const key = node.dataset.chart;
      if (key === 'appeals') {
        const set = node.dataset.set || 'decade';
        pixelChart(node, DATA.appeals[set], DATA.appeals.series);
      } else if (DATA[key]) pixelChart(node, DATA[key], DATA[key].series);
    });
    // dataset switchers
    $$('[data-dataset]').forEach(group => {
      const target = document.getElementById(group.dataset.dataset);
      group.addEventListener('click', e => {
        const b = e.target.closest('button[data-set]'); if (!b || !target) return;
        target.dataset.set = b.dataset.set;
        const res = pixelChart(target, DATA.appeals[b.dataset.set], DATA.appeals.series);
        const tot = document.querySelector('[data-total="' + target.id + '"]');
        if (tot) tot.textContent = fmt(res.total);
        chartStats(b.dataset.set);
        const tbl = document.getElementById(target.id + '-table');
        if (tbl && !tbl.hidden) { tbl.textContent = ''; tbl.appendChild(chartTable(DATA.appeals[b.dataset.set], DATA.appeals.series)); }
      });
    });
    // chart/table view toggles
    $$('[data-view-toggle]').forEach(group => {
      const chart = document.getElementById(group.dataset.viewToggle);
      const tbl = document.getElementById(group.dataset.viewToggle + '-table');
      group.addEventListener('click', e => {
        const b = e.target.closest('button'); if (!b || !chart || !tbl) return;
        const toTable = b === group.children[1];
        chart.hidden = toTable; tbl.hidden = !toTable;
        if (toTable) { tbl.textContent = ''; tbl.appendChild(chartTable(DATA.appeals[chart.dataset.set || 'decade'], DATA.appeals.series)); }
      });
    });
    const t = document.querySelector('[data-total="chartA"]');
    if (t) t.textContent = fmt(DATA.appeals.decade.cols.reduce((s, c) => s + c.a + c.b, 0));
    chartStats('decade');
  }

  /* ---------- Heat grid ---------------------------------------------------- */
  const REGIONS = [
    { n: 'Qoraqalpog‘iston', code: 'QQR', base: 89.5, trend: 0, dens: 18, pos: [1, 1] },
    { n: 'Xorazm', code: 'XOR', base: 91.5, trend: -0.55, dens: 44, pos: [1, 2] },
    { n: 'Navoiy', code: 'NAV', base: 97, trend: 0.05, dens: 14, pos: [2, 1] },
    { n: 'Buxoro', code: 'BUX', base: 92, trend: 0.1, dens: 26, pos: [2, 2] },
    { n: 'Samarqand', code: 'SAM', base: 93, trend: 0.1, dens: 33, pos: [3, 2] },
    { n: 'Qashqadaryo', code: 'QAS', base: 89.5, trend: -0.2, dens: 31, pos: [3, 3] },
    { n: 'Surxondaryo', code: 'SUR', base: 88, trend: -0.1, dens: 28, pos: [4, 3] },
    { n: 'Jizzax', code: 'JIZ', base: 88.6, trend: -0.05, dens: 24, pos: [3, 1] },
    { n: 'Sirdaryo', code: 'SIR', base: 90, trend: 0.05, dens: 22, pos: [4, 2] },
    { n: 'Toshkent v.', code: 'TSV', base: 92, trend: 0.1, dens: 29, pos: [4, 1] },
    { n: 'Toshkent sh.', code: 'TSH', base: 95, trend: 0.1, dens: 48, pos: [5, 1] },
    { n: 'Namangan', code: 'NAM', base: 91, trend: 0, dens: 35, pos: [6, 1] },
    { n: 'Andijon', code: 'AND', base: 92, trend: 0.05, dens: 41, pos: [7, 1] },
    { n: 'Farg‘ona', code: 'FAR', base: 90, trend: -0.15, dens: 39, pos: [6, 2] }
  ];
  function slaBucket(v) {
    if (v == null) return null;
    if (v < 75) return 'critical';
    if (v < 85) return 'warning';
    if (v < 88) return '1';
    if (v < 91) return '2';
    if (v < 94) return '3';
    if (v < 97) return '4';
    return '5';
  }
  function heatGrid(node) {
    const r = rng(77);
    node.textContent = '';
    node.style.setProperty('--cols', 12);
    node.appendChild(el('span'));
    MONTHS.forEach(m => node.appendChild(el('span', 'hg-head', m)));
    const tip = el('div', 'viz-tip'); tip.setAttribute('aria-hidden', 'true');
    REGIONS.forEach(reg => {
      node.appendChild(el('span', 'hg-row', reg.n));
      for (let m = 0; m < 12; m++) {
        const cell = el('span', 'hg-cell');
        let v = null;
        if (m < 11) {
          v = reg.base + reg.trend * m + (r() - 0.5) * 3.2;
          if (reg.code === 'XOR' && m >= 9) v = [76.4, 71.2][m - 9];
          if (reg.code === 'SUR' && m === 6) v = 79.8;
          if (reg.code === 'QAS' && m === 10) v = 82.5;
          v = Math.min(99.6, v);
        }
        const b = slaBucket(v);
        if (b) cell.dataset.s = b;
        const label = reg.n + ' · ' + MONTHS_FULL[m] + ': ' + (v == null ? 'ma’lumot yo‘q' : fmt(v, 1) + '%');
        cell.setAttribute('aria-label', label);
        cell.addEventListener('pointerenter', () => {
          tip.textContent = '';
          tip.appendChild(el('div', 'viz-tip-title', reg.n + ' · ' + MONTHS[m]));
          const row = el('div', 'viz-tip-row');
          const key = el('span', 'viz-key'); if (b === 'critical' || b === 'warning') key.dataset.k = b;
          row.append(key, el('b', null, v == null ? '—' : fmt(v, 1) + '%'), el('span', null, b === 'critical' ? 'SLA buzilgan' : b === 'warning' ? 'Xavf ostida' : 'SLA bajarilishi'));
          tip.appendChild(row);
          tip.classList.add('is-on');
          const nb = node.getBoundingClientRect(), cb = cell.getBoundingClientRect();
          let left = cb.left - nb.left + cb.width / 2 - tip.offsetWidth / 2;
          left = Math.max(0, Math.min(nb.width - tip.offsetWidth, left));
          tip.style.left = left + 'px'; tip.style.top = (cb.top - nb.top - tip.offsetHeight - 8) + 'px';
        });
        node.appendChild(cell);
      }
    });
    node.addEventListener('pointerleave', () => tip.classList.remove('is-on'));
    node.appendChild(tip);
  }

  /* ---------- Hour grid (day × 2-hour block) -------------------------------- */
  function hourGrid(node) {
    const r = rng(9);
    const days = ['Du', 'Se', 'Ch', 'Pa', 'Ju', 'Sh', 'Ya'];
    const dayFull = ['Dushanba', 'Seshanba', 'Chorshanba', 'Payshanba', 'Juma', 'Shanba', 'Yakshanba'];
    const hours = ['00', '02', '04', '06', '08', '10', '12', '14', '16', '18', '20', '22'];
    const shape = [4, 2, 1, 6, 62, 88, 70, 74, 66, 41, 22, 10];
    const dayK = [1.18, 1.02, 0.98, 0.96, 0.9, 0.38, 0.22];
    node.textContent = '';
    node.style.setProperty('--cols', 12);
    node.appendChild(el('span'));
    hours.forEach((h, i) => node.appendChild(el('span', 'hg-head', i % 2 === 0 ? h : '')));
    const tip = el('div', 'viz-tip'); tip.setAttribute('aria-hidden', 'true');
    days.forEach((d, di) => {
      node.appendChild(el('span', 'hg-row', d));
      hours.forEach((h, hi) => {
        const v = Math.round(shape[hi] * dayK[di] * (0.9 + r() * 0.2) * 4.6);
        const b = v < 30 ? null : v < 110 ? '1' : v < 190 ? '2' : v < 270 ? '3' : v < 350 ? '4' : '5';
        const c = el('span', 'hg-cell'); c.style.aspectRatio = '1';
        if (b) c.dataset.s = b;
        const h2 = String(+h + 2).padStart(2, '0');
        c.setAttribute('aria-label', dayFull[di] + ', ' + h + ':00–' + h2 + ':00: ' + v + ' ta');
        c.addEventListener('pointerenter', () => {
          tip.textContent = '';
          tip.appendChild(el('div', 'viz-tip-title', d + ' · ' + h + '–' + h2));
          const row = el('div', 'viz-tip-row'); row.append(el('span', 'viz-key'), el('b', null, fmt(v)), el('span', null, 'murojaat'));
          tip.appendChild(row); tip.classList.add('is-on');
          const nb = node.getBoundingClientRect(), cb = c.getBoundingClientRect();
          let left = cb.left - nb.left + cb.width / 2 - tip.offsetWidth / 2;
          left = Math.max(0, Math.min(nb.width - tip.offsetWidth, left));
          tip.style.left = left + 'px'; tip.style.top = (cb.top - nb.top - tip.offsetHeight - 8) + 'px';
        });
        node.appendChild(c);
      });
    });
    node.addEventListener('pointerleave', () => tip.classList.remove('is-on'));
    node.appendChild(tip);
  }

  /* ---------- Tile cartogram ------------------------------------------------ */
  function densBucket(d) { return d < 19 ? '1' : d < 26 ? '2' : d < 33 ? '3' : d < 40 ? '4' : '5'; }
  function cartogram(node, opts = {}) {
    node.textContent = '';
    node.style.gridTemplateRows = 'repeat(3, auto)';
    const tip = el('div', 'viz-tip'); tip.setAttribute('aria-hidden', 'true');
    REGIONS.forEach(reg => {
      const t = el('button', 'ct-tile');
      t.type = 'button';
      t.style.gridColumn = reg.pos[0];
      t.style.gridRow = reg.pos[1];
      t.dataset.s = densBucket(reg.dens);
      if (opts.focus) {
        if (!opts.focus.includes(reg.code)) t.classList.add('is-dim');
        else t.dataset.flag = 'critical';
      } else if (reg.code === 'XOR') t.dataset.flag = 'critical';
      t.appendChild(el('span', null, reg.code));
      t.appendChild(el('b', null, String(reg.dens)));
      t.setAttribute('aria-label', reg.n + ': 10 000 aholiga ' + reg.dens + ' ta murojaat');
      const show = () => {
        tip.textContent = '';
        tip.appendChild(el('div', 'viz-tip-title', reg.n));
        const row = el('div', 'viz-tip-row'); row.append(el('span', 'viz-key'), el('b', null, String(reg.dens)), el('span', null, '10 000 aholiga'));
        tip.appendChild(row);
        tip.classList.add('is-on');
        const nb = node.getBoundingClientRect(), cb = t.getBoundingClientRect();
        let left = cb.left - nb.left + cb.width / 2 - tip.offsetWidth / 2;
        left = Math.max(0, Math.min(nb.width - tip.offsetWidth, left));
        tip.style.left = left + 'px'; tip.style.top = (cb.top - nb.top - tip.offsetHeight - 8) + 'px';
      };
      t.addEventListener('pointerenter', show);
      t.addEventListener('focus', show);
      t.addEventListener('blur', () => tip.classList.remove('is-on'));
      node.appendChild(t);
    });
    node.addEventListener('pointerleave', () => tip.classList.remove('is-on'));
    node.appendChild(tip);
  }

  /* ---------- Uptime strips ------------------------------------------------- */
  function uptime(node) {
    const marks = {};
    (node.dataset.uptime || '').split(',').filter(Boolean).forEach(tok => { marks[parseInt(tok.slice(1), 10)] = tok[0]; });
    node.textContent = '';
    node.setAttribute('role', 'img');
    for (let d = 1; d <= 30; d++) {
      const s = document.createElement('span');
      const k = marks[d];
      if (k) s.className = k;
      s.title = (d) + '-kun: ' + (k === 'c' ? 'uzilish' : k === 'w' ? 'sekinlashuv' : k === 'n' ? 'ma’lumot yo‘q' : 'normal');
      node.appendChild(s);
    }
  }

  /* ---------- Calendar ------------------------------------------------------ */
  function calendar(node) {
    node.textContent = '';
    ['Du', 'Se', 'Ch', 'Pa', 'Ju', 'Sh', 'Ya'].forEach(d => node.appendChild(el('span', 'cal-h', d)));
    // November 2026 starts on Sunday -> 6 leading days from October (26–31).
    const days = [];
    for (let d = 26; d <= 31; d++) days.push({ d, out: true });
    for (let d = 1; d <= 30; d++) days.push({ d });
    let n = 1; while (days.length % 7) days.push({ d: n++, out: true });
    const marks = { 6: 'ink', 13: 'ink', 21: 'critical', 24: 'ink', 28: 'critical' };
    days.forEach(x => {
      const b = el('button', 'cal-d', String(x.d)); b.type = 'button';
      if (x.out) { b.classList.add('is-out'); b.tabIndex = -1; }
      else {
        if (x.d === 21) { b.classList.add('is-today'); b.setAttribute('aria-current', 'date'); }
        if (x.d === 24) b.classList.add('is-sel');
        if (marks[x.d]) b.dataset.mark = marks[x.d];
        b.setAttribute('aria-label', x.d + '-noyabr' + (marks[x.d] ? ', muddat bor' : ''));
      }
      node.appendChild(b);
    });
  }

  /* ---------- Forecast line chart ----------------------------------------- */
  function forecast(node) {
    const actual = [10420, 10980, 11650, 11240, 11820, 12410, 12100, 11760, 12350, 11980, 12480];
    const fc = [{ v: 13900, lo: 13300, hi: 14500 }, { v: 13350, lo: 12550, hi: 14150 }, { v: 12900, lo: 11950, hi: 13850 }];
    const labels = [...MONTHS.slice(0, 11), 'Dek', 'Yan', 'Fev'];
    const W = 320, H = 150, pl = 34, pr = 8, pt = 10, pb = 22;
    const n = actual.length + fc.length;
    const min = 9500, max = 15000;
    const X = i => pl + (i / (n - 1)) * (W - pl - pr);
    const Y = v => pt + (1 - (v - min) / (max - min)) * (H - pt - pb);
    node.textContent = '';
    const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'xMidYMid meet' });
    const g = svgEl('g', { class: 'grid' }); const ax = svgEl('g', { class: 'axis' });
    [10000, 12000, 14000].forEach(v => {
      g.appendChild(svgEl('line', { x1: pl, x2: W - pr, y1: Y(v), y2: Y(v) }));
      const t = svgEl('text', { x: pl - 6, y: Y(v) + 3, 'text-anchor': 'end' }); t.textContent = (v / 1000) + 'K'; ax.appendChild(t);
    });
    labels.forEach((l, i) => { if (i % 2 === 0) { const t = svgEl('text', { x: X(i), y: H - 6, 'text-anchor': 'middle' }); t.textContent = l; ax.appendChild(t); } });
    svg.append(g, ax);
    const last = actual.length - 1;
    // divider at "now"
    svg.appendChild(svgEl('line', { class: 'divider-line', x1: X(last), x2: X(last), y1: pt, y2: H - pb }));
    const nl = svgEl('text', { class: 'now-label', x: X(last) + 4, y: pt + 8 }); nl.textContent = 'bugun'; svg.appendChild(nl);
    // band
    let band = `M${X(last)},${Y(actual[last])}`;
    fc.forEach((f, i) => { band += ` L${X(last + 1 + i)},${Y(f.hi)}`; });
    for (let i = fc.length - 1; i >= 0; i--) band += ` L${X(last + 1 + i)},${Y(fc[i].lo)}`;
    band += ' Z';
    svg.appendChild(svgEl('path', { class: 'band', d: band }));
    // area + lines
    let line = ''; actual.forEach((v, i) => { line += (i ? ' L' : 'M') + X(i) + ',' + Y(v); });
    svg.appendChild(svgEl('path', { class: 'area', d: line + ` L${X(last)},${H - pb} L${X(0)},${H - pb} Z` }));
    svg.appendChild(svgEl('path', { class: 'line-actual', d: line }));
    let fl = `M${X(last)},${Y(actual[last])}`; fc.forEach((f, i) => { fl += ` L${X(last + 1 + i)},${Y(f.v)}`; });
    svg.appendChild(svgEl('path', { class: 'line-fc', d: fl }));
    svg.appendChild(svgEl('circle', { class: 'pt', cx: X(last), cy: Y(actual[last]), r: 4.5 }));
    svg.appendChild(svgEl('circle', { class: 'pt-fc', cx: X(last + 1), cy: Y(fc[0].v), r: 4 }));
    const xh = svgEl('line', { class: 'xhair', x1: 0, x2: 0, y1: pt, y2: H - pb });
    const hp = svgEl('circle', { class: 'pt', cx: -10, cy: -10, r: 4, style: 'opacity:0' });
    svg.append(xh, hp);
    const hit = svgEl('rect', { class: 'hit', x: pl, y: 0, width: W - pl - pr, height: H - pb });
    svg.appendChild(hit);
    node.appendChild(svg);
    const tip = el('div', 'viz-tip'); tip.setAttribute('aria-hidden', 'true'); node.appendChild(tip);
    function at(i) {
      const isFc = i > last; const v = isFc ? fc[i - last - 1].v : actual[i];
      xh.setAttribute('x1', X(i)); xh.setAttribute('x2', X(i));
      hp.setAttribute('cx', X(i)); hp.setAttribute('cy', Y(v)); hp.style.opacity = 1;
      hp.setAttribute('class', isFc ? 'pt-fc' : 'pt');
      node.classList.add('is-hover');
      tip.textContent = '';
      tip.appendChild(el('div', 'viz-tip-title', labels[i] + (isFc ? ' · prognoz' : '')));
      const row = el('div', 'viz-tip-row'); const key = el('span', 'viz-key'); if (isFc) key.style.background = 'var(--ink-3)';
      row.append(key, el('b', null, fmt(v)), el('span', null, isFc ? '±' + fmt((fc[i - last - 1].hi - fc[i - last - 1].v)) : 'murojaat'));
      tip.appendChild(row); tip.classList.add('is-on');
      const sx = node.getBoundingClientRect().width / W;
      let left = X(i) * sx - tip.offsetWidth / 2; left = Math.max(0, Math.min(node.getBoundingClientRect().width - tip.offsetWidth, left));
      tip.style.left = left + 'px'; tip.style.top = (Y(v) * sx - tip.offsetHeight - 12) + 'px';
    }
    hit.addEventListener('pointermove', e => {
      const b = svg.getBoundingClientRect(); const x = (e.clientX - b.left) / b.width * W;
      at(Math.max(0, Math.min(n - 1, Math.round((x - pl) / (W - pl - pr) * (n - 1)))));
    });
    hit.addEventListener('pointerleave', () => { node.classList.remove('is-hover'); hp.style.opacity = 0; tip.classList.remove('is-on'); });
  }

  /* ---------- Foundations: swatches + icons -------------------------------- */
  function readVar(v) { return getComputedStyle(document.documentElement).getPropertyValue('--' + v).trim(); }
  function renderSwatches() {
    $$('[data-swatches]').forEach(box => {
      box.textContent = '';
      box.dataset.swatches.split(',').forEach(pair => {
        const [v, name] = pair.split(':');
        const b = el('button', 'swatch'); b.type = 'button';
        const chip = el('span', 'swatch-chip'); chip.style.background = 'var(--' + v + ')';
        const meta = el('span', 'swatch-meta');
        meta.append(el('span', 'swatch-name', name), el('span', 'swatch-var', '--' + v), el('span', 'swatch-var', readVar(v).toUpperCase()));
        b.append(chip, meta);
        b.setAttribute('aria-label', 'Nusxa olish: var(--' + v + ')');
        b.addEventListener('click', () => copy('var(--' + v + ')', 'Token nusxalandi'));
        box.appendChild(b);
      });
    });
  }
  function renderIcons() {
    const grid = $('#iconGrid'); if (!grid) return;
    const ids = $$('symbol[id^="i-"]').map(s => s.id.slice(2)).sort();
    ids.forEach(id => {
      const b = el('button', 'icon-cell'); b.type = 'button'; b.title = id;
      b.append(icon(id), el('span', null, id));
      b.addEventListener('click', () => copy('<svg class="icon"><use href="#i-' + id + '"/></svg>', 'Ikon kodi nusxalandi'));
      grid.appendChild(b);
    });
  }

  /* ---------- Generic toggles --------------------------------------------- */
  function initToggles() {
    document.addEventListener('click', e => {
      const seg = e.target.closest('[data-toggle-group] > button, [data-dataset] > button, [data-view-toggle] > button');
      if (seg) $$(':scope > button', seg.parentElement).forEach(b => b.setAttribute('aria-pressed', String(b === seg)));
      const tab = e.target.closest('[data-tab-group] > [role="tab"]');
      if (tab) $$(':scope > [role="tab"]', tab.parentElement).forEach(b => b.setAttribute('aria-selected', String(b === tab)));
      const press = e.target.closest('[data-press]');
      if (press) {
        const on = press.getAttribute('aria-pressed') !== 'true';
        press.setAttribute('aria-pressed', String(on));
        // thumbs up/down are mutually exclusive inside one action row
        if (on && press.parentElement.classList.contains('msg-actions')) $$('[data-press]', press.parentElement).forEach(b => { if (b !== press) b.setAttribute('aria-pressed', 'false'); });
      }
      const cm = e.target.closest('[data-copy-msg]');
      if (cm) { const t = cm.closest('.msg-main').querySelector('.msg-text'); if (t) copy(t.innerText.trim(), 'Javob nusxalandi'); }
    });
    $$('[data-indeterminate]').forEach(c => { c.indeterminate = true; });
    // keyboard for tabs
    $$('[data-tab-group]').forEach(g => g.addEventListener('keydown', e => {
      if (!['ArrowLeft', 'ArrowRight'].includes(e.key)) return;
      const tabs = $$(':scope > [role="tab"]', g); const i = tabs.indexOf(document.activeElement); if (i < 0) return;
      const n = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length]; n.focus(); n.click(); e.preventDefault();
    }));
  }

  /* ---------- Appeals table selection ------------------------------------- */
  function initTable() {
    const table = $('#appealsTable'); if (!table) return;
    const bar = $('#bulkbar'); const all = $('[data-check-all]', table);
    const rows = $$('tbody tr', table);
    function sync() {
      const sel = rows.filter(r => $('.check', r).checked);
      rows.forEach(r => r.setAttribute('aria-selected', String($('.check', r).checked)));
      $('[data-sel-count]', bar).textContent = sel.length;
      bar.style.visibility = sel.length ? 'visible' : 'hidden';
      all.checked = sel.length === rows.length; all.indeterminate = sel.length > 0 && sel.length < rows.length;
    }
    table.addEventListener('change', e => {
      if (e.target === all) rows.forEach(r => { $('.check', r).checked = all.checked; });
      sync();
    });
    $('[data-clear-sel]', bar).addEventListener('click', () => { rows.forEach(r => { $('.check', r).checked = false; }); sync(); });
    sync();
  }

  /* ---------- Row menu (popover) ------------------------------------------ */
  function initMenus() {
    let open = null;
    function close() { if (open) { open.menu.remove(); open.btn.setAttribute('aria-expanded', 'false'); open = null; } }
    document.addEventListener('click', e => {
      const btn = e.target.closest('[data-menu]');
      if (!btn) { if (open && !open.menu.contains(e.target)) close(); return; }
      e.stopPropagation();
      if (open && open.btn === btn) { close(); return; }
      close();
      const m = el('div', 'menu'); m.setAttribute('role', 'menu');
      m.style.position = 'fixed'; m.style.zIndex = 60; m.style.minWidth = '220px';
      const items = [['pencil', 'Tahrirlash', 'E'], ['user-plus', 'Qayta tayinlash', 'A'], ['corner-up-right', 'Eskalatsiya'], ['ai', 'AI bilan tahlil'], ['sep'], ['trash-2', 'Arxivlash', null, true]];
      items.forEach(([ic, label, kbd, danger]) => {
        if (ic === 'sep') { m.appendChild(el('div', 'menu-sep')); return; }
        const it = el('button', 'menu-item' + (danger ? ' is-danger' : '')); it.setAttribute('role', 'menuitem');
        if (ic === 'ai') { const mx = el('span', 'mz-matrix'); mx.style.setProperty('--s', '16px'); hydrateMatrix(mx); it.appendChild(mx); }
        else it.appendChild(icon(ic));
        it.appendChild(document.createTextNode(label));
        if (kbd) it.appendChild(el('span', 'kbd', kbd));
        it.addEventListener('click', () => { close(); toast(label, btn.closest('tr') ? btn.closest('tr').querySelector('.td-id').textContent : null); });
        m.appendChild(it);
      });
      document.body.appendChild(m);
      const r = btn.getBoundingClientRect();
      const left = Math.min(window.innerWidth - m.offsetWidth - 12, r.right - m.offsetWidth);
      let top = r.bottom + 6; if (top + m.offsetHeight > window.innerHeight - 12) top = r.top - m.offsetHeight - 6;
      m.style.left = left + 'px'; m.style.top = top + 'px';
      btn.setAttribute('aria-expanded', 'true');
      open = { menu: m, btn };
      m.querySelector('.menu-item').focus();
      m.addEventListener('keydown', ev => {
        const its = $$('.menu-item', m); const i = its.indexOf(document.activeElement);
        if (ev.key === 'ArrowDown') { its[(i + 1) % its.length].focus(); ev.preventDefault(); }
        if (ev.key === 'ArrowUp') { its[(i - 1 + its.length) % its.length].focus(); ev.preventDefault(); }
        if (ev.key === 'Escape') { close(); btn.focus(); }
      });
    });
    window.addEventListener('scroll', close, { passive: true });
    window.addEventListener('resize', close);
  }

  /* ---------- Action widget (human-in-the-loop) ---------------------------- */
  function bindAction(w) {
    const btns = $('[data-action-buttons]', w), done = $('[data-action-done]', w), state = $('[data-action-state]', w);
    const set = ok => {
      btns.hidden = ok; done.hidden = !ok;
      state.className = ok ? 'badge' : 'badge badge-outline';
      if (ok) state.dataset.tone = 'good'; else delete state.dataset.tone;
      state.textContent = ok ? 'Bajarildi' : 'Tasdiq kutilmoqda';
    };
    $('[data-action-confirm]', w).addEventListener('click', () => { set(true); toast('18 ta murojaat qayta tayinlandi', 'Xorazm suv ta’minoti · jurnalga yozildi', () => set(false)); });
    const u = $('[data-action-undo]', w); if (u) u.addEventListener('click', () => set(false));
  }

  /* ---------- AI demo (example screen) ------------------------------------- */
  const REPLIES = [
    { k: /solishtir|andijon/i, tpl: 'tpl-compare', steps: ['2 hudud ko‘rsatkichlari olindi', 'SLA va muddatlar solishtirildi'],
      html: 'Andijon SLA bo‘yicha oldinda: <b>92,4%</b>, Farg‘onada esa 88,7% <a class="cite" href="#w-sources">1</a>. Farg‘ona murojaatlarni tezroq yopmoqda: o‘rtacha <b>3,1 kun</b> <a class="cite" href="#w-sources">2</a>.' },
    { k: /tayinla/i, tpl: 'tpl-action', steps: ['Muddati o‘tgan murojaatlar saralandi', 'Mas’ul bo‘lim aniqlandi'],
      html: 'Xorazmda <b>18 ta</b> muddati o‘tgan murojaat ichimlik suvi mavzusida. Ularni suv ta’minoti bo‘limiga o‘tkazishni taklif qilaman. Siz tasdiqlamaguningizcha hech narsa o‘zgarmaydi.' },
    { k: /.*/, tpl: 'tpl-kpi', steps: ['Murojaatlar reestridan so‘rov', 'Ko‘rsatkichlar hisoblandi'],
      html: 'Noyabr (1–21) bo‘yicha asosiy ko‘rsatkichlar. O‘sish asosan Xorazm hisobiga <a class="cite" href="#w-sources">1</a>.' }
  ];
  function initAIDemo() {
    const panel = $('[data-ai-demo]'); if (!panel) return;
    const log = $('[data-ai-log]', panel);
    const form = $('[data-composer]', panel);
    const input = $('.composer-input', form);
    const send = $('.send', form);
    const headMark = $('.ai-head .mz-matrix', panel);
    let busy = false;

    const sync = () => { send.disabled = busy ? false : !input.value.trim(); };
    input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = Math.min(160, input.scrollHeight) + 'px'; sync(); });
    input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (input.value.trim()) form.requestSubmit(); } });
    form.addEventListener('submit', e => { e.preventDefault(); if (busy) return; const q = input.value.trim(); if (!q) return; input.value = ''; input.style.height = ''; ask(q); });

    function scrollDown() { log.scrollTo({ top: log.scrollHeight, behavior: reduceMotion ? 'auto' : 'smooth' }); }
    function now() { const d = new Date(); return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0'); }

    function ask(q) {
      busy = true; send.classList.add('is-stop'); send.innerHTML = ''; send.appendChild(icon('square')); send.setAttribute('aria-label', 'To‘xtatish'); send.disabled = false;
      headMark.classList.add('is-thinking');
      const u = el('div', 'msg msg-user'); u.appendChild(el('div', 'bubble', q)); log.appendChild(u);
      const reply = REPLIES.find(r => r.k.test(q));
      const m = el('div', 'msg msg-ai');
      const mk = el('span', 'mz-matrix is-thinking'); hydrateMatrix(mk);
      const main = el('div', 'msg-main');
      const meta = el('div', 'msg-meta', 'Mezon AI '); const tm = el('time', null, now()); meta.appendChild(tm);
      const think = el('div', 'thinking'); think.appendChild(document.createTextNode('Ma’lumotlar tahlil qilinmoqda '));
      const timer = el('time', null, '0,0 s'); think.appendChild(timer);
      main.append(meta, think); m.append(mk, main); log.appendChild(m); scrollDown();
      const t0 = performance.now();
      const tick = setInterval(() => { timer.textContent = fmt((performance.now() - t0) / 1000, 1) + ' s'; }, 100);
      setTimeout(() => {
        clearInterval(tick);
        const secs = fmt((performance.now() - t0) / 1000, 1);
        think.remove();
        const tr = el('details', 'trace');
        const sm = el('summary'); const ok = icon('circle-check', 'icon icon-sm'); ok.style.color = 'var(--good)';
        sm.append(ok, document.createTextNode(reply.steps.length + ' qadam '), el('time', null, secs + ' s'), icon('chevron-down', 'icon icon-sm chev'));
        const st = el('div', 'trace-steps');
        reply.steps.forEach(s => { const row = el('div', 'trace-step is-done'); row.append(icon('check'), el('span', null, s)); st.appendChild(row); });
        tr.append(sm, st); main.appendChild(tr);
        const text = el('div', 'msg-text'); const p = el('p'); text.appendChild(p); main.appendChild(text);
        stream(p, reply.html, () => {
          const tpl = document.getElementById(reply.tpl);
          if (tpl) {
            const w = tpl.content.firstElementChild.cloneNode(true);
            main.appendChild(w);
            if (w.matches('[data-action-widget]')) bindAction(w);
          }
          const acts = el('div', 'msg-actions');
          [['copy', 'Nusxa olish', 'data-copy-msg'], ['refresh-cw', 'Qayta yaratish'], ['thumbs-up', 'Foydali', 'data-press'], ['thumbs-down', 'Foydasiz', 'data-press']].forEach(([ic, lab, attr]) => {
            const b = el('button', 'btn btn-ghost btn-icon'); b.setAttribute('aria-label', lab); b.appendChild(icon(ic));
            if (attr) b.setAttribute(attr, ''); if (attr === 'data-press') b.setAttribute('aria-pressed', 'false');
            acts.appendChild(b);
          });
          main.appendChild(acts);
          mk.classList.remove('is-thinking'); headMark.classList.remove('is-thinking');
          busy = false; send.classList.remove('is-stop'); send.innerHTML = ''; send.appendChild(icon('arrow-up')); send.setAttribute('aria-label', 'Yuborish'); sync();
          scrollDown();
        });
      }, reduceMotion ? 200 : 1300);
    }
    function stream(p, html, done) {
      if (reduceMotion) { p.innerHTML = html; done(); return; }
      // stream word by word, then swap in the final markup (citations, bold)
      const tmp = el('div'); tmp.innerHTML = html; const words = tmp.textContent.split(' ');
      const caret = el('span', 'caret'); let i = 0;
      const step = () => {
        p.textContent = words.slice(0, i).join(' ') + ' '; p.appendChild(caret);
        if (i++ < words.length) { setTimeout(step, 26 + Math.random() * 30); if (i % 6 === 0) scrollDown(); }
        else { p.innerHTML = html; done(); }
      };
      step();
    }
    document.addEventListener('click', e => {
      const b = e.target.closest('[data-ask]'); if (!b) return;
      if (busy) return;
      const q = b.dataset.ask;
      if (b.closest('.app')) { ask(q); return; }
      $('.showcase').scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
      setTimeout(() => ask(q), reduceMotion ? 0 : 650);
    });
    sync();
  }

  /* ---------- Composer specimens: auto-grow ------------------------------- */
  function initComposers() {
    $$('.composer:not([data-composer]) .composer-input').forEach(t => {
      const s = t.closest('.composer').querySelector('.send:not(.is-stop)');
      t.addEventListener('input', () => { t.style.height = 'auto'; t.style.height = Math.min(160, t.scrollHeight) + 'px'; if (s) s.disabled = !t.value.trim(); });
    });
  }

  /* ---------- Theme ---------------------------------------------------------- */
  function initTheme() {
    const btn = $('#themeToggle'); if (!btn) return;
    const root = document.documentElement;
    const effective = () => root.dataset.theme || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    const paint = () => {
      const dark = effective() === 'dark';
      $('.theme-moon', btn).style.display = dark ? 'none' : '';
      $('.theme-sun', btn).style.display = dark ? '' : 'none';
      btn.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
      renderSwatches();
    };
    btn.addEventListener('click', () => {
      const next = effective() === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('mezon-theme', next); } catch (e) {}
      paint();
    });
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', paint);
    paint();
  }

  /* ---------- Kit nav: active section ------------------------------------- */
  function initNav() {
    const links = $$('#kitNav a');
    const map = new Map(links.map(a => [a.getAttribute('href').slice(1), a]));
    const io = new IntersectionObserver(entries => {
      entries.forEach(en => {
        if (en.isIntersecting) links.forEach(a => a.setAttribute('aria-current', String(a === map.get(en.target.id))));
      });
    }, { rootMargin: '-45% 0px -50% 0px' });
    map.forEach((a, id) => { const s = document.getElementById(id); if (s) io.observe(s); });
  }

  /* ---------- Boot ------------------------------------------------------------ */
  function boot() {
    $$('.mz-matrix').forEach(hydrateMatrix);
    $$('.tick-spark[data-values]').forEach(tickSpark);
    $$('.tick-meter-row[data-meter]').forEach(tickMeter);
    initPixelCharts();
    const hg = $('#heatgrid'); if (hg) heatGrid(hg);
    const hr = $('#hourgrid'); if (hr) hourGrid(hr);
    const ct = $('#cartogram'); if (ct) cartogram(ct);
    $$('[data-cartogram-mini]').forEach(n => cartogram(n, { focus: ['XOR', 'QAS', 'SUR'] }));
    $$('[data-uptime]').forEach(uptime);
    const cal = $('#cal'); if (cal) calendar(cal);
    $$('[data-forecast]').forEach(forecast);
    renderIcons();
    initToggles();
    initTable();
    initMenus();
    $$('[data-action-widget]').forEach(bindAction);
    initAIDemo();
    initComposers();
    initTheme();
    initNav();
  }

  window.Mezon = { pixelChart, tickSpark, tickMeter, heatGrid, hourGrid, cartogram, forecast, hydrateMatrix, toast, fmt };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
