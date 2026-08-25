<#
.SYNOPSIS
    Met en place un acces SSH sans mot de passe vers le PhytoController (Raspberry Pi).

.DESCRIPTION
    Version PowerShell native de scripts/setup-ssh-bridge.sh.

    Pourquoi cette version :
      WSL2 est derriere un NAT / pare-feu Hyper-V et ne peut pas toujours joindre
      le LAN 192.168.1.0/24 ("No route to host"). Lance directement depuis Windows,
      ce script n'a aucun de ces problemes : il utilise le client OpenSSH de Windows,
      qui a un acces direct au reseau local.

    Ce script :
      1. localise ssh.exe / ssh-keygen.exe et le repertoire %USERPROFILE%\.ssh
      2. verifie que le Pi repond sur le port 22
      3. genere une paire de cles ed25519 si necessaire
      4. installe la cle publique dans ~/.ssh/authorized_keys du Pi
         (demande le mot de passe UNE seule fois)
      5. ajoute/actualise un alias "phyto" dans %USERPROFILE%\.ssh\config
      6. verifie que la connexion par cle fonctionne

.EXAMPLE
    .\scripts\Setup-SshBridge.ps1
    .\scripts\Setup-SshBridge.ps1 -HostIp 192.168.1.15 -SshUser progradius -Alias phyto

.NOTES
    Si l'execution de scripts est bloquee :
      powershell -ExecutionPolicy Bypass -File .\scripts\Setup-SshBridge.ps1
#>

[CmdletBinding()]
param(
    [string] $HostIp  = '192.168.1.15',
    [string] $SshUser = 'progradius',
    [string] $Alias   = 'phyto'
)

$ErrorActionPreference = 'Stop'

# --- helpers de console -----------------------------------------------------
function Write-Info { param($m) Write-Host '==>' -ForegroundColor Blue   -NoNewline; Write-Host " $m" }
function Write-Ok   { param($m) Write-Host ' OK' -ForegroundColor Green  -NoNewline; Write-Host " $m" }
function Write-Warn { param($m) Write-Host '  !' -ForegroundColor Yellow -NoNewline; Write-Host " $m" }
function Die        { param($m) Write-Host 'ERR' -ForegroundColor Red    -NoNewline; Write-Host " $m"; exit 1 }

# --- 1. environnement -------------------------------------------------------
$sshExe = $null
$cmd = Get-Command ssh.exe -ErrorAction SilentlyContinue
if ($cmd) { $sshExe = $cmd.Source }
if (-not $sshExe) {
    foreach ($c in @(
        "$env:WINDIR\System32\OpenSSH\ssh.exe",
        "$env:ProgramFiles\OpenSSH\ssh.exe",
        "$env:ProgramFiles\OpenSSH-Win64\ssh.exe")) {
        if (Test-Path $c) { $sshExe = $c; break }
    }
}
if (-not $sshExe) {
    Die "ssh.exe introuvable. Installe le client OpenSSH de Windows`n      (Parametres > Applications > Fonctionnalites facultatives > Client OpenSSH)."
}
$keygenExe = Join-Path (Split-Path $sshExe) 'ssh-keygen.exe'
if (-not (Test-Path $keygenExe)) { Die "ssh-keygen.exe introuvable a cote de $sshExe" }
Write-Ok "client SSH Windows : $sshExe"

$sshDir    = Join-Path $env:USERPROFILE '.ssh'
$sshConfig = Join-Path $sshDir 'config'
if (-not (Test-Path $sshDir)) { New-Item -ItemType Directory -Path $sshDir -Force | Out-Null }
Write-Ok "repertoire SSH Windows : $sshDir"

# --- 2. joignabilite --------------------------------------------------------
Write-Info "Test du port 22 sur $HostIp ..."
$reachable = $false
try {
    # BeginConnect et non ConnectAsync().Wait() : sous Windows PowerShell 5.1 le
    # Task n'est pas ordonnance et Wait() renvoie toujours $false (faux negatif).
    $tcp = New-Object System.Net.Sockets.TcpClient
    $ar  = $tcp.BeginConnect($HostIp, 22, $null, $null)
    if ($ar.AsyncWaitHandle.WaitOne(5000, $false)) {
        $tcp.EndConnect($ar)
        $reachable = $tcp.Connected
    }
    $tcp.Close()
} catch { $reachable = $false }
if (-not $reachable) {
    Write-Warn "$HostIp`:22 ne repond pas au test TCP (5 s). On tente quand meme la suite."
} else {
    Write-Ok "$HostIp`:22 accessible"
}

# --- 3. cle -----------------------------------------------------------------
$keyPriv = $null
foreach ($name in 'id_ed25519', 'id_rsa') {
    $candidate = Join-Path $sshDir $name
    if ((Test-Path $candidate) -and (Test-Path "$candidate.pub")) { $keyPriv = $candidate; break }
}
if ($keyPriv) {
    Write-Ok "cle existante reutilisee : $keyPriv.pub"
} else {
    Write-Info 'Aucune cle trouvee, generation d''une paire ed25519 ...'
    $keyPriv = Join-Path $sshDir 'id_ed25519'
    & $keygenExe -t ed25519 -N '""' -f $keyPriv | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path "$keyPriv.pub")) { Die 'Generation de la cle echouee.' }
    Write-Ok "cle generee : $keyPriv.pub"
}
$keyPub = "$keyPriv.pub"
$pubKey = (Get-Content -Raw -Path $keyPub).Trim()
if (-not $pubKey) { Die "Cle publique vide : $keyPub" }

# --- 4. installation de la cle sur le Pi ------------------------------------
Write-Info 'Verification de l''authentification par cle ...'
& $sshExe -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new `
          -i $keyPriv "$SshUser@$HostIp" 'true' 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Ok 'la cle est deja autorisee sur le Pi'
} else {
    Write-Info "Installation de la cle publique sur $SshUser@$HostIp"
    Write-Warn "Le mot de passe de '$SshUser' va etre demande (une seule fois)."
    # La cle est passee en argument, pas via stdin : stdin reste libre pour que
    # ssh.exe puisse lire le mot de passe au clavier.
    $remoteCmd = "set -e; " +
                 "mkdir -p ~/.ssh && chmod 700 ~/.ssh; " +
                 "touch ~/.ssh/authorized_keys; " +
                 "grep -qxF '$pubKey' ~/.ssh/authorized_keys || echo '$pubKey' >> ~/.ssh/authorized_keys; " +
                 "chmod 600 ~/.ssh/authorized_keys"
    & $sshExe -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new "$SshUser@$HostIp" $remoteCmd
    if ($LASTEXITCODE -ne 0) {
        Die 'Installation de la cle echouee (mot de passe errone, ou PasswordAuthentication desactive sur le Pi).'
    }
    Write-Ok 'cle publique installee'
}

# --- 5. alias dans le ssh_config Windows ------------------------------------
Write-Info "Mise a jour de l'alias '$Alias' dans $sshConfig"
$lines = if (Test-Path $sshConfig) { @(Get-Content -Path $sshConfig) } else { @() }

# on retire un eventuel bloc "Host <alias>" existant
$kept = New-Object System.Collections.Generic.List[string]
$inBlock = $false
foreach ($line in $lines) {
    if ($line -match '^\s*[Hh]ost\s+(.*)$') {
        $inBlock = ($Matches[1].Trim() -split '\s+') -contains $Alias
    }
    if (-not $inBlock) { $kept.Add($line) }
}
# une seule ligne vide de separation en fin de fichier
while ($kept.Count -gt 0 -and [string]::IsNullOrWhiteSpace($kept[$kept.Count - 1])) {
    $kept.RemoveAt($kept.Count - 1)
}
if ($kept.Count -gt 0) { $kept.Add('') }

$kept.Add("Host $Alias")
$kept.Add("  HostName $HostIp")
$kept.Add("  User $SshUser")
$kept.Add("  IdentityFile ~/.ssh/$(Split-Path $keyPriv -Leaf)")
$kept.Add('  IdentitiesOnly yes')
$kept.Add('  ServerAliveInterval 15')
# Wi-Fi domestique : quelques tentatives valent mieux qu'un timeout court
$kept.Add('  ConnectTimeout 15')
$kept.Add('  ConnectionAttempts 3')

# UTF8 sans BOM : OpenSSH refuse de lire un config avec BOM
[System.IO.File]::WriteAllLines($sshConfig, $kept, (New-Object System.Text.UTF8Encoding $false))
Write-Ok "alias '$Alias' configure"

# --- 6. verification finale -------------------------------------------------
Write-Info 'Verification de bout en bout ...'
$remoteId = (& $sshExe -o BatchMode=yes $Alias 'echo "$(hostname) | $(uname -srm)"' 2>&1) -join "`n"
if ($LASTEXITCODE -ne 0) { Die "La connexion par cle echoue toujours : $remoteId" }
Write-Ok "connecte : $remoteId"

@"

------------------------------------------------------------------
Pont SSH pret.

  Utilisation manuelle :
    ssh $Alias

  Wrapper fourni (PowerShell) :
    .\scripts\Invoke-PhytoSsh.ps1 'journalctl -n 200 --no-pager'
    .\scripts\Invoke-PhytoSsh.ps1 'cat ~/PhytoController/param/param.json'
------------------------------------------------------------------
"@ | Write-Host
