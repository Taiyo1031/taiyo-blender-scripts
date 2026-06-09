$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$gitRoot = Join-Path $repoRoot ".codex-tools\MinGit"
$gitExe = Join-Path $gitRoot "cmd\git.exe"

if (Test-Path $gitExe) {
    $env:PATH = "$gitRoot\cmd;$gitRoot\mingw64\bin;$gitRoot\usr\bin;$env:PATH"
    $env:GIT_EXEC_PATH = "$gitRoot\mingw64\bin"
} else {
    $gitExe = "git"
}

& $gitExe @args
exit $LASTEXITCODE
