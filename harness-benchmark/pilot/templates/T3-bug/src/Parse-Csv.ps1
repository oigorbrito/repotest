function Parse-CsvLine {
    param([string]$Line)
    return $Line.Split(',') | ForEach-Object { $_.Trim('"') }
}
