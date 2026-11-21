// DOM-only readers for public e-qaror.gov.uz pages (no API calls). Paste into the page via javascript_tool,
// on any e-qaror.gov.uz page. The site is a Next.js app: mzRun moves between pages with the site's own router
// (window.next.router.push), so this script keeps running and results accumulate in window.__mz.
const MZ_GREEN = "rgb(9, 111, 53)", MZ_GREY = "rgb(182, 181, 181)";
const MZ_STATUSES = ["Haqiqiy emas deb topilgan", "Oʻzgartirish kiritilgan", "O‘zgartirish kiritilgan", "Bekor qilingan", "Amalda"];
const MZ_REG = /^[IVX\d]+(-[\dA-Z]+)+\/[\dQFK]+$/;

// Registration number shown in a decision page header, or null before the page has rendered.
window.mzHeadReg = function () {
  const t = document.body.innerText; const i = t.indexOf("Hujjat qabul qilish bosqichlari");
  if (i < 0) return null;
  return t.slice(0, i).split("\n").map(s => s.trim()).filter(Boolean).find(l => MZ_REG.test(l)) || "";
};

// One decision page: type, number, status, Asos and the 8 adoption stages as a bit string
// (1 = green/done, 0 = grey/skipped) in the order: Qoralama, Idoraviy kelishuv, Hokimiyat tarkibiy bo‘linmalari,
// Kengash kotibiyati, Hokimlik yuriskonsulti, Jamoatchilik muhokamasi, Huquqiy ekspertiza, E’lon qilish.
window.mzExtractDoc = function () {
  const stages = [...document.querySelectorAll(".ant-steps-item-title")].map(e => {
    const c = getComputedStyle(e).color; return c === MZ_GREEN ? "1" : c === MZ_GREY ? "0" : "?";
  }).join("");
  const t = document.body.innerText; const head = t.slice(0, Math.max(t.indexOf("Hujjat qabul qilish bosqichlari"), 0));
  const lines = head.split("\n").map(s => s.trim()).filter(Boolean);
  const ri = lines.findIndex(l => MZ_REG.test(l));
  const sl = ri >= 0 ? lines.slice(ri + 1).join(" ") : "";
  const asosM = sl.match(/Asos\s*(.*)$/);
  return { type: ri > 0 ? lines[ri - 1] : "", reg_number: ri >= 0 ? lines[ri] : "",
    status: MZ_STATUSES.find(s => sl.includes(s)) || "", asos: asosM ? asosM[1].trim() : "", stages };
};

// One search results page (https://e-qaror.gov.uz/search?...&page=N, 20 rows).
window.mzExtractList = function () {
  return [...document.querySelectorAll("tbody tr")].map(tr => {
    const td = [...tr.querySelectorAll("td")].map(c => c.innerText.trim()); const a = tr.querySelector('a[href*="/doc/"]');
    return a && td.length >= 7 ? { pos: td[0], title: td[1], type: td[2], content: td[3], body: td[4], reg_number: td[5],
      date: td[6], id: a.href.slice(-32) } : null;
  }).filter(Boolean).filter((r, i, all) => all.findIndex(x => x.id === r.id) === i);
};

// jobs: [{url, id?, reg?, ...}], kind: "doc" | "list". One page at a time, pauseMs between pages.
// Hidden decisions ("Hujjat yashiringan") have no tracker and are recorded as {hidden: true}.
window.mzRun = function (jobs, kind, pauseMs = 900) {
  window.__mz = window.__mz || { out: [], errors: [], done: 0 }; const st = window.__mz; st.running = true; st.stop = false;
  (async () => {
    let prevKey = null;
    for (const job of jobs) {
      if (st.stop) break;
      try { await window.next.router.push(job.url); } catch (e) { }
      const t0 = Date.now(); let got = null;
      while (Date.now() - t0 < 20000) {
        await new Promise(r => setTimeout(r, 300));
        if (kind === "doc") {
          if (!location.pathname.endsWith(job.id)) continue;
          if (/yashiringan/i.test(document.title) || /Hujjat yashiringan/.test(document.body.innerText.slice(0, 600))) {
            got = { hidden: true, stages: "", status: "", asos: "" }; break;
          }
          const reg = mzHeadReg();
          if (document.querySelectorAll(".ant-steps-item-title").length >= 8 && reg && (!job.reg || reg === job.reg)) {
            await new Promise(r => setTimeout(r, 250)); got = mzExtractDoc(); break;
          }
          if (Date.now() - t0 > 9000 && reg && job.reg && reg !== job.reg) { got = { mismatch: reg, stages: "", status: "", asos: "" }; break; }
        } else {
          const rows = mzExtractList(); const key = rows.length ? rows[0].id + rows.length : null;
          if (rows.length && location.search === new URL(job.url, location.origin).search && key !== prevKey) {
            await new Promise(r => setTimeout(r, 400));
            got = { rows: mzExtractList(), pager: [...document.querySelectorAll(".ant-pagination li")].map(l => l.title || l.innerText).join("|") };
            prevKey = key; break;
          }
        }
      }
      if (got) st.out.push({ ...job, data: got }); else st.errors.push({ ...job, err: "timeout" });
      st.done++; await new Promise(r => setTimeout(r, pauseMs));
    }
    st.running = false;
  })();
  return "started " + jobs.length;
};

// Tab-separated export line for research/eqaror_save.py (tool output caps each string near 1,000 chars).
window.mzLine = o => {
  const d = o.data, c = s => String(s == null ? "" : s).replace(/[\t\n\r]+/g, " ").trim();
  return [o.set, c(d.reg_number || o.reg), c(d.type || ""), d.hidden ? "hidden" : c(d.status), c(d.asos).slice(0, 170), "",
    o.is_normative, d.stages || "", c(o.date).replace(/\./g, "/"), c(o.body).slice(0, 60), d.hidden ? "" : c(o.title).slice(0, 90),
    o.id, o.page + ":" + o.pos].join("\t");
};
