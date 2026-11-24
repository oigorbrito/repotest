function Read-KeyValue {
    param([string]$Text)
    $h = @{}
    foreach ($line in ($Text -split "`n")) {
        $l = $line.Trim()
        if ($l -eq '' -or $l.StartsWith('#')) { continue }
        $i = $l.IndexOf('=')
        if ($i -lt 0) { continue }
        $h[$l.Substring(0, $i).Trim()] = $l.Substring($i + 1).Trim()
    }
    return $h
}
