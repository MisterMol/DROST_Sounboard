using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

// Dit programma draait uitsluitend vanaf de complete offline Setup.
// Het downloadt geen bestanden en verwijdert nooit een bestaande bibliotheek.
internal sealed class CompleteInstallatie : Form
{
    const string SetupNaam = "DrostSoundboard.Desktop-beta-Setup.exe";
    const string PackNaam = "DrostSoundboard_startersoundpack.zip";
    const string AppNaam = "DrostSoundboard.exe";
    readonly Label titel = new Label();
    readonly Label melding = new Label();
    readonly Label toelichting = new Label();
    readonly ProgressBar voortgang = new ProgressBar();
    readonly Button openDownloads = new Button();
    readonly Button sluiten = new Button();
    readonly HttpClient client = new HttpClient();
    bool bezig;
    string soundpackInDownloads;

    public CompleteInstallatie()
    {
        Text = "DrostSoundboard compleet installeren";
        ClientSize = new Size(610, 304);
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        BackColor = Color.FromArgb(30, 40, 49);
        ForeColor = Color.FromArgb(241, 248, 249);
        Font = new Font("Segoe UI", 10);
        titel.Bounds = new Rectangle(22, 17, 566, 38);
        titel.Text = "DrostSoundboard compleet installeren";
        titel.Font = new Font("Segoe UI", 17, FontStyle.Bold);
        titel.ForeColor = Color.FromArgb(120, 214, 197);
        toelichting.Bounds = new Rectangle(22, 64, 566, 52);
        toelichting.Text = "De app en het startersoundpack zitten al in dit bestand. Er is geen internet nodig. Bestaande geluiden en instellingen blijven bewaard.";
        melding.Bounds = new Rectangle(22, 133, 565, 54);
        melding.Text = "Installatie voorbereiden...";
        voortgang.Bounds = new Rectangle(22, 197, 564, 19);
        openDownloads.Bounds = new Rectangle(22, 238, 315, 40);
        openDownloads.Text = "Soundpack in Downloads bekijken";
        openDownloads.Enabled = false;
        sluiten.Bounds = new Rectangle(350, 238, 236, 40);
        sluiten.Text = "Sluiten";
        sluiten.Enabled = false;
        foreach (var knop in new Button[] { openDownloads, sluiten })
        {
            knop.FlatStyle = FlatStyle.Flat;
            knop.FlatAppearance.BorderColor = Color.FromArgb(115, 170, 158);
            knop.UseVisualStyleBackColor = false;
            knop.BackColor = Color.FromArgb(44, 62, 72);
            knop.ForeColor = Color.FromArgb(245, 250, 249);
        }
        openDownloads.Click += (s, e) =>
        {
            if (!string.IsNullOrEmpty(soundpackInDownloads) && File.Exists(soundpackInDownloads))
                Process.Start("explorer.exe", "/select,\"" + soundpackInDownloads + "\"");
        };
        sluiten.Click += (s, e) => Close();
        FormClosing += (s, e) =>
        {
            if (bezig)
            {
                e.Cancel = true;
                melding.Text = "De installatie wordt afgerond. Sluit dit venster daarna.";
            }
        };
        Controls.AddRange(new Control[] { titel, toelichting, melding, voortgang, openDownloads, sluiten });
        client.Timeout = TimeSpan.FromMinutes(30);
        Shown += async (s, e) => await Begin();
    }

    void Status(string fase, int procent = -1)
    {
        melding.Text = fase;
        if (procent < 0)
        {
            voortgang.Style = ProgressBarStyle.Marquee;
            voortgang.MarqueeAnimationSpeed = 20;
        }
        else
        {
            voortgang.Style = ProgressBarStyle.Continuous;
            voortgang.Value = Math.Max(0, Math.Min(100, procent));
        }
    }

    static string Sha256(string pad)
    {
        using (var stroom = File.OpenRead(pad))
        using (var algoritme = SHA256.Create())
            return BitConverter.ToString(algoritme.ComputeHash(stroom)).Replace("-", "").ToLowerInvariant();
    }

    static Dictionary<string, object> Json(string tekst)
    {
        var data = new JavaScriptSerializer { MaxJsonLength = 10 * 1024 * 1024 }
            .DeserializeObject(tekst) as Dictionary<string, object>;
        if (data == null) throw new InvalidDataException("Ongeldige installatiegegevens.");
        return data;
    }

    static string Waarde(Dictionary<string, object> data, string sleutel)
    {
        object waarde;
        return data.TryGetValue(sleutel, out waarde) && waarde != null
            ? Convert.ToString(waarde) : "";
    }

    static void ControleerHash(string bestand, string verwacht)
    {
        if (!File.Exists(bestand)) throw new FileNotFoundException("Installatieonderdeel ontbreekt.", bestand);
        if (!Regex.IsMatch(verwacht ?? "", @"\A[a-fA-F0-9]{64}\z") ||
            !string.Equals(Sha256(bestand), verwacht, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Een installatieonderdeel is beschadigd (SHA256). Installeer niet verder.");
    }

    static string DownloadsMap()
    {
        const string downloadsId = "{374DE290-123F-4565-9164-39C4925E467B}";
        try
        {
            using (var sleutel = Registry.CurrentUser.OpenSubKey(
                @"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"))
            {
                var waarde = sleutel == null ? null : sleutel.GetValue(downloadsId) as string;
                if (!string.IsNullOrEmpty(waarde))
                    return Path.GetFullPath(Environment.ExpandEnvironmentVariables(waarde));
            }
        }
        catch (Exception) { /* Windows gebruikt dan de standaardlocatie. */ }
        return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads");
    }

    async Task<string> BewaarSoundpack(string bron, string verwachteHash)
    {
        string downloads = DownloadsMap();
        Directory.CreateDirectory(downloads);
        string doel = Path.Combine(downloads, PackNaam);
        if (File.Exists(doel))
        {
            if (string.Equals(Sha256(doel), verwachteHash, StringComparison.OrdinalIgnoreCase))
                return doel;
            doel = Path.Combine(downloads, "DrostSoundboard_startersoundpack_RC5.zip");
            if (File.Exists(doel))
            {
                if (string.Equals(Sha256(doel), verwachteHash, StringComparison.OrdinalIgnoreCase))
                    return doel;
                // Overschrijf geen anders bestaand geluidspakket.
                doel = Path.Combine(downloads, "DrostSoundboard_startersoundpack_RC5_" +
                    DateTime.UtcNow.ToString("yyyyMMddHHmmss") + ".zip");
            }
        }
        string tijdelijk = doel + ".deel";
        if (File.Exists(tijdelijk)) throw new IOException("Een eerdere tijdelijke kopie bestaat nog in Downloads.");
        try
        {
            using (var invoer = File.OpenRead(bron))
            using (var uitvoer = new FileStream(tijdelijk, FileMode.CreateNew, FileAccess.Write,
                       FileShare.None, 1024 * 1024, true))
            {
                byte[] buffer = new byte[1024 * 1024];
                long totaal = invoer.Length, gedaan = 0;
                int aantal;
                while ((aantal = await invoer.ReadAsync(buffer, 0, buffer.Length)) > 0)
                {
                    await uitvoer.WriteAsync(buffer, 0, aantal);
                    gedaan += aantal;
                    int percentage = (int)(gedaan * 100 / totaal);
                    Status("Soundpack bewaren in Downloads: " + percentage + "%", percentage);
                }
            }
            ControleerHash(tijdelijk, verwachteHash);
            File.Move(tijdelijk, doel);
            return doel;
        }
        finally { if (File.Exists(tijdelijk)) File.Delete(tijdelijk); }
    }

    static string GegevensMap()
    {
        return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "DrostSoundboard");
    }

    static string LeesDashboardAdres()
    {
        string bestand = Path.Combine(GegevensMap(), "actieve_desktopinstantie.json");
        if (!File.Exists(bestand)) return null;
        try
        {
            var gegevens = Json(File.ReadAllText(bestand));
            int poort;
            if (!int.TryParse(Waarde(gegevens, "poort"), out poort) || poort < 1 || poort > 65535)
                return null;
            return "http://127.0.0.1:" + poort;
        }
        catch (Exception) { return null; }
    }

    async Task<string> VindWerkendDashboard()
    {
        for (int poging = 0; poging < 90; poging++)
        {
            string adres = LeesDashboardAdres();
            if (adres != null)
            {
                try
                {
                    using (var antwoord = await client.GetAsync(adres + "/api/app"))
                    {
                        if (antwoord.IsSuccessStatusCode)
                        {
                            var gegevens = Json(await antwoord.Content.ReadAsStringAsync());
                            if (Waarde(gegevens, "versie") == "6.1.0-rc.5")
                                return adres;
                        }
                    }
                }
                catch (HttpRequestException) { }
                catch (TaskCanceledException) { }
                catch (InvalidDataException) { }
            }
            await Task.Delay(1000);
        }
        return null;
    }

    async Task<string> ImporteerPack(string adres, string pack)
    {
        string html = await client.GetStringAsync(adres + "/");
        var tokenMatch = Regex.Match(html, "<meta\\s+name=\"drost-token\"\\s+content=\"([^\"]+)\"",
                                     RegexOptions.IgnoreCase);
        if (!tokenMatch.Success) throw new InvalidDataException("De lokale beveiligingscode ontbreekt.");
        string token = WebUtility.HtmlDecode(tokenMatch.Groups[1].Value);
        using (var stroom = new FileStream(pack, FileMode.Open, FileAccess.Read, FileShare.Read))
        using (var inhoud = new StreamContent(stroom, 1024 * 1024))
        using (var request = new HttpRequestMessage(HttpMethod.Post,
                                adres + "/api/bibliotheek/importeer?dubbelen=overslaan"))
        {
            inhoud.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue("application/octet-stream");
            inhoud.Headers.ContentLength = stroom.Length;
            request.Headers.Add("X-Drost-Token", token);
            request.Headers.Add("X-Bestandsnaam", Uri.EscapeDataString(Path.GetFileName(pack)));
            request.Content = inhoud;
            using (var resultaat = await client.SendAsync(request))
            {
                string tekst = await resultaat.Content.ReadAsStringAsync();
                if (!resultaat.IsSuccessStatusCode)
                    throw new InvalidDataException("Import mislukt. Servermelding: " + tekst.Substring(0, Math.Min(400, tekst.Length)));
                return Waarde(Json(tekst), "melding");
            }
        }
    }

    async Task Begin()
    {
        bezig = true;
        Environment.ExitCode = 1;
        string map = AppDomain.CurrentDomain.BaseDirectory;
        string setup = Path.Combine(map, SetupNaam);
        string soundpack = Path.Combine(map, PackNaam);
        try
        {
            Status("Beide onderdelen controleren...");
            var manifest = Json(File.ReadAllText(Path.Combine(map, "pakket.json")));
            if (Waarde(manifest, "release_tag") != "v6.1.0-rc.5")
                throw new InvalidDataException("Ongeldige releaseversie in pakket.");
            await Task.Run(() =>
            {
                ControleerHash(setup, Waarde(manifest, "setup_sha256"));
                ControleerHash(soundpack, Waarde(manifest, "soundpack_sha256"));
            });

            Status("DrostSoundboard installeren. Windows verwerkt de Setup...");
            using (var proces = Process.Start(new ProcessStartInfo(setup, "--silent")
            {
                UseShellExecute = true,
                WorkingDirectory = map
            }))
            {
                if (proces == null) throw new IOException("Windows Setup kon niet starten.");
                await Task.Run(() => proces.WaitForExit());
                if (proces.ExitCode != 0)
                    throw new IOException("Windows Setup stopte met foutcode " + proces.ExitCode + ".");
            }

            soundpackInDownloads = await BewaarSoundpack(soundpack, Waarde(manifest, "soundpack_sha256"));
            openDownloads.Enabled = true;
            Status("App starten en bibliotheekimport voorbereiden...");
            string launcher = Path.Combine(Environment.GetFolderPath(
                Environment.SpecialFolder.LocalApplicationData), "DrostSoundboard.Desktop", AppNaam);
            if (!File.Exists(launcher))
                throw new FileNotFoundException("DrostSoundboard is geïnstalleerd, maar de launcher ontbreekt.", launcher);

            Process.Start(new ProcessStartInfo(launcher, "--achtergrond") { UseShellExecute = true });
            string adres = await VindWerkendDashboard();
            if (adres == null)
                throw new IOException("DrostSoundboard startte niet op tijd. Importeer het ZIP-bestand zelf via Bibliotheek.");

            Status("Startersoundpack importeren. Dit kan enkele minuten duren...");
            string boodschap = await ImporteerPack(adres, soundpackInDownloads);
            Status("Installatie afgerond. " + boodschap, 100);
            toelichting.Text = "De app en het soundpack zijn klaar. Een kopie van het soundpack staat in Downloads.";
            Environment.ExitCode = 0;
            try { Process.Start(new ProcessStartInfo(adres + "/") { UseShellExecute = true }); }
            catch (Exception) { /* De app is geïnstalleerd; browser openen is optioneel. */ }
        }
        catch (Exception fout)
        {
            Status("Installatie of import niet volledig afgerond.", 0);
            toelichting.Text = File.Exists(soundpackInDownloads ?? "")
                ? "Het soundpack staat veilig in Downloads. Je kunt het handmatig importeren via Bibliotheek > Audiopack importeren."
                : "Controleer het installatiebestand en probeer het opnieuw.";
            MessageBox.Show(this, fout.Message, "Installatiecontrole", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
        finally
        {
            bezig = false;
            sluiten.Enabled = true;
        }
    }

    [STAThread]
    static void Main()
    {
        ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new CompleteInstallatie());
    }
}