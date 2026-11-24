using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Net;
using System.Net.NetworkInformation;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace OverFieldLocal
{
    static class Program
    {
        [STAThread]
        static void Main(string[] args)
        {
            bool created;
            using (var instance = new Mutex(true, "Local\\OverFieldLocalLauncher", out created))
            {
                if (!created)
                {
                    Native.FocusLauncher();
                    return;
                }
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Application.ThreadException += delegate(object sender, ThreadExceptionEventArgs e)
                {
                    MessageBox.Show("操作未完成：" + e.Exception.Message, "开放空间启动器", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                };
                var form = new LauncherForm(args);
                Application.Run(form);
            }
        }
    }

    static class Native
    {
        [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr handle);
        [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr handle, int command);
        public static void FocusLauncher()
        {
            foreach (var p in Process.GetProcessesByName(Process.GetCurrentProcess().ProcessName))
                using (p) { if (p.Id != Process.GetCurrentProcess().Id && p.MainWindowHandle != IntPtr.Zero) Focus(p.MainWindowHandle); }
        }
        public static void Focus(IntPtr handle) { ShowWindow(handle, 9); SetForegroundWindow(handle); }
        public static void FocusGame(string root)
        {
            foreach (var p in Process.GetProcessesByName("launcher"))
                using (p)
                    try
                    {
                        if (String.Equals(p.MainModule.FileName, Path.Combine(root, "OverField Game", "launcher.exe"), StringComparison.OrdinalIgnoreCase) && p.MainWindowHandle != IntPtr.Zero)
                            Focus(p.MainWindowHandle);
                    }
                    catch { }
        }
    }

    static class Theme
    {
        public static Color Bg = Color.FromArgb(237, 247, 250), Panel = Color.FromArgb(252, 254, 253), Border = Color.FromArgb(198, 221, 226);
        public static Color Text = Color.FromArgb(39, 71, 90), Muted = Color.FromArgb(87, 120, 137), Accent = Color.FromArgb(49, 166, 171);
        public static Font Font(float size, FontStyle style = FontStyle.Regular) { return new Font("Microsoft YaHei UI", size, style); }
        public static GraphicsPath Round(Rectangle r, int radius)
        {
            var p = new GraphicsPath(); int d = radius * 2;
            p.AddArc(r.Left, r.Top, d, d, 180, 90); p.AddArc(r.Right - d, r.Top, d, d, 270, 90);
            p.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90); p.AddArc(r.Left, r.Bottom - d, d, d, 90, 90); p.CloseFigure(); return p;
        }
    }

    class Surface : Panel
    {
        public Surface() { DoubleBuffered = true; BackColor = Theme.Panel; }
        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            using (var path = Theme.Round(new Rectangle(0, 0, Width - 1, Height - 1), 12))
            using (var brush = new SolidBrush(Theme.Panel))
            using (var pen = new Pen(Theme.Border)) { e.Graphics.FillPath(brush, path); e.Graphics.DrawPath(pen, path); }
            base.OnPaint(e);
        }
    }

    class ActionButton : Button
    {
        public bool Primary;
        bool hover;
        public ActionButton(string text, bool primary = false)
        {
            Text = text; Primary = primary; Font = Theme.Font(11, FontStyle.Bold); Cursor = Cursors.Hand;
            FlatStyle = FlatStyle.Flat; FlatAppearance.BorderSize = 0; BackColor = Theme.Bg; Dock = DockStyle.Fill;
            Margin = new Padding(0, 0, 12, 0); SetStyle(ControlStyles.UserPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.AllPaintingInWmPaint, true);
        }
        protected override void OnMouseEnter(EventArgs e) { hover = true; Invalidate(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { hover = false; Invalidate(); base.OnMouseLeave(e); }
        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.Clear(Theme.Bg); e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            Color fill = Primary ? (hover ? Color.FromArgb(63, 183, 187) : Theme.Accent) : (hover ? Color.FromArgb(226, 245, 246) : Theme.Panel);
            if (!Enabled) fill = Color.FromArgb(228, 237, 239);
            using (var path = Theme.Round(new Rectangle(0, 0, Width - 1, Height - 1), 10))
            using (var brush = new SolidBrush(fill))
            using (var pen = new Pen(Primary && Enabled ? fill : Theme.Border)) { e.Graphics.FillPath(brush, path); e.Graphics.DrawPath(pen, path); }
            TextRenderer.DrawText(e.Graphics, Text, Font, new Rectangle(12, 8, Math.Max(1, Width - 24), Math.Max(1, Height - 16)), !Enabled ? Theme.Muted : Primary ? Color.White : Theme.Text, TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.SingleLine | TextFormatFlags.EndEllipsis);
            if (Focused) ControlPaint.DrawFocusRectangle(e.Graphics, new Rectangle(6, 6, Width - 12, Height - 12), Theme.Muted, fill);
        }
    }

    class StatusTile : Control
    {
        public string Caption, Detail = "正在检查";
        public bool Online;
        public StatusTile(string caption) { Caption = caption; DoubleBuffered = true; Dock = DockStyle.Fill; BackColor = Theme.Bg; Margin = new Padding(0, 0, 12, 0); }
        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            using (var path = Theme.Round(new Rectangle(0, 0, Width - 1, Height - 1), 10))
            using (var brush = new SolidBrush(Theme.Panel))
            using (var pen = new Pen(Theme.Border)) { e.Graphics.FillPath(brush, path); e.Graphics.DrawPath(pen, path); }
            using (var dot = new SolidBrush(Online ? Theme.Accent : Theme.Muted)) e.Graphics.FillEllipse(dot, 17, 19, 7, 7);
            using (var font = Theme.Font(10, FontStyle.Bold)) TextRenderer.DrawText(e.Graphics, Caption, font, new Rectangle(33, 10, Math.Max(1, Width - 47), 28), Theme.Text, TextFormatFlags.SingleLine | TextFormatFlags.EndEllipsis | TextFormatFlags.VerticalCenter);
            using (var font = Theme.Font(9)) TextRenderer.DrawText(e.Graphics, Detail, font, new Rectangle(17, 41, Math.Max(1, Width - 34), Math.Max(1, Height - 48)), Theme.Muted, TextFormatFlags.SingleLine | TextFormatFlags.EndEllipsis);
        }
        public void UpdateState(bool online, string detail) { Online = online; Detail = detail; Invalidate(); }
    }

    class Result { public int Code; public string Output, Error; }
    class ServiceStatus
    {
        public bool HttpListening { get; set; }
        public bool GatewayListening { get; set; }
        public bool ProxyListening { get; set; }
        public bool ServerRunning { get; set; }
        public bool ProxyRunning { get; set; }
        public bool ProxyEnabled { get; set; }
        public bool ClientRunning { get; set; }
        public string Mode { get; set; }
        public string RuntimeMode { get; set; }
        public string Target { get; set; }
        public string ProfilePath { get; set; }
        public bool FirewallConfigured { get; set; }
        public bool Ready { get { return HttpListening && GatewayListening && ProxyListening && ServerRunning && ProxyRunning && ProxyEnabled; } }
    }

    class Backend
    {
        public readonly string BaseDir = AppDomain.CurrentDomain.BaseDirectory;
        public string Root = "";
        public string Python;
        public string Mode = "solo";
        public string HostAddress;
        public uint Uid = 1000000;
        public string ProfilePath { get { return Path.Combine(BaseDir, "profiles", Mode); } }
        public string ClientExe { get { return Path.Combine(ProfilePath, "client", "launcher.exe"); } }
        internal string ControlScript;
        internal int ControlTimeoutMilliseconds = 60000;
        readonly CancellationTokenSource lifetime = new CancellationTokenSource();
        public void CancelAll() { lifetime.Cancel(); }
        public Backend()
        {
            ControlScript = Path.Combine(BaseDir, "World-Control.ps1");
            var addresses = LanAddresses(); HostAddress = addresses.Count > 0 ? addresses[0] : "";
            Python = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Python", "Python312", "python.exe");
            var path = Path.Combine(BaseDir, "launcher.settings.json");
            if (File.Exists(path))
                try
                {
                    var data = new JavaScriptSerializer().Deserialize<Dictionary<string, string>>(File.ReadAllText(path, Encoding.UTF8));
                    if (data.ContainsKey("gameRoot")) Root = data["gameRoot"];
                    if (data.ContainsKey("pythonExe")) Python = data["pythonExe"];
                    if (data.ContainsKey("mode") && (data["mode"] == "solo" || data["mode"] == "host")) Mode = data["mode"];
                    if (data.ContainsKey("hostAddress") && !String.IsNullOrWhiteSpace(data["hostAddress"])) HostAddress = data["hostAddress"];
                    if (data.ContainsKey("uid")) { uint parsed; if (UInt32.TryParse(data["uid"], out parsed) && parsed > 0) Uid = parsed; }
                }
                catch { }
            string bundled = Path.Combine(BaseDir, "runtime-python", "python.exe");
            if (File.Exists(bundled)) Python = bundled;
            if (!File.Exists(Python))
                foreach (string folder in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(';'))
                    if (File.Exists(Path.Combine(folder, "python.exe"))) { Python = Path.Combine(folder, "python.exe"); break; }
        }
        public void Save()
        {
            var path = Path.Combine(BaseDir, "launcher.settings.json");
            var temp = path + ".tmp";
            File.WriteAllText(temp, new JavaScriptSerializer().Serialize(new Dictionary<string, string> { { "gameRoot", Root }, { "pythonExe", Python }, { "mode", Mode }, { "hostAddress", HostAddress }, { "uid", Uid.ToString() } }), new UTF8Encoding(false));
            if (File.Exists(path)) File.Replace(temp, path, null); else File.Move(temp, path);
        }
        public static List<string> LanAddresses()
        {
            var result = new List<string>();
            foreach (var adapter in NetworkInterface.GetAllNetworkInterfaces())
                if (adapter.OperationalStatus == OperationalStatus.Up)
                    foreach (var item in adapter.GetIPProperties().UnicastAddresses)
                    {
                        byte[] b = item.Address.GetAddressBytes();
                        if (b.Length == 4 && (b[0] == 10 || b[0] == 172 && b[1] >= 16 && b[1] <= 31 || b[0] == 192 && b[1] == 168)) result.Add(item.Address.ToString());
                    }
            return result;
        }
        public static string Quote(string arg)
        {
            var b = new StringBuilder("\""); int slashes = 0;
            foreach (char c in arg)
            {
                if (c == '\\') { slashes++; continue; }
                if (c == '"') b.Append('\\', slashes * 2 + 1).Append('"');
                else b.Append('\\', slashes).Append(c);
                slashes = 0;
            }
            return b.Append('\\', slashes * 2).Append('"').ToString();
        }
        public Result Run(string action, bool launch = false, CancellationToken cancellation = default(CancellationToken))
        {
            var arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File " + Quote(ControlScript) + " -Action " + action + " -GameRoot " + Quote(Root);
            arguments += " -Mode " + Mode + " -HostAddress " + Quote(Mode == "solo" ? "127.0.0.1" : HostAddress) + " -Uid " + Uid.ToString();
            if (action == "Status") arguments += " -Json";
            if (action == "Start" || action == "Backup") arguments += " -PythonExe " + Quote(Python);
            if (action == "Stop") arguments += " -StopServer";
            if (launch) arguments += " -LaunchClient";
            string operations = Path.Combine(BaseDir, "runtime", "operations");
            Directory.CreateDirectory(operations);
            string resultPath = Path.Combine(operations, Guid.NewGuid().ToString("N") + ".json");
            arguments += " -ResultPath " + Quote(resultPath);
            try
            {
                ExecuteProcess(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell", "v1.0", "powershell.exe"), arguments, action == "Status" ? 12000 : ControlTimeoutMilliseconds, false, cancellation);
                if (!File.Exists(resultPath)) throw new InvalidOperationException("服务控制程序未返回结果，请查看运行记录。");
                return new JavaScriptSerializer().Deserialize<Result>(File.ReadAllText(resultPath, Encoding.UTF8));
            }
            finally { try { if (File.Exists(resultPath)) File.Delete(resultPath); } catch { } }
        }
        public Result Execute(string executable, string arguments)
        {
            return ExecuteProcess(executable, arguments, 15000, true, CancellationToken.None);
        }
        Result ExecuteProcess(string executable, string arguments, int timeout, bool capture, CancellationToken cancellation)
        {
            using (var linked = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token, cancellation))
            using (var p = new Process())
            {
                linked.Token.ThrowIfCancellationRequested();
                p.StartInfo = new ProcessStartInfo(executable, arguments) { UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = BaseDir,
                    RedirectStandardOutput = capture, RedirectStandardError = capture };
                if (capture) { p.StartInfo.StandardOutputEncoding = Encoding.UTF8; p.StartInfo.StandardErrorEncoding = Encoding.UTF8; }
                p.Start();
                var output = capture ? p.StandardOutput.ReadToEndAsync() : Task.FromResult("");
                var error = capture ? p.StandardError.ReadToEndAsync() : Task.FromResult("");
                using (linked.Token.Register(delegate { try { if (!p.HasExited) p.Kill(); } catch { } }))
                {
                    var clock = Stopwatch.StartNew();
                    while (!p.WaitForExit(100))
                    {
                        linked.Token.ThrowIfCancellationRequested();
                        if (clock.ElapsedMilliseconds > timeout)
                        {
                            try { p.Kill(); } catch { }
                            throw new TimeoutException("操作超时，已停止等待。请检查状态后重试。");
                        }
                    }
                    linked.Token.ThrowIfCancellationRequested();
                    if (capture && !Task.WaitAll(new Task[] { output, error }, 2000))
                        throw new TimeoutException("程序已经退出，但输出流未结束，已停止等待。");
                    return new Result { Code = p.ExitCode, Output = output.Result.Trim(), Error = error.Result.Trim() };
                }
            }
        }
        public ServiceStatus Status()
        {
            var r = Run("Status");
            if (r.Code != 0) throw new InvalidOperationException(r.Error.Length > 0 ? r.Error : "无法读取服务状态。");
            return new JavaScriptSerializer().Deserialize<ServiceStatus>(r.Output);
        }
        public static string FindClient(string root)
        {
            if (String.IsNullOrWhiteSpace(root)) return null;
            var direct = new[] { Path.Combine(root, "OverField Game", "launcher.exe"), Path.Combine(root, "launcher.exe") };
            foreach (var candidate in direct) if (File.Exists(candidate)) return candidate;
            try
            {
                foreach (var child in Directory.GetDirectories(root))
                    foreach (var candidate in new[] { Path.Combine(child, "OverField Game", "launcher.exe"), Path.Combine(child, "launcher.exe") })
                        if (File.Exists(candidate)) return candidate;
            }
            catch { }
            return null;
        }
        public static string FindServer(string root)
        {
            if (!String.IsNullOrWhiteSpace(root))
            {
                if (File.Exists(Path.Combine(root, "LoloServer", "Lolo.exe"))) return Path.Combine(root, "LoloServer");
                try
                {
                    foreach (var child in Directory.GetDirectories(root))
                    {
                        var nested = Path.Combine(child, "LoloServer");
                        if (File.Exists(Path.Combine(nested, "Lolo.exe"))) return nested;
                    }
                }
                catch { }
            }
            return Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "server-kit");
        }
        public void ValidateRoot(string root)
        {
            string server = FindServer(root);
            foreach (var path in new[] { Path.Combine(server, "Lolo.exe"), Path.Combine(server, "config.json") })
                if (!File.Exists(path))
                    throw new InvalidOperationException("所选目录缺少服务端：" + path + "\n请选择包含 LoloServer 的上层目录，或把服务端放到启动器旁边的 server-kit 文件夹。");
        }
        public Dictionary<string, object> Official(string action, string extra = "")
        {
            string script = Path.Combine(BaseDir, "official_capture.py");
            if (!File.Exists(script)) throw new InvalidOperationException("缺少 official_capture.py，请重新解压完整工具包。");
            var arguments = "-X utf8 " + Quote(script) + " " + action + extra;
            var result = Execute(Python, arguments);
            if (result.Code != 0)
            {
                string message = result.Error.Length > 0 ? result.Error : result.Output;
                try
                {
                    var parsed = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(message);
                    if (parsed.ContainsKey("error")) message = Convert.ToString(parsed["error"]);
                }
                catch { }
                throw new InvalidOperationException(message.Length > 0 ? message : "公服采集操作失败。");
            }
            return new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(result.Output);
        }
        public Dictionary<string, object> OfficialImport(string action, string accountZip, uint uid, bool replace)
        {
            string script = Path.Combine(BaseDir, "official_import.py");
            if (!File.Exists(script)) throw new InvalidOperationException("缺少 official_import.py，请重新解压完整工具包。");
            var arguments = "-X utf8 " + Quote(script) + " " + action + " --file " + Quote(accountZip) + " --database " + Quote(Path.Combine(ProfilePath, "db", "lolo.db"));
            if (uid > 0) arguments += " --uid " + uid;
            if (replace) arguments += " --replace";
            var result = Execute(Python, arguments);
            if (result.Code != 0)
            {
                string message = result.Error.Length > 0 ? result.Error : result.Output;
                try
                {
                    var parsed = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(message);
                    if (parsed.ContainsKey("error")) message = Convert.ToString(parsed["error"]);
                }
                catch { }
                throw new InvalidOperationException(message.Length > 0 ? message : "账号入库失败。");
            }
            return new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(result.Output);
        }
        public Dictionary<string, object> Capture(string action, string path, uint uid, bool replace)
        {
            string arguments = "-X utf8 " + Quote(Path.Combine(BaseDir, "capture_import.py")) + " " + action + " --file " + Quote(path) + " --profile " + Quote(ProfilePath) + " --uid " + uid.ToString();
            if (replace) arguments += " --replace";
            var result = Execute(Python, arguments);
            if (result.Code != 0) throw new InvalidOperationException(result.Error);
            return new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(result.Output);
        }
        public void PrepareProfile()
        {
            var result = Execute(Python, "-X utf8 " + Quote(Path.Combine(BaseDir, "profile_manager.py")) + " prepare --root " + Quote(Root) + " --base " + Quote(Path.Combine(BaseDir, "profiles")) + " --mode " + Mode + " --host " + Quote(Mode == "solo" ? "127.0.0.1" : HostAddress));
            if (result.Code != 0) throw new InvalidOperationException(result.Error);
        }
        public void FocusClient()
        {
            foreach (var process in Process.GetProcessesByName("launcher"))
                using (process) try { if (String.Equals(process.MainModule.FileName, ClientExe, StringComparison.OrdinalIgnoreCase) && process.MainWindowHandle != IntPtr.Zero) Native.Focus(process.MainWindowHandle); } catch { }
        }
        public void EnableLanFirewall()
        {
            var arguments = "-NoProfile -ExecutionPolicy Bypass -File " + Quote(Path.Combine(BaseDir, "Lan-Firewall.ps1")) + " -GameRoot " + Quote(Root) + " -HostAddress " + Quote(HostAddress) + " -ServerExe " + Quote(Path.Combine(BaseDir, "profiles", "host", "server", "Lolo.exe")) + " -PythonExe " + Quote(Python);
            using (var process = Process.Start(new ProcessStartInfo("powershell.exe", arguments) { UseShellExecute = true, Verb = "runas", WindowStyle = ProcessWindowStyle.Hidden }))
                if (!process.WaitForExit(30000) || process.ExitCode != 0) throw new InvalidOperationException("局域网权限未设置，请允许 Windows 管理员确认后重试。");
        }
    }

    partial class LauncherForm : Form
    {
        readonly Backend backend = new Backend();
        readonly StatusTile server = new StatusTile("服务端"), gateway = new StatusTile("游戏网关"), proxy = new StatusTile("游戏连接");
        readonly ActionButton start = new ActionButton("启动游戏  →", true), services = new ActionButton("启动服务"), stop = new ActionButton("停止服务"), browse = new ActionButton("更改目录");
        readonly ActionButton captureStart = new ActionButton("开始采集"), captureStop = new ActionButton("结束采集");
        readonly Label captureHint = new Label();
        readonly ActionButton soloMode = new ActionButton("单机模式"), hostMode = new ActionButton("局域网服务"), captureMode = new ActionButton("公服采集"), importData = new ActionButton("导入数据"), backupData = new ActionButton("备份存档"), openData = new ActionButton("数据目录"), firewall = new ActionButton("局域网权限"), roomsButton=new ActionButton("房间与玩家");
        readonly NumericUpDown uidBox = new NumericUpDown();
        readonly ComboBox hostBox = new ComboBox();
        readonly Label profileLabel = new Label(), modeHint = new Label();
        Surface capturePage;
        Panel mainScroll;
        readonly Label captureSteps = new Label();
        readonly Label headline = new Label(), subtitle = new Label(), badge = new Label(), footer = new Label();
        readonly TextBox rootPath = new TextBox();
        readonly RichTextBox logs = new RichTextBox();
        readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer();
        bool busy, checking, closing;
        CancellationTokenSource operationCancellation;
        ServiceStatus lastStatus;
        string lastStatusError, smokePath;
        bool verify, uiPreview;
        string uiPreviewDir, uiPage="";
        public LauncherForm(string[] args)
        {
            Text = "开放空间 · 本地启动器"; Font = Theme.Font(10); BackColor = Theme.Bg; ForeColor = Theme.Text;
            ClientSize = new Size(1240, 900); MinimumSize = new Size(1040, 740); StartPosition = FormStartPosition.CenterScreen;
            AutoScaleMode = AutoScaleMode.Dpi; DoubleBuffered = true;
            if (File.Exists(Path.Combine(backend.BaseDir, "launcher.ico"))) Icon = new Icon(Path.Combine(backend.BaseDir, "launcher.ico"));
            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--smoke-test" && i + 1 < args.Length) smokePath = args[++i];
                else if (args[i] == "--verify") verify = true;
                else if (args[i] == "--ui-preview" && i + 1 < args.Length) { uiPreview=true;uiPreviewDir=args[++i]; }
                else if (args[i] == "--ui-mode" && i + 1 < args.Length) { string m=args[++i];if(m=="solo"||m=="host")backend.Mode=m; }
                else if (args[i] == "--ui-page" && i + 1 < args.Length) { uiPage=args[++i]; }
                else if (args[i] == "--ui-size" && i + 1 < args.Length) { string[] s=args[++i].Split('x');int w,h;if(s.Length==2 && Int32.TryParse(s[0],out w) && Int32.TryParse(s[1],out h))ClientSize=new Size(Math.Max(1024,w),Math.Max(700,h)); }
            }
            if(uiPreview) { backend.HostAddress="192.168.1.10";backend.Uid=1000000;backend.Root=""; }
            BuildLayout();
            ApplyMode();
            ShowCapturePage(false);
            soloMode.Click += async delegate { await SwitchMode("solo"); };
            captureMode.Click += delegate { ShowCapturePage(true); };
            hostMode.Click += async delegate { await SwitchMode("host"); };
            uidBox.ValueChanged += delegate { if (!busy) { backend.Uid=(uint)uidBox.Value; backend.Save(); } };
            hostBox.SelectedIndexChanged += delegate { if (!busy && backend.Mode=="host" && hostBox.SelectedItem != null) { backend.HostAddress=hostBox.SelectedItem.ToString(); backend.Save(); } };
            captureStart.Click += async delegate
            {
                if (busy) return;
                SetBusy(true, "正在开始公服采集");
                try
                {
                    var result = await Task.Run(() => backend.Official("start"));
                    Append("公服采集已开始。现在启动官方客户端，用自己的渠道账号登录并进入游戏。");
                    if (result.ContainsKey("hint")) Append(Convert.ToString(result["hint"]));
                    captureHint.Text = "采集中：请正常登录官方客户端并打开要保存的界面，完成后点「结束采集」。";
                }
                catch (Exception error) { Append(error.Message); captureHint.Text = error.Message; }
                finally { SetBusy(false, ""); }
            };
            captureStop.Click += async delegate
            {
                if (busy) return;
                SetBusy(true, "正在结束采集并写入账号库");
                try
                {
                    var captured = await Task.Run(() => backend.Official("stop"));
                    string zip = captured.ContainsKey("accountZip") ? Convert.ToString(captured["accountZip"]) : "";
                    if (String.IsNullOrWhiteSpace(zip) || !System.IO.File.Exists(zip))
                    {
                        Append("采集结束，但没有生成账号包。请确认登录公服后确实进入了游戏场景。");
                        captureHint.Text = "未获得账号数据，可重新采集。";
                        return;
                    }
                    uint loginUid = (uint)uidBox.Value;
                    var review = await Task.Run(() => backend.OfficialImport("plan", zip, loginUid, false));
                    bool conflict = review.ContainsKey("conflict") && Convert.ToBoolean(review["conflict"]);
                    if (conflict)
                    {
                        string detail = review.ContainsKey("conflictWith") ? Convert.ToString(review["conflictWith"]) : "";
                        Append("UID 冲突：" + detail + " 已有存档，未写入。请先备份该账号或换用其他 UID。");
                        captureHint.Text = "UID 冲突，未写入数据库：" + detail;
                        return;
                    }
                    string message = "即将写入账号库\nUID " + Convert.ToString(review["uid"]) +
                        " · " + Convert.ToString(review["name"]) + "\n等级 " + Convert.ToString(review["level"]) +
                        " · " + Convert.ToString(review["characters"]) + " 个角色\n\n确认写入？";
                    if (MessageBox.Show(this, message, "确认入库", MessageBoxButtons.OKCancel, MessageBoxIcon.Question) != DialogResult.OK) return;
                    var imported = await Task.Run(() => backend.OfficialImport("import", zip, loginUid, false));
                    uint usedUid = Convert.ToUInt32(imported["uid"]);
                    backend.Uid = usedUid; backend.Save(); uidBox.Value = usedUid;
                    Append("账号已写入数据库：UID " + usedUid + "（" + Convert.ToString(imported["name"]) + "）。");
                    captureHint.Text = "已入库：UID " + usedUid + "。可用该 UID 登录当前模式。";
                }
                catch (Exception error) { Append(error.Message); captureHint.Text = error.Message; }
                finally { SetBusy(false, ""); }
            };
            importData.Click += async delegate { await ImportCapture(); };
            backupData.Click += async delegate { await Operate("Backup", false); };
            openData.Click += delegate { OpenFolder(backend.ProfilePath); };
            firewall.Click += async delegate
            {
                if (busy || backend.Mode != "host") return;
                SetBusy(true,"正在设置局域网权限");
                try { await Task.Run(() => { backend.PrepareProfile(); backend.EnableLanFirewall(); }); Append("已允许同一局域网访问当前服务。"); }
                catch (Exception e) { Append(e.Message); }
                finally { SetBusy(false,""); }
                await RefreshStatus();
            };
            start.Click += async delegate { await Operate("Start", backend.Mode=="solo"); };
            services.Click += async delegate { await Operate("Start", false); };
            stop.Click += async delegate
            {
                if (busy && operationCancellation != null) { stop.Enabled = false; operationCancellation.Cancel(); }
                else await Operate("Stop", false);
            };
            browse.Click += BrowseRoot;
            roomsButton.Click += delegate { using(var dialog=new RoomManagerForm(backend)) dialog.ShowDialog(this); };
            timer.Interval = 5000; timer.Tick += async delegate { await RefreshStatus(); };
            Shown += async delegate
            {
                if(uiPreview) { await Task.Delay(400); if(uiPage=="capture") ShowCapturePage(true); await Task.Delay(150); SaveUIPreview(uiPreviewDir); Close(); return; }
                Append("启动器已就绪，正在读取本地服务状态。");
                await RefreshStatus(); if (closing) return; timer.Start();
                if (verify) await Verify();
                if (Array.IndexOf(args,"--rooms-smoke")>=0)
                {
                    using(var dialog=new RoomManagerForm(backend))
                    {
                        dialog.Shown+=async delegate { await Task.Delay(1200);using(var bitmap=new Bitmap(dialog.Width,dialog.Height)) { dialog.DrawToBitmap(bitmap,new Rectangle(0,0,dialog.Width,dialog.Height));bitmap.Save(Path.Combine(backend.BaseDir,"runtime","rooms-preview.png")); } dialog.Close(); };
                        dialog.ShowDialog(this);
                    }
                }
                if (smokePath != null) { await Task.Delay(600); SaveSmoke(); }
            };
            FormClosing += delegate(object sender, FormClosingEventArgs e)
            {
                closing = true; timer.Stop(); timer.Dispose();
                backend.CancelAll();
            };
        }
        Label LabelText(string text, float size, Color color, FontStyle style = FontStyle.Regular)
        {
            return new Label { Text = text, Font = Theme.Font(size, style), ForeColor = color, AutoSize = true, BackColor = Color.Transparent };
        }
        void BuildLegacyLayout()
        {
            var shell = new TableLayoutPanel { Dock=DockStyle.Fill, ColumnCount=2, RowCount=1, Margin=Padding.Empty, BackColor=Theme.Bg };
            shell.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,190)); shell.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100)); Controls.Add(shell);
            var sidebar = new Panel { Dock=DockStyle.Fill, BackColor=Theme.Panel, Padding=new Padding(18,24,18,20), Margin=Padding.Empty };
            shell.Controls.Add(sidebar,0,0);
            var sideBrand=LabelText("本 地 世 界",13,Theme.Accent,FontStyle.Bold); sideBrand.Location=new Point(18,26); sidebar.Controls.Add(sideBrand);
            var sideSmall=LabelText("OVERFIELD",9,Theme.Muted); sideSmall.Location=new Point(19,62); sidebar.Controls.Add(sideSmall);
            var sideCaption=LabelText("运行模式",9,Theme.Muted); sideCaption.Location=new Point(19,137); sidebar.Controls.Add(sideCaption);
            soloMode.Dock=DockStyle.None; soloMode.Location=new Point(16,169); soloMode.Size=new Size(156,48); sidebar.Controls.Add(soloMode);
            var soloDescription=LabelText("仅本机连接\n独立数据与存档",9,Theme.Muted); soloDescription.Location=new Point(23,232); sidebar.Controls.Add(soloDescription);
            hostMode.Dock=DockStyle.None; hostMode.Location=new Point(16,303); hostMode.Size=new Size(156,48); sidebar.Controls.Add(hostMode);
            var hostDescription=LabelText("发布局域网服务\n独立联机存档",9,Theme.Muted); hostDescription.Location=new Point(23,367); sidebar.Controls.Add(hostDescription);
            roomsButton.Dock=DockStyle.None; roomsButton.Location=new Point(16,435); roomsButton.Size=new Size(156,46); sidebar.Controls.Add(roomsButton);
            var localLogin=LabelText("UID 本地登录\n\n数据保存在本电脑\n支持各自导入与备份",9,Theme.Muted); localLogin.Location=new Point(22,550); sidebar.Controls.Add(localLogin);
            var layout = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(26, 22, 26, 18), ColumnCount = 1, RowCount = 8, BackColor = Theme.Bg };
            layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            foreach (int h in new[] { 110, 84, 68, 126, 94, 112, 104, 30 }) layout.RowStyles.Add(new RowStyle(SizeType.Absolute, h));
            layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100)); layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 28)); layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 0));
            shell.Controls.Add(layout,1,0);
            var hero = new Panel { Dock = DockStyle.Fill, Margin = Padding.Empty, BackColor = Theme.Bg };
            var brand = LabelText("O V E R F I E L D   /   L O C A L", 9, Theme.Accent, FontStyle.Bold); brand.Location = new Point(2, 0); hero.Controls.Add(brand);
            headline.Text = "开放空间"; headline.Font = Theme.Font(30, FontStyle.Bold); headline.ForeColor = Theme.Text; headline.AutoSize = true; headline.Location = new Point(-3, 20); hero.Controls.Add(headline);
            subtitle.Text = "你的世界，从这里出发。"; subtitle.Font = Theme.Font(10); subtitle.ForeColor = Theme.Muted; subtitle.AutoSize = true; subtitle.Location = new Point(2, 81); hero.Controls.Add(subtitle);
            badge.Text = "检查中"; badge.Font = Theme.Font(10, FontStyle.Bold); badge.ForeColor = Theme.Muted; badge.TextAlign = ContentAlignment.MiddleRight; badge.Size = new Size(200, 35); badge.Anchor = AnchorStyles.Top | AnchorStyles.Right;
            hero.Controls.Add(badge); hero.Resize += delegate { badge.Location = new Point(hero.Width - badge.Width, 5); };
            hero.Paint += delegate(object sender, PaintEventArgs e)
            {
                var g = e.Graphics; g.SmoothingMode = SmoothingMode.AntiAlias; float x = hero.Width - 184, y = 78;
                using (var p = new Pen(Color.FromArgb(45, 78, 85), 1.4f)) { g.DrawEllipse(p, x - 75, y - 20, 210, 41); g.DrawEllipse(p, x - 18, y - 50, 60, 94); }
                using (var b = new SolidBrush(Theme.Accent)) g.FillEllipse(b, x + 17, y - 6, 9, 9);
                using (var b = new SolidBrush(Color.FromArgb(64, 91, 109))) foreach (var s in new[] { new PointF(x - 88, y - 17), new PointF(x + 89, y - 52), new PointF(x + 135, y + 7) }) g.FillEllipse(b, s.X, s.Y, 3, 3);
            };
            layout.Controls.Add(hero, 0, 0);
            var states = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 3, RowCount = 1, Margin = new Padding(0, 0, 0, 10) };
            for (int i = 0; i < 3; i++) states.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 33.33f));
            proxy.Margin = Padding.Empty; states.Controls.Add(server, 0, 0); states.Controls.Add(gateway, 1, 0); states.Controls.Add(proxy, 2, 0); layout.Controls.Add(states, 0, 1);
            var actions = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 3, RowCount = 1, Margin = new Padding(0, 2, 0, 14) };
            actions.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50)); actions.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 25)); actions.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 25));
            stop.Margin = Padding.Empty; actions.Controls.Add(start, 0, 0); actions.Controls.Add(services, 1, 0); actions.Controls.Add(stop, 2, 0); layout.Controls.Add(actions, 0, 2);
            var directory = new Surface { Dock = DockStyle.Fill, Margin = new Padding(0, 0, 0, 14), Padding = new Padding(17, 12, 15, 12) };
            var pathTitle = LabelText("启动设置", 9, Theme.Muted); pathTitle.Dock = DockStyle.Top; directory.Controls.Add(pathTitle);
            var pathRow = new TableLayoutPanel { Dock = DockStyle.Top, Height = 32, ColumnCount = 2, RowCount = 1, Margin = Padding.Empty, BackColor = Theme.Panel };
            pathRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); pathRow.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 105));
            rootPath.Text = String.IsNullOrWhiteSpace(backend.Root)?"单机启动时选择客户端目录":backend.Root; rootPath.ReadOnly = true; rootPath.BorderStyle = BorderStyle.None; rootPath.BackColor = Theme.Panel; rootPath.ForeColor = Theme.Text; rootPath.Dock = DockStyle.Fill; rootPath.Margin = new Padding(0, 6, 12, 0);
            browse.Font = Theme.Font(9); browse.Margin = Padding.Empty; pathRow.Controls.Add(rootPath, 0, 0); pathRow.Controls.Add(browse, 1, 0); directory.Controls.Add(pathRow); pathTitle.BringToFront();
            var uidRow=new TableLayoutPanel { Dock=DockStyle.Bottom, Height=32, ColumnCount=4, RowCount=1, BackColor=Theme.Panel };
            foreach(float width in new[]{80f,180f,90f}) uidRow.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,width)); uidRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
            var uidLabel=LabelText("UID",9,Theme.Muted); uidLabel.Dock=DockStyle.Fill; uidLabel.TextAlign=ContentAlignment.MiddleLeft;
            uidBox.Minimum=1; uidBox.Maximum=UInt32.MaxValue; uidBox.Value=backend.Uid; uidBox.Dock=DockStyle.Fill; uidBox.Font=Theme.Font(10); uidBox.BackColor=Theme.Panel; uidBox.ForeColor=Theme.Text; uidBox.Margin=new Padding(0,2,20,0);
            var addressLabel=LabelText("服务地址",9,Theme.Muted); addressLabel.Dock=DockStyle.Fill; addressLabel.TextAlign=ContentAlignment.MiddleLeft;
            hostBox.DropDownStyle=ComboBoxStyle.DropDownList; hostBox.Dock=DockStyle.Fill; hostBox.Font=Theme.Font(9); hostBox.BackColor=Theme.Panel; hostBox.ForeColor=Theme.Text; hostBox.Margin=new Padding(0,2,0,0);
            uidRow.Controls.Add(uidLabel,0,0); uidRow.Controls.Add(uidBox,1,0); uidRow.Controls.Add(addressLabel,2,0); uidRow.Controls.Add(hostBox,3,0); directory.Controls.Add(uidRow); layout.Controls.Add(directory, 0, 3);
            directory.Controls.Clear();
            var settingRows=new TableLayoutPanel { Dock=DockStyle.Fill,ColumnCount=1,RowCount=3,Margin=Padding.Empty,BackColor=Theme.Panel };
            settingRows.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
            settingRows.RowStyles.Add(new RowStyle(SizeType.Absolute,22));settingRows.RowStyles.Add(new RowStyle(SizeType.Absolute,32));settingRows.RowStyles.Add(new RowStyle(SizeType.Absolute,32));
            pathTitle.Dock=pathRow.Dock=uidRow.Dock=DockStyle.Fill;pathTitle.Margin=pathRow.Margin=uidRow.Margin=Padding.Empty;
            settingRows.Controls.Add(pathTitle,0,0);settingRows.Controls.Add(pathRow,0,1);settingRows.Controls.Add(uidRow,0,2);directory.Controls.Add(settingRows);
            var dataPanel=new Surface { Dock=DockStyle.Fill, Margin=new Padding(0,0,0,14), Padding=new Padding(16,10,16,10) };
            profileLabel.Dock=DockStyle.Top; profileLabel.Height=24; profileLabel.Font=Theme.Font(8.5f); profileLabel.ForeColor=Theme.Muted; profileLabel.AutoEllipsis=true; dataPanel.Controls.Add(profileLabel);
            var dataActions=new TableLayoutPanel { Dock=DockStyle.Bottom, Height=31, ColumnCount=4, RowCount=1, BackColor=Theme.Panel };
            for(int i=0;i<4;i++) dataActions.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,25));
            int buttonIndex=0; foreach(var button in new[]{importData,backupData,openData,firewall}) { button.Font=Theme.Font(9); dataActions.Controls.Add(button,buttonIndex++,0); } firewall.Margin=Padding.Empty;
            dataPanel.Controls.Add(dataActions); layout.Controls.Add(dataPanel,0,4);
            var logPanel = new Surface { Dock = DockStyle.Fill, Margin = Padding.Empty, Padding = new Padding(16, 13, 16, 14) };
            var logHead = new Panel { Dock = DockStyle.Top, Height = 33, BackColor = Theme.Panel };
            logHead.Controls.Add(LabelText("运行记录", 10, Theme.Text, FontStyle.Bold));
            var openLogs = new LinkLabel { Text = "打开日志文件夹", LinkColor = Theme.Muted, ActiveLinkColor = Theme.Accent, VisitedLinkColor = Theme.Muted, AutoSize = true, Anchor = AnchorStyles.Right | AnchorStyles.Top, BackColor = Theme.Panel };
            logHead.Controls.Add(openLogs); logHead.Resize += delegate { openLogs.Location = new Point(logHead.Width - openLogs.Width, 1); };
            openLogs.LinkClicked += delegate { OpenFolder(Path.Combine(backend.ProfilePath, "logs")); };
            logs.Dock = DockStyle.Fill; logs.ReadOnly = true; logs.BackColor = Theme.Panel; logs.ForeColor = Theme.Muted; logs.BorderStyle = BorderStyle.None; logs.Font = Theme.Font(9); logs.DetectUrls = false; logs.ScrollBars = RichTextBoxScrollBars.Vertical;
            logPanel.Controls.Add(logs); logPanel.Controls.Add(logHead); layout.Controls.Add(logPanel, 0, 6);
            footer.Text = "可随时退出 · 游戏与服务独立运行 · 两种模式的存档分开保存"; footer.ForeColor = Theme.Muted; footer.Font = Theme.Font(8.5f); footer.Dock = DockStyle.Fill; footer.TextAlign = ContentAlignment.BottomLeft; layout.Controls.Add(footer, 0, 7);
        }
        void ShowCapturePage(bool show)
        {
            if (capturePage != null) capturePage.Visible = show;
            if (mainScroll != null && mainScroll.Controls.Count > 1)
                mainScroll.Controls[0].Visible = !show;
            if (show && captureHint != null && String.IsNullOrWhiteSpace(captureHint.Text))
                captureHint.Text = "用你自己的渠道账号登录官方客户端，采集到的数据只写入本机账号库。";
            captureMode.Primary = show;
            soloMode.Primary = !show && backend.Mode == "solo";
            hostMode.Primary = !show && backend.Mode == "host";
            captureMode.Invalidate(); soloMode.Invalidate(); hostMode.Invalidate();
        }
        void ApplyMode()
        {
            soloMode.Primary=backend.Mode=="solo"; hostMode.Primary=backend.Mode=="host"; soloMode.Invalidate(); hostMode.Invalidate();
            subtitle.Text=backend.Mode=="solo" ? "本机单机 · 按 UID 登录 · 独立数据目录" : "局域网服务端 · 按 UID 管理 · 独立联机存档";
            profileLabel.Text="独立数据目录  ·  "+backend.ProfilePath;
            hostBox.Items.Clear();
            if(backend.Mode=="solo") { hostBox.Items.Add("127.0.0.1（仅本机）"); hostBox.SelectedIndex=0; }
            else
            {
                foreach(string address in Backend.LanAddresses()) hostBox.Items.Add(address);
                if(!String.IsNullOrEmpty(backend.HostAddress) && !hostBox.Items.Contains(backend.HostAddress)) hostBox.Items.Add(backend.HostAddress);
                if(hostBox.Items.Contains(backend.HostAddress)) hostBox.SelectedItem=backend.HostAddress;
                else if(hostBox.Items.Count>0) { backend.HostAddress=hostBox.Items[0].ToString();hostBox.SelectedIndex=0; }
            }
            firewall.Enabled=backend.Mode=="host";
            services.Text=backend.Mode=="host" ? "启动服务" : "仅启动服务";
            uidBox.Value=backend.Uid;
        }
        async Task SwitchMode(string mode)
        {
            if(busy || backend.Mode==mode) return;
            {int guard=0;while(checking && !closing && guard++<40) await Task.Delay(50);}
            if(closing) return;
            if(lastStatus!=null && lastStatus.ClientRunning) { Append("请先退出游戏，再切换运行模式。"); return; }
            if(lastStatus!=null && !String.IsNullOrEmpty(lastStatus.RuntimeMode)) await Operate("Stop",false);
            if(closing) return;
            ShowCapturePage(false);
            backend.Mode=mode; backend.Save(); ApplyMode(); Append(mode=="solo" ? "已切换到单机，使用本电脑的独立单机存档。" : "已切换到局域网服务端，使用独立联机存档。");
            await RefreshStatus();
        }
        async Task ImportCapture()
        {
            if(busy) return;
            {int guard=0;while(checking && !closing && guard++<40) await Task.Delay(50);}
            if(closing) return;
            if(lastStatus!=null && lastStatus.ClientRunning) { Append("请先退出游戏，再导入角色数据。"); return; }
            string path;
            using(var dialog=new OpenFileDialog { Title="选择开放空间完整抓包数据",Filter="完整抓包 ZIP|*.zip",CheckFileExists=true })
            { if(dialog.ShowDialog(this)!=DialogResult.OK) return; path=dialog.FileName; }
            try
            {
                var info=await Task.Run(()=>backend.Capture("inspect",path,0,false)); if(closing) return;
                uint uid=Convert.ToUInt32(info["uid"]);
                string message="UID "+uid+" · "+info["name"]+"\n等级 "+info["level"]+" · "+info["characters"]+" 个角色\n\n将导入当前模式的独立数据目录。已有数据会先备份；其他 UID 保留。\n运行中的服务会先停止，并断开在线玩家。\n角色、装备和背包会写入存档，尚未支持的模块会保留原始抓包数据。";
                if(MessageBox.Show(this,message,"确认导入资料",MessageBoxButtons.OKCancel,MessageBoxIcon.Information)!=DialogResult.OK) return;
                if(lastStatus!=null && !String.IsNullOrEmpty(lastStatus.RuntimeMode)) await Operate("Stop",false);
                SetBusy(true,"正在导入角色资料"); stop.Enabled=false;
                await Task.Run(()=> { backend.PrepareProfile(); backend.Capture("import",path,uid,true); }); if(closing) return;
                backend.Uid=uid; backend.Save(); uidBox.Value=uid;
                Append("已导入 UID "+uid+" 的资料。原数据已有备份，其他 UID 保留。");
                Append("导入报告位于数据目录 accounts\\"+uid+"\\import-report.json。");
            }
            catch(Exception e) { Append("导入未完成："+e.Message); }
            finally { SetBusy(false,""); }
            await RefreshStatus();
        }
        void OpenFolder(string path)
        {
            try { Directory.CreateDirectory(path); Process.Start(new ProcessStartInfo("explorer.exe", Backend.Quote(path)) { UseShellExecute = true }); }
            catch (Exception e) { Append("无法打开文件夹：" + e.Message); }
        }
        void Append(string message)
        {
            if (closing) return;
            string line = "[" + DateTime.Now.ToString("HH:mm:ss") + "]  " + message + Environment.NewLine;
            if (logs.TextLength > 45000) logs.Text = logs.Text.Substring(logs.TextLength - 25000);
            logs.AppendText(line); logs.SelectionStart = logs.TextLength; logs.ScrollToCaret();
            try { Directory.CreateDirectory(Path.Combine(backend.BaseDir, "runtime")); File.AppendAllText(Path.Combine(backend.BaseDir, "runtime", "launcher.log"), line, new UTF8Encoding(false)); }
            catch { }
        }
        void SetBusy(bool value, string text)
        {
            if (closing) return;
            busy = value; start.Enabled = services.Enabled = !value; stop.Enabled = true;
            soloMode.Enabled=hostMode.Enabled=importData.Enabled=backupData.Enabled=!value;
            captureMode.Enabled = !value;
            uidBox.Enabled=!value && (lastStatus==null || !lastStatus.ClientRunning); hostBox.Enabled=!value && backend.Mode=="host" && (lastStatus==null || String.IsNullOrEmpty(lastStatus.RuntimeMode)); firewall.Enabled=!value && backend.Mode=="host";
            stop.Text = value ? "取消操作" : "停止服务";
            browse.Enabled = !value && lastStatus != null && !lastStatus.ServerRunning && !lastStatus.ProxyRunning;
            if (value) { badge.Text = text; badge.ForeColor = Theme.Accent; start.Text = "正在处理…"; }
            else start.Text = backend.Mode=="host" ? "发布局域网服务  →" : lastStatus != null && lastStatus.ClientRunning ? "返回游戏  →" : "启动单机游戏  →";
        }
        async Task RefreshStatus()
        {
            if (busy || checking || closing) return; checking = true;
            try
            {
                var status = await Task.Run(() => backend.Status()); if (closing) return;
                lastStatus = status; lastStatusError = null;
                server.UpdateState(status.ServerRunning && status.HttpListening, status.ServerRunning && status.HttpListening ? "运行中 · 本地服务正常" : "未启动");
                gateway.UpdateState(status.GatewayListening && status.ServerRunning, status.GatewayListening && status.ServerRunning ? "已就绪 · 等待游戏连接" : "等待服务启动");
                proxy.UpdateState(status.ProxyRunning && status.ProxyListening && status.ProxyEnabled, status.ProxyRunning && status.ProxyListening && status.ProxyEnabled ? "已连接 · 本地游戏线路" : status.ProxyRunning && status.ProxyListening ? "代理设置未接入" : "等待连接");
                badge.Text = status.Ready ? (backend.Mode=="host" ? "●  局域网已发布" : status.ClientRunning ? "●  游戏已运行" : "●  可以开始游戏") : "○  等待启动";
                badge.ForeColor = status.Ready ? Theme.Accent : Theme.Muted;
                start.Text = backend.Mode=="host" ? "发布局域网服务  →" : status.ClientRunning ? "返回游戏  →" : "启动单机游戏  →";
                browse.Enabled = !status.ServerRunning && !status.ProxyRunning;
                uidBox.Enabled=!status.ClientRunning;
                hostBox.Enabled=backend.Mode=="host" && String.IsNullOrEmpty(status.RuntimeMode);
                profileLabel.Text="独立数据目录  ·  "+backend.ProfilePath;
                proxy.Caption="UID 与房间网关";
                proxy.UpdateState(status.ProxyRunning && status.ProxyEnabled,status.ProxyRunning && status.ProxyEnabled ? "已就绪 · 独立账号与房间管理" : "等待网关启动");
                roomsButton.Enabled=backend.Mode=="host" && status.Ready;
                if(backend.Mode=="host") gateway.UpdateState(status.GatewayListening,status.GatewayListening ? "局域网地址 · "+status.Target : "等待发布局域网服务");
                firewall.Text=backend.Mode=="host" && status.FirewallConfigured ? "权限已配置" : "局域网权限";
            }
            catch (Exception e)
            {
                if (closing) return;
                server.UpdateState(false, "无法检查，请查看运行记录"); gateway.UpdateState(false, "等待检查"); proxy.UpdateState(false, "等待检查");
                badge.Text = "需要检查配置"; badge.ForeColor = Color.FromArgb(244, 181, 125); browse.Enabled = true;
                if (lastStatusError != e.Message) Append("状态检查失败：" + e.Message); lastStatusError = e.Message;
            }
            finally { checking = false; }
        }
        async Task Operate(string action, bool launch)
        {
            if (busy) return;
            while (checking && !closing) await Task.Delay(50);
            if (busy || closing) return;
            operationCancellation = new CancellationTokenSource();
            SetBusy(true, action == "Stop" ? "正在停止服务" : "正在准备游戏");
            Append(action == "Stop" ? "正在停止当前模式的服务并恢复原网络路线。" : action=="Backup" ? "正在备份独立存档…" : launch ? "正在准备 UID "+backend.Uid+" 的本地游戏，请稍候…" : "正在启动 "+(backend.Mode=="solo" ? "单机" : "局域网")+" 服务，请稍候…");
            try
            {
                if (action == "Start") { backend.ValidateRoot(backend.Root); if (!File.Exists(backend.Python)) throw new InvalidOperationException("未找到 Python，请在 launcher.settings.json 中设置 pythonExe。"); }
                var token = operationCancellation.Token;
                var result = await Task.Run(() => backend.Run(action, launch, token));
                if (closing) return;
                if (result.Code != 0) throw new InvalidOperationException(result.Error.Length > 0 ? result.Error : result.Output);
                if (action == "Stop") Append("当前模式的服务已停止，原网络路线已恢复。");
                else if(action=="Backup") Append("备份已保存："+result.Output);
                else
                {
                    Append("本地服务与游戏线路已就绪。");
                    if (launch) { Append(result.Output.Contains("Client already running") ? "游戏已经运行，已保留当前进度。" : "游戏已打开，使用本地 UID "+backend.Uid+" 登录。" ); backend.FocusClient(); }
                }
            }
            catch (OperationCanceledException) { Append("操作已取消。已启动的服务会保留，请查看状态后重试。"); }
            catch (Exception e) { Append("操作失败：" + e.Message); }
            finally
            {
                if (operationCancellation != null) { operationCancellation.Dispose(); operationCancellation = null; }
                SetBusy(false, "");
            }
            if (closing) return;
            await RefreshStatus();
        }
        async void BrowseRoot(object sender, EventArgs e)
        {
            if (busy || checking) return;
            using (var dialog = new FolderBrowserDialog { Description = "选择游戏安装目录，单机启动时使用其中的 launcher.exe", SelectedPath = backend.Root, ShowNewFolderButton = false })
                if (dialog.ShowDialog(this) == DialogResult.OK)
                    try { backend.ValidateRoot(dialog.SelectedPath); if (Backend.FindClient(dialog.SelectedPath) == null) throw new InvalidOperationException("所选目录里没有找到游戏客户端 launcher.exe。\n请选择包含 OverField Game 或 launcher.exe 的目录。"); backend.Root = dialog.SelectedPath; backend.Save(); rootPath.Text = backend.Root; Append("游戏目录已保存。"); await RefreshStatus(); }
                    catch (Exception ex) { Append(ex.Message); MessageBox.Show(this, ex.Message, "目录不可用", MessageBoxButtons.OK, MessageBoxIcon.Warning); }
        }
        async Task Verify()
        {
            var report = new Dictionary<string, object>();
            try
            {
                backend.ValidateRoot(backend.Root); report["gameFiles"] = true;
                var python = await Task.Run(() => backend.Execute(backend.Python, "-X utf8 -c " + Backend.Quote("import asyncio, sqlite3, room_gateway; print('ok')")));
                report["proxyDependency"] = python.Code == 0;
                var version = await Task.Run(() => backend.Execute(backend.Python, "-X utf8 " + Backend.Quote(Path.Combine(backend.BaseDir, "repair_version.py")) + " --root " + Backend.Quote(backend.Root)));
                report["versionRead"] = version.Code == 0; report["version"] = version.Output;
                report["status"] = lastStatus; report["ready"] = lastStatus != null && lastStatus.Ready;
                report["timestamp"] = DateTime.Now.ToString("o");
            }
            catch (Exception e) { report["error"] = e.Message; }
            Directory.CreateDirectory(Path.Combine(backend.BaseDir, "runtime"));
            File.WriteAllText(Path.Combine(backend.BaseDir, "runtime", "launcher-verification.json"), new JavaScriptSerializer().Serialize(report), new UTF8Encoding(false));
            if (smokePath == null) Close();
        }
        void SaveSmoke()
        {
            try { using (var bitmap = new Bitmap(Width, Height)) { DrawToBitmap(bitmap, new Rectangle(0, 0, Width, Height)); bitmap.Save(smokePath, System.Drawing.Imaging.ImageFormat.Png); } }
            finally { Close(); }
        }
    }
}
