function Parse-CsvLine {
    param([string]$Line)
    $campos = @()
    $atual = New-Object System.Text.StringBuilder
    $aspas = $false
    for ($i = 0; $i -lt $Line.Length; $i++) {
        $c = $Line[$i]
        if ($aspas) {
            if ($c -eq '"') {
                if ($i + 1 -lt $Line.Length -and $Line[$i+1] -eq '"') { [void]$atual.Append('"'); $i++ }
                else { $aspas = $false }
            } else { [void]$atual.Append($c) }
        } else {
            if ($c -eq '"') { $aspas = $true }
            elseif ($c -eq ',') { $campos += $atual.ToString(); [void]$atual.Clear() }
            else { [void]$atual.Append($c) }
        }
    }
    $campos += $atual.ToString()
    return $campos
}
