/* Mezon UI kit 2.0 - behaviour for the kit page and the live demos.
   No dependencies. Everything degrades: without JS the objects still render. */
(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  var ICON = function (n, c) { return '<svg class="icon ' + (c || '') + '" aria-hidden="true"><use href="#i-' + n + '"/></svg>'; };

  /* ---------- toast ---------- */
  function toast(text) {
    var host = $('#toastHost'); if (!host) return;
    var t = document.createElement('div'); t.className = 'toast rise'; t.setAttribute('role', 'status');
    t.innerHTML = ICON('circle-check') + '<span></span>'; t.lastChild.textContent = text;
    host.appendChild(t); setTimeout(function () { t.remove(); }, 2200);
  }

  /* ---------- theme ---------- */
  function setTheme(t, save) {
    document.documentElement.setAttribute('data-theme', t);
    var b = $('#themeBtn'); if (b) {
      b.setAttribute('aria-pressed', String(t === 'dark'));
      $('#themeLabel').textContent = t === 'dark' ? 'Yorug’' : 'Qorong’i';
      b.querySelector('use').setAttribute('href', t === 'dark' ? '#i-sun' : '#i-moon');
    }
    if (save) try { localStorage.setItem('mezon-theme', t); } catch (e) {}
    renderSwatches();
  }
  var tb = $('#themeBtn');
  if (tb) tb.addEventListener('click', function () { setTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark', true); });

  /* ---------- swatches with live contrast ---------- */
  function lum(rgb) { var a = rgb.map(function (v) { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }); return .2126 * a[0] + .7152 * a[1] + .0722 * a[2]; }
  function parse(c) { var m = c.match(/\d+(\.\d+)?/g); return m ? m.slice(0, 3).map(Number) : [0, 0, 0]; }
  function resolve(v) { var p = document.createElement('i'); p.style.cssText = 'position:absolute;visibility:hidden;color:var(--' + v + ')'; document.body.appendChild(p); var c = getComputedStyle(p).color; p.remove(); return c; }
  function renderSwatches() {
    $$('[data-swatches]').forEach(function (box) {
      var surface = lum(parse(resolve('surface')));
      box.innerHTML = box.getAttribute('data-swatches').split(',').map(function (p) {
        var kv = p.split(':'), c = resolve(kv[0]), l = lum(parse(c));
        var hi = Math.max(l, surface) + .05, lo = Math.min(l, surface) + .05;
        var hex = '#' + parse(c).map(function (n) { return ('0' + Math.round(n).toString(16)).slice(-2); }).join('');
        return '<div class="swatch"><i style="background:var(--' + kv[0] + ')"></i><div><b>' + kv[1] + '</b><code>--' + kv[0] + '</code><br><code>' + hex + '</code> <span class="cr">' + (hi / lo).toFixed(1) + ':1 yuzada</span></div></div>';
      }).join('');
    });
    $$('[data-space]').forEach(function (box) {
      if (box.children.length) return;
      box.innerHTML = [4, 8, 12, 16, 24, 32, 48, 64].map(function (n) { return '<div class="space-row"><span>space-' + n / 4 + ' &middot; ' + n + '</span><i style="width:' + n + 'px"></i></div>'; }).join('');
    });
  }

  /* ---------- objects: copyable HTML snippet ---------- */
  function dedent(s) {
    var lines = s.replace(/\t/g, '  ').split('\n');
    while (lines.length && !lines[0].trim()) lines.shift();
    while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
    var min = Infinity; lines.forEach(function (l) { if (l.trim()) min = Math.min(min, l.match(/^ */)[0].length); });
    return lines.map(function (l) { return l.slice(min === Infinity ? 0 : min); }).join('\n');
  }
  function esc(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  function copyText(text, msg) {
    var done = function () { toast(msg || 'HTML nusxalandi'); };
    if (navigator.clipboard && window.isSecureContext !== false) navigator.clipboard.writeText(text).then(done, fallback); else fallback();
    function fallback() { var t = document.createElement('textarea'); t.value = text; t.style.cssText = 'position:fixed;opacity:0'; document.body.appendChild(t); t.select(); try { document.execCommand('copy'); } catch (e) {} t.remove(); done(); }
  }
  function initObjects() {
    $$('.obj').forEach(function (obj, i) {
      var stage = $('.stage', obj); if (!stage) return;
      var html = dedent(stage.innerHTML.replace(/ aria-live="polite"/g, '').replace(/ data-[a-z-]+(="[^"]*")?/g, function (m) { return /data-(tone|state|status|src|k|verdict|res|kind|model|sortable)/.test(m) ? m : ''; }));
      var bar = document.createElement('div'); bar.className = 'obj-bar';
      var id = 'snip' + i;
      bar.innerHTML = '<div><div class="obj-name"></div><div class="obj-note"></div></div><div class="end"><button class="btn btn-ghost btn-sm" type="button" aria-expanded="false" aria-controls="' + id + '">HTML</button><button class="btn btn-secondary btn-sm" type="button">' + ICON('copy', 'icon-sm') + ' Nusxalash</button></div>';
      $('.obj-name', bar).textContent = obj.getAttribute('data-name'); $('.obj-note', bar).textContent = obj.getAttribute('data-note') || '';
      obj.insertBefore(bar, stage);
      var snip = document.createElement('div'); snip.className = 'snip'; snip.id = id;
      var pre = document.createElement('pre'); var code = document.createElement('code'); code.innerHTML = esc(html); pre.appendChild(code); pre.tabIndex = 0; pre.setAttribute('aria-label', 'HTML kodi'); snip.appendChild(pre);
      obj.appendChild(snip);
      var b = bar.querySelectorAll('button');
      b[0].addEventListener('click', function () { var o = snip.getAttribute('data-open') === 'true'; snip.setAttribute('data-open', String(!o)); b[0].setAttribute('aria-expanded', String(!o)); });
      b[1].addEventListener('click', function () { copyText(html); });
    });
  }

  /* ---------- tabs, segmented, chips ---------- */
  function initToggles() {
    $$('.tabs[role="tablist"]').forEach(function (g) {
      var tabs = $$('[role="tab"]', g);
      tabs.forEach(function (t) { t.tabIndex = t.getAttribute('aria-selected') === 'true' ? 0 : -1; });
      g.addEventListener('click', function (e) { var t = e.target.closest('[role="tab"]'); if (t) sel(t); });
      g.addEventListener('keydown', function (e) {
        var i = tabs.indexOf(document.activeElement); if (i < 0) return;
        var n = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 : e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : null;
        if (n === null) return; e.preventDefault(); n = (n + tabs.length) % tabs.length; tabs[n].focus(); sel(tabs[n]);
      });
      function sel(t) { tabs.forEach(function (x) { var on = x === t; x.setAttribute('aria-selected', String(on)); x.tabIndex = on ? 0 : -1; }); }
    });
    document.addEventListener('click', function (e) {
      var s = e.target.closest('.segmented button');
      if (s) { $$('button', s.parentNode).forEach(function (b) { b.setAttribute('aria-pressed', String(b === s)); }); return; }
      var c = e.target.closest('button.chip[aria-pressed]');
      if (c) c.setAttribute('aria-pressed', String(c.getAttribute('aria-pressed') !== 'true'));
      var sg = e.target.closest('.suggest .chip'); if (sg) { var ta = $('#cmp1'); if (ta) { ta.value = sg.textContent.trim(); ta.dispatchEvent(new Event('input')); ta.focus(); } }
    });
  }

  /* ---------- sortable table ---------- */
  function initTable() {
    $$('table[data-sortable]').forEach(function (t) {
      var tb = t.tBodies[0];
      $$('th button[data-sort]', t).forEach(function (b) {
        b.addEventListener('click', function () {
          var i = +b.getAttribute('data-sort'), num = b.hasAttribute('data-num'), th = b.parentNode;
          var dir = th.getAttribute('aria-sort') === 'descending' ? 'ascending' : 'descending';
          $$('th', t).forEach(function (x) { x.removeAttribute('aria-sort'); }); th.setAttribute('aria-sort', dir);
          var rows = $$('tr', tb).sort(function (a, c) {
            var x = a.cells[i].textContent.trim(), y = c.cells[i].textContent.trim();
            var r = num ? (+x - +y) : x.localeCompare(y, 'uz'); return dir === 'ascending' ? r : -r;
          });
          rows.forEach(function (r) { tb.appendChild(r); });
        });
      });
    });
  }

  /* ---------- model menu ---------- */
  function initModel() {
    var btn = $('[data-model-btn]'), menu = $('[data-model-menu]'); if (!btn) return;
    function open(v) { menu.hidden = !v; btn.setAttribute('aria-expanded', String(v)); if (v) { var c = $('[aria-checked="true"]', menu); c && c.focus(); } }
    btn.addEventListener('click', function () { open(menu.hidden); });
    document.addEventListener('click', function (e) { if (!menu.hidden && !e.target.closest('.model-wrap')) open(false); });
    menu.addEventListener('keydown', function (e) {
      var items = $$('.model-opt', menu), i = items.indexOf(document.activeElement);
      if (e.key === 'Escape') { open(false); btn.focus(); }
      if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length].focus(); }
      if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
    });
    menu.addEventListener('click', function (e) {
      var o = e.target.closest('.model-opt'); if (!o) return;
      $$('.model-opt', menu).forEach(function (x) { x.setAttribute('aria-checked', String(x === o)); });
      $('[data-model-label]').textContent = o.getAttribute('data-model'); open(false); btn.focus();
    });
  }

  /* ---------- composer: file drop + paste ---------- */
  function fmtSize(n) { return n > 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB'; }
  function addChip(list, name, meta, onChange) {
    var el = document.createElement('span'); el.className = 'attach rise';
    el.innerHTML = ICON('file-text', 'icon-sm') + '<b></b><small></small><button class="btn btn-ghost btn-icon btn-sm" type="button" style="--h:24px" aria-label="Olib tashlash">' + ICON('x', 'icon-sm') + '</button>';
    $('b', el).textContent = name; $('small', el).textContent = meta;
    $('button', el).addEventListener('click', function () { el.remove(); onChange && onChange(); });
    list.appendChild(el); onChange && onChange();
  }
  function takeFiles(list, files, onChange) { Array.prototype.forEach.call(files, function (f) { addChip(list, f.name || 'rasm.png', fmtSize(f.size), onChange); }); }
  function initComposer() {
    $$('[data-composer]').forEach(function (form) {
      var ta = $('textarea', form), send = $('.send', form), list = $('[data-attach]', form), pick = $('[data-pick]', form), file = $('[data-file]', form);
      function sync() { send.disabled = !ta.value.trim() && !list.children.length; }
      function grow() { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 200) + 'px'; }
      ta.addEventListener('input', function () { grow(); sync(); });
      ta.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); if (!send.disabled) form.requestSubmit(); } });
      form.addEventListener('submit', function (e) { e.preventDefault(); ta.value = ''; list.innerHTML = ''; grow(); sync(); toast('Yuborildi (demo)'); });
      pick.addEventListener('click', function () { file.click(); });
      file.addEventListener('change', function () { takeFiles(list, file.files, sync); file.value = ''; });
      ['dragenter', 'dragover'].forEach(function (n) { form.addEventListener(n, function (e) { e.preventDefault(); form.setAttribute('data-drag', 'true'); }); });
      ['dragleave', 'drop'].forEach(function (n) { form.addEventListener(n, function (e) { e.preventDefault(); form.removeAttribute('data-drag'); }); });
      form.addEventListener('drop', function (e) { if (e.dataTransfer && e.dataTransfer.files.length) takeFiles(list, e.dataTransfer.files, sync); });
      ta.addEventListener('paste', function (e) {
        var cd = e.clipboardData; if (!cd) return;
        if (cd.files && cd.files.length) { e.preventDefault(); takeFiles(list, cd.files, sync); return; }
        var txt = cd.getData('text'); if (txt && txt.length > 600) { e.preventDefault(); addChip(list, 'Joylangan matn', txt.length.toLocaleString('en-US') + ' belgi', sync); }
      });
    });
    $$('[data-drop]').forEach(function (dz) {
      var list = $('[data-drop-list]', dz.parentNode), input = document.createElement('input'); input.type = 'file'; input.multiple = true; input.hidden = true; dz.appendChild(input);
      dz.addEventListener('click', function (e) { if (e.target !== input) input.click(); });
      dz.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } });
      input.addEventListener('change', function () { takeFiles(list, input.files); input.value = ''; });
      ['dragenter', 'dragover'].forEach(function (n) { dz.addEventListener(n, function (e) { e.preventDefault(); dz.setAttribute('data-drag', 'true'); }); });
      ['dragleave', 'drop'].forEach(function (n) { dz.addEventListener(n, function (e) { e.preventDefault(); dz.removeAttribute('data-drag'); }); });
      dz.addEventListener('drop', function (e) { if (e.dataTransfer) takeFiles(list, e.dataTransfer.files); });
      document.addEventListener('paste', function (e) { if (e.target.closest && e.target.closest('textarea')) return; var f = e.clipboardData && e.clipboardData.files; if (f && f.length) takeFiles(list, f); });
    });
  }

  /* ---------- live agent steps: spinner -> check ---------- */
  var timers = [];
  function replaySteps() {
    var ol = $('[data-steps]'); if (!ol) return;
    timers.forEach(clearTimeout); timers = [];
    var steps = $$('.step', ol), ans = $('[data-answer]');
    var times = ['0,4 s', '1,1 s', '2,0 s', '14 s'];
    steps.forEach(function (s) { setState(s, 'wait'); });
    if (ans) ans.style.visibility = 'hidden';
    var step = reduce ? 80 : 900;
    steps.forEach(function (s, i) {
      timers.push(setTimeout(function () { setState(s, 'run'); }, i * step));
      timers.push(setTimeout(function () { setState(s, 'done', times[i]); if (i === steps.length - 1 && ans) ans.style.visibility = ''; }, i * step + step * .85));
    });
    function setState(s, st, time) {
      s.setAttribute('data-state', st);
      $('.step-mark', s).innerHTML = st === 'run' ? '<span class="spinner"></span>' : st === 'done' ? ICON('check', 'icon-sm') : '<span class="dot"></span>';
      $('.step-time', s).textContent = st === 'done' ? time : st === 'run' ? '...' : '';
    }
  }
  var rp = $('[data-replay]'); if (rp) rp.addEventListener('click', replaySteps);

  /* ---------- streaming text ---------- */
  var streamT;
  function stream() {
    var el = $('[data-stream]'); if (!el) return; clearInterval(streamT);
    var words = el.getAttribute('data-text').split(' '), i = 0; el.innerHTML = '';
    var txt = document.createTextNode(''), caret = document.createElement('span'); caret.className = 'caret'; caret.setAttribute('aria-hidden', 'true');
    el.appendChild(txt); el.appendChild(caret);
    if (reduce) { txt.nodeValue = words.join(' ') + '.'; caret.remove(); return; }
    streamT = setInterval(function () {
      txt.nodeValue += (i ? ' ' : '') + words[i++];
      if (i >= words.length) { clearInterval(streamT); txt.nodeValue += '.'; setTimeout(function () { caret.remove(); }, 600); }
    }, 130);
  }
  var sr = $('[data-stream-replay]'); if (sr) sr.addEventListener('click', stream);

  /* ---------- nav highlight ---------- */
  function initNav() {
    var links = $$('.kit-nav a'); if (!('IntersectionObserver' in window)) return;
    var io = new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting) links.forEach(function (a) { a.setAttribute('aria-current', String(a.getAttribute('href') === '#' + e.target.id)); }); }); }, { rootMargin: '-40% 0px -55% 0px' });
    $$('.sec').forEach(function (s) { io.observe(s); });
  }

  /* ---------- boot ---------- */
  setTheme(document.documentElement.getAttribute('data-theme') || 'light', false);
  initObjects(); initToggles(); initTable(); initModel(); initComposer(); initNav();
  if ('IntersectionObserver' in window && !reduce) {
    var started = false, host = $('.chat-demo');
    if (host) new IntersectionObserver(function (es, o) { if (!started && es[0].isIntersecting) { started = true; replaySteps(); stream(); o.disconnect(); } }, { threshold: .3 }).observe(host);
  }
})();
