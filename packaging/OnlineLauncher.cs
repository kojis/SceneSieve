using System;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Collections.Generic;
using System.Windows.Forms;
class OnlineLauncher:Form {
 Label label=new Label();ProgressBar bar=new ProgressBar();string root;int code=1;string[] args;
 OnlineLauncher(string[] a){args=a;Icon=System.Drawing.Icon.ExtractAssociatedIcon(Application.ExecutablePath);Text="SceneSieve setup";Width=610;Height=170;StartPosition=FormStartPosition.CenterScreen;FormBorderStyle=FormBorderStyle.FixedDialog;MaximizeBox=false;ControlBox=false;label.SetBounds(20,18,555,65);label.Text="Verifying SceneSieve...";bar.SetBounds(20,88,555,18);bar.Style=ProgressBarStyle.Marquee;Controls.Add(label);Controls.Add(bar);Shown+=(s,e)=>Task.Run((Action)Run);}
 void Status(string s){BeginInvoke((Action)(()=>label.Text=s));}
 string Hash(string p){using(var sha=SHA256.Create())using(var f=File.OpenRead(p))return BitConverter.ToString(sha.ComputeHash(f)).Replace("-","").ToLowerInvariant();}
 string Quote(string s){return "\""+s.Replace("\"","")+"\"";}
 void Run(){try {
  ServicePointManager.SecurityProtocol=SecurityProtocolType.Tls12;
  root=Environment.GetEnvironmentVariable("SCENESIEVE_HOME")??Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"SceneSieve");Directory.CreateDirectory(root);
  bool created;using(var mutex=new Mutex(true,"Local\\SceneSieveOnlineSetup",out created)){
   if(!created)throw new Exception("SceneSieve is already starting or running.");
   string app=Path.Combine(root,"app-"+Hash(Application.ExecutablePath).Substring(0,12));Directory.CreateDirectory(app);
   using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("app.zip"))using(var zip=new ZipArchive(stream)){
    foreach(var e in zip.Entries){string path=Path.GetFullPath(Path.Combine(app,e.FullName));if(!path.StartsWith(app+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new Exception("Invalid app entry");Directory.CreateDirectory(Path.GetDirectoryName(path));using(var input=e.Open())using(var output=File.Create(path))input.CopyTo(output);}
   }
   var manifest=new JavaScriptSerializer().Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(app,"runtime-manifest.json")));
   var py=(Dictionary<string,object>)manifest["python"];string pydir=Path.Combine(root,"python-3.12.10"),python=Path.Combine(pydir,"python.exe");string cache=Path.Combine(root,"downloads");Directory.CreateDirectory(cache);string archive=Path.Combine(cache,"python.zip");
   Status("Verifying Python runtime...");
   if(!File.Exists(archive)||Hash(archive)!=(string)py["sha256"]){
    Status("Downloading Python runtime...");string partial=archive+".partial";
    using(var client=new WebClient()){client.Headers.Add("User-Agent","SceneSieve/2.0");client.DownloadFile((string)py["url"],partial);}
    if(Hash(partial)!=(string)py["sha256"])throw new Exception("Python download verification failed. Restart to retry.");
    if(File.Exists(archive))File.Delete(archive);File.Move(partial,archive);
   }
   Directory.CreateDirectory(pydir);
   // Restore verified Python files on every launch; user libraries live separately.
   using(var zip=ZipFile.OpenRead(archive)){foreach(var e in zip.Entries){if(e.FullName.EndsWith("/"))continue;string p=Path.GetFullPath(Path.Combine(pydir,e.FullName));if(!p.StartsWith(pydir+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new Exception("Invalid Python entry");Directory.CreateDirectory(Path.GetDirectoryName(p));if(File.Exists(p)&&e.Name.EndsWith("._pth"))continue;using(var input=e.Open())using(var output=File.Create(p))input.CopyTo(output);}}
   File.WriteAllText(Path.Combine(pydir,"python312._pth"),"python312.zip\n.\nLib\\site-packages\n"+app+"\nimport site\n");
   var info=new ProcessStartInfo(python,Quote(Path.Combine(app,"provision.py")));info.UseShellExecute=false;info.CreateNoWindow=true;info.RedirectStandardOutput=true;info.RedirectStandardError=true;info.StandardOutputEncoding=System.Text.Encoding.UTF8;info.StandardErrorEncoding=System.Text.Encoding.UTF8;info.EnvironmentVariables["SCENESIEVE_HOME"]=root;info.EnvironmentVariables["PYTHONIOENCODING"]="utf-8";
   string log=Path.Combine(root,"setup.log");using(var writer=new StreamWriter(log,false)){object gate=new object();using(var p=new Process()){p.StartInfo=info;p.OutputDataReceived+=(s,e)=>{if(e.Data!=null){Status(e.Data);lock(gate){writer.WriteLine(e.Data);writer.Flush();}}};p.ErrorDataReceived+=(s,e)=>{if(e.Data!=null)lock(gate){writer.WriteLine(e.Data);writer.Flush();}};p.Start();p.BeginOutputReadLine();p.BeginErrorReadLine();p.WaitForExit();if(p.ExitCode!=0)throw new Exception("Setup could not finish. Restart to retry. Details: "+log);}}
   if(Array.IndexOf(args,"--setup-only")>=0){code=0;return;}
   info=new ProcessStartInfo(Path.Combine(pydir,"pythonw.exe"),Quote(Path.Combine(app,"desktop_entry.py")));int ti=Array.IndexOf(args,"--self-test");if(ti>=0&&ti+1<args.Length)info.Arguments+=" --self-test "+Quote(args[ti+1]);info.UseShellExecute=false;info.CreateNoWindow=true;info.EnvironmentVariables["HF_HUB_DISABLE_PROGRESS_BARS"]="1";info.EnvironmentVariables["SCENESIEVE_HOME"]=root;info.EnvironmentVariables["HF_HOME"]=Path.Combine(root,"models","speech");info.EnvironmentVariables["PYTHONIOENCODING"]="utf-8";
   using(var child=Process.Start(info)){BeginInvoke((Action)(()=>Hide()));child.WaitForExit();code=child.ExitCode;}
  }
 }catch(Exception e){if(root!=null)File.WriteAllText(Path.Combine(root,"launcher-error.txt"),e.ToString());if(Array.IndexOf(args,"--setup-only")<0)BeginInvoke((Action)(()=>MessageBox.Show(e.Message,"SceneSieve setup",MessageBoxButtons.OK,MessageBoxIcon.Error)));}finally{BeginInvoke((Action)(()=>Close()));}}
 [STAThread]static int Main(string[] args){Application.EnableVisualStyles();var app=new OnlineLauncher(args);Application.Run(app);return app.code;}
}
