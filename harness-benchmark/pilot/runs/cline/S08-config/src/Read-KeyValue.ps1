function Read-KeyValue {
    param([string]$Text)
    $h = @{}
    foreach ($line in ($Text -split "`n")) {
        $l = $line.Trim()
        if ($l -eq "" -or $l.StartsWith("#")) { continue }
        $idx = $l.IndexOf("=")
        if ($idx -lt 0) { continue }
        $h[$l.Substring(0, $idx).Trim()] = $l.Substring($idx + 1).Trim()
    }
    return $h
}
