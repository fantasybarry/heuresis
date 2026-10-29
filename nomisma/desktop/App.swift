import AppKit
import Foundation
import WebKit
import UserNotifications

/// A native window around Nomisma's local service. No third-party web content
/// receives the print or notification bridge, and app updates contain no data.
@main
struct NomismaApplication {
    static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.regular)
        app.run()
        withExtendedLifetime(delegate) {}
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate,
    WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandlerWithReply,
    WKDownloadDelegate, UNUserNotificationCenterDelegate, NSMenuItemValidation {
    private var window: NSWindow!
    private var webView: WKWebView!
    private var startupView: NSView!
    private var startupTitle: NSTextField!
    private var startupDetail: NSTextField!
    private var progress: NSProgressIndicator!
    private var retryButton: NSButton!
    private var hostProcess: Process?
    private var startupGeneration = UUID()
    private var appURL: URL?
    private var dataDirectory: URL?
    private var envFile: URL?
    private var origin: String?
    private var isPrinting = false
    private var pendingNotification: (id: String, symbol: String)?

    private struct DownloadDestination {
        let temporaryDirectory: URL
        let temporaryFile: URL
        let chosenFile: URL
    }
    private var downloads: [ObjectIdentifier: DownloadDestination] = [:]

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMenu()
        buildWindow()
        UNUserNotificationCenter.current().delegate = self
        startHost()
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows: Bool) -> Bool {
        window.makeKeyAndOrderFront(nil)
        return true
    }

    // Closing the window keeps opted-in notifications available. Cmd-Q quits
    // the shell; the local service and its user-selected schedules stay running.
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    func applicationWillTerminate(_ notification: Notification) {
        if let process = hostProcess, process.isRunning { process.terminate() }
    }

    private func buildWindow() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1280, height: 900),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "Nomisma"
        window.minSize = NSSize(width: 390, height: 540)
        window.isReleasedWhenClosed = false
        window.delegate = self
        window.center()
        window.setFrameAutosaveName("Nomisma.MainWindow")

        let content = NSView()
        window.contentView = content
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = false
        configuration.preferences.tabFocusesLinks = true
        configuration.mediaTypesRequiringUserActionForPlayback = []
        configuration.userContentController.addScriptMessageHandler(self, contentWorld: .page, name: "nomisma")
        webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = false
        webView.translatesAutoresizingMaskIntoConstraints = false
        webView.isHidden = true
        content.addSubview(webView)
        NSLayoutConstraint.activate([
            webView.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            webView.topAnchor.constraint(equalTo: content.topAnchor),
            webView.bottomAnchor.constraint(equalTo: content.bottomAnchor)
        ])

        startupView = NSView()
        startupView.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(startupView)
        NSLayoutConstraint.activate([
            startupView.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            startupView.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            startupView.topAnchor.constraint(equalTo: content.topAnchor),
            startupView.bottomAnchor.constraint(equalTo: content.bottomAnchor)
        ])
        let icon = NSImageView(image: NSApp.applicationIconImage)
        icon.translatesAutoresizingMaskIntoConstraints = false
        icon.widthAnchor.constraint(equalToConstant: 92).isActive = true
        icon.heightAnchor.constraint(equalToConstant: 92).isActive = true
        startupTitle = NSTextField(labelWithString: "Opening your workspace")
        startupTitle.font = .systemFont(ofSize: 25, weight: .semibold)
        startupTitle.alignment = .center
        startupDetail = NSTextField(wrappingLabelWithString: "Starting Nomisma's local service…")
        startupDetail.font = .systemFont(ofSize: 14)
        startupDetail.textColor = .secondaryLabelColor
        startupDetail.alignment = .center
        progress = NSProgressIndicator()
        progress.style = .spinning
        progress.controlSize = .regular
        retryButton = NSButton(title: "Try Again", target: self, action: #selector(retryStartup))
        retryButton.bezelStyle = .rounded
        retryButton.isHidden = true
        let stack = NSStackView(views: [icon, startupTitle, startupDetail, progress, retryButton])
        stack.orientation = .vertical
        stack.alignment = .centerX
        stack.spacing = 20
        stack.translatesAutoresizingMaskIntoConstraints = false
        startupView.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.centerXAnchor.constraint(equalTo: startupView.centerXAnchor),
            stack.centerYAnchor.constraint(equalTo: startupView.centerYAnchor, constant: -30),
            stack.widthAnchor.constraint(lessThanOrEqualToConstant: 620),
            stack.leadingAnchor.constraint(greaterThanOrEqualTo: startupView.leadingAnchor, constant: 24),
            stack.trailingAnchor.constraint(lessThanOrEqualTo: startupView.trailingAnchor, constant: -24),
            startupDetail.widthAnchor.constraint(equalTo: stack.widthAnchor)
        ])
        window.makeKeyAndOrderFront(nil)
    }

    private func buildMenu() {
        let menu = NSMenu()
        NSApp.mainMenu = menu
        func submenu(_ title: String) -> NSMenu {
            let item = NSMenuItem(title: title, action: nil, keyEquivalent: "")
            let child = NSMenu(title: title)
            item.submenu = child
            menu.addItem(item)
            return child
        }
        func item(_ menu: NSMenu, _ title: String, _ action: Selector, _ key: String = "", target: AnyObject? = nil) {
            let result = NSMenuItem(title: title, action: action, keyEquivalent: key)
            result.target = target
            menu.addItem(result)
        }
        let app = submenu("Nomisma")
        item(app, "About Nomisma", #selector(showAbout), target: self)
        app.addItem(.separator())
        item(app, "Settings…", #selector(showSettings), ",", target: self)
        item(app, "Show Research Data in Finder", #selector(showDataFolder), target: self)
        item(app, "Open Configuration Folder", #selector(showConfigurationFolder), target: self)
        app.addItem(.separator())
        let services = NSMenuItem(title: "Services", action: nil, keyEquivalent: "")
        services.submenu = NSMenu(title: "Services")
        app.addItem(services)
        NSApp.servicesMenu = services.submenu
        app.addItem(.separator())
        item(app, "Hide Nomisma", #selector(NSApplication.hide(_:)), "h")
        item(app, "Show All", #selector(NSApplication.unhideAllApplications(_:)))
        app.addItem(.separator())
        item(app, "Quit Nomisma", #selector(NSApplication.terminate(_:)), "q")

        let file = submenu("File")
        item(file, "Open in Browser", #selector(openInBrowser), target: self)
        file.addItem(.separator())
        item(file, "Print…", #selector(printPage), "p", target: self)
        item(file, "Close Window", #selector(NSWindow.performClose(_:)), "w")
        let edit = submenu("Edit")
        item(edit, "Undo", Selector(("undo:")), "z")
        item(edit, "Redo", Selector(("redo:")), "Z")
        edit.addItem(.separator())
        item(edit, "Cut", #selector(NSText.cut(_:)), "x")
        item(edit, "Copy", #selector(NSText.copy(_:)), "c")
        item(edit, "Paste", #selector(NSText.paste(_:)), "v")
        item(edit, "Select All", #selector(NSText.selectAll(_:)), "a")
        let view = submenu("View")
        item(view, "Reload Workspace", #selector(reloadWorkspace), "r", target: self)
        view.addItem(.separator())
        item(view, "Live Monitor", #selector(showLive), "1", target: self)
        item(view, "Daily Screener", #selector(showDaily), "2", target: self)
        item(view, "Watchlist", #selector(showWatchlist), "3", target: self)
        item(view, "Scan History", #selector(showHistory), "4", target: self)
        let windowMenu = submenu("Window")
        item(windowMenu, "Minimize", #selector(NSWindow.performMiniaturize(_:)), "m")
        item(windowMenu, "Zoom", #selector(NSWindow.performZoom(_:)))
        windowMenu.addItem(.separator())
        item(windowMenu, "Show Nomisma", #selector(showMainWindow), target: self)
        NSApp.windowsMenu = windowMenu
    }

    @objc private func showAbout() {
        NSApp.orderFrontStandardAboutPanel(options: [
            .applicationName: "Nomisma",
            .applicationVersion: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "1.0",
            .credits: NSAttributedString(string: "A clearer market view, by Heuresis.\nYour research data stays on this Mac.\nThe local service keeps running when you quit the app.")
        ])
    }
    @objc private func showMainWindow() { window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true) }
    @objc private func showSettings() { showMainWindow(); evaluateTrusted("document.querySelector('#sidebar-settings')?.click()") }
    @objc private func showLive() { showMainWindow(); evaluateTrusted("location.hash = 'live'") }
    @objc private func showDaily() { showMainWindow(); evaluateTrusted("location.hash = 'dashboard'") }
    @objc private func showWatchlist() { showMainWindow(); evaluateTrusted("location.hash = 'watchlist'") }
    @objc private func showHistory() { showMainWindow(); evaluateTrusted("location.hash = 'history'") }
    @objc private func showDataFolder() { if let url = dataDirectory { NSWorkspace.shared.open(url) } }
    @objc private func showConfigurationFolder() { if let url = envFile { NSWorkspace.shared.open(url.deletingLastPathComponent()) } }
    @objc private func openInBrowser() { if let url = webView.url, isTrusted(url) { NSWorkspace.shared.open(url) } }
    @objc private func retryStartup() { startHost() }
    @objc private func reloadWorkspace() {
        guard let url = appURL else { startHost(); return }
        showLoading("Refreshing your workspace", detail: "Connecting to Nomisma's local service…")
        webView.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData))
    }

    func validateMenuItem(_ menuItem: NSMenuItem) -> Bool {
        if menuItem.action == #selector(showDataFolder) { return dataDirectory != nil }
        if menuItem.action == #selector(showConfigurationFolder) { return envFile != nil }
        let needsWorkspace: [Selector] = [#selector(showSettings), #selector(showLive), #selector(showDaily),
            #selector(showWatchlist), #selector(showHistory), #selector(openInBrowser), #selector(printPage)]
        if let action = menuItem.action, needsWorkspace.contains(action) {
            return webView.url.map { isTrusted($0) } == true && !webView.isHidden
        }
        return true
    }

    private func evaluateTrusted(_ source: String) {
        guard let url = webView.url, isTrusted(url) else { return }
        webView.evaluateJavaScript(source, completionHandler: nil)
    }

    private func showLoading(_ title: String, detail: String) {
        startupTitle.stringValue = title
        startupDetail.stringValue = detail
        retryButton.isHidden = true
        progress.isHidden = false
        progress.startAnimation(nil)
        startupView.isHidden = false
        webView.isHidden = true
    }

    private func showStartupError(_ detail: String) {
        startupTitle.stringValue = "Nomisma couldn't open"
        startupDetail.stringValue = detail
        progress.stopAnimation(nil)
        progress.isHidden = true
        retryButton.isHidden = false
        startupView.isHidden = false
        webView.isHidden = true
    }

    private func startHost() {
        if let process = hostProcess, process.isRunning { process.terminate() }
        let generation = UUID()
        startupGeneration = generation
        appURL = nil
        origin = nil
        showLoading("Opening your workspace", detail: "Starting Nomisma's local service…")
        guard let resources = Bundle.main.resourceURL else {
            showStartupError("The application is missing its resources. Rebuild or reinstall Nomisma.")
            return
        }
        prepareWorkspaceLocations(resources)
        let process = Process()
        process.executableURL = resources.appendingPathComponent("python/bin/python3")
        process.arguments = [resources.appendingPathComponent("backend/desktop/host.py").path,
                             "--config", resources.appendingPathComponent("workspace.json").path]
        process.currentDirectoryURL = resources.appendingPathComponent("backend")
        var environment = ProcessInfo.processInfo.environment
        for key in environment.keys where key.hasPrefix("PYTHON") || key.hasPrefix("DYLD_") {
            environment.removeValue(forKey: key)
        }
        environment["PYTHONNOUSERSITE"] = "1"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        process.environment = environment
        let stdout = Pipe(), stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr
        process.standardInput = FileHandle.nullDevice
        hostProcess = process
        do { try process.run() }
        catch {
            showStartupError("The bundled runtime could not start. \(error.localizedDescription)")
            return
        }
        // host.py only emits one small readiness message and detaches all
        // server descriptors, so these pipes close as soon as it is ready.
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let errorData = stderr.fileHandleForReading.readDataToEndOfFile()
            let outputData = stdout.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            DispatchQueue.main.async {
                guard let self = self, self.startupGeneration == generation else { return }
                self.hostProcess = nil
                guard process.terminationStatus == 0 else {
                    let detail = String(data: errorData, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                    self.showStartupError(detail.isEmpty ? "The local service could not start. Try again, or open the configuration folder to check your settings." : String(detail.prefix(1800)))
                    return
                }
                do {
                    guard let line = String(data: outputData, encoding: .utf8)?.split(separator: "\n").first,
                          let data = String(line).data(using: .utf8),
                          let result = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                          result["desktop_api"] as? Int == 1,
                          let urlString = result["url"] as? String,
                          let url = URL(string: urlString),
                          url.scheme == "http", ["127.0.0.1", "localhost", "[::1]", "::1"].contains(url.host ?? ""),
                          url.user == nil, url.password == nil, let port = url.port, (1...65535).contains(port),
                          let directory = result["data_directory"] as? String, directory.hasPrefix("/"),
                          let configFile = result["env_file"] as? String, configFile.hasPrefix("/") else {
                        self.showStartupError("The local service returned an invalid connection address. Rebuild or reinstall Nomisma.")
                        return
                    }
                    var originParts = URLComponents()
                    originParts.scheme = url.scheme
                    originParts.host = url.host
                    originParts.port = port
                    self.origin = originParts.string
                    self.appURL = url
                    self.dataDirectory = URL(fileURLWithPath: directory, isDirectory: true)
                    self.envFile = URL(fileURLWithPath: configFile)
                    self.installBridge()
                    self.webView.load(URLRequest(url: url))
                } catch { self.showStartupError("The local service returned an unreadable startup response.") }
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 60) { [weak self] in
            guard let self = self, self.startupGeneration == generation, let active = self.hostProcess, active.isRunning else { return }
            self.startupGeneration = UUID()
            active.terminate()
            self.hostProcess = nil
            self.showStartupError("The local service took too long to start. Try again, or check the log in your research data folder.")
        }
    }

    private func prepareWorkspaceLocations(_ resources: URL) {
        // Make Finder actions useful even if the service cannot start. These
        // non-secret paths follow host.py's existing-workspace fallback; the
        // readiness response becomes authoritative once startup succeeds.
        let support = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Nomisma", isDirectory: true)
        dataDirectory = support.appendingPathComponent("data", isDirectory: true)
        envFile = support.appendingPathComponent(".env")
        guard let data = try? Data(contentsOf: resources.appendingPathComponent("workspace.json")),
              let config = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let directory = config["data_directory"] as? String, directory.hasPrefix("/") else { return }
        let candidate = URL(fileURLWithPath: directory, isDirectory: true)
        let hasDatabase = FileManager.default.fileExists(atPath: candidate.appendingPathComponent("nomisma.sqlite3").path)
        let project = config["project_directory"] as? String
        let hasProject = project.map { $0.hasPrefix("/") && FileManager.default.fileExists(atPath: URL(fileURLWithPath: $0).appendingPathComponent("run.py").path) } ?? false
        if hasDatabase || hasProject {
            dataDirectory = candidate
            if let environment = config["env_file"] as? String, environment.hasPrefix("/") {
                envFile = URL(fileURLWithPath: environment)
            }
        }
    }

    private func isTrusted(_ url: URL) -> Bool {
        guard let origin = origin, let expected = URL(string: origin) else { return false }
        return url.scheme == expected.scheme && url.host == expected.host && url.port == expected.port && url.user == nil && url.password == nil
    }

    private func isTrusted(_ frame: WKFrameInfo) -> Bool {
        guard frame.isMainFrame, let url = frame.request.url, isTrusted(url),
              let current = webView.url, isTrusted(current) else { return false }
        return true
    }

    private func installBridge() {
        guard let origin = origin else { return }
        let config: [String: String] = ["origin": origin, "dataDirectory": dataDirectory?.path ?? "", "configFile": envFile?.path ?? ""]
        guard let data = try? JSONSerialization.data(withJSONObject: config, options: [.sortedKeys]),
              let json = String(data: data, encoding: .utf8) else { return }
        let script = """
        (() => {
          'use strict';
          const config = \(json);
          if (location.origin !== config.origin || window.top !== window) return;
          const bridge = window.webkit.messageHandlers.nomisma;
          const send = (action, values = {}) => bridge.postMessage({action, ...values});
          let permission = 'default';
          const notifications = new Map();
          class DesktopNotification extends EventTarget {
            static get permission() { return permission; }
            static async requestPermission(callback) {
              if (!navigator.userActivation.isActive) return permission;
              permission = await send('requestPermission');
              if (typeof callback === 'function') callback(permission);
              return permission;
            }
            constructor(title, options = {}) {
              super();
              if (permission !== 'granted') throw new Error('Desktop notifications are not enabled.');
              this.title = String(title); this.body = String(options.body || '');
              this.tag = String(options.tag || ''); this.onclick = null;
              this._id = crypto.randomUUID();
              notifications.set(this._id, this);
              send('notify', {id:this._id, title:this.title, body:this.body, tag:this.tag}).catch(() => notifications.delete(this._id));
              if (notifications.size > 500) notifications.delete(notifications.keys().next().value);
            }
            close() { notifications.delete(this._id); send('closeNotification', {id:this._id}).catch(() => {}); }
          }
          Object.defineProperty(window, 'Notification', {value:DesktopNotification, configurable:false});
          const desktop = Object.freeze({
            configFile:config.configFile, dataDirectory:config.dataDirectory,
            print:() => send('print'),
            fullScreen:(on) => send('fullScreen', {on:!!on}),
            notificationClicked:(id, symbol) => {
              const item = notifications.get(id);
              if (item) {
                const event = new Event('click');
                if (typeof item.onclick === 'function') item.onclick(event);
                item.dispatchEvent(event);
              } else {
                location.hash = 'live';
                [...document.querySelectorAll('[data-live-symbol]')].find(button => button.dataset.liveSymbol === symbol)?.click();
              }
            }
          });
          Object.defineProperty(window, 'nomismaDesktop', {value:desktop, configurable:false});
          window.print = () => desktop.print();
          send('permission').then(value => permission = value).catch(() => {});
          window.addEventListener('focus', () => send('permission').then(value => permission = value).catch(() => {}));
        })();
        """
        let controller = webView.configuration.userContentController
        controller.removeAllUserScripts()
        controller.addUserScript(WKUserScript(source: script, injectionTime: .atDocumentStart, forMainFrameOnly: true))
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        let trusted = isTrusted(url)
        let localBlob = origin.map { url.absoluteString.hasPrefix("blob:\($0)/") } ?? false
        if trusted || (localBlob && navigationAction.shouldPerformDownload) {
            if navigationAction.shouldPerformDownload { decisionHandler(.download) }
            else if navigationAction.targetFrame == nil {
                decisionHandler(.cancel)
                if trusted { webView.load(navigationAction.request) }
            } else { decisionHandler(.allow) }
        } else {
            decisionHandler(.cancel)
            if navigationAction.navigationType == .linkActivated, ["http", "https", "mailto"].contains(url.scheme ?? "") {
                NSWorkspace.shared.open(url)
            }
        }
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        guard let url = navigationResponse.response.url,
              isTrusted(url) || (origin.map { url.absoluteString.hasPrefix("blob:\($0)/") } ?? false) else {
            decisionHandler(.cancel); return
        }
        if !navigationResponse.canShowMIMEType { decisionHandler(.download) }
        else { decisionHandler(.allow) }
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard let url = webView.url, isTrusted(url) else { return }
        progress.stopAnimation(nil)
        startupView.isHidden = true
        webView.isHidden = false
        window.makeFirstResponder(webView)
        if let pending = pendingNotification {
            pendingNotification = nil
            navigateToNotification(id: pending.id, symbol: pending.symbol)
        }
    }
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        if (error as NSError).code == NSURLErrorCancelled { return }
        showStartupError("The workspace connection was interrupted. Try again to reconnect to the local service.")
    }
    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) { reloadWorkspace() }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        guard isTrusted(frame) else { completionHandler(nil); return }
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.beginSheetModal(for: window) { result in completionHandler(result == .OK ? panel.urls : nil) }
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        guard isTrusted(frame) else { completionHandler(); return }
        let alert = NSAlert()
        alert.messageText = "Nomisma"
        alert.informativeText = String(message.prefix(2000))
        alert.addButton(withTitle: "OK")
        alert.beginSheetModal(for: window) { _ in completionHandler() }
    }
    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        guard isTrusted(frame) else { completionHandler(false); return }
        let alert = NSAlert()
        alert.messageText = "Nomisma"
        alert.informativeText = String(message.prefix(2000))
        alert.addButton(withTitle: "Continue")
        alert.addButton(withTitle: "Cancel")
        alert.beginSheetModal(for: window) { result in completionHandler(result == .alertFirstButtonReturn) }
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }
    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { download.delegate = self }
    func download(_ download: WKDownload, willPerformHTTPRedirection response: HTTPURLResponse,
                  newRequest request: URLRequest, decisionHandler: @escaping (WKDownload.RedirectPolicy) -> Void) {
        decisionHandler(request.url.map { isTrusted($0) } == true ? .allow : .cancel)
    }
    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse,
                  suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        guard let url = response.url,
              isTrusted(url) || (origin.map { url.absoluteString.hasPrefix("blob:\($0)/") } ?? false) else {
            completionHandler(nil); return
        }
        let panel = NSSavePanel()
        panel.title = "Save Nomisma Export"
        panel.nameFieldStringValue = URL(fileURLWithPath: suggestedFilename).lastPathComponent
        panel.canCreateDirectories = true
        panel.beginSheetModal(for: window) { [weak self] result in
            guard let self = self, result == .OK, let destination = panel.url else { completionHandler(nil); return }
            let directory = FileManager.default.temporaryDirectory.appendingPathComponent("Nomisma-\(UUID().uuidString)", isDirectory: true)
            do {
                try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
                let temporary = directory.appendingPathComponent("export")
                self.downloads[ObjectIdentifier(download)] = DownloadDestination(temporaryDirectory: directory, temporaryFile: temporary, chosenFile: destination)
                completionHandler(temporary)
            } catch { self.showError("The export could not be saved.", detail: error.localizedDescription); completionHandler(nil) }
        }
    }
    func downloadDidFinish(_ download: WKDownload) {
        guard let destination = downloads.removeValue(forKey: ObjectIdentifier(download)) else { return }
        defer { try? FileManager.default.removeItem(at: destination.temporaryDirectory) }
        let staged = destination.chosenFile.deletingLastPathComponent().appendingPathComponent(".nomisma-\(UUID().uuidString)")
        do {
            // Stage beside the chosen file, then replace atomically so a failed
            // export cannot remove an existing backup the user chose to replace.
            try FileManager.default.copyItem(at: destination.temporaryFile, to: staged)
            if FileManager.default.fileExists(atPath: destination.chosenFile.path) {
                _ = try FileManager.default.replaceItemAt(destination.chosenFile, withItemAt: staged)
            } else { try FileManager.default.moveItem(at: staged, to: destination.chosenFile) }
        } catch {
            try? FileManager.default.removeItem(at: staged)
            showError("The export could not be saved.", detail: error.localizedDescription)
        }
    }
    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        if let destination = downloads.removeValue(forKey: ObjectIdentifier(download)) {
            try? FileManager.default.removeItem(at: destination.temporaryDirectory)
        }
        if (error as NSError).code != NSURLErrorCancelled { showError("The export did not finish.", detail: error.localizedDescription) }
    }

    private func showError(_ title: String, detail: String) {
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = detail
        alert.beginSheetModal(for: window)
    }

    @objc private func printPage() {
        guard let url = webView.url, isTrusted(url) else { return }
        evaluateTrusted("(() => { const button = document.querySelector('#live-report-dialog[open] #live-print'); if (button) button.click(); else window.nomismaDesktop.print(); })()")
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage,
                               replyHandler: @escaping (Any?, String?) -> Void) {
        guard isTrusted(message.frameInfo), let body = message.body as? [String: Any], let action = body["action"] as? String else {
            replyHandler(nil, "The desktop bridge is only available to the local workspace."); return
        }
        let center = UNUserNotificationCenter.current()
        switch action {
        case "permission":
            center.getNotificationSettings { settings in
                DispatchQueue.main.async { replyHandler(Self.permissionName(settings.authorizationStatus), nil) }
            }
        case "requestPermission":
            center.requestAuthorization(options: [.alert, .badge]) { _, error in
                if let error = error { DispatchQueue.main.async { replyHandler(nil, error.localizedDescription) }; return }
                center.getNotificationSettings { settings in
                    DispatchQueue.main.async { replyHandler(Self.permissionName(settings.authorizationStatus), nil) }
                }
            }
        case "notify":
            guard let id = body["id"] as? String, UUID(uuidString: id) != nil,
                  let title = body["title"] as? String, let text = body["body"] as? String else {
                replyHandler(nil, "Invalid notification."); return
            }
            center.getNotificationSettings { settings in
                guard Self.permissionName(settings.authorizationStatus) == "granted" else {
                    DispatchQueue.main.async { replyHandler(nil, "Desktop notification permission is not enabled.") }; return
                }
                let content = UNMutableNotificationContent()
                content.title = String(title.prefix(180))
                content.body = String(text.prefix(1200))
                // Alert sound is controlled by the existing explicit sound
                // toggle and Web Audio. Native notifications remain silent.
                content.sound = nil
                let symbol = String(title.split(separator: " ").first ?? "")
                content.userInfo = ["id": id, "symbol": symbol]
                let request = UNNotificationRequest(identifier: id, content: content, trigger: nil)
                center.add(request) { error in DispatchQueue.main.async { replyHandler(error == nil, error?.localizedDescription) } }
            }
        case "closeNotification":
            if let id = body["id"] as? String, UUID(uuidString: id) != nil {
                center.removeDeliveredNotifications(withIdentifiers: [id])
                center.removePendingNotificationRequests(withIdentifiers: [id])
            }
            replyHandler(true, nil)
        case "print":
            guard !isPrinting else { replyHandler(nil, "A print dialog is already open."); return }
            isPrinting = true
            let info = NSPrintInfo.shared.copy() as! NSPrintInfo
            info.horizontalPagination = .fit
            info.verticalPagination = .automatic
            let operation = webView.printOperation(with: info)
            operation.showsPrintPanel = true
            operation.showsProgressPanel = true
            // This modal call keeps the JS promise pending until the print
            // panel closes, preserving the report's print-only layout.
            let result = operation.run()
            isPrinting = false
            replyHandler(result, nil)
        case "fullScreen":
            // The candle chart fills the window; the native window supplies true full screen.
            if (body["on"] as? Bool ?? false) != window.styleMask.contains(.fullScreen) { window.toggleFullScreen(nil) }
            replyHandler(true, nil)
        default: replyHandler(nil, "Unknown desktop action.")
        }
    }

    private static func permissionName(_ status: UNAuthorizationStatus) -> String {
        switch status {
        case .authorized, .provisional: return "granted"
        case .denied: return "denied"
        default: return "default"
        }
    }

    private func navigateToNotification(id: String, symbol: String) {
        guard let url = webView.url, isTrusted(url), !webView.isLoading else {
            pendingNotification = (id, symbol)
            return
        }
        webView.callAsyncJavaScript("window.nomismaDesktop.notificationClicked(id, symbol)", arguments: ["id": id, "symbol": symbol], in: nil, in: .page, completionHandler: nil)
    }
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .list])
    }
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        guard response.actionIdentifier == UNNotificationDefaultActionIdentifier else { completionHandler(); return }
        let info = response.notification.request.content.userInfo
        let id = info["id"] as? String ?? ""
        let symbol = info["symbol"] as? String ?? ""
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { completionHandler(); return }
            self.showMainWindow()
            self.navigateToNotification(id: id, symbol: symbol)
            completionHandler()
        }
    }
}
