// 2028 map builder: start from the last result, tap states to flip them, swing the whole map, share the link.
// The page is complete without JS (the last result's map and closest states); this only makes it interactive.
(function () {
  var root = document.querySelector("[data-builder]");
  var dataEl = document.getElementById("map-data");
  if (!root || !dataEl) return;
  var data = JSON.parse(dataEl.textContent);
  var units = {};
  data.units.forEach(function (u) { units[u.po] = u; });
  var calls = {};  // po -> "D" | "R" | "T", set by tapping; every other unit follows the swing
  var swing = 0;   // points added to every margin; margins are Republican-positive

  var map = root.querySelector("[data-builder-map]");
  var slider = root.querySelector("[data-swing]");
  var swingLabel = root.querySelector("[data-swing-label]");
  var info = root.querySelector("[data-map-info]");
  var idle = info.textContent;
  var shareBtn = root.querySelector("[data-share]");
  var shareText = shareBtn.textContent;
  var PARTY = { D: "Democrats", R: "Republicans" };

  function fmt(m) { return Math.abs(m) < 0.05 ? "Even" : (m > 0 ? "R+" : "D+") + Math.abs(m).toFixed(1); }
  function margin(u) { return u.m === null ? null : u.m + swing; }
  function auto(u) { var m = margin(u); return m === null ? u.w : m > 0 ? "R" : m < 0 ? "D" : "T"; }
  function call(u) { return calls[u.po] || auto(u); }
  function shade(u) {
    var c = calls[u.po];
    if (c === "T" || (!c && auto(u) === "T")) return "tu";
    if (c) return c === "D" ? "d3" : "r3";
    var m = margin(u);
    if (m === null) return u.w === "D" ? "d2" : "r2";
    var a = Math.abs(m);
    return (m > 0 ? "r" : "d") + (a < 5 ? 1 : a < 15 ? 2 : 3);
  }
  function describe(u) {
    var m = margin(u), c = call(u);
    return u.n + " · " + u.ev + " electoral vote" + (u.ev === 1 ? "" : "s") +
      (u.m === null ? "" : " · " + data.year + " " + fmt(u.m) + (swing ? ", with swing " + fmt(m) : "")) +
      " · " + (c === "T" ? "toss-up" : c === "D" ? "Democratic" : "Republican") + (calls[u.po] ? " (your call)" : "");
  }

  function render() {
    var ev = { D: 0, R: 0, T: 0 };
    data.units.forEach(function (u) { ev[call(u)] += u.ev; });
    map.querySelectorAll("[data-po]").forEach(function (a) {
      var u = units[a.getAttribute("data-po")];
      a.querySelector(".st").setAttribute("class", "st " + shade(u));
      a.querySelector("title").textContent = describe(u);
    });
    ["D", "R", "T"].forEach(function (p) {
      root.querySelector('[data-ev="' + p + '"]').textContent = ev[p];
      root.querySelector('[data-w="' + p + '"]').style.width = (100 * ev[p] / 538).toFixed(2) + "%";
    });
    root.querySelector("[data-tu]").hidden = !ev.T;
    root.querySelector("[data-ev-bar]").setAttribute("aria-label", "Electoral votes on this map: Democrats " + ev.D +
      ", Republicans " + ev.R + (ev.T ? ", toss-up " + ev.T : "") + ". 270 needed to win.");

    var status;
    if (ev.D >= 270 || ev.R >= 270) {
      var w = ev.D >= 270 ? "D" : "R";
      status = PARTY[w] + " win, " + ev[w] + "–" + ev[w === "D" ? "R" : "D"] + (ev.T ? ", with " + ev.T + " toss-up" : "") + ".";
    } else if (ev.D === 269 && ev.R === 269) {
      status = "A 269–269 tie: the new House would choose the president, one vote per state delegation.";
    } else {
      status = "No one has 270 yet: " + ev.T + " electoral votes are toss-ups.";
    }
    root.querySelector("[data-status]").textContent = status;
    swingLabel.textContent = swing ? fmt(swing) + " points" : "none";
    tipping(ev);
    closest();
    var h = hash();
    history.replaceState(null, "", h ? "#" + h : location.pathname + location.search);
  }

  // the unit that takes the leader to 270 when states are ordered from its strongest to its weakest
  function tipping(ev) {
    var el = root.querySelector("[data-tipping]");
    if (!el) return;
    var w = ev.D >= 270 ? "D" : ev.R >= 270 ? "R" : null;
    if (!w) { el.textContent = "Tipping point: none yet. Neither party has 270."; return; }
    var lean = function (u) {
      if (calls[u.po]) return calls[u.po] === w ? -1000 : 1000;
      var m = margin(u);
      return m === null ? -999 : (w === "D" ? m : -m);
    };
    var total = 0, mine = data.units.filter(function (u) { return call(u) === w; }).sort(function (a, b) { return lean(a) - lean(b); });
    for (var i = 0; i < mine.length; i++) {
      total += mine[i].ev;
      if (total >= 270) {
        var u = mine[i], m = margin(u);
        el.textContent = "Tipping point: " + u.n + (calls[u.po] || m === null ? " (your call)" : " (" + fmt(m) + ")") +
          ", the state that takes the " + PARTY[w] + " to 270.";
        return;
      }
    }
  }

  function closest() {
    var tb = root.querySelector("[data-closest]");
    var rows = data.units.filter(function (u) { return u.m !== null; })
      .sort(function (a, b) { return Math.abs(margin(a)) - Math.abs(margin(b)); }).slice(0, 10);
    tb.textContent = "";
    rows.forEach(function (u) {
      var tr = document.createElement("tr"), c = call(u);
      var cells = [null, u.ev, fmt(u.m), swing ? fmt(margin(u)) : "same",
        (c === "T" ? "Toss-up" : c === "D" ? "Dem" : "Rep") + (calls[u.po] ? " ✎" : "")];
      cells.forEach(function (v, i) {
        var td = document.createElement("td");
        if (i === 0) { var a = document.createElement("a"); a.href = u.u; a.textContent = u.n; td.appendChild(a); }
        else td.textContent = v;
        if (i > 0 && i < 4) td.className = "num nowrap";
        tr.appendChild(td);
      });
      tb.appendChild(tr);
    });
  }

  // #swing=-2.5&set=PAd,GAt keeps a map in its link, so it can be shared and reopened
  function hash() {
    var parts = [];
    if (swing) parts.push("swing=" + swing);
    var set = Object.keys(calls).sort().map(function (po) { return po + calls[po].toLowerCase(); });
    if (set.length) parts.push("set=" + set.join(","));
    return parts.join("&");
  }
  function load() {
    location.hash.replace(/^#/, "").split("&").forEach(function (kv) {
      var p = kv.split("="), v = decodeURIComponent(p[1] || "");
      if (p[0] === "swing" && !isNaN(parseFloat(v))) swing = Math.max(-10, Math.min(10, Math.round(parseFloat(v) * 2) / 2));
      if (p[0] === "set") v.split(",").forEach(function (s) {
        var m = s.match(/^([A-Z]{2}2?)([drt])$/);
        if (m && units[m[1]]) calls[m[1]] = m[2].toUpperCase();
      });
    });
    slider.value = swing;
  }

  map.addEventListener("click", function (e) {
    var a = e.target.closest("a[data-po]");
    if (!a) return;
    e.preventDefault();  // the link to the state page is for crawlers and no-JS readers
    var u = units[a.getAttribute("data-po")], cur = calls[u.po];
    if (cur === undefined) calls[u.po] = auto(u) === "D" ? "R" : "D";
    else if (cur === "T") delete calls[u.po];
    else calls[u.po] = "T";
    render();
    info.textContent = describe(u);
  });
  function hover(e) {
    var a = e.target.closest && e.target.closest("a[data-po]");
    info.textContent = a ? describe(units[a.getAttribute("data-po")]) : idle;
  }
  map.addEventListener("mouseover", hover);
  map.addEventListener("focusin", hover);
  map.addEventListener("mouseleave", function () { info.textContent = idle; });

  slider.addEventListener("input", function () { swing = parseFloat(slider.value); render(); });
  root.querySelector("[data-reset]").addEventListener("click", function () {
    calls = {}; swing = 0; slider.value = 0; render(); info.textContent = idle;
  });
  shareBtn.addEventListener("click", function () {
    var text = "My 2028 electoral map: " + root.querySelector("[data-status]").textContent;
    if (navigator.share) {
      navigator.share({ title: document.title, text: text, url: location.href }).catch(function () {});
    } else if (navigator.clipboard) {
      navigator.clipboard.writeText(location.href).then(function () {
        shareBtn.textContent = "Link copied";
        setTimeout(function () { shareBtn.textContent = shareText; }, 2000);
      });
    }
  });

  load();
  render();
})();
