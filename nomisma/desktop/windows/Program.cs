using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Nomisma.Desktop;

internal sealed record LaunchOptions(bool SmokeTest, string? DataDirectory, string? ResultFile)
{
    internal static LaunchOptions Parse(string[] args)
    {
        bool smoke = false;
        string? directory = null, result = null;
        for (int index = 0; index < args.Length; index++)
        {
            switch (args[index])
            {
                case "--smoke-test": smoke = true; break;
                case "--data-dir" when index + 1 < args.Length: directory = Path.GetFullPath(args[++index]); break;
                case "--result-file" when index + 1 < args.Length: result = Path.GetFullPath(args[++index]); break;
                default: throw new ArgumentException("Unrecognized or incomplete launch option.");
            }
        }
        if (smoke && (directory is null || result is null))
            throw new ArgumentException("Smoke testing requires --data-dir and --result-file.");
        return new(smoke, directory, result);
    }

    internal string MutexName => SmokeTest
        ? "Local\\Nomisma.Desktop.Smoke." + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(DataDirectory!)))[..16]
        : "Local\\Nomisma.Desktop";
}

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        LaunchOptions options;
        try { options = LaunchOptions.Parse(args); }
        catch (ArgumentException error)
        {
            MessageBox.Show(error.Message, "Nomisma", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        using var instance = new Mutex(true, options.MutexName, out bool isNew);
        if (!isNew)
        {
            if (!options.SmokeTest)
                MessageBox.Show("Nomisma is already open. Select its window from the taskbar.", "Nomisma", MessageBoxButtons.OK, MessageBoxIcon.Information);
            else WriteResult(options.ResultFile, new { success = false, error = "Another smoke test uses this data folder." });
            return 1;
        }
        using var window = new MainWindow(options);
        Application.Run(window);
        return window.ExitCode;
    }

    internal static void WriteResult(string? path, object result)
    {
        if (path is null) return;
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        string temporary = path + ".tmp";
        File.WriteAllText(temporary, JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }));
        File.Move(temporary, path, true);
    }
}
