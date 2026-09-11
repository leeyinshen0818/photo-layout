$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $projectRoot
try {
    python -m PyInstaller --noconfirm --clean PhotoPrintLayoutManager.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
    if (-not (Test-Path -LiteralPath "$projectRoot\dist\PhotoPrintLayoutManager.exe")) {
        throw "Build completed without producing PhotoPrintLayoutManager.exe"
    }
    Get-Item -LiteralPath "$projectRoot\dist\PhotoPrintLayoutManager.exe"
}
finally {
    Pop-Location
}
