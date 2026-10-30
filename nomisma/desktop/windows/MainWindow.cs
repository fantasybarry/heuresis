using System.Diagnostics;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace Nomisma.Desktop;

internal sealed record HostReady(
    [property: JsonPropertyName("url")] string Url,
    [property: JsonPropertyName("data_directory")] string DataDirectory,
    [property: JsonPropertyName("env_file")] string EnvFile,
    [property: JsonPropertyName("owned_server")] bool OwnedServer,
    [property: JsonPropertyName("desktop_api")] int DesktopApi);

internal sealed class MainWindow : Form
{
    private const string WebViewDownload = "https://developer.microsoft.com/microsoft-edge/webview2/";
    private readonly LaunchOptions options;
    private readonly WebView2 web = new() { Dock = DockStyle.Fill, Visible = false, DefaultBackgroundColor = Color.FromArgb(248, 249, 246) };
    private readonly Panel startup = new() { Dock = DockStyle.Fill, BackColor = Color.FromArgb(248, 249, 246) };
    private readonly Label heading = new() { Text = "Opening your workspace", Font = new Font("Segoe UI", 24, FontStyle.Bold), AutoSize = true, TextAlign = ContentAlignment.MiddleCenter, Margin = new Padding(12, 8, 12, 8) };
    private readonly Label detail = new() { Text = "Starting Nomisma’s local service…", Font = new Font("Segoe UI", 11), AutoSize = true, MaximumSize = new Size(580, 0), TextAlign = ContentAlignment.MiddleCenter, Margin = new Padding(12, 4, 12, 16) };
    private readonly Button retry = new() { Text = "Try again", AutoSize = true, Visible = false, Padding = new Padding(18, 6, 18, 6) };
    private readonly Button installWebView = new() { Text = "Get Microsoft WebView2", AutoSize = true, Visible = false, Padding = new Padding(18, 6, 18, 6) };
    private readonly ProgressBar progress = new() { Width = 240, Height = 5, Style = ProgressBarStyle.Marquee, MarqueeAnimationSpeed = 25, Margin = new Padding(12, 12, 12, 12) };
    private readonly ToolStripStatusLabel status = new() { Spring = true, TextAlign = ContentAlignment.MiddleLeft };
    private readonly ToolStripMenuItem restart = new("Restart local service") { Enabled = false };
    private readonly NotifyIcon notificationIcon;
    private readonly string preferenceFile;
    private readonly System.Windows.Forms.Timer smokeTimer = new() { Interval = 100000 };
    private readonly SemaphoreSlim startupLogLock = new(1, 1);
    private Process? host;
    private HostReady? ready;
    private Uri? origin;
    private string? bridgeScriptId;
    private string permission = "default";
    private string? latestNotification;
    private bool starting, closing, closed, smokeStarted, smokeFinished;
    private Stopwatch? startupWatch;
    private long? backendReadyMs, webviewReadyMs, pageReadyMs;
    private bool startupTimingRecorded;
    internal int ExitCode { get; private set; }

    internal MainWindow(LaunchOptions options)
    {
        this.options = options;
        Text = "Nomisma";
        ClientSize = new Size(1280, 900);
        MinimumSize = new Size(430, 590);
        StartPosition = FormStartPosition.CenterScreen;
        AutoScaleMode = AutoScaleMode.Dpi;
        Icon = Icon.ExtractAssociatedIcon(Environment.ProcessPath!) ?? SystemIcons.Application;
        var menu = BuildMenu();
        MainMenuStrip = menu;
        var bottom = new StatusStrip { SizingGrip = true };
        bottom.Items.Add(status);
        status.Text = "Your research data stays on this PC.";
        Controls.Add(web);
        Controls.Add(startup);
        Controls.Add(bottom);
        Controls.Add(menu);

        var layout = new TableLayoutPanel { AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink, ColumnCount = 1, RowCount = 6 };
        var mark = new Label { Text = "N", BackColor = Color.FromArgb(33, 70, 54), ForeColor = Color.FromArgb(241, 231, 205), Font = new Font("Georgia", 52, FontStyle.Bold), Width = 94, Height = 94, TextAlign = ContentAlignment.MiddleCenter, Margin = new Padding(12, 8, 12, 24) };
        foreach (Control control in new Control[] { mark, heading, detail, progress, retry, installWebView })
        {
            control.Anchor = AnchorStyles.None;
            layout.Controls.Add(control);
        }
        startup.Controls.Add(layout);
        void CenterStartup() => layout.Location = new Point(Math.Max(8, (startup.Width - layout.Width) / 2), Math.Max(8, (startup.Height - layout.Height) / 2 - 20));
        startup.Resize += (_, _) => CenterStartup();
        layout.SizeChanged += (_, _) => CenterStartup();
        retry.Click += async (_, _) => await StartWorkspaceAsync();
        installWebView.Click += (_, _) => OpenExternal(WebViewDownload);

        var preferencesDirectory = options.SmokeTest ? options.DataDirectory! : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Nomisma");
        preferenceFile = Path.Combine(preferencesDirectory, "desktop.json");
        try
        {
            if (File.Exists(preferenceFile))
            {
                using var document = JsonDocument.Parse(File.ReadAllText(preferenceFile));
                if (document.RootElement.TryGetProperty("notificationPermission", out var value) && value.GetString() is "granted" or "denied")
                    permission = value.GetString()!;
            }
        }
        catch (Exception error) when (error is IOException or JsonException or UnauthorizedAccessException) { }
        notificationIcon = new NotifyIcon { Icon = Icon, Text = "Nomisma", Visible = false };
        notificationIcon.BalloonTipClicked += (_, _) =>
        {
            if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal;
            Show(); Activate();
            if (latestNotification is not null && TrustedCurrent())
                Post(new { channel = "nomisma", @event = "notificationClick", notificationId = latestNotification });
        };
        notificationIcon.DoubleClick += (_, _) => { Show(); WindowState = FormWindowState.Normal; Activate(); };
        Shown += async (_, _) =>
        {
            if (options.SmokeTest) smokeTimer.Start();
            await StartWorkspaceAsync();
        };
        smokeTimer.Tick += async (_, _) => await FinishSmokeAsync(false, "Desktop startup or page verification timed out.");
        FormClosing += OnClosing;
    }

    private MenuStrip BuildMenu()
    {
        var menu = new MenuStrip();
        var file = new ToolStripMenuItem("&File");
        var view = new ToolStripMenuItem("&View");
        var help = new ToolStripMenuItem("&Help");
        menu.Items.AddRange([file, view, help]);
        void Item(ToolStripMenuItem parent, string title, Action action, Keys shortcut = Keys.None)
        {
            var item = new ToolStripMenuItem(title) { ShortcutKeys = shortcut };
            item.Click += (_, _) => action();
            parent.DropDownItems.Add(item);
        }
        Item(file, "Settings…", () => EvaluateTrusted("document.querySelector('#sidebar-settings')?.click()"), Keys.Control | Keys.Oemcomma);
        Item(file, "Show research data", () => { if (ready is not null) OpenFolder(ready.DataDirectory); });
        Item(file, "Open configuration folder", () => { if (ready is not null) OpenFolder(Path.GetDirectoryName(ready.EnvFile)!); });
        file.DropDownItems.Add(new ToolStripSeparator());
        Item(file, "Open in browser", () => { if (TrustedCurrent()) OpenExternal(web.Source.AbsoluteUri); });
        Item(file, "Print…", () => EvaluateTrusted("document.querySelector('#live-report-dialog[open]') ? document.querySelector('#live-print')?.click() : window.nomismaDesktop.print()"), Keys.Control | Keys.P);
        file.DropDownItems.Add(new ToolStripSeparator());
        restart.Click += async (_, _) =>
        {
            if (ready?.OwnedServer != true || starting) return;
            starting = true;
            await StopHostAsync();
            starting = false;
            await StartWorkspaceAsync();
        };
        file.DropDownItems.Add(restart);
        Item(file, "Exit", Close, Keys.Alt | Keys.F4);
        Item(view, "Reload workspace", () => { if (TrustedCurrent()) web.Reload(); }, Keys.Control | Keys.R);
        view.DropDownItems.Add(new ToolStripSeparator());
        Item(view, "Live monitor", () => EvaluateTrusted("location.hash = 'live'"), Keys.Control | Keys.D1);
        Item(view, "Daily screener", () => EvaluateTrusted("location.hash = 'dashboard'"), Keys.Control | Keys.D2);
        Item(view, "Scan history", () => EvaluateTrusted("location.hash = 'history'"), Keys.Control | Keys.D3);
        Item(help, "About Nomisma", () => MessageBox.Show(this,
            "Nomisma " + Application.ProductVersion.Split('+')[0] + "\nA local market research workspace by Heuresis.\n\nYour research data stays on this PC. Closing the app stops the local service it started, including live monitoring and scheduled scans.",
            "About Nomisma", MessageBoxButtons.OK, MessageBoxIcon.Information));
        return menu;
    }

    private async Task StartWorkspaceAsync()
    {
        if (starting || closing) return;
        starting = true;
        startupWatch = Stopwatch.StartNew();
        backendReadyMs = webviewReadyMs = pageReadyMs = null;
        startupTimingRecorded = false;
        web.Visible = false;
        startup.Visible = true;
        startup.BringToFront();
        heading.Text = "Opening your workspace";
        detail.Text = "Starting Nomisma’s local service…";
        retry.Visible = installWebView.Visible = false;
        progress.Visible = true;
        restart.Enabled = false;
        try
        {
            await StopHostAsync();
            ready = null;
            origin = null;
            var resourceDirectory = Path.Combine(AppContext.BaseDirectory, "resources");
            var python = Path.Combine(resourceDirectory, "python", "python.exe");
            var script = Path.Combine(resourceDirectory, "backend", "desktop", "host.py");
            if (!File.Exists(python) || !File.Exists(script))
                throw new InvalidOperationException("Nomisma’s bundled files are incomplete. Reinstall the application; your research data will be preserved.");
            var info = new ProcessStartInfo(python) { UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true, WorkingDirectory = resourceDirectory };
            foreach (string argument in new[] { "-B", script, "--config", Path.Combine(resourceDirectory, "workspace.json"), "--managed" }) info.ArgumentList.Add(argument);
            if (options.DataDirectory is not null)
            {
                info.ArgumentList.Add("--data-dir"); info.ArgumentList.Add(options.DataDirectory);
            }
            if (options.SmokeTest)
            {
                info.ArgumentList.Add("--env-file"); info.ArgumentList.Add(Path.Combine(options.DataDirectory!, ".smoke.env"));
                foreach (var key in info.Environment.Keys.Where(key => key.StartsWith("ALPACA", StringComparison.OrdinalIgnoreCase) || key.StartsWith("FMP", StringComparison.OrdinalIgnoreCase)).ToArray()) info.Environment.Remove(key);
            }
            foreach (var key in info.Environment.Keys.Where(key => key.StartsWith("PYTHON", StringComparison.OrdinalIgnoreCase)).ToArray()) info.Environment.Remove(key);
            var process = Process.Start(info) ?? throw new InvalidOperationException("The local service could not start.");
            host = process;
            _ = SaveServiceLogAsync(process);
            string? line = await process.StandardOutput.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(60));
            if (line is null) throw new InvalidOperationException("The local service could not start. Check the data folder’s nomisma.log, then try again.");
            ready = JsonSerializer.Deserialize<HostReady>(line) ?? throw new InvalidOperationException("The local service returned an incomplete response.");
            if (ready.DesktopApi != 1 || !Uri.TryCreate(ready.Url, UriKind.Absolute, out var address) || address.Scheme != "http" || address.Host != "127.0.0.1" || address.Port < 1 || !Path.IsPathFullyQualified(ready.DataDirectory) || !Path.IsPathFullyQualified(ready.EnvFile))
                throw new InvalidOperationException("The local service returned an invalid workspace address.");
            origin = new Uri(address.GetLeftPart(UriPartial.Authority));
            backendReadyMs = startupWatch.ElapsedMilliseconds;
            if (closing) return;
            detail.Text = "Opening your market research window…";
            if (web.CoreWebView2 is null)
            {
                string profile = options.SmokeTest ? Path.Combine(options.DataDirectory!, ".webview2-smoke") : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Nomisma", "WebView2");
                var environment = await CoreWebView2Environment.CreateAsync(null, profile);
                await web.EnsureCoreWebView2Async(environment);
                ConfigureWebView();
            }
            var core = web.CoreWebView2 ?? throw new InvalidOperationException("The workspace browser could not initialize.");
            webviewReadyMs = startupWatch.ElapsedMilliseconds;
            if (bridgeScriptId is not null) core.RemoveScriptToExecuteOnDocumentCreated(bridgeScriptId);
            using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("Nomisma.Desktop.Bridge.js")!;
            using var reader = new StreamReader(stream);
            var configuration = JsonSerializer.Serialize(new { origin = origin.GetLeftPart(UriPartial.Authority), configFile = ready.EnvFile, dataDirectory = ready.DataDirectory, notificationPermission = permission });
            bridgeScriptId = await core.AddScriptToExecuteOnDocumentCreatedAsync((await reader.ReadToEndAsync()).Replace("__NOMISMA_CONFIG__", configuration, StringComparison.Ordinal));
            restart.Enabled = ready.OwnedServer;
            status.Text = ready.OwnedServer ? "Local workspace · Closing Nomisma stops monitoring and its local service." : "Connected to an existing local service · It continues after this window closes.";
            core.Navigate(ready.Url);
            if (ready.OwnedServer)
            {
                process.EnableRaisingEvents = true;
                process.Exited += (_, _) =>
                {
                    if (!IsDisposed && IsHandleCreated) BeginInvoke(() =>
                    {
                        if (!closing && !starting && ReferenceEquals(host, process)) ShowError("The local service stopped", "Your saved data is intact. Select Try again to reopen the workspace.");
                    });
                };
            }
        }
        catch (Exception error)
        {
            await StopHostAsync();
            if (!closing)
            {
                bool missingRuntime = error is WebView2RuntimeNotFoundException;
                string message = missingRuntime ? "Install Microsoft Edge WebView2 Runtime, then select Try again. Nomisma uses it to display your workspace." : error is InvalidOperationException ? error.Message : "Nomisma could not open this workspace. Check that the data folder is writable, or reinstall the app.";
                ShowError("Could not open Nomisma", message, missingRuntime);
                if (options.SmokeTest) await FinishSmokeAsync(false, error.GetType().Name + ": " + message);
            }
        }
        finally { starting = false; }
    }

    private void ConfigureWebView()
    {
        var core = web.CoreWebView2;
        core.Settings.IsStatusBarEnabled = false;
        core.Settings.AreDevToolsEnabled = false;
        core.Settings.AreHostObjectsAllowed = false;
        core.Settings.IsPasswordAutosaveEnabled = false;
        core.Settings.IsGeneralAutofillEnabled = false;
        core.NavigationStarting += (_, args) =>
        {
            if (Trusted(args.Uri)) return;
            args.Cancel = true;
            if (args.IsUserInitiated) OpenExternal(args.Uri);
        };
        core.FrameNavigationStarting += (_, args) => { if (args.Uri != "about:blank" && !Trusted(args.Uri)) args.Cancel = true; };
        core.NewWindowRequested += (_, args) => { args.Handled = true; if (args.IsUserInitiated) OpenExternal(args.Uri); };
        core.PermissionRequested += (_, args) => { args.State = CoreWebView2PermissionState.Deny; args.Handled = true; };
        core.WebMessageReceived += OnWebMessage;
        core.DownloadStarting += OnDownload;
        core.NavigationCompleted += async (_, args) =>
        {
            if (closing) return;
            if (!args.IsSuccess)
            {
                if (args.WebErrorStatus != CoreWebView2WebErrorStatus.OperationCanceled)
                {
                    ShowError("Could not load the workspace", "The local service could not be reached. Select Try again to reopen it.");
                    if (options.SmokeTest) await FinishSmokeAsync(false, "WebView2 navigation failed: " + args.WebErrorStatus);
                }
                return;
            }
            if (!TrustedCurrent()) return;
            web.Visible = true;
            startup.Visible = false;
            web.Focus();
            if (!startupTimingRecorded)
            {
                pageReadyMs = startupWatch?.ElapsedMilliseconds;
                RecordStartupTiming(success: true);
            }
            if (options.SmokeTest && !smokeStarted)
            {
                smokeStarted = true;
                await VerifySmokeAsync();
            }
        };
        core.ProcessFailed += async (_, args) =>
        {
            ShowError("The workspace window stopped", "Select Try again to reconnect. Your research data is saved by the local service.");
            if (options.SmokeTest) await FinishSmokeAsync(false, "WebView2 process failed: " + args.ProcessFailedKind);
        };
    }

    private bool Trusted(string value) => origin is not null && Uri.TryCreate(value, UriKind.Absolute, out var candidate) && candidate.Scheme == origin.Scheme && candidate.Host == origin.Host && candidate.Port == origin.Port && string.IsNullOrEmpty(candidate.UserInfo);
    private bool TrustedCurrent() => web.CoreWebView2 is not null && web.Source is not null && Trusted(web.Source.AbsoluteUri);

    private async void EvaluateTrusted(string script)
    {
        if (!TrustedCurrent()) return;
        try { await web.ExecuteScriptAsync(script); }
        catch (Exception error) when (error is InvalidOperationException or System.Runtime.InteropServices.COMException) { }
    }

    private void Post(object message)
    {
        if (TrustedCurrent()) web.CoreWebView2.PostWebMessageAsJson(JsonSerializer.Serialize(message));
    }

    private void OnWebMessage(object? sender, CoreWebView2WebMessageReceivedEventArgs args)
    {
        if (!TrustedCurrent() || !Trusted(args.Source) || args.WebMessageAsJson.Length > 16384) return;
        try
        {
            using var document = JsonDocument.Parse(args.WebMessageAsJson);
            var message = document.RootElement;
            if (message.GetProperty("channel").GetString() != "nomisma") return;
            string? id = message.GetProperty("id").GetString();
            if (id is null || id.Length > 80) return;
            string? action = message.GetProperty("action").GetString();
            object? result;
            switch (action)
            {
                case "ping": result = new { platform = "windows", desktop_api = 1 }; break;
                case "notificationPermission":
                    if (options.SmokeTest) { result = "denied"; break; }
                    // Leave the WebView2 callback before opening a modal dialog.
                    BeginInvoke(() =>
                    {
                        if (closing || !TrustedCurrent()) return;
                        permission = MessageBox.Show(this, "Allow Nomisma to show desktop alerts while this app is open?\n\nWindows notification settings and Do not disturb may suppress alerts.", "Nomisma desktop alerts", MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes ? "granted" : "denied";
                        try
                        {
                            Directory.CreateDirectory(Path.GetDirectoryName(preferenceFile)!);
                            File.WriteAllText(preferenceFile, JsonSerializer.Serialize(new { notificationPermission = permission }));
                        }
                        catch (Exception error) when (error is IOException or UnauthorizedAccessException) { }
                        Post(new { channel = "nomisma", id, result = permission });
                    });
                    return;
                case "notify" when permission == "granted" && !options.SmokeTest:
                    latestNotification = Limit(message.GetProperty("notificationId").GetString(), 100);
                    notificationIcon.Visible = true;
                    notificationIcon.ShowBalloonTip(8000, Limit(message.GetProperty("title").GetString(), 63), Limit(message.GetProperty("body").GetString(), 255), ToolTipIcon.Info);
                    result = true;
                    break;
                default: Post(new { channel = "nomisma", id, error = "This desktop action is unavailable." }); return;
            }
            Post(new { channel = "nomisma", id, result });
        }
        catch (Exception error) when (error is JsonException or KeyNotFoundException or InvalidOperationException) { }
    }

    private static string Limit(string? value, int maximum) => value is null ? "" : value.Length <= maximum ? value : value[..maximum];

    private void OnDownload(object? sender, CoreWebView2DownloadStartingEventArgs args)
    {
        string source = args.DownloadOperation.Uri;
        bool allowed = TrustedCurrent() && (Trusted(source) || source.StartsWith("blob:", StringComparison.Ordinal) && Trusted(source[5..]));
        if (!allowed || options.SmokeTest) { args.Cancel = true; return; }
        var deferral = args.GetDeferral();
        BeginInvoke(() =>
        {
            try
            {
                if (closing) { args.Cancel = true; return; }
                string name = Path.GetFileName(args.ResultFilePath);
                using var dialog = new SaveFileDialog { Title = "Save Nomisma export", FileName = name, AddExtension = true, OverwritePrompt = true, RestoreDirectory = true };
                string extension = Path.GetExtension(name).ToLowerInvariant();
                dialog.Filter = extension == ".csv" ? "CSV file (*.csv)|*.csv|All files (*.*)|*.*" : extension is ".sqlite3" or ".sqlite" ? "SQLite backup (*.sqlite3)|*.sqlite3|All files (*.*)|*.*" : "All files (*.*)|*.*";
                if (dialog.ShowDialog(this) == DialogResult.OK) args.ResultFilePath = dialog.FileName;
                else args.Cancel = true;
            }
            finally { deferral.Complete(); }
        });
    }

    private static void OpenExternal(string value)
    {
        if (!Uri.TryCreate(value, UriKind.Absolute, out var address) || address.Scheme is not ("https" or "http") || !string.IsNullOrEmpty(address.UserInfo)) return;
        try { Process.Start(new ProcessStartInfo(address.AbsoluteUri) { UseShellExecute = true }); }
        catch (Exception error) when (error is System.ComponentModel.Win32Exception or InvalidOperationException) { }
    }

    private void OpenFolder(string path)
    {
        try { Directory.CreateDirectory(path); Process.Start(new ProcessStartInfo("explorer.exe") { ArgumentList = { path }, UseShellExecute = false }); }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or System.ComponentModel.Win32Exception) { MessageBox.Show(this, "This folder could not be opened.", "Nomisma", MessageBoxButtons.OK, MessageBoxIcon.Error); }
    }

    private void ShowError(string title, string message, bool webViewMissing = false)
    {
        if (closing) return;
        RecordStartupTiming(success: false);
        web.Visible = false;
        startup.Visible = true;
        startup.BringToFront();
        heading.Text = title;
        detail.Text = message;
        progress.Visible = false;
        retry.Visible = true;
        installWebView.Visible = webViewMissing;
    }

    private void RecordStartupTiming(bool success)
    {
        if (startupWatch is null || startupTimingRecorded) return;
        startupTimingRecorded = true;
        startupWatch.Stop();
        // Milestones are cumulative milliseconds from this opening attempt.
        // Keep diagnostics limited to app metadata and durations: never include
        // the workspace path, provider response, environment, or error text.
        string record = JsonSerializer.Serialize(new
        {
            timestamp = DateTimeOffset.UtcNow.ToString("O"),
            version = Application.ProductVersion.Split('+')[0],
            success,
            elapsed_ms = startupWatch.ElapsedMilliseconds,
            backend_ready_ms = backendReadyMs,
            webview_ready_ms = webviewReadyMs,
            page_ready_ms = pageReadyMs,
        });
        string directory = ready?.DataDirectory ?? options.DataDirectory ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Nomisma", "data");
        _ = WriteStartupTimingAsync(directory, record);
    }

    private async Task WriteStartupTimingAsync(string directory, string record)
    {
        await startupLogLock.WaitAsync();
        try
        {
            Directory.CreateDirectory(directory);
            string path = Path.Combine(directory, "startup.log");
            const long maximumBytes = 256 * 1024;
            if (File.Exists(path) && new FileInfo(path).Length + System.Text.Encoding.UTF8.GetByteCount(record) + 2 > maximumBytes)
                File.Move(path, path + ".previous", true);
            await File.AppendAllTextAsync(path, record + Environment.NewLine);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or System.Security.SecurityException) { }
        finally { startupLogLock.Release(); }
    }

    private async Task StopHostAsync()
    {
        var process = host;
        host = null;
        if (process is null) return;
        try
        {
            if (!process.HasExited)
            {
                process.StandardInput.Close();
                try { await process.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(8)); }
                catch (TimeoutException) { process.Kill(entireProcessTree: true); await process.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(5)); }
            }
        }
        catch (Exception error) when (error is InvalidOperationException or System.ComponentModel.Win32Exception or IOException or TimeoutException) { }
        finally { process.Dispose(); }
    }

    private async Task SaveServiceLogAsync(Process process)
    {
        try
        {
            string? line;
            while ((line = await process.StandardError.ReadLineAsync()) is not null)
            {
                // The backend sanitizes provider errors before logging. Strip
                // credential assignments as a second guard and bound log size.
                string sanitized = System.Text.RegularExpressions.Regex.Replace(line, @"(?i)(ALPACA_[A-Z_]*(?:KEY|SECRET)|FMP_API_KEY|Authorization)\s*[:=]\s*\S+", "$1=[redacted]");
                string directory = ready?.DataDirectory ?? options.DataDirectory ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Nomisma", "data");
                Directory.CreateDirectory(directory);
                string path = Path.Combine(directory, "nomisma.log");
                if (File.Exists(path) && new FileInfo(path).Length > 5 * 1024 * 1024) File.Move(path, path + ".previous", true);
                await File.AppendAllTextAsync(path, DateTimeOffset.Now.ToString("O") + " " + Limit(sanitized, 4096) + Environment.NewLine);
            }
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidOperationException or ObjectDisposedException) { }
    }

    private async void OnClosing(object? sender, FormClosingEventArgs args)
    {
        if (closed) return;
        args.Cancel = true;
        if (closing) return;
        closing = true;
        RecordStartupTiming(success: false);
        smokeTimer.Stop();
        Enabled = false;
        status.Text = "Closing the local service…";
        await StopHostAsync();
        notificationIcon.Visible = false;
        web.Dispose();
        closed = true;
        Close();
    }

    private async Task VerifySmokeAsync()
    {
        try
        {
            await web.ExecuteScriptAsync("void (async () => { const health = await (await fetch('/api/health')).json(); const bridge = await window.nomismaDesktop.ping(); window.__nomismaSmoke = {health_ok:health.app === 'nomisma' && health.status === 'ok', bridge_ready:bridge.platform === 'windows' && bridge.desktop_api === 1}; })().catch(error => {window.__nomismaSmoke = {error:String(error)}})");
            for (int attempt = 0; attempt < 120 && !closing; attempt++)
            {
                var result = await web.ExecuteScriptAsync("JSON.stringify({...window.__nomismaSmoke, page_loaded:!!document.querySelector('#live-start') && !!document.querySelector('#sidebar-settings') && !document.querySelector('#workspace-content')?.classList.contains('hidden')})");
                string json = JsonSerializer.Deserialize<string>(result) ?? "{}";
                using var document = JsonDocument.Parse(json);
                var value = document.RootElement;
                if (value.TryGetProperty("error", out var error)) throw new InvalidOperationException("Desktop bridge check failed: " + error.GetString());
                if (value.TryGetProperty("health_ok", out var health) && health.GetBoolean() && value.GetProperty("bridge_ready").GetBoolean() && value.GetProperty("page_loaded").GetBoolean())
                {
                    await FinishSmokeAsync(true);
                    return;
                }
                await Task.Delay(200);
            }
            await FinishSmokeAsync(false, "The workspace page or desktop bridge did not become ready.");
        }
        catch (Exception error) { await FinishSmokeAsync(false, error.GetType().Name + ": " + error.Message); }
    }

    private async Task FinishSmokeAsync(bool success, string? error = null)
    {
        if (smokeFinished) return;
        smokeFinished = true;
        smokeTimer.Stop();
        string? webViewVersion = web.CoreWebView2?.Environment.BrowserVersionString;
        await StopHostAsync();
        bool stopped = ready?.OwnedServer == true;
        if (ready is not null && stopped)
        {
            using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
            try
            {
                using var response = await client.GetAsync(new Uri(new Uri(ready.Url), "/api/health"));
                stopped = false;
            }
            catch (Exception failure) when (failure is HttpRequestException or TaskCanceledException) { }
        }
        if (success && !stopped) { success = false; error = "The smoke test did not stop its owned backend."; }
        ExitCode = success ? 0 : 1;
        try
        {
            Program.WriteResult(options.ResultFile, new { success, error, platform = "windows", url = ready?.Url, data_directory = ready?.DataDirectory, owned_server = ready?.OwnedServer ?? false, webview_version = webViewVersion, page_loaded = success, bridge_ready = success, health_ok = success, backend_stopped = stopped, backend_ready_ms = backendReadyMs, webview_ready_ms = webviewReadyMs, page_ready_ms = pageReadyMs });
        }
        catch (Exception failure) when (failure is IOException or UnauthorizedAccessException) { ExitCode = 1; }
        Close();
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing) { smokeTimer.Dispose(); notificationIcon.Dispose(); }
        base.Dispose(disposing);
    }
}
