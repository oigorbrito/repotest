function Read-KeyValue {
    param([string]$Text)
    $h = @{}
    foreach ($line in ($Text -split "`n")) {
        $l = $line.Split('#')[0].Trim()
        if ($l -eq '') { continue }
        $parts = $l.Split('=')
        $h[$parts[0].Trim()] = $parts[1].Trim()
    }
    return $h
}
