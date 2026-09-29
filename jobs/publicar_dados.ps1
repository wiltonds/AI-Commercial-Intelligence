<#
publicar_dados.ps1 — Sobe para o GitHub os arquivos de dados que o painel lê.

Só faz commit se algum arquivo mudou. Não troca de branch: publica na
branch da pasta indicada (use a pasta do worktree da master para publicar
lá sem sair da branch em que o robô está rodando).

Uso (na raiz do repositório):
  .\jobs\publicar_dados.ps1                          # publica na branch atual
  .\jobs\publicar_dados.ps1 -Destino ..\AI-CI-master # copia para a pasta da master e publica lá

Em laço, a cada 5 minutos, enquanto os jobs rodam:
  while ($true) { .\jobs\publicar_dados.ps1; .\jobs\publicar_dados.ps1 -Destino ..\AI-CI-master; Start-Sleep 300 }
#>
param([string]$Destino = "")

$arquivos = @(
    "data/processed/BASE_MESTRE_COMERCIAL.csv",
    "data/processed/PORTE_FIEA.csv",
    "data/processed/PRODUTOS_RANKING.csv",
    "data/processed/ATENDIMENTO_POR_ANO.csv",
    "data/processed/BASE_AMPLIADA_AL.csv",
    "data/contatos/CONTATOS_EMPRESAS.csv",
    "data/contatos/CONTATOS_RECEITA.csv"
)
$origem = (Get-Location).Path
$alvo = if ($Destino) { (Resolve-Path $Destino).Path } else { $origem }

$presentes = @()
foreach ($a in $arquivos) {
    $de = Join-Path $origem $a
    if (-not (Test-Path $de)) { continue }
    if ($alvo -ne $origem) {
        $para = Join-Path $alvo $a
        New-Item -ItemType Directory -Force -Path (Split-Path $para) | Out-Null
        Copy-Item $de $para -Force
    }
    $presentes += $a
}
if ($presentes.Count -eq 0) { Write-Host "Nada para publicar."; exit 0 }

$branch = (git -C $alvo branch --show-current).Trim()
git -C $alvo add -f -- $presentes
git -C $alvo diff --cached --quiet
if ($LASTEXITCODE -eq 0) { Write-Host "$(Get-Date -Format HH:mm) [$branch] sem mudanças."; exit 0 }

git -C $alvo commit -q -m "Dados atualizados $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
git -C $alvo push -q origin $branch
if ($LASTEXITCODE -eq 0) { Write-Host "$(Get-Date -Format HH:mm) [$branch] publicado: $($presentes -join ', ')" }
else { Write-Host "$(Get-Date -Format HH:mm) [$branch] FALHA no push — confira a conexão/credenciais." }
