/**
 * Dedicated ConnectionManager class to handle dynamic switching between local IP and public domain.
 * Gracefully disconnects and reconnects based on reachability and IP changes.
 */
export class ConnectionManager {
  constructor(defaultDomain, onUrlChange) {
    this.defaultDomain = defaultDomain; // e.g. window.location.origin
    this.onUrlChange = onUrlChange;     // Callback when base URL changes
    this.currentBaseUrl = defaultDomain;
    this.serverLocalIp = null;
    this.sameNetwork = false;
    this.checkInterval = null;
    this.isChecking = false;
  }

  /**
   * Starts the automatic connection checking loop.
   */
  start() {
    this.checkConnection();
    // Check connection health every 10 seconds
    this.checkInterval = setInterval(() => {
      this.checkConnection();
    }, 10000);
  }

  /**
   * Stops the automatic connection checking loop.
   */
  stop() {
    if (this.checkInterval) {
      clearInterval(this.checkInterval);
    }
  }

  /**
   * Main checking algorithm.
   */
  async checkConnection() {
    if (this.isChecking) return;
    this.isChecking = true;

    try {
      // 1. Fetch network info from current active endpoint
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 2000);

      const response = await fetch(`${this.currentBaseUrl}/api/network-info`, { 
        signal: controller.signal 
      });
      clearTimeout(timeoutId);

      if (response.ok) {
        const data = await response.json();
        this.serverLocalIp = data.server_local_ip;
        
        // Active probing: Test if the client can hit the server's local IP on port 8000 directly.
        // This is 100% reliable for same local network detection, regardless of client IPv4/IPv6 format.
        let isLocalReachable = false;
        let localUrl = null;

        if (this.serverLocalIp) {
          localUrl = `${window.location.protocol}//${this.serverLocalIp}:8000`;
          isLocalReachable = await this.testUrl(localUrl);
        }

        const sameNetworkDetected = data.same_network || isLocalReachable;
        this.sameNetwork = sameNetworkDetected;

        if (sameNetworkDetected && localUrl && isLocalReachable) {
          if (this.currentBaseUrl !== localUrl) {
            console.log(`ConnectionManager: Switching to LOCAL IP: ${localUrl}`);
            this.currentBaseUrl = localUrl;
            if (this.onUrlChange) {
              this.onUrlChange(localUrl);
            }
          }
        } else {
          // If we are no longer on the same network or local IP is not reachable, revert to default domain
          if (this.currentBaseUrl !== this.defaultDomain) {
            console.log(`ConnectionManager: Reverting to DEFAULT domain (local not reachable/not same network): ${this.defaultDomain}`);
            this.currentBaseUrl = this.defaultDomain;
            if (this.onUrlChange) {
              this.onUrlChange(this.defaultDomain);
            }
          }
        }
      }
    } catch (err) {
      console.warn("ConnectionManager: Current base URL failed connection check.", err);
      // If current fails, try to fall back to the default domain (public domain)
      if (this.currentBaseUrl !== this.defaultDomain) {
        console.log(`ConnectionManager: Reverting to DEFAULT domain (fallback): ${this.defaultDomain}`);
        this.currentBaseUrl = this.defaultDomain;
        if (this.onUrlChange) {
          this.onUrlChange(this.defaultDomain);
        }
      }
    } finally {
      this.isChecking = false;
    }
  }

  /**
   * Tests if a URL is reachable by performing a fast ping request.
   */
  async testUrl(url) {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 1500);
      
      const response = await fetch(`${url}/api/network-info`, { 
        signal: controller.signal 
      });
      clearTimeout(timeoutId);
      return response.ok;
    } catch (err) {
      return false;
    }
  }

  /**
   * Returns the active base URL to use.
   */
  getBaseUrl() {
    return this.currentBaseUrl;
  }
}
