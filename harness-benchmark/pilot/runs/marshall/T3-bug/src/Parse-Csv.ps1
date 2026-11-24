function Parse-CsvLine {
    param([string]$Line)
    $fields = New-Object System.Collections.Generic.List[string]
    $sb = New-Object System.Text.StringBuilder
    $inQuotes = $false
    for ($i = 0; $i -lt $Line.Length; $i++) {
        $ch = $Line[$i]
        if ($inQuotes) {
            if ($ch -eq '"') {
                if ($i + 1 -lt $Line.Length -and $Line[$i + 1] -eq '"') { [void]$sb.Append('"'); $i++ }
                else { $inQuotes = $false }
            } else { [void]$sb.Append($ch) }
        } elseif ($ch -eq '"') {
            $inQuotes = $true
        } elseif ($ch -eq ',') {
            $fields.Add($sb.ToString()); [void]$sb.Clear()
        } else {
            [void]$sb.Append($ch)
        }
    }
    $fields.Add($sb.ToString())
    return $fields.ToArray()
}
