using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Web.Script.Serialization;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

internal sealed class Bestand {
    public string naam, url, hash, tag;
    public long lengte;
}

internal sealed class Installer : Form {
    const string Api = "https://api.github.com/repos/MisterMol/DROST_Sounboard/releases?per_page=30";
    const string Setup = "DrostSoundboard.Desktop-beta-Setup.exe";
    const string Pack = "DrostSoundboard_startersoundpack.zip";
    readonly Label status = new Label(), hint = new Label(), uitleg = new Label();
    readonly Label onder = new Label();
    readonly ProgressBar balk = new ProgressBar();
    readonly CheckBox pack = new CheckBox();
    readonly Button start = new Button(), stop = new Button(), map = new Button(), openen = new Button();
    readonly HttpClient http = new HttpClient();
    readonly GebundeldeSetup ingesloten;
    CancellationTokenSource annulering;
    bool setupBezig;
    bool basisGeinstalleerd;
    string packPad;

    public Installer() {
        ingesloten = GebundeldeSetup.Zoek();
        if (InstallerUitvoering.VereistGebundeldeRc6 && ingesloten == null)
            throw new InvalidDataException("Deze RC6 testinstaller is beschadigd. Download het bestand opnieuw.");
        Text = "DrostSoundboard installeren";
        ClientSize = new Size(735, 420);
        StartPosition = FormStartPosition.CenterScreen;
        MaximizeBox = false;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        BackColor = Color.FromArgb(30, 40, 49);
        ForeColor = Color.FromArgb(241, 248, 249);
        Font = new Font("Segoe UI", 10);

        var kop = new Label {
            Text = "DrostSoundboard installeren",
            Bounds = new Rectangle(24, 20, 675, 41),
            Font = new Font("Segoe UI", 20, FontStyle.Bold),
            ForeColor = Color.FromArgb(120, 214, 197)
        };
        hint.SetBounds(24, 73, 685, 52);
        hint.Text = ingesloten != null
            ? "RC6 Compact is inbegrepen in dit bestand (ongeveer 73 MiB).\nJe hebt geen Python, Git, .NET SDK of andere ontwikkelsoftware nodig."
            : "DrostSoundboard wordt automatisch gedownload en geïnstalleerd.\nJe bestaande bibliotheek, favorieten en instellingen blijven bewaard.";

        pack.SetBounds(24, 139, 690, 31);
        pack.Text = "Ook het startersoundpack met 141 geluiden toevoegen (download +310 MiB)";
        pack.Checked = false;
        pack.ForeColor = ForeColor;
        pack.BackColor = BackColor;

        uitleg.SetBounds(44, 174, 654, 50);
        uitleg.Text = "Niet verplicht. Zonder vinkje installeer je alleen DrostSoundboard.\nMet vinkje downloaden we het pakket en voegen de geluiden daarna automatisch toe.";
        uitleg.ForeColor = Color.FromArgb(193, 210, 217);

        status.SetBounds(24, 235, 685, 48);
        status.Text = "Klaar om te installeren. Kies hierboven of je startergeluiden wilt.";
        status.ForeColor = Color.FromArgb(241, 248, 249);
        balk.SetBounds(24, 288, 685, 20);
        balk.Style = ProgressBarStyle.Continuous;
        balk.Value = 0;

        start.SetBounds(24, 327, 140, 38);
        start.Text = "Installeren";
        stop.SetBounds(175, 327, 106, 38);
        stop.Text = "Annuleren";
        stop.Enabled = false;
        map.SetBounds(291, 327, 188, 38);
        map.Text = "Geluidsarchief tonen";
        map.Enabled = false;
        openen.SetBounds(490, 327, 219, 38);
        openen.Text = "DrostSoundboard openen";
        openen.Enabled = false;

        onder.SetBounds(24, 377, 685, 34);
        onder.Text = "Soundpack later toevoegen? Open Bibliotheek > Audiopack importeren.";
        onder.ForeColor = Color.FromArgb(193, 210, 217);

        Controls.AddRange(new Control[] { kop, hint, pack, uitleg, status, balk,
                                           start, stop, map, openen, onder });
        foreach (var knop in new Button[] { start, stop, map, openen }) {
            knop.UseVisualStyleBackColor = false;
            knop.FlatStyle = FlatStyle.Flat;
            knop.FlatAppearance.BorderColor = Color.FromArgb(115, 170, 158);
            knop.BackColor = Color.FromArgb(44, 62, 72);
            knop.ForeColor = Color.FromArgb(245, 250, 249);
        }
        start.BackColor = Color.FromArgb(120, 214, 197);
        start.ForeColor = Color.FromArgb(18, 39, 37);
        start.Click += async (s, e) => await Begin();
        stop.Click += (s, e) => { if (annulering != null) annulering.Cancel(); };
        map.Click += (s, e) => {
            if (File.Exists(packPad ?? ""))
                Process.Start("explorer.exe", "/select,\"" + packPad + "\"");
        };
        openen.Click += (s, e) => {
            try {
                var app = GeinstalleerdeApp();
                if (app == null) throw new FileNotFoundException("DrostSoundboard staat niet op de gebruikelijke locatie.");
                Process.Start(new ProcessStartInfo(app) { UseShellExecute = true });
            } catch (Exception fout) {
                MessageBox.Show(this, "Open DrostSoundboard via het Startmenu.\n\n" + fout.Message,
                                "App starten", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
        };
        FormClosing += (s, e) => {
            if (annulering != null || setupBezig) {
                e.Cancel = true;
                status.Text = setupBezig ? "De installatie is bezig. Sluit dit venster nadat de installatie klaar is."
                                         : "Annuleer eerst de download.";
            }
        };
        http.DefaultRequestHeaders.UserAgent.ParseAdd("DrostSoundboard-Installeren/2.0");
        http.Timeout = TimeSpan.FromMinutes(40);
    }

    void Meld(string tekst, int pct = -1) {
        status.Text = tekst;
        if (pct < 0) {
            balk.Style = ProgressBarStyle.Marquee;
            balk.MarqueeAnimationSpeed = 24;
        } else {
            balk.Style = ProgressBarStyle.Continuous;
            balk.Value = Math.Min(100, Math.Max(0, pct));
        }
    }

    static string Get(Dictionary<string, object> d, string key) {
        object v;
        return d != null && d.TryGetValue(key, out v) && v != null ? Convert.ToString(v) : "";
    }

    static string Hash(string path) {
        using (var sha = SHA256.Create())
        using (var f = File.OpenRead(path))
            return BitConverter.ToString(sha.ComputeHash(f)).Replace("-", "").ToLowerInvariant();
    }

    static string GeinstalleerdeApp() {
        var lokaal = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        foreach (var kandidaat in new[] {
            Path.Combine(lokaal, "DrostSoundboard.Desktop", "current", "DrostSoundboard.exe"),
            Path.Combine(lokaal, "DrostSoundboard.Desktop", "DrostSoundboard.exe")
        }) if (File.Exists(kandidaat)) return kandidaat;
        return null;
    }

    async Task<List<Bestand>> Assets(CancellationToken token) {
        using (var response = await http.GetAsync(Api, token)) {
            response.EnsureSuccessStatusCode();
            var parsed = new JavaScriptSerializer { MaxJsonLength = 10 * 1024 * 1024 }
                .DeserializeObject(await response.Content.ReadAsStringAsync()) as object[];
            if (parsed == null) throw new InvalidDataException("GitHub stuurde geen geldige releasegegevens.");
            var gevonden = new List<Bestand>();
            foreach (var item in parsed) {
                var release = item as Dictionary<string, object>;
                if (release == null || Get(release, "draft") == "True") continue;
                object assets;
                if (!release.TryGetValue("assets", out assets) || !(assets is object[])) continue;
                foreach (var a in (object[])assets) {
                    var d = a as Dictionary<string, object>;
                    string naam = Get(d, "name");
                    if (naam != Setup && naam != Pack) continue;
                    string url = Get(d, "browser_download_url");
                    string digest = Get(d, "digest");
                    Uri uri; long bytes;
                    if (!Uri.TryCreate(url, UriKind.Absolute, out uri) || uri.Scheme != "https" ||
                        uri.Host != "github.com" ||
                        !uri.AbsolutePath.StartsWith("/MisterMol/DROST_Sounboard/releases/download/", StringComparison.Ordinal) ||
                        !digest.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase) ||
                        digest.Length != 71 || !Int64.TryParse(Get(d, "size"), out bytes) || bytes < 1024) continue;
                    gevonden.Add(new Bestand {
                        naam = naam, url = url, hash = digest.Substring(7).ToLowerInvariant(),
                        lengte = bytes, tag = Get(release, "tag_name")
                    });
                }
            }
            return gevonden;
        }
    }

    async Task<string> Download(Bestand b, string folder, CancellationToken token) {
        Directory.CreateDirectory(folder);
        string target = Path.Combine(folder, b.naam);
        string temporary = target + "." + Guid.NewGuid().ToString("N") + ".download";
        if (File.Exists(target)) {
            Meld("Bestaand pakket controleren...");
            if (Hash(target) == b.hash) return target;
        }
        try {
            using (var response = await http.GetAsync(b.url, HttpCompletionOption.ResponseHeadersRead, token)) {
                response.EnsureSuccessStatusCode();
                using (var source = await response.Content.ReadAsStreamAsync())
                using (var dest = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write,
                                                FileShare.None, 1024 * 1024, true))
                using (var sha = SHA256.Create()) {
                    long total = 0;
                    byte[] buffer = new byte[1024 * 1024];
                    int n;
                    while ((n = await source.ReadAsync(buffer, 0, buffer.Length, token)) > 0) {
                        await dest.WriteAsync(buffer, 0, n, token);
                        sha.TransformBlock(buffer, 0, n, buffer, 0);
                        total += n;
                        int pct = (int)Math.Min(100, total * 100 / b.lengte);
                        Meld(String.Format("{0}: {1:0.0} / {2:0.0} MiB ({3}%)",
                             b.naam == Setup ? "DrostSoundboard downloaden" : "Startergeluiden downloaden",
                             total / 1048576.0, b.lengte / 1048576.0, pct), pct);
                    }
                    sha.TransformFinalBlock(new byte[0], 0, 0);
                    var check = BitConverter.ToString(sha.Hash).Replace("-", "").ToLowerInvariant();
                    if (total != b.lengte || check != b.hash)
                        throw new InvalidDataException("Download beschadigd of onvolledig (SHA256-controle).");
                }
            }
            if (File.Exists(target)) File.Delete(target);
            File.Move(temporary, target);
            return target;
        } finally {
            if (File.Exists(temporary)) File.Delete(temporary);
        }
    }

    async Task Begin() {
        start.Enabled = false;
        pack.Enabled = false;
        stop.Enabled = true;
        map.Enabled = false;
        openen.Enabled = false;
        packPad = null;
        basisGeinstalleerd = false;
        bool geluiden = pack.Checked;
        annulering = new CancellationTokenSource();
        try {
            if (!Environment.Is64BitOperatingSystem)
                throw new InvalidOperationException("Deze DrostSoundboard-versie vereist 64-bits Windows.");
            Bestand setup;
            string exe;
            if (ingesloten != null) {
                setup = ingesloten.Beschrijf();
                string folder = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "DrostSoundboard", "Installers", setup.tag);
                Meld("Stap 1 van 3: de inbegrepen RC6 Setup controleren...", -1);
                exe = await ingesloten.PakUit(folder, new Progress<int>(
                    p => Meld("Stap 1 van 3: RC6 voorbereiden (" + p + "%)", p)), annulering.Token);
            } else {
                Meld("Stap 1 van 3: officiële GitHub-release controleren...");
                var gevonden = await Assets(annulering.Token);
                setup = gevonden.Find(b => b.naam == Setup);
                if (setup == null)
                    throw new InvalidDataException("Er is nog geen officiële Windows Setup gepubliceerd.");
                string folder = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "DrostSoundboard", "Installers", setup.tag);
                exe = await Download(setup, folder, annulering.Token);
            }

            annulering.Dispose(); annulering = null;
            stop.Enabled = false;
            setupBezig = true;
            Meld("Stap 2 van 3: DrostSoundboard installeren...", -1);
            hint.Text = "Windows installeert DrostSoundboard nu op je pc.\nDit venster laat zien wanneer dat klaar is. Je hoeft niets anders te doen.";

            using (var proces = Process.Start(new ProcessStartInfo(exe) { UseShellExecute = true })) {
                if (proces == null)
                    throw new InvalidOperationException("Windows kon de Setup niet starten.");
                await Task.Run(() => proces.WaitForExit());
                if (proces.ExitCode != 0)
                    throw new InvalidOperationException("De Setup is geëindigd met foutcode " + proces.ExitCode + ".");
            }
            if (GeinstalleerdeApp() == null)
                throw new InvalidOperationException(
                    "De Setup is afgesloten, maar DrostSoundboard staat niet op de verwachte installatielocatie.");
            setupBezig = false;
            basisGeinstalleerd = true;
            openen.Enabled = true;

            if (geluiden) {
                hint.Text = "DrostSoundboard is geïnstalleerd. Nu worden de extra geluiden toegevoegd.\nHet pakket is ongeveer 310 MiB en blijft in Downloads staan.";
                try {
                    annulering = new CancellationTokenSource();
                    stop.Enabled = true;
                    Meld("Stap 3 van 3: startersoundpack zoeken en downloaden...");
                    var releases = await Assets(annulering.Token);
                    var sounds = releases.Find(b => b.naam == Pack);
                    if (sounds == null)
                        throw new InvalidDataException("Het startersoundpack is niet beschikbaar op GitHub.");
                    var downloads = Path.Combine(
                        Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads");
                    packPad = await Download(sounds, downloads, annulering.Token);
                    hint.Text = "Soundpack opgeslagen in Downloads: " + Path.GetFileName(packPad) +
                                "\nDe geluiden worden nu in de bibliotheek geplaatst.";
                    map.Enabled = true;
                    annulering.Dispose(); annulering = null;
                    stop.Enabled = false;
                    setupBezig = true;
                    Meld("Stap 3 van 3: geluiden automatisch importeren...", -1);
                    string melding = await StartersoundpackAutomatisch.VoegToe(
                        http, packPad, setup.tag, (tekst, pct) => Meld(tekst, pct));
                    Meld("DrostSoundboard en de startergeluiden zijn klaar. " + melding, 100);
                    hint.Text = "Installatie geslaagd. Je vindt de geluiden in de Bibliotheek.\nKlik op 'DrostSoundboard openen' om de app te gebruiken.";
                } catch (Exception fout) {
                    bool zipBeschikbaar = File.Exists(packPad ?? "");
                    Meld("DrostSoundboard is geïnstalleerd. Geluiden nog niet toegevoegd.", 0);
                    hint.Text = zipBeschikbaar
                        ? "De app werkt. Het ZIP-bestand staat in Downloads.\n" +
                          "Ga naar Bibliotheek > Audiopack importeren om het zelf toe te voegen."
                        : "De app werkt. Het geluidenpakket is nog niet gedownload.\n" +
                          "Je kunt het later via de officiële GitHub Releases ophalen.";
                    string stappen = zipBeschikbaar
                        ? "1. Open DrostSoundboard en ga naar Bibliotheek > Audiopack importeren.\n" +
                          "2. Selecteer het ZIP-bestand in Downloads, kies Alle nieuwe en klik " +
                          "Geselecteerde geluiden importeren."
                        : "1. Download DrostSoundboard_startersoundpack.zip via " +
                          "https://github.com/MisterMol/DROST_Sounboard/releases\n" +
                          "2. Open DrostSoundboard en ga naar Bibliotheek > Audiopack importeren.\n" +
                          "3. Selecteer het ZIP-bestand in Downloads, kies Alle nieuwe en klik " +
                          "Geselecteerde geluiden importeren.";
                    MessageBox.Show(this, "DrostSoundboard is geïnstalleerd, maar de startergeluiden zijn nog niet toegevoegd.\n\n" +
                        fout.Message + "\n\nHandmatig toevoegen:\n" + stappen +
                        "\nDe ZIP hoef je niet uit te pakken.",
                        "Soundpack nog niet toegevoegd", MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
            } else {
                Meld("DrostSoundboard is geïnstalleerd en klaar voor gebruik.", 100);
                hint.Text = "Installatie voltooid. Klik op 'DrostSoundboard openen'.\n" +
                            "Je kunt later geluiden toevoegen via Bibliotheek > Audiopack importeren.";
            }
            start.Text = "Opnieuw installeren";
        } catch (OperationCanceledException) {
            Meld(basisGeinstalleerd ? "DrostSoundboard is klaar. Het geluidenpakket is geannuleerd."
                                   : "Download is geannuleerd; de installatie is niet voltooid.", 0);
        } catch (Exception fout) {
            Meld(basisGeinstalleerd ? "App geïnstalleerd; extra geluiden niet voltooid."
                                   : "Installatie niet voltooid: " + fout.Message, 0);
            MessageBox.Show(this, fout.Message + "\n\nDe bestanden zijn afkomstig van de officiële DrostSoundboard-release.",
                            "Installatiecontrole", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        } finally {
            setupBezig = false;
            if (annulering != null) { annulering.Dispose(); annulering = null; }
            start.Enabled = true;
            pack.Enabled = true;
            stop.Enabled = false;
            openen.Enabled = basisGeinstalleerd && GeinstalleerdeApp() != null;
        }
    }

    [STAThread]
    static void Main() {
        ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        try {
            Application.Run(new Installer());
        } catch (Exception fout) {
            MessageBox.Show("De installerstarter kon niet openen:\n\n" + fout.Message,
                "DrostSoundboard installeren", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
