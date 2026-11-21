// Mezon: E-qaror / E-qaror-respublika -> laptop receiver (research/browser_sink.py) -> Mezon box (data/raw/browser/).
// Boss runs this himself: open https://e-qaror.gov.uz (or https://e-qaror-respublika.gov.uz) in Chrome,
// F12 -> Console, paste, Enter. Reads the same list and the same "download" PDF links the site's own page uses,
// one request every ~1.5 s, no cookies. If the site throttles, it PAUSES 5 min and retries; it never changes session.
// Order (E-qaror): normative list -> declared-invalid list -> their PDFs -> the whole list (45,959 pages) -> all PDFs.
// Resumes after a reload (localStorage). Stop: mezonStop()   Progress: mezonStatus()
(async () => {
  const E = "https://api-eqaror.gov.uz/v2/doc";
  const SITES = {
    "e-qaror.gov.uz": [
      { name: "eqaror_normative", list: p => `${E}/list?is_normative=1&page=${p}&limit=20&lang=oz`, pdf: true },
      { name: "eqaror_invalid", list: p => `${E}/list?release=200&page=${p}&limit=20&lang=oz`, pdf: true },
      { name: "eqaror_all", list: p => `${E}/list?page=${p}&limit=20&lang=oz`, pdf: false },
    ],
    "e-qaror-respublika.gov.uz": [
      { name: "eqaror_respublika", list: p => `https://e-res.ecdn.uz/v2/documents?lang=oz&page=${p}`, pdf: false },
    ],
  };
  const jobs = SITES[location.hostname];
  if (!jobs) { console.error("Open https://e-qaror.gov.uz or https://e-qaror-respublika.gov.uz first, then paste again."); return; }
  const SINK = "http://127.0.0.1:8765/put?name=", GAP = 1500, PAUSE = 5 * 60 * 1000;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const st = { job: "", page: 0, rows: 0, pdfs: 0, pdfFail: 0 };
  let stop = false;
  window.mezonStop = () => { stop = true; console.log("Mezon: stopping after the current request"); };
  window.mezonStatus = () => console.log("Mezon:", JSON.stringify(st));

  const items = j => { let best = []; const walk = v => { if (Array.isArray(v)) { if (v.length && typeof v[0] === "object" && v.length > best.length) best = v; v.forEach(walk); } else if (v && typeof v === "object") Object.values(v).forEach(walk); }; walk(j); return best; };
  const codeOf = r => { let c = null; const walk = v => { if (c) return; if (typeof v === "string" && /^[0-9a-f]{32}$/.test(v)) c = v; else if (v && typeof v === "object") Object.values(v).forEach(walk); }; walk(r); return c; };
  const post = (name, body) => fetch(SINK + name, { method: "POST", headers: { "Content-Type": "text/plain" }, body });
  const b64 = buf => { const b = new Uint8Array(buf); let s = ""; for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000)); return btoa(s); };

  async function polite(url, asJson) {           // one request; on trouble pause 5 min and retry (max 6 pauses)
    for (let tries = 0; ; tries++) {
      try {
        const r = await fetch(url);
        if (r.ok) return asJson ? await r.json() : await r.arrayBuffer();
        if (r.status === 404 || r.status === 422) return null;  // nothing there / not allowed: skip, don't hammer
        console.warn(`Mezon: HTTP ${r.status} on ${url.slice(0, 90)}`);
      } catch (e) { console.warn(`Mezon: ${e.message} on ${url.slice(0, 90)}`); }
      if (tries >= 6) throw new Error("site keeps refusing; paste again later to resume");
      console.warn("Mezon: pausing 5 min (site busy or throttling)"); await sleep(PAUSE);
    }
  }

  try { await fetch(SINK.replace("/put?name=", "/status")); } catch (e) { console.error("Mezon: receiver not running on 127.0.0.1:8765 (research.browser_sink)"); return; }

  const pdfQueue = [];
  async function runList(job) {
    const key = "mezon_page_" + job.name; let page = +(localStorage.getItem(key) || 1), first = null, empties = 0;
    st.job = job.name; console.log(`Mezon: ${job.name} list from page ${page}`);
    while (!stop) {
      st.page = page;
      const j = await polite(job.list(page), true); const rows = j ? items(j) : [];
      if (page === 1 && rows.length) first = JSON.stringify(rows[0]);
      else if (rows.length && JSON.stringify(rows[0]) === first) { console.error(`Mezon: ${job.name}: page parameter ignored; stopped this list`); break; }
      if (!rows.length) { if (++empties >= 2) { console.log(`Mezon: ${job.name} list done at page ${page - 1}`); localStorage.setItem(key + "_done", "1"); break; } }
      else {
        empties = 0; st.rows += rows.length;
        await post(job.name, rows.map(r => JSON.stringify({ _page: page, ...r })).join("\n") + "\n");
        if (job.pdf) rows.forEach(r => { const c = codeOf(r); if (c) pdfQueue.push(c); });
      }
      localStorage.setItem(key, String(page + 1));
      if (page % 25 === 0) console.log(`Mezon: ${job.name} page ${page}, rows this run ${st.rows}`);
      page++; await sleep(GAP);
    }
  }
  async function runPdfs(codes, tag) {
    const doneKey = "mezon_pdfs_done_" + tag, done = new Set(JSON.parse(localStorage.getItem(doneKey) || "[]"));
    console.log(`Mezon: PDFs for ${tag}: ${codes.length} codes, ${done.size} already sent`);
    for (const c of codes) {
      if (stop) return; if (done.has(c)) continue;
      const buf = await polite(`${E}/show?code=${c}`, false);
      if (buf && buf.byteLength) { await post("eqaror_pdf", JSON.stringify({ code: c, bytes: buf.byteLength, b64: b64(buf) }) + "\n"); st.pdfs++; }
      else st.pdfFail++;
      done.add(c); if (done.size % 50 === 0) { localStorage.setItem(doneKey, JSON.stringify([...done])); console.log(`Mezon: PDFs ${tag}: ${done.size}/${codes.length}`); }
      await sleep(GAP);
    }
    localStorage.setItem(doneKey, JSON.stringify([...done]));
  }

  try {
    for (const job of jobs) {
      if (stop) break;
      if (!localStorage.getItem("mezon_page_" + job.name + "_done")) await runList(job);
      if (job.pdf && pdfQueue.length && !stop) await runPdfs([...new Set(pdfQueue)], job.name);
      pdfQueue.length = 0;
    }
    console.log("Mezon: finished this round.", JSON.stringify(st));
  } catch (e) { console.error("Mezon:", e.message, JSON.stringify(st)); }
})();
