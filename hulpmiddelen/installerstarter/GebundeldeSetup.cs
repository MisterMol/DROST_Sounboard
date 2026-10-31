using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

internal static class InstallerUitvoering {
#if RC6_BUNDEL
    public const bool VereistGebundeldeRc6 = true;
#else
    public const bool VereistGebundeldeRc6 = false;
#endif
}

// Het Windows-testinstallatiebestand bevat de officiële RC6 Velopack Setup
// direct achter de PE-uitvoer, gevolgd door een klein, gecontroleerd manifest.
// De Setup wordt nooit zonder SHA256-controle uitgevoerd.
internal sealed class GebundeldeSetup {
    public const string Tag = "v6.1.0-rc.6";
    const string Kenmerk = "DROSTPKGv000001!";
    const int Trailer = 56;  // SHA256 (32) + lengte (8) + kenmerk (16)
    readonly string executable;
    readonly long begin;
    readonly long lengte;
    readonly string hash;

    GebundeldeSetup(string executable, long begin, long lengte, string hash) {
        this.executable = executable;
        this.begin = begin;
        this.lengte = lengte;
        this.hash = hash;
    }

    public static GebundeldeSetup Zoek() {
        string pad = Application.ExecutablePath;
        using (var bron = new FileStream(pad, FileMode.Open, FileAccess.Read,
                                         FileShare.ReadWrite)) {
            if (bron.Length < Trailer + 10 * 1024 * 1024) return null;
            var reader = new BinaryReader(bron, Encoding.ASCII);
            bron.Seek(-Kenmerk.Length, SeekOrigin.End);
            string kenmerk = Encoding.ASCII.GetString(reader.ReadBytes(Kenmerk.Length));
            if (kenmerk != Kenmerk) return null;
            bron.Seek(-Kenmerk.Length - 8, SeekOrigin.End);
            long grootte = reader.ReadInt64();
            if (grootte < 10 * 1024 * 1024 || grootte > 300 * 1024 * 1024)
                throw new InvalidDataException("De inbegrepen Windows Setup heeft een ongeldige grootte.");
            bron.Seek(-Trailer, SeekOrigin.End);
            byte[] sha = reader.ReadBytes(32);
            long offset = bron.Length - Trailer - grootte;
            if (offset < 16384 || sha.Length != 32)
                throw new InvalidDataException("Het inbegrepen RC6-pakket is beschadigd.");
            return new GebundeldeSetup(pad, offset, grootte, BitConverter.ToString(sha)
                                      .Replace("-", "").ToLowerInvariant());
        }
    }

    public Bestand Beschrijf() {
        return new Bestand {
            naam = "DrostSoundboard.Desktop-beta-Setup.exe",
            lengte = lengte,
            hash = hash,
            tag = Tag
        };
    }

    public async Task<string> PakUit(string map, IProgress<int> progress,
                                      CancellationToken token) {
        Directory.CreateDirectory(map);
        string doel = Path.Combine(map, "DrostSoundboard.Desktop-beta-Setup.exe");
        if (File.Exists(doel) && BestandSha(doel) == hash) {
            progress.Report(100);
            return doel;
        }
        string tijdelijk = Path.Combine(map, Guid.NewGuid().ToString("N") + ".download");
        try {
            await Task.Run(() => {
                using (var bron = new FileStream(executable, FileMode.Open, FileAccess.Read,
                                                  FileShare.ReadWrite, 1024 * 1024))
                using (var dest = new FileStream(tijdelijk, FileMode.CreateNew, FileAccess.Write,
                                                 FileShare.None, 1024 * 1024))
                using (var sha = SHA256.Create()) {
                    bron.Seek(begin, SeekOrigin.Begin);
                    long rest = lengte, totaal = 0;
                    byte[] buffer = new byte[1024 * 1024];
                    int laatst = -1;
                    while (rest > 0) {
                        token.ThrowIfCancellationRequested();
                        int aantal = bron.Read(buffer, 0, (int)Math.Min(buffer.Length, rest));
                        if (aantal <= 0)
                            throw new EndOfStreamException("Het ingesloten Setup-bestand is onvolledig.");
                        dest.Write(buffer, 0, aantal);
                        sha.TransformBlock(buffer, 0, aantal, buffer, 0);
                        rest -= aantal;
                        totaal += aantal;
                        int pct = (int)(totaal * 100 / lengte);
                        if (pct != laatst) { progress.Report(pct); laatst = pct; }
                    }
                    sha.TransformFinalBlock(new byte[0], 0, 0);
                    string werkelijk = BitConverter.ToString(sha.Hash).Replace("-", "").ToLowerInvariant();
                    if (werkelijk != hash)
                        throw new InvalidDataException("De SHA256-controle van de inbegrepen RC6 Setup is mislukt.");
                }
                using (var check = File.OpenRead(tijdelijk)) {
                    if (check.ReadByte() != 0x4D || check.ReadByte() != 0x5A)
                        throw new InvalidDataException("Het inbegrepen bestand is geen Windows EXE.");
                }
            }, token);
            if (File.Exists(doel)) File.Delete(doel);
            File.Move(tijdelijk, doel);
            return doel;
        } finally {
            if (File.Exists(tijdelijk)) File.Delete(tijdelijk);
        }
    }

    static string BestandSha(string pad) {
        using (var sha = SHA256.Create())
        using (var bron = File.OpenRead(pad))
            return BitConverter.ToString(sha.ComputeHash(bron))
                .Replace("-", "").ToLowerInvariant();
    }
}
