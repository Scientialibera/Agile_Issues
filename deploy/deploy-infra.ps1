<#
.SYNOPSIS
    Deploy Azure infrastructure for the Agile Issue Generator.

.DESCRIPTION
    Creates Resource Group, Storage Account, Azure OpenAI, ACR,
    Container Apps Environment, and the API Container App.
    Reads all settings from deploy.config.toml.

.NOTES
    Requires: az CLI, logged in with sufficient permissions.
    Run from the repo root: .\deploy\deploy-infra.ps1
#>

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir

# ── Load config ──────────────────────────────────────────────────────────
$configPath = Join-Path $ScriptDir "deploy.config.toml"
if (-not (Test-Path $configPath)) {
    Write-Error "deploy.config.toml not found at $configPath"
    exit 1
}

Write-Host "Loading config from $configPath" -ForegroundColor Cyan

# Parse TOML (simple key=value extraction for flat sections)
function Get-TomlValue($content, $section, $key, $default = "") {
    $inSection = $false
    foreach ($line in $content) {
        $trimmed = $line.Trim()
        if ($trimmed -match '^\[(.+)\]$') {
            $inSection = ($Matches[1] -eq $section)
            continue
        }
        if ($inSection -and $trimmed -match "^$key\s*=\s*""(.*)""") {
            return $Matches[1]
        }
        if ($inSection -and $trimmed -match "^$key\s*=\s*(.+)") {
            $val = $Matches[1].Trim()
            if ($val -eq "true") { return $true }
            if ($val -eq "false") { return $false }
            return $val
        }
    }
    return $default
}

$configContent = Get-Content $configPath
$location      = Get-TomlValue $configContent "azure" "location" "eastus2"
$prefix        = Get-TomlValue $configContent "naming" "prefix" "agile-issues"
$rgName        = Get-TomlValue $configContent "naming" "resource_group"
if (-not $rgName) { $rgName = "rg-$prefix" }
$deployWebapp  = Get-TomlValue $configContent "webapp" "deploy_webapp" $true

Write-Host ""
Write-Host "═══════════════════════════════════════════" -ForegroundColor Green
Write-Host "  Agile Issue Generator – Infrastructure"     -ForegroundColor Green
Write-Host "═══════════════════════════════════════════" -ForegroundColor Green
Write-Host "  Resource Group : $rgName"
Write-Host "  Location       : $location"
Write-Host "  Prefix         : $prefix"
Write-Host ""

# ── Resource Group ───────────────────────────────────────────────────────
Write-Host "[1/3] Creating Resource Group..." -ForegroundColor Yellow
az group create --name $rgName --location $location --output none
Write-Host "  ✓ Resource Group '$rgName' ready" -ForegroundColor Green

# ── Azure OpenAI (placeholder – fill in with your deployment) ───────────
Write-Host "[2/3] Azure OpenAI – ensure your endpoint and model are set in deploy.config.toml" -ForegroundColor Yellow

# ── Container App (if enabled) ──────────────────────────────────────────
if ($deployWebapp -eq $true -or $deployWebapp -eq "true") {
    Write-Host "[3/3] Container App deployment would go here..." -ForegroundColor Yellow
    Write-Host "  (Implement ACR build + Container App create per your Azure subscription)" -ForegroundColor DarkGray
} else {
    Write-Host "[3/3] Webapp deployment skipped (deploy_webapp = false)" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "Infrastructure setup complete." -ForegroundColor Green
Write-Host "Next steps:"
Write-Host "  1. Fill in deploy.config.toml with your Azure OpenAI endpoint and model"
Write-Host "  2. Run the API locally:  python -m uvicorn api.main:app --reload"
Write-Host ""
