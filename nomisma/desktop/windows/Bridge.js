(() => {
  "use strict";
  const config = __NOMISMA_CONFIG__;
  if (window.top !== window || location.origin !== config.origin || !window.chrome?.webview) return;
  const pending = new Map();
  const notifications = new Map();
  let permission = config.notificationPermission;
  let sequence = 0;
  const send = (action, payload = {}) => new Promise((resolve, reject) => {
    const id = String(++sequence);
    const timer = setTimeout(() => { pending.delete(id); reject(new Error("Nomisma did not respond.")); }, 120000);
    pending.set(id, {resolve, reject, timer});
    window.chrome.webview.postMessage({channel: "nomisma", id, action, ...payload});
  });
  window.chrome.webview.addEventListener("message", (event) => {
    const data = event.data;
    if (data?.channel !== "nomisma") return;
    if (data.event === "notificationClick") {
      const notification = notifications.get(data.notificationId);
      if (notification) notification.dispatchEvent(new Event("click"));
      return;
    }
    const request = pending.get(data.id);
    if (!request) return;
    clearTimeout(request.timer);
    pending.delete(data.id);
    if (data.error) request.reject(new Error(data.error));
    else request.resolve(data.result);
  });

  class DesktopNotification extends EventTarget {
    static get permission() { return permission; }
    static get maxActions() { return 0; }
    static async requestPermission(callback) {
      if (!navigator.userActivation?.isActive) return permission;
      permission = await send("notificationPermission");
      if (typeof callback === "function") callback(permission);
      return permission;
    }
    constructor(title, options = {}) {
      super();
      this.title = String(title);
      this.body = String(options.body || "");
      this.tag = String(options.tag || "");
      this.data = options.data;
      this.notificationId = "n" + (++sequence);
      this.onclick = null;
      this.onshow = null;
      this.onerror = null;
      this.onclose = null;
      for (const name of ["click", "show", "error", "close"])
        this.addEventListener(name, event => { if (typeof this["on" + name] === "function") this["on" + name](event); });
      if (permission !== "granted") throw new TypeError("Enable desktop alerts before creating a notification.");
      notifications.set(this.notificationId, this);
      if (notifications.size > 100) notifications.delete(notifications.keys().next().value);
      send("notify", {notificationId: this.notificationId, title: this.title, body: this.body}).then(() => {
        this.dispatchEvent(new Event("show"));
      }).catch(() => this.dispatchEvent(new Event("error")));
    }
    close() {
      notifications.delete(this.notificationId);
      this.dispatchEvent(new Event("close"));
    }
  }
  let activePrint;
  const print = () => {
    if (activePrint) return activePrint;
    activePrint = new Promise((resolve, reject) => {
      const complete = () => resolve();
      window.addEventListener("afterprint", complete, {once: true});
      try { window.print(); }
      catch (error) { window.removeEventListener("afterprint", complete); reject(error); }
    });
    activePrint.then(() => { activePrint = null; }, () => { activePrint = null; });
    return activePrint;
  };
  Object.defineProperty(window, "Notification", {value: DesktopNotification, configurable: false});
  Object.defineProperty(window, "nomismaDesktop", {value: Object.freeze({
    platform: "windows", version: 1, configFile: config.configFile,
    dataDirectory: config.dataDirectory, print,
    ping: () => send("ping"),
  }), configurable: false});
})();
