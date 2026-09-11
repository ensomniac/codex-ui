# Portable lifecycle installer. Windows native desktop control is planned.
$ErrorActionPreference = 'Stop'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Invoke-Expression (Invoke-RestMethod https://astral.sh/uv/install.ps1)
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
$release = Invoke-RestMethod https://api.github.com/repos/ensomniac/codex-ui/releases/latest
if ($release.tag_name -notmatch '^v\d+\.\d+\.\d+$') { throw 'Expected a stable release' }
$name = "ensomniac_codex_ui-$($release.tag_name.Substring(1))-py3-none-any.whl"
$asset = $release.assets | Where-Object name -eq $name
$url = "https://github.com/ensomniac/codex-ui/releases/download/$($release.tag_name)/$name"
if ($asset.browser_download_url -ne $url -or $asset.digest -notmatch '^sha256:[0-9a-f]{64}$') {
    throw 'Invalid release artifact or digest'
}
uv tool install --python 3.12 --force "$url#sha256=$($asset.digest.Substring(7))"
if ($LASTEXITCODE -ne 0) { throw 'Installation failed' }
uv tool update-shell
Write-Output 'Installed. Run codex-ui capabilities. Windows native desktop control is planned.'
