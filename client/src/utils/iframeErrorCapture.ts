export const injectErrorCaptureScript = (htmlContent: string): string => {
    const errorCaptureScript = `
    <script>
      (function() {
        let errorCount = 0;
        let capturedErrors = [];
        // In srcdoc iframes, origin is the string "null", not actual null
        const origin = window.location.origin;
        const targetOrigin = (origin && origin !== 'null') ? origin : '*';

        function reportError(error) {
          errorCount++;
          capturedErrors.push(error);
          try {
            window.parent.postMessage({ type: 'iframe-error', error }, targetOrigin);
          } catch (e) {
            // If postMessage fails, at least store the error
            console.error('[ErrorCapture] Failed to report error:', error);
          }
        }

        // Store original methods early to ensure we can use them even if something breaks
        const originalError = console.error;
        const originalWarn = console.warn;
        const originalLog = console.log;

        // 1. Capture runtime JS errors
        window.onerror = function(message, source, lineno, colno, error) {
          let errorMessage = message;
          let errorStack = undefined;

          // If we have an error object, extract the details
          if (error instanceof Error) {
            errorMessage = error.message || message;
            errorStack = error.stack;
          } else if (error) {
            // For other error types, try to extract message
            errorMessage = error.message || String(error) || message;
            errorStack = error.stack;
          }

          reportError({
            type: 'onerror',
            message: errorMessage,
            source,
            lineno,
            colno,
            stack: errorStack
          });
          return false; // keep default behavior too
        };

        window.addEventListener('error', function(event) {
          // Distinguish between JS runtime errors vs resource load errors
          if (event.target && (event.target.src || event.target.href)) {
            // Resource load error (scripts, images, stylesheets)
            reportError({
              type: 'resource',
              tag: event.target.tagName,
              url: event.target.src || event.target.href
            });
          } else {
            // JS runtime error
            reportError({
              type: 'error',
              message: event.message,
              source: event.filename,
              lineno: event.lineno,
              colno: event.colno,
              stack: event.error ? event.error.stack : undefined
            });
          }
        }, true);

        // 2. Capture unhandled promise rejections
        window.addEventListener('unhandledrejection', function(event) {
          let errorMessage = 'Unhandled Promise Rejection';
          let errorStack = undefined;

          if (event.reason) {
            if (event.reason instanceof Error) {
              errorMessage = event.reason.message || String(event.reason);
              errorStack = event.reason.stack;
            } else if (typeof event.reason === 'object') {
              errorMessage = event.reason.message || JSON.stringify(event.reason);
              errorStack = event.reason.stack;
            } else {
              errorMessage = String(event.reason);
            }
          }

          reportError({
            type: 'unhandledRejection',
            message: errorMessage,
            stack: errorStack
          });
        });

        // 3. Capture all console output (errors, warnings, logs with error context)
        const originalInfo = console.info || console.log;
        const originalDebug = console.debug || console.log;

        function formatConsoleArgs(args) {
          return Array.from(args).map(arg => {
            // Handle null and undefined
            if (arg === null) return 'null';
            if (arg === undefined) return 'undefined';

            // Handle Error objects specially - they don't serialize well to JSON
            if (arg instanceof Error) {
              const errorInfo = {
                name: arg.name || 'Error',
                message: arg.message || String(arg),
                stack: arg.stack
              };
              const stackStr = errorInfo.stack ? '\\n' + errorInfo.stack : '';
              return errorInfo.name + ': ' + errorInfo.message + stackStr;
            }

            // Handle plain objects
            if (typeof arg === 'object') {
              try {
                // Check if object has any properties
                const keys = Object.keys(arg);
                if (keys.length === 0) {
                  // Empty object
                  return '{}';
                }
                // Try to extract meaningful error info from plain objects
                if (arg.message || arg.error || arg.err) {
                  return arg.message || arg.error || arg.err;
                }
                return JSON.stringify(arg);
              } catch {
                return String(arg);
              }
            }

            return String(arg);
          }).join(' ');
        }

        console.error = function() {
          try {
            const message = formatConsoleArgs(arguments);
            reportError({
              type: 'console',
              message: 'Console Error: ' + message
            });
            originalError.apply(console, arguments);
          } catch (e) {
            originalError.apply(console, arguments);
          }
        };

        console.warn = function() {
          try {
            // Don't report warnings to avoid noise - only capture errors
            originalWarn.apply(console, arguments);
          } catch (e) {
            originalWarn.apply(console, arguments);
          }
        };

        // Capture logs and info that contain error-related keywords
        console.log = function() {
          try {
            const message = formatConsoleArgs(arguments);
            // Capture logs that appear to be error-related (contain brackets or keywords)
            if (message.includes('[') || message.toLowerCase().includes('error') ||
                message.toLowerCase().includes('fail') || message.toLowerCase().includes('unable')) {
              reportError({
                type: 'console',
                message: 'Console Log: ' + message
              });
            }
            originalLog.apply(console, arguments);
          } catch (e) {
            originalLog.apply(console, arguments);
          }
        };

        console.info = function() {
          try {
            const message = formatConsoleArgs(arguments);
            // Capture info that contains error-related keywords
            if (message.toLowerCase().includes('error') || message.toLowerCase().includes('fail')) {
              reportError({
                type: 'console',
                message: 'Console Info: ' + message
              });
            }
            originalInfo.apply(console, arguments);
          } catch (e) {
            originalInfo.apply(console, arguments);
          }
        };

        console.debug = function() {
          try {
            const message = formatConsoleArgs(arguments);
            // Capture debug messages with errors
            if (message.toLowerCase().includes('error') || message.toLowerCase().includes('fail')) {
              reportError({
                type: 'console',
                message: 'Console Debug: ' + message
              });
            }
            originalDebug.apply(console, arguments);
          } catch (e) {
            originalDebug.apply(console, arguments);
          }
        };

        // 4. Capture errors that happen during DOMContentLoaded
        document.addEventListener('DOMContentLoaded', function() {
          try {
            window.parent.postMessage({
              type: 'iframe-status',
              status: 'dom-loaded',
              errorCount: errorCount
            }, targetOrigin);
          } catch (e) {
            // Silently fail
          }
        }, true);

        // Send a signal to parent that error capture is active
        try {
          window.parent.postMessage({
            type: 'iframe-error-capture-ready'
          }, targetOrigin);
        } catch (e) {
          // Silently fail if can't communicate with parent
        }

        // 4. Notify parent when iframe is ready
        window.addEventListener('load', function() {
          window.parent.postMessage({
            type: 'iframe-status',
            status: errorCount === 0 ? 'no-errors' : 'errors-detected',
            errorCount
          }, targetOrigin);
        });

        // 5. PDF Data Ready Detection
        // Signal when all content is loaded for PDF generation
        (function() {
          let dataReadyCheckInterval;
          let consecutiveReadyChecks = 0;
          const REQUIRED_CONSECUTIVE_CHECKS = 3; // Must be stable for 3 checks

          function checkIfDataReady() {
            // Check if React root has mounted
            const root = document.getElementById('root');
            if (!root || root.children.length === 0) {
              consecutiveReadyChecks = 0;
              return false;
            }

            // Check for common dashboard elements
            const hasDashboardContent =
              document.querySelector('div.dashboard, div[class*="dashboard"], div.container') ||
              document.querySelector('canvas, svg') || // Charts
              document.querySelector('.text-2xl, h1, h2, h3') || // Text content
              document.querySelector('[data-chart], [data-query]'); // Data elements

            // Check if there are any loading states
            const hasLoadingStates =
              document.querySelector('[class*="loading"], [class*="Loading"]') ||
              document.querySelector('[class*="spinner"], [class*="Spinner"]') ||
              document.querySelector('[aria-busy="true"]');

            // Check if images are still loading
            const images = Array.from(document.querySelectorAll('img'));
            const imagesLoaded = images.length === 0 || images.every(img => img.complete);

            const isReady = hasDashboardContent && !hasLoadingStates && imagesLoaded;

            if (isReady) {
              consecutiveReadyChecks++;
              if (consecutiveReadyChecks >= REQUIRED_CONSECUTIVE_CHECKS) {
                window.pdfDataReady = true;
                if (dataReadyCheckInterval) {
                  clearInterval(dataReadyCheckInterval);
                }
              }
            } else {
              consecutiveReadyChecks = 0;
            }

            return isReady;
          }

          // Start checking after a short delay to let React initialize
          setTimeout(() => {
            // Check immediately
            if (checkIfDataReady()) {
              return;
            }

            // Then check periodically
            dataReadyCheckInterval = setInterval(checkIfDataReady, 500);

            // Timeout after 30 seconds
            setTimeout(() => {
              if (!window.pdfDataReady) {
                window.pdfDataReady = true;
                if (dataReadyCheckInterval) {
                  clearInterval(dataReadyCheckInterval);
                }
              }
            }, 30000);
          }, 1000);
        })();
      })();
    </script>
  `;

    // Inject at the very beginning to catch errors as early as possible
    if (htmlContent.includes('<head>')) {
        // Replace <head> with <head> + script to ensure it runs before any other head content
        return htmlContent.replace('<head>', `<head>${errorCaptureScript}`);
    } else if (htmlContent.includes('<body>')) {
        // If no head, inject before body
        return htmlContent.replace('<body>', `<head>${errorCaptureScript}</head><body>`);
    } else if (htmlContent.includes('<html>')) {
        // If no head or body, inject right after html tag
        return htmlContent.replace('<html>', `<html><head>${errorCaptureScript}</head>`);
    } else {
        // Wrap entire content with proper structure and inject script
        return `<!DOCTYPE html>
<html>
<head>${errorCaptureScript}</head>
<body>${htmlContent}</body>
</html>`;
    }
};
