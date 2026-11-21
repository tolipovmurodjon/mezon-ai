/* Mezon app behaviour. Builds on mezon-ui/kit.js (window.Mezon); no dependencies. */
(function () {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const M = window.Mezon || {};
  const fmt = M.fmt || (n => String(n));

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function icon(name, cls = 'icon') {
    const ns = 'http://www.w3.org/2000/svg';
    const s = document.createElementNS(ns, 'svg'); s.setAttribute('class', cls); s.setAttribute('aria-hidden', 'true');
    const u = document.createElementNS(ns, 'use'); u.setAttribute('href', '#i-' + name); s.appendChild(u);
    return s;
  }
  function hydrate(root) {
    if (M.hydrateMatrix) $$('.mz-matrix', root).forEach(M.hydrateMatrix);
    if (M.tickMeter) $$('.tick-meter-row[data-meter]', root).forEach(M.tickMeter);
  }

  /* ---------- Toasts ---------- */
  function toast(title, error) {
    const host = $('#toastHost'); if (!host) return;
    const t = el('div', 'toast'); t.setAttribute('role', error ? 'alert' : 'status');
    const badge = el('span', error ? 'toast-err' : 'toast-ok'); badge.appendChild(icon(error ? 'x' : 'check'));
    t.append(badge, el('span', 'toast-text', title));
    host.appendChild(t);
    setTimeout(() => t.remove(), 4500);
  }

  /* ---------- Shell: mobile sidebar, theme, filters ---------- */
  function initShell() {
    const shell = $('.shell'), btn = $('[data-side-toggle]'), scrim = $('[data-scrim]');
    const setSide = open => { shell.classList.toggle('is-side-open', open); scrim.hidden = !open; btn.setAttribute('aria-expanded', String(open)); };
    if (shell && btn) {
      btn.addEventListener('click', () => setSide(!shell.classList.contains('is-side-open')));
      scrim.addEventListener('click', () => setSide(false));
    }
    // kit.js binds #themeToggle with English labels; take the node over
    const old = $('#themeToggle');
    if (old) {
      const root = document.documentElement, btnT = old.cloneNode(true); old.replaceWith(btnT);
      const dark = () => (root.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')) === 'dark';
      const paint = () => {
        $('.theme-moon', btnT).style.display = dark() ? 'none' : '';
        $('.theme-sun', btnT).style.display = dark() ? '' : 'none';
        btnT.setAttribute('aria-label', dark() ? 'Kunduzgi rejim' : 'Tungi rejim');
      };
      btnT.addEventListener('click', () => {
        const next = dark() ? 'light' : 'dark';
        root.setAttribute('data-theme', next);
        try { localStorage.setItem('mezon-theme', next); } catch (e) {}
        paint();
      });
      paint();
    }
    $$('select[data-autosubmit]').forEach(s => s.addEventListener('change', () => s.form.submit()));
    const flash = $('#flash');
    if (flash) $$('div', flash.content).forEach(m => toast(m.textContent, m.dataset.level === 'error'));
  }

  /* ---------- Dashboard: daily stacked pixel chart (kit .pixel-chart) ---------- */
  const SERIES = [['a', 'Qabul qilingan', ''], ['c', 'Rad etilgan', 'critical'], ['b', 'Jarayonda', '2']];
  function dailyChart(node, cols) {
    const total = c => c.a + c.b + c.c;
    const max = Math.max(1, ...cols.map(total));
    const unit = [1, 2, 5, 10, 20, 50].find(u => Math.ceil(max / u) <= 14) || 100;
    const rows = Math.max(6, Math.ceil(max / unit));
    node.style.setProperty('--cols', cols.length);
    node.style.setProperty('--rows', rows);
    node.style.setProperty('--groups', cols.length);

    const y = el('div', 'pc-y');
    [rows, Math.round(rows / 2), 0].forEach(k => y.appendChild(el('span', null, fmt(k * unit))));
    const plot = el('div', 'pc-plot');
    const x = el('div', 'pc-x');
    const tip = el('div', 'viz-tip'); tip.setAttribute('aria-hidden', 'true');

    cols.forEach((c, i) => {
      const col = el('div', 'pc-col');
      const n = {};
      SERIES.forEach(([k]) => { n[k] = c[k] ? Math.max(1, Math.round(c[k] / unit)) : 0; });
      for (let r = rows - 1; r >= 0; r--) {
        const px = document.createElement('i');
        px.className = r < n.a ? 'a' : r < n.a + n.c ? 'c' : r < n.a + n.c + n.b ? 'b' : '';
        col.appendChild(px);
      }
      col.addEventListener('pointerenter', () => {
        tip.textContent = '';
        tip.appendChild(el('div', 'viz-tip-title', c.t));
        SERIES.forEach(([k, label, key]) => {
          const row = el('div', 'viz-tip-row'), sw = el('span', 'viz-key');
          if (key) sw.dataset.k = key;
          row.append(sw, el('b', null, fmt(c[k])), el('span', null, label));
          tip.appendChild(row);
        });
        tip.classList.add('is-on');
        const nb = node.getBoundingClientRect(), cb = col.getBoundingClientRect();
        tip.style.left = Math.max(0, Math.min(nb.width - tip.offsetWidth, cb.left - nb.left + cb.width / 2 - tip.offsetWidth / 2)) + 'px';
        const top = (col.querySelector('i.a, i.b, i.c') || col.lastChild).getBoundingClientRect().top;
        tip.style.top = Math.max(0, top - nb.top - tip.offsetHeight - 8) + 'px';
      });
      plot.appendChild(col);
      const fromEnd = cols.length - 1 - i;
      const lab = el('span', fromEnd === 0 ? 'is-now' : null, fromEnd % 7 === 0 ? c.label : '');
      x.appendChild(lab);
    });
    plot.addEventListener('pointerleave', () => tip.classList.remove('is-on'));
    node.append(y, plot, x, tip);
  }

  /* ---------- Streaming: Server-Sent Events over POST ---------- */
  async function stream(url, body, csrf, onEvent) {
    const res = await fetch(url, { method: 'POST', body, credentials: 'same-origin', headers: { 'X-CSRFToken': csrf } });
    if (!res.ok || !res.body) throw new Error(res.status === 403 ? 'Sessiya tugagan. Sahifani yangilang.' : 'Server xatosi (' + res.status + ').');
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf('\n\n')) >= 0) {
        const line = buf.slice(0, i); buf = buf.slice(i + 2);
        if (line.startsWith('data: ')) { try { onEvent(JSON.parse(line.slice(6))); } catch (e) { /* skip bad line */ } }
      }
    }
  }

  /* ---------- Review: AI analysis + follow-up chat ---------- */
  function initReview(root) {
    const log = $('[data-log]', root), form = $('[data-composer]', root);
    const input = $('.composer-input', form), send = $('.send', form);
    const csrf = $('[name=csrfmiddlewaretoken]', form).value;
    const headMark = $('[data-head-mark]', root);
    let busy = false;
    const modelSel = $('[data-model]', root);
    if (modelSel) { try { const v = localStorage.getItem('mezonModel'); if (v) modelSel.value = v; } catch (e) {} modelSel.addEventListener('change', () => { try { localStorage.setItem('mezonModel', modelSel.value); } catch (e) {} }); }

    const down = () => log.scrollTo({ top: log.scrollHeight });
    const sync = () => { send.disabled = busy || !input.value.trim(); };
    const setBusy = b => { busy = b; input.disabled = b; headMark.classList.toggle('is-thinking', b); sync(); };
    input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = Math.min(160, input.scrollHeight) + 'px'; sync(); });
    input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); } });
    form.addEventListener('submit', e => { e.preventDefault(); const q = input.value.trim(); if (q && !busy) { input.value = ''; ask(q); } });

    // writes streamed tokens into a .msg-text, then swaps in the server-rendered HTML
    function writer(main) {
      let box = null, raw = '';
      const caret = el('span', 'caret');
      return {
        token(t) {
          if (!box) { box = el('div', 'msg-text'); box.appendChild(el('p')); main.appendChild(box); }
          raw += t; box.firstChild.textContent = raw; box.firstChild.appendChild(caret); down();
        },
        done(html) { if (!box) { box = el('div', 'msg-text'); main.appendChild(box); } box.innerHTML = html || ''; },
      };
    }
    function errorBox(text, retry, again) {
      const b = el('div', 'msg-error'); b.setAttribute('role', 'alert');
      b.append(icon('circle-alert'), el('span', null, text));
      if (retry) { const r = el('button', 'btn btn-secondary btn-sm', 'Qayta urinish'); r.type = 'button'; if (again) r.onclick = () => { if (!busy) { b.closest('.msg').remove(); ask(again); } }; else r.dataset.reanalyze = ''; b.appendChild(r); }
      return b;
    }

    function analyze() {
      if (busy) return;
      setBusy(true);
      const msg = $('[data-analysis-msg]', log), main = $('[data-analysis-main]', msg);
      const mark = $(':scope > .mz-matrix', msg); mark.classList.add('is-thinking');
      main.textContent = '';
      main.appendChild(el('div', 'msg-meta', 'Mezon AI'));
      const trace = el('details', 'trace'); trace.open = true;
      const sum = el('summary'), spin = el('span', 'spinner'), sumText = el('span', null, 'Hujjatlar tahlil qilinmoqda');
      sum.append(spin, sumText, icon('chevron-down', 'icon icon-sm chev'));
      const steps = el('div', 'trace-steps'); trace.append(sum, steps); main.appendChild(trace);
      const rows = {}; let strip = null, finished = false;
      const out = writer(main);

      function step(ev) {
        let row = rows[ev.id];
        if (!row) { row = el('div', 'trace-step is-run'); row.append(el('span', 'spinner'), el('span')); steps.appendChild(row); rows[ev.id] = row; }
        const label = row.children[1];
        label.textContent = ev.label || '';
        if (ev.detail) label.appendChild(el('span', 'trace-detail', ' · ' + ev.detail));
        if (ev.id === 'checks') { strip = strip || el('span', 'trace-strip'); label.appendChild(strip); }
        if (ev.status && ev.status !== 'run') {
          row.className = 'trace-step ' + (ev.status === 'warn' ? 'is-warn' : 'is-done');
          row.replaceChild(icon(ev.status === 'warn' ? 'triangle-alert' : 'check'), row.firstChild);
        }
        down();
      }
      function fail(text) { finished = true; spin.replaceWith(icon('circle-alert', 'icon icon-sm')); sumText.textContent = 'Tahlil to‘xtadi'; main.appendChild(errorBox(text, true)); }

      stream(root.dataset.analyzeUrl, new FormData(), csrf, ev => {
        if (ev.type === 'step') step(ev);
        else if (ev.type === 'check' && strip) { const px = el('i'); px.dataset.s = ev.status; strip.appendChild(px); }
        else if (ev.type === 'token') out.token(ev.text);
        else if (ev.type === 'error') fail(ev.message);
        else if (ev.type === 'result') {
          finished = true;
          const ok = icon('circle-check', 'icon icon-sm'); ok.style.color = 'var(--good)'; spin.replaceWith(ok);
          sumText.textContent = Object.keys(rows).length + ' qadam';
          trace.open = false;
          out.done(ev.summary_html);
          main.insertAdjacentHTML('beforeend', ev.html || '');
          hydrate(main);
          const rec = $('[data-ai-rec]'); if (rec) rec.innerHTML = ev.decision_html || '';
          const df = $('[data-decision-form]'); if (df) df.dataset.ai = ev.recommendation || '';
        }
      }).catch(e => fail(e.message))
        .finally(() => { if (!finished) fail('Javob to‘liq kelmadi.'); mark.classList.remove('is-thinking'); setBusy(false); });
    }

    function ask(q) {
      setBusy(true);
      const u = el('div', 'msg msg-user'); u.appendChild(el('div', 'bubble', q));
      const m = el('div', 'msg msg-ai'), mk = el('span', 'mz-matrix is-thinking'), main = el('div', 'msg-main');
      if (M.hydrateMatrix) M.hydrateMatrix(mk);
      main.appendChild(el('div', 'msg-meta', 'Mezon AI'));
      m.append(mk, main); log.append(u, m); down();
      const out = writer(main); let finished = false;
      const fd = new FormData(); fd.append('message', q); fd.append('model', modelSel ? modelSel.value : 'qwen');
      let trace = null, steps = null, rows = {}, sumText = null;
      function chatStep(ev) {
        if (!trace) {
          trace = el('details', 'trace'); trace.open = true;
          const sum = el('summary'); sumText = el('span', null, 'Javob tayyorlanmoqda');
          sum.append(el('span', 'spinner'), sumText, icon('chevron-down', 'icon icon-sm chev'));
          steps = el('div', 'trace-steps'); trace.append(sum, steps); main.insertBefore(trace, main.children[1] || null);
        }
        let row = rows[ev.id];
        if (!row) { row = el('div', 'trace-step is-run'); row.append(el('span', 'spinner'), el('span')); steps.appendChild(row); rows[ev.id] = row; }
        const label = row.children[1]; label.textContent = ev.label || '';
        if (ev.detail) label.appendChild(el('span', 'trace-detail', ' · ' + ev.detail));
        if (ev.status && ev.status !== 'run') { row.className = 'trace-step ' + (ev.status === 'warn' ? 'is-warn' : 'is-done'); row.replaceChild(icon(ev.status === 'warn' ? 'triangle-alert' : 'check'), row.firstChild); }
        down();
      }
      stream(root.dataset.chatUrl, fd, csrf, ev => {
        if (ev.type === 'step') chatStep(ev);
        else if (ev.type === 'token') out.token(ev.text);
        else if (ev.type === 'result') {
          finished = true; out.done(ev.html);
          if (trace) { const ok = icon('circle-check', 'icon icon-sm'); ok.style.color = 'var(--good)'; trace.firstChild.firstChild.replaceWith(ok); sumText.textContent = Object.keys(rows).length + ' qadam'; trace.open = false; }
          if (ev.model) main.appendChild(el('div', 'msg-meta model-tag', ev.model));
        }
        else if (ev.type === 'error') { finished = true; main.appendChild(errorBox(ev.message, true, q)); }
      }).catch(e => { finished = true; main.appendChild(errorBox('Internet aloqasi uzildi — qayta urinib ko‘ring', true, q)); })
        .finally(() => { if (!finished) main.appendChild(errorBox('Javob to‘liq kelmadi.')); mk.classList.remove('is-thinking'); setBusy(false); down(); });
    }

    document.addEventListener('click', e => {
      if (!e.target.closest('[data-new-chat]') || busy) return;
      fetch(root.dataset.clearUrl, { method: 'POST', headers: { 'X-CSRFToken': csrf } }).then(() => {
        $$('.msg', log).slice(2).forEach(n => n.remove()); input.focus();
      });
    });
    document.addEventListener('click', e => { if (e.target.closest('[data-reanalyze]')) analyze(); });
    if (root.dataset.autostart === '1') analyze(); else sync();
  }

  /* ---------- Document viewer (opens at a quoted line) ---------- */
  function initDocs() {
    const dlg = $('#docDialog'); if (!dlg) return;
    const body = $('[data-doc-body]', dlg);
    function open(tpl, quote) {
      const text = tpl.content.textContent, at = quote ? text.indexOf(quote) : -1;
      $('[data-doc-title]', dlg).textContent = tpl.dataset.title;
      $('[data-doc-download]', dlg).href = tpl.dataset.download;
      body.textContent = '';
      if (at < 0) body.textContent = text;
      else body.append(text.slice(0, at), el('mark', null, quote), text.slice(at + quote.length));
      dlg.showModal();
      const mark = $('mark', body);
      if (mark) mark.scrollIntoView({ block: 'center' }); else $('.doc-dialog-body', dlg).scrollTop = 0;
    }
    document.addEventListener('click', e => {
      const d = e.target.closest('[data-open-doc]');
      if (d) return open(document.getElementById('doc-' + d.dataset.openDoc));
      const q = e.target.closest('[data-open-quote]');
      if (q) {
        const tpl = $$('template[id^="doc-"]').find(t => t.content.textContent.includes(q.dataset.openQuote));
        if (tpl) open(tpl, q.dataset.openQuote);
      }
    });
  }

  /* ---------- Decision: confirm in a dialog ---------- */
  function initDecision() {
    const form = $('[data-decision-form]'), dlg = $('#decisionDialog');
    if (!form || !dlg) return;
    const comment = form.elements.comment, help = $('[data-comment-help]', form);
    comment.addEventListener('input', () => { help.hidden = true; });
    let outcome = 'accept';
    form.addEventListener('submit', e => {
      if (form.dataset.confirmed) return;
      e.preventDefault();
      outcome = e.submitter ? e.submitter.value : 'accept';
      if (outcome === 'reject' && !comment.value.trim()) { help.hidden = false; comment.focus(); return; }
      const ai = form.dataset.ai;
      const against = (outcome === 'accept' && ai === 'reject') || (outcome === 'reject' && ai === 'accept');
      $('[data-dlg-title]', dlg).textContent = form.dataset.number + (outcome === 'accept' ? ' qabul qilinsinmi?' : ' rad etilsinmi?');
      $('[data-dlg-text]', dlg).textContent = (against ? 'Bu qaror AI tavsiyasiga zid. ' : '') + 'Qaror ismingiz bilan saqlanadi va uni o‘zgartirib bo‘lmaydi.';
      const ok = $('[data-dlg-confirm]', dlg);
      ok.className = 'btn ' + (outcome === 'accept' ? 'btn-primary' : 'btn-danger');
      ok.textContent = outcome === 'accept' ? 'Qabul qilish' : 'Rad etish';
      dlg.showModal();
    });
    $('[data-dlg-confirm]', dlg).addEventListener('click', () => {
      form.dataset.confirmed = '1';
      const h = el('input'); h.type = 'hidden'; h.name = 'outcome'; h.value = outcome; form.appendChild(h);
      form.submit();
    });
  }

  function boot() {
    initShell();
    const chart = $('#dailyChart'), data = $('#chart-data');
    if (chart && data) dailyChart(chart, JSON.parse(data.textContent));
    const review = $('[data-review]'); if (review) initReview(review);
    initDocs();
    initDecision();
    document.addEventListener('click', e => { const c = e.target.closest('dialog [data-close]'); if (c) c.closest('dialog').close(); });
    $$('dialog').forEach(d => d.addEventListener('click', e => { if (e.target === d) d.close(); }));
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
