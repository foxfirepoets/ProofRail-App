/* STV Dashboard shared data layer — live Supabase (PostgREST) reads.
 * Read-only. PUBLISHABLE keys only (safe for client HTML; RLS/anon governed).
 * Exposes window.STV: { A, B, rows(), count(), health(), fmtMoney(), fmtDate(), ago() }.
 *
 * NOTE: the dashboard pages are self-contained bundler output whose <script>
 * src is rewritten from a manifest, so relative file:// loading of this file is
 * unreliable. The SAME helper is therefore inlined into each page's
 * `text/x-dc` logic block. This file is the canonical source of that helper.
 */
(function (root) {
  var STV = {
    A: { ref: 'ejxrbxoncsgglrqvjulr', key: 'sb_publishable_QY_6z8pMe5az_S1E2-wbxQ__MM_JmFD' }, // Gmail Automation
    B: { ref: 'fdnwlcomuddzmluvbylg', key: 'sb_publishable_92eXLW0-VrmURZAnZQ4eFg_4FauDR_W' }  // QB / AI Accounting Hub
  };

  function base(proj) { return 'https://' + proj.ref + '.supabase.co/rest/v1/'; }
  function headers(proj, extra) {
    var h = { apikey: proj.key, Authorization: 'Bearer ' + proj.key };
    if (extra) for (var k in extra) h[k] = extra[k];
    return h;
  }

  // rows(project, table, {select, order, limit, embed, filter})
  STV.rows = function (proj, table, opts) {
    opts = opts || {};
    var sel = opts.select || '*';
    if (opts.embed) sel += ',' + opts.embed;
    var qs = 'select=' + encodeURIComponent(sel);
    qs += '&order=' + encodeURIComponent(opts.order || 'created_at.desc');
    qs += '&limit=' + (opts.limit || 200);
    if (opts.filter) qs += '&' + opts.filter;
    return fetch(base(proj) + table + '?' + qs, { headers: headers(proj) })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status + ' ' + table);
        return r.json();
      });
  };

  // count(project, table, filter?) -> integer total via Content-Range
  STV.count = function (proj, table, filter) {
    var qs = 'select=*&limit=1';
    if (filter) qs += '&' + filter;
    return fetch(base(proj) + table + '?' + qs,
      { headers: headers(proj, { Prefer: 'count=exact' }) })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status + ' ' + table);
        var cr = r.headers.get('content-range') || '';
        var total = cr.split('/')[1];
        return total ? parseInt(total, 10) : 0;
      });
  };

  // health(url) -> {status, version} (QBWC railway /health)
  STV.health = function (url) {
    return fetch(url, { headers: { Accept: 'application/json' } })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
  };

  // ---- display formatters ----
  STV.fmtMoney = function (v) {
    if (v === null || v === undefined || v === '') return '—';
    var n = typeof v === 'number' ? v : parseFloat(v);
    if (isNaN(n)) return '—';
    return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };
  STV.fmtInt = function (v) {
    var n = typeof v === 'number' ? v : parseInt(v, 10);
    if (isNaN(n)) return '0';
    return n.toLocaleString('en-US');
  };
  STV.fmtDate = function (v) {
    if (!v) return '—';
    var d = new Date(v);
    if (isNaN(d.getTime())) return '—';
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };
  STV.ago = function (v) {
    if (!v) return '—';
    var d = new Date(v); if (isNaN(d.getTime())) return '—';
    var s = Math.floor((Date.now() - d.getTime()) / 1000);
    if (s < 60) return s + 's ago';
    if (s < 3600) return Math.floor(s / 60) + 'm ago';
    if (s < 86400) return Math.floor(s / 3600) + 'h ago';
    return Math.floor(s / 86400) + 'd ago';
  };
  STV.titleCase = function (s) {
    if (!s) return '—';
    return String(s).replace(/[_-]/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  };

  root.STV = STV;
})(typeof window !== 'undefined' ? window : this);
