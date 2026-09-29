<#
backup_teams.ps1 — Copia os dados confidenciais para a pasta da Inteligência
Comercial no Teams/SharePoint (sincronizada no computador pelo OneDrive).

O que vai (e nunca vai para o GitHub):
  data/privado   exportação de propostas, valores por empresa, clientes fora da base
  data/contatos  contatos do robô, presença digital, contatos da Receita
Vai como um .zip em  <pasta do Teams>\Backup\AAAA-MM\ ; mantém os últimos 3 meses.
As listas para o comercial (INDUSTRIAS_NOVAS_*.xlsx) vão para
  <pasta do Teams>\Listas para o comercial\

A pasta do Teams é achada sozinha (qualquer pasta "INTELIGÊNCIA COMERCIAL - 2026"
dentro do seu usuário). Se não achar, sincronize a pasta no Teams/SharePoint
(botão "Sincronizar" ou "Adicionar atalho ao Meu OneDrive") ou informe:
  .\jobs\backup_teams.ps1 -Destino "C:\...\INTELIGÊNCIA COMERCIAL - 2026"
#>
param([string]$Destino = $env:BACKUP_TEAMS, [int]$ManterMeses = 3)

if (-not $Destino) {
    $achada = Get-ChildItem $env:USERPROFILE -Directory -Recurse -Depth 4 -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "INTELIG*COMERCIAL - 2026" } | Select-Object -First 1
    if ($achada) { $Destino = $achada.FullName }
}
if (-not $Destino -or -not (Test-Path $Destino)) {
    Write-Host "Backup: pasta do Teams não encontrada no computador. Sincronize 'INTELIGÊNCIA COMERCIAL - 2026' pelo SharePoint (Sincronizar) e rode de novo."
    exit 0
}

$raiz = (Get-Location).Path
$fontes = @("data\privado", "data\contatos") | Where-Object { Test-Path (Join-Path $raiz $_) }
if ($fontes.Count -eq 0) { Write-Host "Backup: nada para copiar."; exit 0 }

$mes = Get-Date -Format "yyyy-MM"
$pastaMes = Join-Path $Destino "Backup\$mes"
New-Item -ItemType Directory -Force -Path $pastaMes | Out-Null
$zip = Join-Path $pastaMes ("dados_confidenciais_" + (Get-Date -Format "yyyyMMdd_HHmm") + ".zip")
Compress-Archive -Path ($fontes | ForEach-Object { Join-Path $raiz $_ }) -DestinationPath $zip -Force
Write-Host "Backup: $zip"

$listas = Get-ChildItem (Join-Path $raiz "data\contatos") -Filter "INDUSTRIAS_NOVAS_*.xlsx" -ErrorAction SilentlyContinue
if ($listas) {
    $pastaListas = Join-Path $Destino "Listas para o comercial"
    New-Item -ItemType Directory -Force -Path $pastaListas | Out-Null
    $listas | Copy-Item -Destination $pastaListas -Force
    Write-Host "Listas para o comercial: $($listas.Count) arquivo(s) em $pastaListas"
}

# mantém só os últimos N meses (apenas pastas AAAA-MM criadas por este script)
Get-ChildItem (Join-Path $Destino "Backup") -Directory |
    Where-Object { $_.Name -match '^\d{4}-\d{2}$' } | Sort-Object Name -Descending |
    Select-Object -Skip $ManterMeses | ForEach-Object {
        Remove-Item $_.FullName -Recurse -Force
        Write-Host "Backup antigo removido: $($_.Name)"
    }
