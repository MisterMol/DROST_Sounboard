using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Web.Script.Serialization;

// Herstel altijd de bestaande app met de officiële Velopack Setup.
// Gebruikersdata staan bewust buiten de installatiemap en worden niet gewist.
internal static class HerstelVanBestaandeInstallatie {
    static string LokaleMap() {
        return Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
    }

    public static string Installatiemap() {
        return Path.Combine(LokaleMap(), "DrostSoundboard.Desktop");
    }

    public static bool IsGeinstalleerd() {
        string pad = Installatiemap();
        // Ook een onvolledige installatie moet als herstelbaar herkenbaar zijn.
        return File.Exists(Path.Combine(pad, "Update.exe")) ||
               File.Exists(Path.Combine(pad, "current", "DrostSoundboard.exe"));
    }

    static string ActieveInstantieBestand() {
        return Path.Combine(LokaleMap(), "DrostSoundboard", "actieve_desktopinstantie.json");
    }

    static bool IsEigenAppProces(Process proces) {
        try {
            string verwacht = Path.GetFullPath(Path.Combine(
                Installatiemap(), "current", "DrostSoundboard.exe"));
            string werkelijk = Path.GetFullPath(proces.MainModule.FileName);
            return string.Equals(verwacht, werkelijk, StringComparison.OrdinalIgnoreCase);
        } catch (System.ComponentModel.Win32Exception) {
            // Bij ontoegankelijke processen nooit stilzwijgend proces beëindigen.
            return false;
        } catch (InvalidOperationException) {
            return false;
        }
    }

    static Process[] ZoekDraaiendeApp() {
        var gevonden = new List<Process>();
        foreach (var proces in Process.GetProcessesByName("DrostSoundboard")) {
            if (IsEigenAppProces(proces)) gevonden.Add(proces);
            else proces.Dispose();
        }
        return gevonden.ToArray();
    }

    static Dictionary<string, object> LeesJson(string inhoud) {
        return new JavaScriptSerializer { MaxJsonLength = 1024 * 1024 }
            .DeserializeObject(inhoud) as Dictionary<string, object>;
    }

    static int LeesInt(Dictionary<string, object> data, string sleutel) {
        object obj;
        int nummer;
        return data != null && data.TryGetValue(sleutel, out obj)
            && int.TryParse(Convert.ToString(obj), out nummer) ? nummer : -1;
    }

    static async Task VraagAppNetjesAfTeSluiten(Process proces) {
        string staat = ActieveInstantieBestand();
        if (!File.Exists(staat))
            throw new IOException("DrostSoundboard draait nog, maar de lokale verbinding is niet beschikbaar.");
        var instantie = LeesJson(File.ReadAllText(staat));
        int pid = LeesInt(instantie, "proces_id");
        int poort = LeesInt(instantie, "poort");
        if (pid != proces.Id || poort < 1 || poort > 65535)
            throw new IOException("De actieve app kan niet veilig worden herkend.");
        string basis = "http://127.0.0.1:" + poort;
        using (var http = new HttpClient(new HttpClientHandler { UseProxy = false })) {
            http.Timeout = TimeSpan.FromSeconds(6);
            using (var antwoord = await http.GetAsync(basis + "/api/versie")) {
                if (!antwoord.IsSuccessStatusCode ||
                    LeesInt(LeesJson(await antwoord.Content.ReadAsStringAsync()), "proces_id") != pid)
                    throw new IOException("Het lokaal draaiende programma antwoordt niet met het verwachte procesnummer.");
            }
            string html = await http.GetStringAsync(basis + "/");
            var token = Regex.Match(html,
                @"<meta\s+name=""drost-token""\s+content=""([A-Za-z0-9_-]{32,128})""",
                RegexOptions.IgnoreCase);
            if (!token.Success)
                throw new IOException("De beveiligingscode van de draaiende app ontbreekt.");
            using (var request = new HttpRequestMessage(
                HttpMethod.Post, basis + "/api/app/afsluiten")) {
                request.Headers.Add("X-Drost-Token", token.Groups[1].Value);
                request.Content = new StringContent(
                    "{\"bevestiging\":\"AFSLUITEN\"}", Encoding.UTF8, "application/json");
                using (var response = await http.SendAsync(request)) {
                    if ((int)response.StatusCode != 202)
                        throw new IOException("De bestaande app kon niet veilig worden afgesloten.");
                }
            }
        }
        // Geef audio en systeemvak ruimte om hun streams en mutex vrij te geven.
        bool afgesloten = await Task.Run(() => proces.WaitForExit(20000));
        if (!afgesloten)
            throw new IOException("DrostSoundboard heeft de audio nog niet vrijgegeven.");
    }

    public static async Task BereidHerstelVoor(Action<string, int> meld) {
        if (!IsGeinstalleerd()) return;
        var processen = ZoekDraaiendeApp();
        try {
            if (processen.Length == 0) return;
            if (processen.Length != 1)
                throw new IOException("Er zijn meerdere DrostSoundboard-processen gevonden.");
            meld("De bestaande app netjes afsluiten vóór herstel...", -1);
            await VraagAppNetjesAfTeSluiten(processen[0]);
        } catch (Exception fout) {
            throw new IOException(
                "De oude installatie blijft intact. Sluit DrostSoundboard volledig af via het systeemvak " +
                "en klik opnieuw op Herstellen. Oorzaak: " + fout.Message, fout);
        } finally {
            foreach (var proces in processen) proces.Dispose();
        }
    }
}
