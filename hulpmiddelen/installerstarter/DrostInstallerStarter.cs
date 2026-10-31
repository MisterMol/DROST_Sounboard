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

internal class Bestand {
    public string naam, url, hash, tag;
    public long lengte;
}

internal sealed class Installer : Form {
    const string Api="https://api.github.com/repos/MisterMol/DROST_Sounboard/releases?per_page=30";
    const string Setup="DrostSoundboard.Desktop-beta-Setup.exe";
    const string Pack="DrostSoundboard_startersoundpack.zip";
    readonly Label status=new Label(), hint=new Label();
    readonly ProgressBar balk=new ProgressBar();
    readonly CheckBox pack=new CheckBox();
    readonly Button start=new Button(), stop=new Button(), map=new Button();
    readonly HttpClient http=new HttpClient();
    CancellationTokenSource annulering;
    bool setupBezig;
    string packPad;
    public Installer(){
        Text="DrostSoundboard installeren"; ClientSize=new Size(570,290);
        StartPosition=FormStartPosition.CenterScreen; MaximizeBox=false; FormBorderStyle=FormBorderStyle.FixedDialog;
        BackColor=Color.FromArgb(18,24,32); ForeColor=Color.White; Font=new Font("Segoe UI",10);
        var kop=new Label(){Text="DrostSoundboard installeren",Bounds=new Rectangle(20,15,530,36),
            Font=new Font("Segoe UI",17,FontStyle.Bold),ForeColor=Color.FromArgb(120,214,197)};
        hint.SetBounds(20,60,530,40);
        hint.Text="Download de Windows Setup met zichtbare voortgang. Je bestaande bibliotheek blijft bewaard.";
        pack.SetBounds(20,106,530,28); pack.Text="Ook startersoundpack downloaden (ongeveer 310 MiB)";pack.Checked=true;
        status.SetBounds(20,144,530,40);status.Text="Klaar om te beginnen.";
        balk.SetBounds(20,190,530,18);
        start.SetBounds(20,225,145,34);start.Text="Installeren";
        stop.SetBounds(175,225,115,34);stop.Text="Annuleren";stop.Enabled=false;
        map.SetBounds(300,225,250,34);map.Text="Map met soundpack openen";map.Enabled=false;
        Controls.AddRange(new Control[]{kop,hint,pack,status,balk,start,stop,map});
        start.Click+=async (s,e)=>await Begin();
        stop.Click+=(s,e)=>{if(annulering!=null)annulering.Cancel();};
        map.Click+=(s,e)=>{if(File.Exists(packPad??""))Process.Start("explorer.exe","/select,\""+packPad+"\"");};
        FormClosing+=(s,e)=>{if(annulering!=null||setupBezig){e.Cancel=true;status.Text="Annuleer eerst de download of voltooi de installatie."; }};
        http.DefaultRequestHeaders.UserAgent.ParseAdd("DrostSoundboard-Installeren/1.0");
        http.Timeout=TimeSpan.FromMinutes(30);
    }
    void Meld(string tekst,int pct=-1){
        status.Text=tekst;
        if(pct<0){balk.Style=ProgressBarStyle.Marquee;balk.MarqueeAnimationSpeed=25;}
        else {balk.Style=ProgressBarStyle.Continuous;balk.Value=Math.Min(100,Math.Max(0,pct));}
    }
    static string Get(Dictionary<string,object> d,string key){
        object v;return d!=null&&d.TryGetValue(key,out v)&&v!=null?Convert.ToString(v):"";
    }
    static string Hash(string path){
        using(var sha=SHA256.Create())using(var f=File.OpenRead(path))
            return BitConverter.ToString(sha.ComputeHash(f)).Replace("-","").ToLowerInvariant();
    }
    async Task<List<Bestand>> Assets(CancellationToken token){
        using(var response=await http.GetAsync(Api,token)){
            response.EnsureSuccessStatusCode();
            var parsed=new JavaScriptSerializer{MaxJsonLength=10*1024*1024}.DeserializeObject(
                await response.Content.ReadAsStringAsync()) as object[];
            if(parsed==null)throw new InvalidDataException("Ongeldige GitHub-releasegegevens.");
            var gevonden=new List<Bestand>();
            foreach(var item in parsed){
                var release=item as Dictionary<string,object>;
                if(release==null||Get(release,"draft")=="True")continue;
                object assets;
                if(!release.TryGetValue("assets",out assets)||!(assets is object[]))continue;
                foreach(var a in (object[])assets){
                    var d=a as Dictionary<string,object>;string naam=Get(d,"name");
                    if(naam!=Setup&&naam!=Pack)continue;
                    string url=Get(d,"browser_download_url"),digest=Get(d,"digest");
                    Uri uri;long bytes;
                    if(!Uri.TryCreate(url,UriKind.Absolute,out uri)||uri.Scheme!="https"||
                        uri.Host!="github.com"||
                        !uri.AbsolutePath.StartsWith("/MisterMol/DROST_Sounboard/releases/download/",StringComparison.Ordinal)||
                        !digest.StartsWith("sha256:",StringComparison.OrdinalIgnoreCase)||
                        digest.Length!=71||!Int64.TryParse(Get(d,"size"),out bytes)||bytes<1024)continue;
                    gevonden.Add(new Bestand{naam=naam,url=url,hash=digest.Substring(7).ToLowerInvariant(),
                        lengte=bytes,tag=Get(release,"tag_name")});
                }
            }
            return gevonden;
        }
    }
    async Task<string> Download(Bestand b,string folder,CancellationToken token){
        Directory.CreateDirectory(folder);
        string target=Path.Combine(folder,b.naam),temporary=target+".download";
        if(File.Exists(target)){
            Meld("Bestaande download controleren...");
            if(Hash(target)==b.hash)return target;
            File.Delete(target);
        }
        try{
            if(File.Exists(temporary))File.Delete(temporary);
            using(var response=await http.GetAsync(b.url,HttpCompletionOption.ResponseHeadersRead,token)){
                response.EnsureSuccessStatusCode();
                using(var source=await response.Content.ReadAsStreamAsync())
                using(var dest=new FileStream(temporary,FileMode.CreateNew,FileAccess.Write,FileShare.None,1048576,true))
                using(var sha=SHA256.Create()){
                    long total=0;byte[] buffer=new byte[1048576];int n;
                    while((n=await source.ReadAsync(buffer,0,buffer.Length,token))>0){
                        await dest.WriteAsync(buffer,0,n,token);
                        sha.TransformBlock(buffer,0,n,buffer,0);total+=n;
                        int pct=(int)Math.Min(100,total*100/b.lengte);
                        Meld(String.Format("{0}: {1:0.0} / {2:0.0} MiB ({3}%)",
                            b.naam==Setup?"Setup downloaden":"Soundpack downloaden",
                            total/1048576.0,b.lengte/1048576.0,pct),pct);
                    }
                    sha.TransformFinalBlock(new byte[0],0,0);
                    var check=BitConverter.ToString(sha.Hash).Replace("-","").ToLowerInvariant();
                    if(total!=b.lengte||check!=b.hash)throw new InvalidDataException("SHA256 of bestandsgrootte klopt niet.");
                }
            }
            File.Move(temporary,target);return target;
        }finally{if(File.Exists(temporary))File.Delete(temporary);}
    }
    async Task Begin(){
        start.Enabled=false;pack.Enabled=false;stop.Enabled=true;map.Enabled=false;packPad=null;
        annulering=new CancellationTokenSource();
        try{
            Meld("GitHub-release controleren...");
            var list=await Assets(annulering.Token);Bestand setup=null,sounds=null;
            foreach(var b in list){if(setup==null&&b.naam==Setup)setup=b;if(sounds==null&&b.naam==Pack)sounds=b;}
            if(setup==null)throw new InvalidDataException("Geen Windows Setup in de recente GitHub-releases.");
            if(pack.Checked&&sounds==null)throw new InvalidDataException("Geen startersoundpack beschikbaar.");
            string baseDir=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "DrostSoundboard","Installers",setup.tag);
            string exe=await Download(setup,baseDir,annulering.Token);
            if(pack.Checked)packPad=await Download(sounds,
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),"Downloads"),annulering.Token);
            annulering.Dispose();annulering=null;stop.Enabled=false;setupBezig=true;
            Meld("Windows Setup wordt gestart. Dit kan even duren...");
            hint.Text="Wacht tot Windows Setup klaar is. Dit venster blijft open.";
            using(var p=Process.Start(new ProcessStartInfo(exe){UseShellExecute=true})){
                if(p==null)throw new InvalidOperationException("Setup kon niet worden gestart.");
                await Task.Run(()=>p.WaitForExit());
                if(p.ExitCode!=0)throw new InvalidOperationException("Setup heeft foutcode "+p.ExitCode+" teruggegeven.");
            }
            setupBezig=false;Meld("Installatie afgerond.",100);
            hint.Text=packPad==null?"Open DrostSoundboard via het Startmenu.":
                "Open DrostSoundboard en kies Bibliotheek > Audiopack importeren. Selecteer de ZIP in Downloads.";
            map.Enabled=packPad!=null&&File.Exists(packPad);
            start.Text="Opnieuw installeren";
        }catch(OperationCanceledException){Meld("Download geannuleerd.",0);}
        catch(Exception ex){
            Meld("Niet voltooid: "+ex.Message,0);
            MessageBox.Show(this,ex.Message+"\n\nGebruik eventueel de Setup op github.com/MisterMol/DROST_Sounboard/releases",
                "Installatie niet voltooid",MessageBoxButtons.OK,MessageBoxIcon.Warning);
        }finally{
            setupBezig=false;
            if(annulering!=null){annulering.Dispose();annulering=null;}
            start.Enabled=true;pack.Enabled=true;stop.Enabled=false;
        }
    }
    [STAThread]static void Main(){
        ServicePointManager.SecurityProtocol=SecurityProtocolType.Tls12;
        Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new Installer());
    }
}