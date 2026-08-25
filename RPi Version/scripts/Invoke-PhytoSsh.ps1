<#
.SYNOPSIS
    Execute une commande sur le PhytoController depuis PowerShell (Windows).

.DESCRIPTION
    Version PowerShell native de scripts/phyto-ssh.sh.
    Utilise le client OpenSSH de Windows et l'alias "phyto" defini par
    .\scripts\Setup-SshBridge.ps1.

.PARAMETER Command
    Commande a executer sur le Pi. Sans argument : session interactive.

.PARAMETER PhytoHost
    Alias ou user@ip a utiliser (defaut : phyto, ou $env:PHYTO_HOST).

.EXAMPLE
    .\scripts\Invoke-PhytoSsh.ps1 'journalctl -n 200 --no-pager'
    .\scripts\Invoke-PhytoSsh.ps1 'cat ~/PhytoController/param/param.json'
    .\scripts\Invoke-PhytoSsh.ps1                 # session interactive
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Command,

    [string] $PhytoHost = $(if ($env:PHYTO_HOST) { $env:PHYTO_HOST } else { 'phyto' })
)

$ErrorActionPreference = 'Stop'

# --- localisation de ssh.exe ------------------------------------------------
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
    Write-Error "ssh.exe introuvable - lance d'abord .\scripts\Setup-SshBridge.ps1"
    exit 1
}

# --- session interactive ----------------------------------------------------
if (-not $Command -or $Command.Count -eq 0) {
    & $sshExe $PhytoHost
    exit $LASTEXITCODE
}

# --- commande non interactive ----------------------------------------------
# BatchMode : jamais de prompt de mot de passe, on echoue vite si la cle n'est
# pas (ou plus) installee - indispensable pour un appel non interactif.
$out = (& $sshExe -o BatchMode=yes $PhytoHost @Command 2>&1) -join "`n"
$status = $LASTEXITCODE

if ($status -ne 0) {
    Write-Host $out -ForegroundColor Red
    switch -Regex ($out) {
        'Permission denied|Could not resolve|No such host' {
            Write-Host "-> Pont SSH non configure ou casse : .\scripts\Setup-SshBridge.ps1" -ForegroundColor Yellow; break
        }
        'Connection timed out|refused|No route to host' {
            Write-Host '-> Pi injoignable : verifie qu''il est allume et sur le reseau.' -ForegroundColor Yellow; break
        }
    }
    exit $status
}
Write-Output $out
