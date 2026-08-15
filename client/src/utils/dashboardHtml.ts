import { isTauriApp, getBackendUrl } from '../lib/tauri-api'
import type { DashboardFilterDefinition } from '../services/api'

const getDefaultBackendUrl = (): string => {
  if (typeof window !== 'undefined' && !isTauriApp()) {
    return window.location.origin
  }
  return 'http://127.0.0.1:8000'
}

const normalizeBackendUrl = (url?: string): string => {
  if (!url) {
    return getDefaultBackendUrl()
  }
  try {
    const parsed = new URL(url.startsWith('http') || url.startsWith('ws') ? url : `http://${url}`)
    return `${parsed.protocol}//${parsed.hostname}${parsed.port ? `:${parsed.port}` : ''}`
  } catch (error) {
    console.warn('Failed to normalize backend URL, falling back to default', { url, error })
    return getDefaultBackendUrl()
  }
}

const normalizeViewerApiBase = (apiBase?: string): string => {
  const normalizedBackend = normalizeBackendUrl()
  const fallback = `${normalizedBackend.replace(/\/$/, '')}/api/viewer`
  if (!apiBase) {
    return fallback
  }

  const trimmed = apiBase.replace(/\/$/, '')
  if (/^https?:\/\//i.test(trimmed)) {
    return trimmed
  }
  if (trimmed.startsWith('/')) {
    return `${normalizedBackend.replace(/\/$/, '')}${trimmed}`
  }
  return trimmed
}

export const getBackendUrlForHtmlProcessing = async (): Promise<string | undefined> => {
  if (isTauriApp()) {
    return getBackendUrl()
  }
  return undefined
}

const ABSOLUTE_PATTERN = /(https?:|wss?:)?\/\/(localhost|127\.0\.0\.1|0\.0\.0\.0)(?::(\d+))?/gi
const BARE_PATTERN = /(?<![\w.])(localhost|127\.0\.0\.1|0\.0\.0\.0)(?::(\d+))?/gi

export const rewriteDashboardHtmlForBackend = (htmlContent: string, backendUrl?: string): string => {
  if (!htmlContent) {
    return htmlContent
  }

  const normalized = normalizeBackendUrl(backendUrl)
  let target: URL
  try {
    target = new URL(normalized)
  } catch (error) {
    console.warn('Failed to parse backend URL, skipping HTML rewrite', { backendUrl, error })
    return htmlContent
  }

  let rewritten = htmlContent.replace(ABSOLUTE_PATTERN, (_match, protocolGroup: string | undefined) => {
    const protocol = protocolGroup ? `${protocolGroup}` : `${target.protocol.replace(/:$/, '')}:`
    const isWebSocket = protocol.startsWith('ws')
    const derivedProtocol = isWebSocket ? (target.protocol === 'https:' ? 'wss:' : 'ws:') : `${target.protocol.replace(/:$/, '')}:`
    const finalProtocol = protocolGroup ? protocol : derivedProtocol
    const host = target.hostname
    const port = target.port ? `:${target.port}` : ''
    return `${finalProtocol}//${host}${port}`
  })

  rewritten = rewritten.replace(BARE_PATTERN, () => {
    const host = target.hostname
    const port = target.port ? `:${target.port}` : ''
    return `${host}${port}`
  })

  return rewritten
}

export const ensureBaseHref = (htmlContent: string, backendUrl?: string): string => {
  if (!htmlContent) {
    return htmlContent
  }

  const normalizedBase = normalizeBackendUrl(backendUrl)
  const baseAttr = `${normalizedBase.replace(/\/$/, '')}/`

  if (/<base\s+href=/i.test(htmlContent)) {
    return htmlContent
  }

  if (/<head[^>]*>/i.test(htmlContent)) {
    return htmlContent.replace(/<head([^>]*)>/i, `<head$1><base href="${baseAttr}">`)
  }

  return `<!DOCTYPE html><html><head><base href="${baseAttr}"></head>${htmlContent.includes('<body') ? htmlContent : `<body>${htmlContent}</body>`}</html>`
}

const escapeForScript = (value: string): string =>
  value.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/'/g, "\\'")

const serializeForScript = (value: unknown): string => JSON.stringify(value).replace(/</g, '\\u003c')

export const injectViewerConfig = (
  htmlContent: string,
  dashboardId?: string,
  apiBase: string = normalizeViewerApiBase(),
  fetchCredentials: 'omit' | 'same-origin' | 'include' = 'same-origin',
  tenantId?: string | null,
  initialFilterValues?: Record<string, unknown> | null,
  filterDefinitions?: DashboardFilterDefinition[] | null,
): string => {
  if (!htmlContent) return htmlContent

  const safeDashboardId = dashboardId ? escapeForScript(dashboardId) : ''
  const safeApiBase = escapeForScript(normalizeViewerApiBase(apiBase))
  const safeCredentials = escapeForScript(fetchCredentials)
  const safeTenantId = tenantId ? escapeForScript(tenantId) : ''
  const serializedInitialFilterValues = serializeForScript(initialFilterValues || {})
  const serializedFilterDefinitions = serializeForScript(filterDefinitions || [])

  const viewerScript = `
  <script>
    (function() {
      window.__VIEWER_DASHBOARD_ID__ = "${safeDashboardId}";
      window.__VIEWER_API_BASE__ = "${safeApiBase}";
      window.__VIEWER_FETCH_CREDENTIALS__ = "${safeCredentials}";
      window.__VIEWER_TENANT_ID__ = "${safeTenantId}";
      var initialParentFilterValues = ${serializedInitialFilterValues};
      var parentFilterDefinitions = ${serializedFilterDefinitions};

      function normalizeIncomingFilterDefinitions(definitions) {
        if (!Array.isArray(definitions)) return null;
        var normalized = [];
        for (var i = 0; i < definitions.length; i += 1) {
          var item = definitions[i];
          if (!item || typeof item !== 'object') continue;
          var id = String(item.id || '').trim();
          var queryId = String(item.query_id || '').trim();
          if (!id || !queryId) continue;
          normalized.push(item);
        }
        return normalized;
      }
      var dashboardIdForFilters = window.__VIEWER_DASHBOARD_ID__ || '';
      var filterStorageKey = '__byaan_parent_filters__' + dashboardIdForFilters;

      function cloneObject(value) {
        if (!value || typeof value !== 'object') return {};
        try {
          return JSON.parse(JSON.stringify(value));
        } catch (e) {
          return {};
        }
      }

      function isEmptyFilterValue(value) {
        if (value === null || value === undefined) return true;
        if (typeof value === 'string') return value.trim() === '';
        if (Array.isArray(value)) return value.length === 0;
        return false;
      }

      function hasActiveFilters(values) {
        if (!values || typeof values !== 'object') return false;
        for (var key in values) {
          if (!Object.prototype.hasOwnProperty.call(values, key)) continue;
          if (!isEmptyFilterValue(values[key])) return true;
        }
        return false;
      }

      function readStoredParentFilters() {
        try {
          var raw = window.sessionStorage.getItem(filterStorageKey);
          if (!raw) return null;
          var parsed = JSON.parse(raw);
          return parsed && typeof parsed === 'object' ? parsed : null;
        } catch (e) {
          return null;
        }
      }

      function persistParentFilters(values) {
        try {
          window.sessionStorage.setItem(filterStorageKey, JSON.stringify(values || {}));
        } catch (e) {}
      }

      var storedParentFilters = readStoredParentFilters();
      window.__PARENT_FILTER_VALUES__ = hasActiveFilters(storedParentFilters || {})
        ? cloneObject(storedParentFilters)
        : cloneObject(initialParentFilterValues || {});
      persistParentFilters(window.__PARENT_FILTER_VALUES__);

      function mergeParentFiltersIntoBody(parsedBody) {
        if (!parsedBody || typeof parsedBody !== 'object') return parsedBody;
        var parentFilterValues = window.__PARENT_FILTER_VALUES__ || {};
        if (!hasActiveFilters(parentFilterValues)) return parsedBody;

        function keyMatchesQuery(filterKey, queryId) {
          if (!queryId || !Array.isArray(parentFilterDefinitions) || parentFilterDefinitions.length === 0) {
            return false;
          }
          var baseKey = String(filterKey || '')
            .replace(/_start$/, '')
            .replace(/_end$/, '')
            .replace(/_min$/, '')
            .replace(/_max$/, '');
          for (var index = 0; index < parentFilterDefinitions.length; index += 1) {
            var definition = parentFilterDefinitions[index];
            if (!definition || typeof definition !== 'object') continue;
            if (String(definition.id || '') !== baseKey) continue;
            if (String(definition.query_id || '') === String(queryId)) return true;
          }
          return false;
        }

        function buildScopedFilterValues(queryId) {
          var scoped = {};
          for (var key in parentFilterValues) {
            if (!Object.prototype.hasOwnProperty.call(parentFilterValues, key)) continue;
            if (!keyMatchesQuery(key, queryId)) continue;
            scoped[key] = parentFilterValues[key];
          }
          return scoped;
        }

        var body = cloneObject(parsedBody);
        if (Array.isArray(body.queries_with_filters)) {
          body.queries_with_filters = body.queries_with_filters.map(function(queryEntry) {
            if (!queryEntry || typeof queryEntry !== 'object') return queryEntry;
            var nextEntry = cloneObject(queryEntry);
            var scopedFilterValues = buildScopedFilterValues(nextEntry.query_id);
            if (!hasActiveFilters(scopedFilterValues)) {
              if (nextEntry.filter_values) {
                delete nextEntry.filter_values;
              }
              return nextEntry;
            }
            var existingValues = nextEntry.filter_values && typeof nextEntry.filter_values === 'object'
              ? nextEntry.filter_values
              : {};
            nextEntry.filter_values = Object.assign({}, existingValues, scopedFilterValues);
            if (Array.isArray(nextEntry.filters)) {
              nextEntry.filters = [];
            }
            return nextEntry;
          });
          return body;
        }

        if (Array.isArray(body.query_ids)) {
          body.queries_with_filters = body.query_ids.map(function(queryId) {
            var scopedFilterValues = buildScopedFilterValues(queryId);
            return {
              query_id: queryId,
              filter_values: cloneObject(scopedFilterValues),
              filters: []
            };
          });
        }

        return body;
      }

      function normalizeBatchResponse(response) {
        if (!response || typeof response.clone !== 'function' || typeof Response === 'undefined') {
          return Promise.resolve(response);
        }
        if (response.ok === false) {
          return Promise.resolve(createViewerBatchErrorResponse(response, 'Dashboard data request failed'));
        }
        try {
          return response.clone().json().then(function(payload) {
            if (!payload || typeof payload !== 'object') {
              return response;
            }
            var hasPartialSuccess = payload.partial_success === true;
            var hasSuccessfulQueries = Number(payload.successful_queries || 0) > 0;
            if (!hasPartialSuccess || !hasSuccessfulQueries || payload.success === true) {
              return response;
            }

            var normalized = Object.assign({}, payload, {
              success: true,
              _viewer_partial_success: true,
            });

            var headers = new Headers(response.headers || {});
            headers.set('content-type', 'application/json');
            headers.delete('content-length');
            return new Response(JSON.stringify(normalized), {
              status: response.status,
              statusText: response.statusText,
              headers: headers,
            });
          }).catch(function(error) {
            return createViewerBatchErrorResponse(response, 'Dashboard data response was not JSON', error);
          });
        } catch (e) {
          return Promise.resolve(createViewerBatchErrorResponse(response, 'Dashboard data response could not be read', e));
        }
      }

      function createViewerBatchErrorResponse(response, message, error) {
        if (typeof Response === 'undefined') {
          return response;
        }

        var status = response && typeof response.status === 'number' ? response.status : 0;
        var payload = {
          success: false,
          message: message || 'Dashboard data request failed',
          data: [],
          partial_success: false,
          total_queries: 0,
          successful_queries: 0,
          failed_queries: 0,
          total_execution_time_ms: 0,
          _viewer_fetch_error: true,
          _viewer_status: status,
          _viewer_error: error && error.message ? String(error.message) : null
        };

        var headers = typeof Headers !== 'undefined'
          ? new Headers({ 'content-type': 'application/json' })
          : { 'content-type': 'application/json' };

        return new Response(JSON.stringify(payload), {
          status: 200,
          statusText: 'OK',
          headers: headers,
        });
      }

      function waitForViewerRetry(delayMs) {
        return new Promise(function(resolve) {
          setTimeout(resolve, delayMs);
        });
      }

      function shouldRetryViewerBatchResponse(response) {
        if (!response) return true;
        var status = typeof response.status === 'number' ? response.status : 0;
        return status === 0 || status === 400 || status === 408 || status === 409 || status === 429 || status >= 500;
      }

      function fetchViewerBatchWithRetry(fetchThis, fetchInput, fetchInit, attempt) {
        var currentAttempt = attempt || 0;
        var retryDelays = [350, 1000, 2500];
        return originalFetch.call(fetchThis, fetchInput, fetchInit).then(function(response) {
          if (shouldRetryViewerBatchResponse(response) && currentAttempt < retryDelays.length) {
            return waitForViewerRetry(retryDelays[currentAttempt]).then(function() {
              return fetchViewerBatchWithRetry(fetchThis, fetchInput, fetchInit, currentAttempt + 1);
            });
          }
          return normalizeBatchResponse(response);
        }).catch(function(error) {
          if (currentAttempt < retryDelays.length) {
            return waitForViewerRetry(retryDelays[currentAttempt]).then(function() {
              return fetchViewerBatchWithRetry(fetchThis, fetchInput, fetchInit, currentAttempt + 1);
            });
          }
          return createViewerBatchErrorResponse(null, 'Dashboard data request failed', error);
        });
      }

      var originalFetch = window.fetch;
      if (typeof originalFetch === 'function') {
        window.fetch = function(input, init) {
          var isViewerBatchRequest = false;
          try {
            var urlStr = input && typeof input === 'object' && input.url ? String(input.url) : String(input);
            var apiBase = String(window.__VIEWER_API_BASE__ || '/api/viewer').replace(/\\/$/, '');
            var dashboardId = window.__VIEWER_DASHBOARD_ID__;
            var relativeViewerApiBase = '/api/viewer';

            function getViewerOrigin() {
              try {
                if (window.location && window.location.origin && window.location.origin !== 'null') {
                  return window.location.origin;
                }
              } catch (e) {}
              try {
                if (window.parent && window.parent.location && window.parent.location.origin && window.parent.location.origin !== 'null') {
                  return window.parent.location.origin;
                }
              } catch (e) {}
              return '';
            }

            function toAbsoluteViewerUrl(value) {
              var text = String(value || '');
              if (text.indexOf(relativeViewerApiBase) === 0) {
                var origin = getViewerOrigin();
                return origin ? origin + text : text;
              }
              return text;
            }

            apiBase = toAbsoluteViewerUrl(apiBase).replace(/\\/$/, '');

            // Redirect /api/queries/batch to viewer batch endpoint
            if (dashboardId && (urlStr === '/api/queries/batch' || urlStr.endsWith('/api/queries/batch'))) {
              input = apiBase + '/dashboards/' + dashboardId + '/queries/batch';
              urlStr = input;
            }

            var isViewerRequest = urlStr.startsWith(apiBase) || urlStr.startsWith(relativeViewerApiBase);
            if (isViewerRequest) {
              if (urlStr.startsWith(relativeViewerApiBase)) {
                input = toAbsoluteViewerUrl(urlStr);
                urlStr = String(input);
              }
              isViewerBatchRequest = urlStr.indexOf('/queries/batch') !== -1;
              init = init || {};
              if (!init.credentials) {
                init.credentials = window.__VIEWER_FETCH_CREDENTIALS__ || 'same-origin';
              }
              if (window.__VIEWER_TENANT_ID__) {
                init.headers = init.headers || {};
                if (typeof init.headers.get === 'function') {
                  if (!init.headers.get('X-Tenant-ID')) {
                    init.headers.set('X-Tenant-ID', window.__VIEWER_TENANT_ID__);
                  }
                } else if (!init.headers['X-Tenant-ID']) {
                  init.headers['X-Tenant-ID'] = window.__VIEWER_TENANT_ID__;
                }
              }

              if (typeof init.body === 'string' && urlStr.indexOf('/queries/batch') !== -1) {
                try {
                  var parsedBody = JSON.parse(init.body);
                  var mergedBody = mergeParentFiltersIntoBody(parsedBody);
                  init.body = JSON.stringify(mergedBody);
                } catch (e) {}
              }
            }
          } catch (e) {}
          if (isViewerBatchRequest) {
            return fetchViewerBatchWithRetry(this, input, init, 0);
          }
          return originalFetch.call(this, input, init);
        };
      }

      window.addEventListener('message', function(event) {
        var data = event && event.data;
        if (!data || typeof data !== 'object') return;
        if (data.type !== 'dashboard.filters.update.v1') return;
        if (data.dashboardId && window.__VIEWER_DASHBOARD_ID__ && data.dashboardId !== window.__VIEWER_DASHBOARD_ID__) return;

        var incomingValues = data.filterValues && typeof data.filterValues === 'object' ? data.filterValues : {};
        var incomingDefinitions = normalizeIncomingFilterDefinitions(data.filterDefinitions);
        if (incomingDefinitions) {
          parentFilterDefinitions = incomingDefinitions;
        }
        window.__PARENT_FILTER_VALUES__ = cloneObject(incomingValues);
        persistParentFilters(window.__PARENT_FILTER_VALUES__);

        try {
          if (event.source && typeof event.source.postMessage === 'function') {
            event.source.postMessage({
              type: 'dashboard.filters.ack.v1',
              dashboardId: window.__VIEWER_DASHBOARD_ID__ || null,
              appliedFilterKeys: Object.keys(window.__PARENT_FILTER_VALUES__ || {}),
              timestamp: Date.now()
            }, '*');
          }
        } catch (e) {}

        if (data.reload === true) {
          setTimeout(function() {
            window.location.reload();
          }, 0);
        }
      });

      try {
        if (window.parent && window.parent !== window) {
          window.parent.postMessage({
            type: 'dashboard.filters.ready.v1',
            dashboardId: window.__VIEWER_DASHBOARD_ID__ || null,
            timestamp: Date.now()
          }, '*');
        }
      } catch (e) {}
    })();
  </script>`

  if (/<head[^>]*>/i.test(htmlContent)) {
    return htmlContent.replace(/<head([^>]*)>/i, `<head$1>${viewerScript}`)
  }

  return viewerScript + htmlContent
}
