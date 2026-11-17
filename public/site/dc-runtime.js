/* A small runtime for the Claude Design boards in /design (built into /public/site by scripts/build_site.py).
   It renders a board's template (<template id="tpl">) with its Component class: {{bindings}}, <sc-if>, <sc-for>,
   refs, event handlers, and setState re-renders that patch the DOM in place, so canvases, scroll positions and
   inputs survive. Theme changes are passed down to embedded boards (the demo inside the landing page). */
(function () {
  'use strict';
  function DCLogic(props) { this.props = props || {}; this.state = {}; }
  DCLogic.prototype.setState = function (patch) { Object.assign(this.state, typeof patch === 'function' ? patch(this.state) : patch); schedule(); };
  window.DCLogic = DCLogic;

  var comp = null, pending = false, tpl = null, app = null;
  function schedule() { if (pending) return; pending = true; Promise.resolve().then(function () { pending = false; render(); }); }

  function lookup(expr, scopes) {
    expr = expr.trim();
    if (expr === 'true') return true; if (expr === 'false') return false;
    var path = expr.split('.');
    for (var i = scopes.length - 1; i >= 0; i--) {
      var s = scopes[i];
      if (s && typeof s === 'object' && path[0] in s) return path.reduce(function (a, k) { return a == null ? a : a[k]; }, s);
    }
    return undefined;
  }
  function interp(str, scopes) {
    var whole = str.match(/^\s*\{\{([^}]+)\}\}\s*$/);
    if (whole) return lookup(whole[1], scopes);
    return str.replace(/\{\{([^}]+)\}\}/g, function (_, e) { var v = lookup(e, scopes); return v == null ? '' : v; });
  }
  function bindEvent(el, type) {
    el.__h = el.__h || {};
    if (el.__bound && el.__bound[type]) return;
    el.__bound = el.__bound || {}; el.__bound[type] = true;
    el.addEventListener(type, function (e) { var h = (e.currentTarget.__h || {})[type]; if (typeof h === 'function') h(e); });
  }
  function build(node, scopes, out) {
    node.childNodes.forEach(function (ch) {
      if (ch.nodeType === 3) { out.appendChild(document.createTextNode(interp(ch.textContent, scopes))); return; }
      if (ch.nodeType !== 1) return;
      var tag = ch.tagName.toLowerCase();
      if (tag === 'sc-if') { if (interp(ch.getAttribute('value'), scopes)) build(ch, scopes, out); return; }
      if (tag === 'sc-for') {
        var list = interp(ch.getAttribute('list'), scopes) || [], as = ch.getAttribute('as');
        list.forEach(function (it) { var sc = {}; sc[as] = it; build(ch, scopes.concat([sc]), out); });
        return;
      }
      var el = ch.cloneNode(false);
      Array.prototype.slice.call(ch.attributes).forEach(function (a) {
        var n = a.name;
        if (n.indexOf('hint-') === 0) { el.removeAttribute(n); return; }
        if (n.indexOf('on') === 0) { el.removeAttribute(n); var fn = interp(a.value, scopes), type = n.slice(2); el.__h = el.__h || {}; el.__h[type] = fn; bindEvent(el, type); return; }
        if (n === 'ref') { el.removeAttribute(n); var rf = interp(a.value, scopes); if (typeof rf === 'function') el.__ref = rf; return; }
        el.setAttribute(n, interp(a.value, scopes));
      });
      if (tag === 'textarea') { el.textContent = interp(ch.textContent, scopes); out.appendChild(el); return; }
      build(ch, scopes, el); out.appendChild(el);
    });
  }
  function fresh(n) { if (n.nodeType !== 1) return; Array.prototype.slice.call(n.children).forEach(fresh); if (n.__ref) n.__ref(n); }
  function morph(oldP, newP) {
    var ok = Array.prototype.slice.call(oldP.childNodes), nk = Array.prototype.slice.call(newP.childNodes);
    nk.forEach(function (n, i) {
      var o = ok[i];
      if (!o) { oldP.appendChild(n); fresh(n); return; }
      var keyChanged = n.nodeType === 1 && o.nodeType === 1 && n.getAttribute('key') !== o.getAttribute('key');
      if (o.nodeType !== n.nodeType || o.nodeName !== n.nodeName || keyChanged) { oldP.replaceChild(n, o); fresh(n); return; }
      if (n.nodeType === 3) { if (o.textContent !== n.textContent) o.textContent = n.textContent; return; }
      if (n.nodeType !== 1) return;
      Array.prototype.slice.call(n.attributes).forEach(function (a) { if (o.getAttribute(a.name) !== a.value) o.setAttribute(a.name, a.value); });
      if (n.__h) { o.__h = n.__h; Object.keys(n.__h).forEach(function (t) { bindEvent(o, t); }); }
      if (o.tagName === 'TEXTAREA' || o.tagName === 'INPUT') return;
      morph(o, n);
    });
    for (var i = nk.length; i < ok.length; i++) ok[i].remove();
  }
  function render() {
    var vals = comp.renderVals(), frag = document.createElement('div');
    build(tpl.content, [vals], frag);
    morph(app, frag);
  }
  function mount() {
    tpl = document.getElementById('tpl'); app = document.getElementById('app');
    var props = JSON.parse(document.body.getAttribute('data-props') || '{}');
    comp = new window.Component(props);
    render(); fresh(app);
    if (comp.componentDidMount) comp.componentDidMount();
    window.comp = comp;
  }

  // light/dark: pass the choice on to embedded boards, and take it from a parent page
  window.addEventListener('clawback-theme', function (e) {
    Array.prototype.forEach.call(document.querySelectorAll('iframe'), function (f) { try { f.contentWindow.postMessage({ clawbackTheme: e.detail }, '*'); } catch (err) {} });
  });
  window.addEventListener('message', function (e) {
    if (e.data && e.data.clawbackTheme && window.parent !== window) window.dispatchEvent(new CustomEvent('clawback-theme', { detail: e.data.clawbackTheme }));
  });

  // fixed-size boards (the demo is 1280x800) scale to fit their window
  function fit() {
    var spec = document.body.getAttribute('data-fit'); if (!spec) return;
    var wh = spec.split('x'), w = +wh[0], h = +wh[1], k = Math.min(window.innerWidth / w, window.innerHeight / h);
    app.style.width = w + 'px'; app.style.height = h + 'px'; app.style.transformOrigin = '0 0';
    app.style.transform = 'scale(' + k + ')';
    app.style.marginLeft = Math.max(0, (window.innerWidth - w * k) / 2) + 'px'; app.style.marginTop = Math.max(0, (window.innerHeight - h * k) / 2) + 'px';
  }
  window.__dcMount = function () { mount(); fit(); window.addEventListener('resize', fit); };
})();
