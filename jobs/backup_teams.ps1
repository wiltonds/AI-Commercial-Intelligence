<#
backup_teams.ps1 — Backup dos dados confidenciais para a pasta da Inteligência
Comercial no Teams/SharePoint.

O que vai (e nunca vai para o GitHub):
  data/privado   exportação de propostas, valores por empresa, clientes fora da base
  data/contatos  contatos do robô, presença digital, contatos da Receita
+ as listas para o comercial (INDUSTRIAS_NOVAS_*.xlsx).

Dois modos:
  * AUTOMÁTICO — se a pasta "INTELIGÊNCIA COMERCIAL - 2026" estiver sincronizada
    no computador (OneDrive), grava direto nela.
  * ARRASTAR (padrão na FIEA) — prepara tudo em Downloads\PARA_O_TEAMS e abre essa
    pasta e o SharePoint; é só arrastar os arquivos para o navegador.
#>
param(
    [string]$Destino = $env:BACKUP_TEAMS,
    [int]$ManterMeses = 3,
    [string]$LinkTeams = "https://sistemafiea-my.sharepoint.com/shared?id=%2Fsites%2FCOORDENAOCOMERCIAL%2FDocumentos%20Compartilhados%2FGeneral%2FINTELIG%C3%8ANCIA%20COMERCIAL%20%2D%202026&listurl=https%3A%2F%2Fsistemafiea%2Esharepoint%2Ecom%2Fsites%2FCOORDENAOCOMERCIAL%2FDocumentos%20Compartilhados&viewid=d7a70296%2Dc755%2D48c6%2Da702%2D94ddc77f03b4"
)

if (-not $Destino) {
    $achada = Get-ChildItem $env:USERPROFILE -Directory -Recurse -Depth 4 -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "INTELIG*COMERCIAL - 2026" } | Select-Object -First 1
    if ($achada) { $Destino = $achada.FullName }
}
$arrastar = -not ($Destino -and (Test-Path $Destino))
if ($arrastar) { $Destino = Join-Path $env:USERPROFILE "Downloads\PARA_O_TEAMS" }

$raiz = (Get-Location).Path
$fontes = @("data\privado", "data\contatos") | Where-Object { Test-Path (Join-Path $raiz $_) }
if ($fontes.Count -eq 0) { Write-Host "Backup: nada para copiar."; exit 0 }

$pastaBackup = Join-Path $Destino "Backup"
New-Item -ItemType Directory -Force -Path $pastaBackup | Out-Null
$zip = Join-Path $pastaBackup ("dados_confidenciais_" + (Get-Date -Format "yyyy-MM-dd_HHmm") + ".zip")
Compress-Archive -Path ($fontes | ForEach-Object { Join-Path $raiz $_ }) -DestinationPath $zip -Force
Write-Host "Backup: $zip"

$listas = Get-ChildItem (Join-Path $raiz "data\contatos") -Filter "INDUSTRIAS_NOVAS_*.xlsx" -ErrorAction SilentlyContinue
if ($listas) {
    $pastaListas = Join-Path $Destino "Listas para o comercial"
    New-Item -ItemType Directory -Force -Path $pastaListas | Out-Null
    $listas | Copy-Item -Destination $pastaListas -Force
    Write-Host "Listas para o comercial: $($listas.Count) arquivo(s)"
}

# mantém só os backups dos últimos N meses (arquivos criados por este script)
$limite = (Get-Date).AddMonths(-$ManterMeses)
Get-ChildItem $pastaBackup -Filter "dados_confidenciais_*.zip" |
    Where-Object { $_.LastWriteTime -lt $limite } | ForEach-Object {
        Remove-Item $_.FullName -Force
        Write-Host "Backup antigo removido: $($_.Name)"
    }

if ($arrastar) {
    Write-Host ""
    Write-Host "PRÓXIMO PASSO (1 minuto):"
    Write-Host "  1. Abriram duas janelas: a pasta PARA_O_TEAMS e o SharePoint da Inteligência Comercial."
    Write-Host "  2. Arraste o .zip mais recente de 'Backup' para a pasta Backup do SharePoint"
    Write-Host "     e as planilhas de 'Listas para o comercial' para a pasta de mesmo nome."
    Write-Host "  3. Depois de conferir que subiram, pode apagar a pasta PARA_O_TEAMS."
    Invoke-Item $Destino
    Start-Process $LinkTeams
}
