export const injectAuthInterceptor = (
  htmlContent: string,
  authToken: string | null,
  tenantId?: string | null,
  dashboardId?: string | null
): string => {
  if (!htmlContent) return htmlContent

  const safeToken = authToken ? authToken.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/'/g, "\\'") : ''
  const safeTenantId = tenantId ? tenantId.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/'/g, "\\'") : ''
  const safeDashboardId = dashboardId ? dashboardId.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/'/g, "\\'") : ''

  const interceptorScript = `
  <script>
    (function() {
      var authToken = "${safeToken}";
      var tenantId = "${safeTenantId}";
      var dashboardId = "${safeDashboardId}";
      // Expose auth headers globally for dashboard code to use
      window.__AUTH_HEADERS__ = {};
      if (authToken) window.__AUTH_HEADERS__['Authorization'] = 'Bearer ' + authToken;
      if (tenantId) window.__AUTH_HEADERS__['X-Tenant-ID'] = tenantId;

      var originalFetch = window.fetch;
      window.fetch = function(url, options) {
        options = options || {};
        try {
          var urlStr = String(url);

          // For relative URLs, we need to check the pathname directly
          var isRelative = !urlStr.startsWith('http');
          var pathname = isRelative ? urlStr.split('?')[0] : new URL(urlStr).pathname;

          // Rewrite batch query endpoint to viewer endpoint when dashboardId is available
          if (pathname === '/api/queries/batch' && dashboardId) {
            urlStr = urlStr.replace('/api/queries/batch', '/api/viewer/dashboards/' + dashboardId + '/queries/batch');
            url = urlStr;
          }

          // Add auth headers for any /api/ requests
          if (pathname.startsWith('/api/')) {
            var headers = {};
            if (authToken) headers['Authorization'] = 'Bearer ' + authToken;
            if (tenantId) headers['X-Tenant-ID'] = tenantId;
            options.headers = Object.assign({}, options.headers, headers);
          }
        } catch (e) {}
        return originalFetch.call(this, url, options);
      };
    })();
  </script>`

  if (/<head[^>]*>/i.test(htmlContent)) {
    return htmlContent.replace(/<head([^>]*)>/i, `<head$1>${interceptorScript}`)
  }

  return interceptorScript + htmlContent
}
