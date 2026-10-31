// ElectionsUSA front-end: live countdowns, sortable tables, and the "Ask" finder.
// Everything is server-rendered first; JS only enhances.
(function () {
  // ---- countdown -------------------------------------------------------
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function tick() {
    document.querySelectorAll("[data-target]").forEach(function (el) {
      var ms = new Date(el.getAttribute("data-target") + "T00:00:00") - new Date();
      var d = el.querySelector("[data-days]");
      if (d && ms > 0) d.textContent = Math.ceil(ms / 86400000);
      var live = el.querySelector("[data-live]");
      if (live && ms > 0) {
        var s = Math.floor(ms / 1000);
        live.textContent = Math.floor(s / 86400) + " days, " + pad(Math.floor((s % 86400) / 3600)) + ":" + pad(Math.floor((s % 3600) / 60)) + ":" + pad(s % 60);
      }
    });
  }
  tick();
  if (document.querySelector("[data-live]")) setInterval(tick, 1000);

  // ---- sortable tables ---------------------------------------------------
  document.querySelectorAll("table.sortable").forEach(function (table) {
    var ths = table.querySelectorAll("thead th");
    ths.forEach(function (th, idx) {
      th.style.cursor = "pointer";
      th.addEventListener("click", function () {
        var rows = Array.prototype.slice.call(table.querySelectorAll("tbody tr"));
        var asc = th.getAttribute("data-asc") !== "true";
        rows.sort(function (a, b) {
          // data-sort carries a signed number when the text can't ("Trump +1.7" vs "Harris +1.7")
          var key = function (row) { var c = row.children[idx]; return c.getAttribute("data-sort") || c.textContent.trim(); };
          var x = key(a), y = key(b);
          var nx = parseFloat(x.replace(/[^0-9.\-]/g, "")), ny = parseFloat(y.replace(/[^0-9.\-]/g, ""));
          if (!isNaN(nx) && !isNaN(ny)) return asc ? nx - ny : ny - nx;
          return asc ? x.localeCompare(y) : y.localeCompare(x);
        });
        ths.forEach(function (t) { t.removeAttribute("data-asc"); });
        th.setAttribute("data-asc", asc);
        var tb = table.querySelector("tbody");
        rows.forEach(function (r) { tb.appendChild(r); });
      });
    });
  });

  // ---- state map: show the hovered or focused state's result in the caption --
  document.querySelectorAll("[data-map]").forEach(function (map) {
    var info = map.parentNode.querySelector("[data-map-info]");
    if (!info) return;
    var idle = info.textContent;
    function show(e) {
      var a = e.target.closest && e.target.closest("a[data-s]");
      info.textContent = a ? a.getAttribute("data-s") : idle;
    }
    map.addEventListener("mouseover", show);
    map.addEventListener("focusin", show);
    map.addEventListener("mouseleave", function () { info.textContent = idle; });
  });

  // ---- folded poll tables ------------------------------------------------
  document.querySelectorAll("[data-fold-toggle]").forEach(function (btn) {
    var fold = document.getElementById(btn.getAttribute("aria-controls"));
    var more = btn.textContent;
    btn.addEventListener("click", function () {
      var open = !fold.classList.toggle("is-folded");
      btn.setAttribute("aria-expanded", open);
      btn.textContent = open ? btn.getAttribute("data-less") : more;
      // folding back up from far down the page would leave the reader in the next section
      if (!open && btn.getBoundingClientRect().top < 0) fold.scrollIntoView();
    });
  });

  // ---- finder ------------------------------------------------------------
  var finders = document.querySelectorAll("[data-finder]");
  if (!finders.length) return;
  var index = null, loading = null;
  // When exported as a relative bundle (export_artifact.py), SITE_ROOT is set per page.
  function siteUrl(u) {
    var root = window.SITE_ROOT;
    if (!root || !u || u.charAt(0) !== "/") return u;
    var hash = "", i = u.indexOf("#");
    if (i >= 0) { hash = u.slice(i); u = u.slice(0, i); }
    u = u.slice(1);
    if (u === "" || u.charAt(u.length - 1) === "/") u += "index.html";
    return root + u + hash;
  }
  function load() {
    if (index) return Promise.resolve(index);
    if (!loading) loading = fetch(siteUrl("/api/search-index.json")).then(function (r) { return r.json(); }).then(function (j) { index = j; return j; });
    return loading;
  }
  var STOP = { the: 1, is: 1, who: 1, what: 1, in: 1, of: 1, a: 1, an: 1, vs: 1, "vs.": 1, are: 1, does: 1, do: 1, how: 1, many: 1, until: 1, to: 1, for: 1, and: 1, leads: 1, leading: 1, ahead: 1, poll: 1, polls: 1, polling: 1 };
  function tokens(s) { return s.toLowerCase().replace(/[^a-z0-9%'\s-]/g, " ").split(/\s+/).filter(function (t) { return t && !STOP[t]; }); }
  function score(entry, qs) {
    var hay = (entry.t + " " + entry.q + " " + entry.s).toLowerCase(), sc = 0;
    qs.forEach(function (t) {
      if (entry.t.toLowerCase().indexOf(t) >= 0) sc += 3;
      else if (hay.indexOf(t) >= 0) sc += 1;
    });
    return sc;
  }
  function esc(s) { return s.replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  finders.forEach(function (box) {
    var input = box.querySelector("[data-finder-input]"), out = box.querySelector("[data-finder-results]");
    var active = -1;
    function render(items, q) {
      if (!q) { out.classList.remove("open"); out.innerHTML = ""; return; }
      if (!items.length) { out.innerHTML = '<div class="none">Nothing matches "' + esc(q) + '". Try a candidate, a pollster or "approval".</div>'; out.classList.add("open"); return; }
      out.innerHTML = items.map(function (e) {
        return '<a href="' + siteUrl(e.u) + '" role="option"><span><span class="t">' + esc(e.t) + '</span><span class="s">' + esc(e.s) + '</span></span><span class="k">' + esc(e.k) + '</span></a>';
      }).join("");
      out.classList.add("open"); active = -1;
    }
    function run() {
      var q = input.value.trim(), qs = tokens(q);
      if (!q) return render([], "");
      load().then(function (idx) {
        var scored = idx.map(function (e) { return [score(e, qs.length ? qs : [q.toLowerCase()]), e]; })
          .filter(function (p) { return p[0] > 0; })
          .sort(function (a, b) { return b[0] - a[0]; })
          .slice(0, 7).map(function (p) { return p[1]; });
        render(scored, q);
      });
    }
    input.addEventListener("input", run);
    input.addEventListener("focus", run);
    input.addEventListener("keydown", function (ev) {
      var links = out.querySelectorAll("a");
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        ev.preventDefault();
        if (!links.length) return;
        active = (active + (ev.key === "ArrowDown" ? 1 : -1) + links.length) % links.length;
        links.forEach(function (l, i) { l.classList.toggle("active", i === active); });
      } else if (ev.key === "Enter") {
        ev.preventDefault();
        var target = links[active >= 0 ? active : 0];
        if (target) window.location.href = target.getAttribute("href");
      } else if (ev.key === "Escape") { render([], ""); input.blur(); }
    });
    document.addEventListener("click", function (ev) { if (!box.contains(ev.target)) render([], ""); });
    var form = box.querySelector("form");
    if (form) form.addEventListener("submit", function (ev) { ev.preventDefault(); var l = out.querySelector("a"); if (l) window.location.href = l.getAttribute("href"); });
  });
})();
