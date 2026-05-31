/**
 * Generic API Interceptor to dynamically handle protocol/port mapping for local network streaming.
 * Intercepts window.fetch calls to dynamically rewrite outgoing URLs and incoming JSON response payloads.
 */
export class ApiInterceptor {
  static initialized = false;

  static initialize() {
    if (this.initialized) return;
    this.initialized = true;

    const originalFetch = window.fetch;

    window.fetch = async function (input, init) {
      let urlStr = typeof input === 'string' ? input : (input instanceof Request ? input.url : String(input));

      // 1. Skip intercepting for the network-info ping API to prevent infinite loops / wrong pings
      const isNetworkInfo = urlStr.includes('/api/network-info');

      // 2. Check if dynamic rewrite has been enabled via global variable
      if (window.activeApiBaseUrl && !isNetworkInfo) {
        try {
          const rewrittenUrl = ApiInterceptor.rewriteUrlString(urlStr, window.activeApiBaseUrl);

          let fetchInput = rewrittenUrl;
          if (input instanceof Request) {
            fetchInput = new Request(rewrittenUrl, input);
          }

          const response = await originalFetch(fetchInput, init);

          // 3. "also if there is a network 404 or something dont do it"
          // If response status is a 404, or is not successful, do not modify or do fallback
          if (response.ok && response.status !== 404) {
            return ApiInterceptor.rewriteResponseUrls(response, window.activeApiBaseUrl);
          }
          
          // If response is not ok or is 404, fall through to make the original call
        } catch (err) {
          console.warn("ApiInterceptor: Rewritten fetch failed, falling back to original URL.", err);
        }
      }

      // Fallback: Perform the original fetch using the original URL
      return originalFetch(input, init);
    };

    console.log("ApiInterceptor: Generic fetch interceptor initialized successfully.");
  }

  /**
   * Helper to rewrite protocol, domain, and port in URL string.
   */
  static rewriteUrlString(urlStr, targetBaseUrl) {
    try {
      const url = new URL(urlStr);
      const base = new URL(targetBaseUrl);
      url.protocol = base.protocol;
      url.host = base.host; // Copies hostname and port!
      return url.toString();
    } catch (e) {
      // Relative URL path fallback
      if (urlStr.startsWith('/')) {
        const cleanBase = targetBaseUrl.replace(/\/$/, "");
        return `${cleanBase}${urlStr}`;
      }
      return urlStr;
    }
  }

  /**
   * Monkeypatches the .json() method of response to recursively rewrite any matching URLs.
   */
  static async rewriteResponseUrls(response, targetBaseUrl) {
    const cloned = response.clone();
    const originalJson = cloned.json;

    cloned.json = async function () {
      const data = await originalJson.call(cloned);
      return ApiInterceptor.rewriteUrlsInObject(data, targetBaseUrl);
    };

    return cloned;
  }

  /**
   * Recursively traverses any JSON structure to rewrite absolute media/API URLs without hardcoding field names.
   */
  static rewriteUrlsInObject(obj, targetBaseUrl) {
    if (obj === null || obj === undefined) return obj;

    if (typeof obj === 'string') {
      // Match URLs that start with http/https and reference /media/ or /api/
      if ((obj.startsWith('http://') || obj.startsWith('https://')) && (obj.includes('/media/') || obj.includes('/api/'))) {
        return ApiInterceptor.rewriteUrlString(obj, targetBaseUrl);
      }
      return obj;
    }

    if (Array.isArray(obj)) {
      return obj.map(item => ApiInterceptor.rewriteUrlsInObject(item, targetBaseUrl));
    }

    if (typeof obj === 'object') {
      const newObj = {};
      for (const key in obj) {
        if (Object.prototype.hasOwnProperty.call(obj, key)) {
          newObj[key] = ApiInterceptor.rewriteUrlsInObject(obj[key], targetBaseUrl);
        }
      }
      return newObj;
    }

    return obj;
  }
}
