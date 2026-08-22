param(
    [string]$SourceFile = "src/cv/main.tex",
    [string]$OutputPath = "$HOME\Desktop\CV_na_data_engineera.pdf"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$sourcePath = Join-Path $repoRoot $SourceFile
$generatedDir = Join-Path $repoRoot "src/cv/output"
if (-not (Test-Path $generatedDir)) {
    New-Item -ItemType Directory -Path $generatedDir -Force | Out-Null
}

if (-not (Test-Path $sourcePath)) {
    Write-Error "Nie znaleziono pliku źródłowego: $sourcePath"
    exit 1
}

$outputDir = Split-Path -Parent $OutputPath
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
}

$compiler = $null
$compilerArgs = @()

if (Get-Command latexmk -ErrorAction SilentlyContinue) {
    $compiler = "latexmk"
    $compilerArgs = @("-pdf", "-interaction=nonstopmode", "-halt-on-error", "-output-directory=$generatedDir", $sourcePath)
}
elseif (Get-Command pdflatex -ErrorAction SilentlyContinue) {
    $compiler = "pdflatex"
    $compilerArgs = @("-interaction=nonstopmode", "-halt-on-error", "-output-directory=$generatedDir", $sourcePath)
}
elseif (Get-Command tectonic -ErrorAction SilentlyContinue) {
    $compiler = "tectonic"
    $compilerArgs = @($sourcePath, "--outdir", $generatedDir)
}
else {
    Write-Error "Nie znaleziono kompilatora LaTeXa. Zainstaluj MiKTeX, TeX Live albo Tectonic i uruchom skrypt ponownie."
    exit 1
}

Push-Location $repoRoot
try {
    Write-Host "Kompiluję CV za pomocą: $compiler"
    & $compiler @compilerArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Compilation failed."
    }

    $generatedPdf = Join-Path $generatedDir "main.pdf"
    if (-not (Test-Path $generatedPdf)) {
        throw "Failed to generate PDF file: $generatedPdf"
    }

    Copy-Item $generatedPdf -Destination $OutputPath -Force
    Write-Host "PDF gotowy: $OutputPath"
}
finally {
    Pop-Location
}
