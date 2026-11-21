# Open a Mezon box's Ubuntu desktop (Amazon DCV) through an SSH tunnel. Port 8443 stays closed on AWS.
#   powershell -File open_mezon_box.ps1 -Box mezon-gpu    (L40S, local port 18443)
#   powershell -File open_mezon_box.ps1 -Box mezon-6000   (RTX PRO 6000, local port 28443)
# DCV asks for the ubuntu password itself; this script never stores or sends one.
param([ValidateSet("mezon-gpu", "mezon-6000")][string]$Box = "mezon-gpu")
$port = @{ "mezon-gpu" = 18443; "mezon-6000" = 28443 }[$Box]
$viewer = "C:\Program Files (x86)\NICE\DCV\Client\bin\dcvviewer.exe"
$ssh = "C:\Windows\System32\OpenSSH\ssh.exe"
if (-not (Test-Path $ssh)) { $ssh = "ssh" }

function Test-Port { try { $t = New-Object Net.Sockets.TcpClient("127.0.0.1", $port); $t.Dispose(); $true } catch { $false } }

$tunnel = $null
if (-not (Test-Port)) {
    $tunnel = Start-Process $ssh -ArgumentList "-N", "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=30",
        "-L", "${port}:localhost:8443", $Box -WindowStyle Hidden -PassThru
    for ($i = 0; $i -lt 30 -and -not (Test-Port); $i++) { Start-Sleep 1 }
}
if (-not (Test-Port)) {
    Add-Type -AssemblyName PresentationFramework
    [Windows.MessageBox]::Show("Could not reach $Box. If your internet IP changed, tell Claude (it adds the new IP).", "Mezon box") | Out-Null
    if ($tunnel) { Stop-Process $tunnel.Id -ErrorAction SilentlyContinue }
    exit 1
}
$dcv = Join-Path $env:LOCALAPPDATA "mezon-$Box.dcv"
@"
[version]
format=1.0

[connect]
host=127.0.0.1
port=$port
user=ubuntu
proxytype=NONE
transport=auto
certificatevalidationpolicy=ask-user

[options]
fullscreen=false
promptreconnect=true
"@ | Set-Content -Encoding ascii $dcv
$v = Start-Process $viewer "`"$dcv`"" -PassThru
$v.WaitForExit()
if ($tunnel) { Stop-Process $tunnel.Id -ErrorAction SilentlyContinue }
