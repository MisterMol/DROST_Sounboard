using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Web.Script.Serialization;

// Verstuurt een groot ZIP-bestand in kleine blokken. Het gehele pack past nooit in RAM.
internal sealed class AudiopackMetVoortgang : HttpContent {
    readonly string bestand;
    readonly IProgress<int> voortgang;
    readonly long grootte;
    public AudiopackMetVoortgang(string bestand, IProgress<int> voortgang) {
        this.bestand = bestand;
        this.voortgang = voortgang;
        grootte = new FileInfo(bestand).Length;
        Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
    }
    protected override bool TryComputeLength(out long length) {
        length = grootte;
        return true; // De lokale Python-server vereist Content-Length.
    }
    protected override async Task SerializeToStreamAsync(Stream uitvoer, TransportContext context) {
        using (var bron = new FileStream(bestand, FileMode.Open, FileAccess.Read, FileShare.Read,
                                        1024 * 1024, true)) {
            var blok = new byte[256 * 1024];
            long gedaan = 0;
            int aantal, laatst = -1;
            while ((aantal = await bron.ReadAsync(blok, 0, blok.Length)) > 0) {
                await uitvoer.WriteAsync(blok, 0, aantal);
                gedaan += aantal;
                int procent = grootte == 0 ? 100 : (int)(gedaan * 100L / grootte);
                if (procent != laatst) {
                    voortgang.Report(procent);
                    laatst = procent;
                }
            }
        }
    }
}

// Beveiligde lokale import, uitsluitend nadat de juiste geïnstalleerde app antwoordt.
internal static class StartersoundpackAutomatisch {
    const string Bestandsnaam = "actieve_desktopinstantie.json";

    static Dictionary<string, object> Json(string tekst) {
        var data = new JavaScriptSerializer { MaxJsonLength = 1024 * 1024 }
            .DeserializeObject(tekst) as Dictionary<string, object>;
        if (data == null) throw new InvalidDataException("De lokale app gaf ongeldige gegevens terug.");
        return data;
    }
    static string Waarde(Dictionary<string, object> data, string veld) {
        object item;
        return data.TryGetValue(veld, out item) && item != null
            ? Convert.ToString(item) : "";
    }
    static string Gegevensbestand() {
        return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                            "DrostSoundboard", Bestandsnaam);
    }
    static string Launcher() {
        return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                            "DrostSoundboard.Desktop", "DrostSoundboard.exe");
    }
    static string BepaalLokaalAdres(out string procesId) {
        procesId = null;
        try {
            var info = Json(File.ReadAllText(Gegevensbestand()));
            int port, pid;
            if (!Int32.TryParse(Waarde(info, "poort"), out port) || port < 1 || port > 65535
                || !Int32.TryParse(Waarde(info, "proces_id"), out pid) || pid <= 0)
                return null;
            procesId = pid.ToString();
            return "http://127.0.0.1:" + port;
        } catch (IOException) { return null; }
          catch (UnauthorizedAccessException) { return null; }
          catch (InvalidDataException) { return null; }
          catch (ArgumentException) { return null; }
    }
    static async Task<string> WachtOpJuisteApp(HttpClient http, string versie,
                                               Action<string, int> toon) {
        bool geprobeerd = false;
        for (int poging = 0; poging < 120; poging++) {
            string pid;
            string adres = BepaalLokaalAdres(out pid);
            if (adres != null) {
                try {
                    using (var r = await http.GetAsync(adres + "/api/versie")) {
                        if (r.IsSuccessStatusCode) {
                            var gegevens = Json(await r.Content.ReadAsStringAsync());
                            if (Waarde(gegevens, "versie") == versie &&
                                Waarde(gegevens, "proces_id") == pid)
                                return adres;
                        }
                    }
                } catch (HttpRequestException) { /* Wacht op start of herstart. */ }
                  catch (TaskCanceledException) { }
                  catch (InvalidDataException) { }
            }
            // Velopack start na een normale installatie meestal al zelf.
            // Start pas na enkele seconden zelf de permanente launcher, hooguit eenmaal.
            if (poging == 8 && !geprobeerd && File.Exists(Launcher())) {
                geprobeerd = true;
                try {
                    Process.Start(new ProcessStartInfo(Launcher(), "--achtergrond") {
                        UseShellExecute = true
                    });
                } catch (System.ComponentModel.Win32Exception) { }
            }
            if (poging % 10 == 0)
                toon("DrostSoundboard opstarten om geluiden toe te voegen...", -1);
            await Task.Delay(1000);
        }
        throw new IOException("DrostSoundboard startte niet op tijd. Het ZIP-bestand staat nog in Downloads.");
    }
    public static async Task<string> VoegToe(HttpClient http, string zip, string releaseTag,
                                             Action<string, int> toon) {
        if (!File.Exists(zip))
            throw new FileNotFoundException("Het startersoundpack ontbreekt.", zip);
        if (string.IsNullOrEmpty(releaseTag) ||
            !Regex.IsMatch(releaseTag, @"\Av\d+\.\d+\.\d+(?:-(?:beta|rc)\.\d+(?:\.\d+)?)?\z"))
            throw new InvalidDataException("Onbekende versie voor automatische import.");
        string adres = await WachtOpJuisteApp(http, releaseTag.Substring(1), toon);
        // Het schrijftoken staat alleen in de lokale HTML. Geen appgegevens of token naar GitHub.
        string html = await http.GetStringAsync(adres + "/");
        var token = Regex.Match(html, @"<meta\s+name=""drost-token""\s+content=""([A-Za-z0-9_-]{32,128})""",
                                RegexOptions.IgnoreCase);
        if (!token.Success)
            throw new InvalidDataException("De lokale beveiligingscode van DrostSoundboard ontbreekt.");
        int vorige = -1;
        var progress = new Progress<int>(percentage => {
            if (percentage != vorige) {
                vorige = percentage;
                if (percentage == 100) toon("Geluiden importeren en controleren...", -1);
                else toon("Startersoundpack toevoegen: " + percentage + "% verstuurd", percentage);
            }
        });
        using (var body = new AudiopackMetVoortgang(zip, progress))
        using (var request = new HttpRequestMessage(
            HttpMethod.Post, adres + "/api/bibliotheek/importeer?dubbelen=overslaan")) {
            request.Headers.Add("X-Drost-Token", token.Groups[1].Value);
            request.Content = body;
            // Na 100% upload begint de Python-server ZIP-validatie en import.
            // Deze status is bewust onbepaald: geen nepvoortgang melden.
            toon("Startersoundpack naar DrostSoundboard versturen...", 0);
            using (var antwoord = await http.SendAsync(request, HttpCompletionOption.ResponseContentRead)) {
                string tekst = await antwoord.Content.ReadAsStringAsync();
                if (!antwoord.IsSuccessStatusCode)
                    throw new InvalidDataException("De import werd geweigerd: "
                        + tekst.Substring(0, Math.Min(450, tekst.Length)));
                return Waarde(Json(tekst), "melding");
            }
        }
    }
}