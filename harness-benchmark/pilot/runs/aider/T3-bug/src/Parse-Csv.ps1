function Parse-CsvLine {
    param([string]$Line)

    $fields = New-Object System.Collections.Generic.List[string]
    $sb = New-Object System.Text.StringBuilder
    $inQuotes = $false

    for ($i = 0; $i -lt $Line.Length; $i++) {
        $ch = $Line[$i]

        if ($inQuotes) {
            if ($ch -eq '"') {
                if ($i + 1 -lt $Line.Length -and $Line[$i + 1] -eq '"') {
                    # "" dentro de campo entre aspas representa uma aspa literal
                    [void]$sb.Append('"')
                    $i++
                }
                else {
                    # aspa de fechamento
                    $inQuotes = $false
                }
            }
            else {
                [void]$sb.Append($ch)
            }
        }
        else {
            if ($ch -eq '"') {
                # abertura de campo entre aspas
                $inQuotes = $true
            }
            elseif ($ch -eq ',') {
                # separador de campo fora de aspas
                $fields.Add($sb.ToString())
                [void]$sb.Clear()
            }
            else {
                [void]$sb.Append($ch)
            }
        }
    }

    # último campo
    $fields.Add($sb.ToString())

    return $fields.ToArray()
}
