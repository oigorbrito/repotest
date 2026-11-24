function Merge-Ranges {
    param([object[]]$Ranges)
    $sorted = @($Ranges | Sort-Object { $_[0] })
    $out = @()
    foreach ($r in $sorted) {
        if ($out.Count -gt 0 -and $r[0] -le $out[-1][1]) {
            if ($r[1] -gt $out[-1][1]) { $out[-1][1] = $r[1] }
        } else {
            $out += ,@($r[0], $r[1])
        }
    }
    return ,$out
}
